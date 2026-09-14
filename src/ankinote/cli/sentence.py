import asyncio
from pathlib import Path

import click
from asynciolimiter import StrictLimiter

from ankinote.cli.factory import (
    THINKING_CHOICES,
    LanguageCollectionOptions,
    anki_client_scope,
    build_sentence_collection,
    resolve_thinking,
)
from ankinote.consts import Language
from ankinote.services.ai import DEFAULT_AI_SERVICE_CONFIG, DISABLE_REASONING

MAX_CONCURRENCY = 10

# -- Shared options -----------------------------------------------------------

COLLECTION_OPTIONS = [
    click.option(
        "--native",
        default="Chinese(Simplified)",
        show_default=True,
        type=click.Choice([lang.value for lang in Language]),
    ),
    click.option(
        "--target",
        default="English",
        show_default=True,
        type=click.Choice([lang.value for lang in Language]),
    ),
    click.option(
        "--llm",
        default=None,
        show_default=DEFAULT_AI_SERVICE_CONFIG.text_model,
    ),
    click.option(
        "--thinking",
        default=None,
        type=click.Choice(THINKING_CHOICES),
        help=(
            "Override the model's extended-thinking level for this run "
            "(default: off for sentence cards)."
        ),
    ),
]


def collection_options(cmd):
    for option in reversed(COLLECTION_OPTIONS):
        cmd = option(cmd)
    return cmd


def build_options(
    native: str,
    target: str,
    llm: str | None,
    thinking: str | None = None,
) -> LanguageCollectionOptions:
    """Convert CLI parameters to typed collection options."""
    return LanguageCollectionOptions(
        native_language=Language(native),
        target_language=Language(target),
        llm_model=llm,
        reasoning_effort=resolve_thinking(thinking, unset=DISABLE_REASONING),
    )


# -- sentence group -----------------------------------------------------------


@click.group("sentence")
def sentence():
    """Sentence card commands (V2 - production cards)."""


# -- init: create note type and deck ------------------------------------------


@sentence.command("init")
@collection_options
def init(native, target, llm, thinking):
    """Create sentence note type and deck in Anki."""

    async def _run():
        options = build_options(native, target, llm, thinking)
        async with (
            anki_client_scope() as client,
            build_sentence_collection(client, options),
        ):
            pass

    asyncio.run(_run())
    click.echo("✓ Ready (sentence collection)")


# -- add: single sentence -----------------------------------------------------


@sentence.command("add")
@click.argument("sentence")
@collection_options
def add(sentence, native, target, llm, thinking):
    """Generate and push a single sentence production card.

    The *sentence* argument should be in the target language. Its
    native-language translation will appear on the card front; the target
    sentence, notes, and phrase breakdown appear on the back.
    """

    async def _run():
        options = build_options(native, target, llm, thinking)
        async with (
            anki_client_scope() as client,
            build_sentence_collection(client, options) as collection,
        ):
            await collection.generate_and_add_note(sentence)

    asyncio.run(_run())
    click.echo(f"✓ Added sentence: {sentence}")


# -- batch: multiple sentences, optionally from file --------------------------


@sentence.command("batch")
@click.argument("sentences", nargs=-1, metavar="[SENTENCE ...]")
@click.option(
    "--file", "-f", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option(
    "--rpm",
    default=60,
    show_default=True,
    help="Max requests per minute (match your AI provider's limit).",
)
@collection_options
def batch(sentences, file, native, target, llm, rpm, thinking):
    """Generate and push multiple sentence production cards.

    \b
    Sentences should be provided in the target language. They can be passed as
    arguments, read from a file (one per line), or both at the same time.

    \b
    Examples:
      anki sentence add "I overslept this morning."
      anki sentence batch --file sentences.txt
      anki sentence batch "I overslept this morning." --file more.txt
    """
    all_sentences = list(sentences)
    if file:
        # One sentence per line; strip empty lines
        file_sentences = [
            line.strip()
            for line in file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        all_sentences += file_sentences

    if not all_sentences:
        raise click.UsageError("Provide at least one sentence via argument or --file.")

    success, failed = [], []

    async def _run():
        nonlocal success

        sem = asyncio.Semaphore(MAX_CONCURRENCY)
        limiter = StrictLimiter(rpm / 60)
        options = build_options(native, target, llm, thinking)

        async def _process(s: str):
            nonlocal success
            async with sem:
                await limiter.wait()
                try:
                    await collection.generate_and_add_note(s)
                    success.append(s)
                except Exception as e:
                    failed.append((s, str(e)))

        async with (
            anki_client_scope() as client,
            build_sentence_collection(client, options) as collection,
        ):
            await asyncio.gather(*[_process(s) for s in all_sentences])

    total = len(all_sentences)
    click.echo(
        f"Processing {total} sentences (concurrency={MAX_CONCURRENCY}, rpm={rpm}) ..."
    )
    asyncio.run(_run())
    if len(success) == total:
        click.echo("✅ All sentences processed successfully!")
    else:
        click.echo(f"\n✅ {len(success)}/{total} succeeded")
        for s in success:
            click.echo(f"   • {s}")
    if failed:
        click.echo(f"\n❌ {len(failed)} failed")
    for s, reason in failed:
        click.echo(f"   • {s}: {reason}")
