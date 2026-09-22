import asyncio
from pathlib import Path

import click
from asynciolimiter import StrictLimiter

from ankinote.cli.factory import (
    THINKING_CHOICES,
    LanguageCollectionOptions,
    anki_client_scope,
    build_phrase_collection,
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
        "--profile",
        default=None,
        help="Named text provider profile (default: the active one in settings).",
    ),
    click.option(
        "--thinking",
        default=None,
        type=click.Choice(THINKING_CHOICES),
        help=(
            "Override the model's extended-thinking level for this run "
            "(default: off for phrase cards)."
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
    profile: str | None = None,
    thinking: str | None = None,
) -> LanguageCollectionOptions:
    """Convert CLI parameters to typed collection options."""
    return LanguageCollectionOptions(
        native_language=Language(native),
        target_language=Language(target),
        llm_model=llm,
        reasoning_effort=resolve_thinking(thinking, unset=DISABLE_REASONING),
        profile=profile,
    )


# -- phrase group -------------------------------------------------------------


@click.group("phrase")
def phrase():
    """Phrase / sentence card commands."""


# -- init: create note type and deck ------------------------------------------


@phrase.command("init")
@collection_options
def init(native, target, llm, profile, thinking):
    """Create phrase note type and deck in Anki."""

    async def _run():
        options = build_options(native, target, llm, profile, thinking)
        async with (
            anki_client_scope() as client,
            build_phrase_collection(client, options),
        ):
            pass

    asyncio.run(_run())
    click.echo("✓ Ready (phrase collection)")


# -- add: single phrase -------------------------------------------------------


@phrase.command("add")
@click.argument("phrase")
@collection_options
def add(phrase, native, target, llm, profile, thinking):
    """Generate and push a single phrase card."""

    async def _run():
        options = build_options(native, target, llm, profile, thinking)
        async with (
            anki_client_scope() as client,
            build_phrase_collection(client, options) as collection,
        ):
            await collection.generate_and_add_note(phrase)

    asyncio.run(_run())
    click.echo(f"✓ Added phrase: {phrase}")


# -- batch: multiple phrases, optionally from file ----------------------------


@phrase.command("batch")
@click.argument("phrases", nargs=-1, metavar="[PHRASE ...]")
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
def batch(phrases, file, native, target, llm, rpm, profile, thinking):
    """Generate and push multiple phrase cards.

    \b
    Phrases can be passed as arguments, read from a file (one per line),
    or both at the same time.

    \b
    Examples:
      anki phrase batch "focus on" "look after"
      anki phrase batch --file phrases.txt
      anki phrase batch "call off" --file more.txt
    """
    all_phrases = list(phrases)
    if file:
        # One phrase per line; strip empty lines
        file_phrases = [
            line.strip()
            for line in file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        all_phrases += file_phrases

    if not all_phrases:
        raise click.UsageError("Provide at least one phrase via argument or --file.")

    success, failed = [], []

    async def _run():
        nonlocal success

        sem = asyncio.Semaphore(MAX_CONCURRENCY)
        limiter = StrictLimiter(rpm / 60)
        options = build_options(native, target, llm, profile, thinking)

        async def _process(p: str):
            nonlocal success
            async with sem:
                await limiter.wait()
                try:
                    await collection.generate_and_add_note(p)
                    success.append(p)
                except Exception as e:
                    failed.append((p, str(e)))

        async with (
            anki_client_scope() as client,
            build_phrase_collection(client, options) as collection,
        ):
            await asyncio.gather(*[_process(p) for p in all_phrases])

    total = len(all_phrases)
    click.echo(f"Processing {total} phrases (concurrency={MAX_CONCURRENCY}) ...")
    asyncio.run(_run())
    if len(success) == total:
        click.echo("✅ All phrases processed successfully!")
    else:
        click.echo(f"\n✅ {len(success)}/{total} succeeded")
        for s in success:
            click.echo(f"   • {s}")
    if failed:
        click.echo(f"\n❌ {len(failed)} failed")
    for s, reason in failed:
        click.echo(f"   • {s}: {reason}")
