import asyncio
from pathlib import Path

import click
from asynciolimiter import StrictLimiter

from ankinote.cli.factory import (
    LanguageCollectionOptions,
    build_sentence_collection,
    collection_context,
)
from ankinote.consts import Language
from ankinote.services.ai import DEFAULT_AI_SERVICE_CONFIG

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
        show_default=DEFAULT_AI_SERVICE_CONFIG.text_model_id,
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
) -> LanguageCollectionOptions:
    """Convert CLI parameters to typed collection options."""
    return LanguageCollectionOptions(
        native_language=Language(native),
        target_language=Language(target),
        llm_model_id=llm,
    )


# -- sentence group -----------------------------------------------------------


@click.group("sentence")
def sentence():
    """Sentence card commands (V2 - production cards)."""
    pass


# -- init: create note type and deck ------------------------------------------


@sentence.command("init")
@collection_options
def init(native, target, llm):
    """Create sentence note type and deck in Anki."""

    async def _run():
        options = build_options(native, target, llm)
        async with collection_context(build_sentence_collection, options):
            pass

    asyncio.run(_run())
    click.echo("✓ Ready (sentence collection)")


# -- add: single sentence -----------------------------------------------------


@sentence.command("add")
@click.argument("sentence")
@collection_options
def add(sentence, native, target, llm):
    """Generate and push a single sentence production card.

    The *sentence* argument should be in the target language. Its
    native-language translation will appear on the card front; the target
    sentence, notes, and phrase breakdown appear on the back.
    """

    async def _run():
        options = build_options(native, target, llm)
        async with collection_context(build_sentence_collection, options) as collection:
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
def batch(sentences, file, native, target, llm, rpm):
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
        options = build_options(native, target, llm)

        async def _process(s: str):
            nonlocal success
            async with sem:
                await limiter.wait()
                try:
                    await collection.generate_and_add_note(s)
                    success.append(s)
                except Exception as e:
                    failed.append((s, str(e)))

        async with collection_context(build_sentence_collection, options) as collection:
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
