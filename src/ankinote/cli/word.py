import asyncio
from pathlib import Path

import click
from asynciolimiter import StrictLimiter

from ankinote.cli.factory import (
    THINKING_CHOICES,
    WordCollectionOptions,
    anki_client_scope,
    build_word_collection,
    resolve_thinking,
)
from ankinote.cli.phrase import MAX_CONCURRENCY
from ankinote.consts import Language
from ankinote.services.ai import DEFAULT_AI_SERVICE_CONFIG, DISABLE_REASONING

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
        "--image-model",
        default=None,
        show_default=DEFAULT_AI_SERVICE_CONFIG.image_model,
    ),
    click.option(
        "--image-size",
        default=None,
        show_default=DEFAULT_AI_SERVICE_CONFIG.image_size,
        type=int,
    ),
    click.option(
        "--profile",
        default=None,
        help="Named text provider profile (default: the active one in settings).",
    ),
    click.option(
        "--image-profile",
        default=None,
        help="Named image provider profile (default: the active one in settings).",
    ),
    click.option(
        "--thinking",
        default=None,
        type=click.Choice(THINKING_CHOICES),
        help=(
            "Override the model's extended-thinking level for this run "
            "(default: off for word cards)."
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
    image_model: str | None,
    image_size: int | None,
    profile: str | None = None,
    image_profile: str | None = None,
    thinking: str | None = None,
) -> WordCollectionOptions:
    """Convert CLI parameters to typed collection options."""
    return WordCollectionOptions(
        native_language=Language(native),
        target_language=Language(target),
        llm_model=llm,
        image_model=image_model,
        image_size=image_size,
        reasoning_effort=resolve_thinking(thinking, unset=DISABLE_REASONING),
        profile=profile,
        image_profile=image_profile,
    )


# -- word group ---------------------------------------------------------------


@click.group("word")
def word():
    """Word card commands"""


# -- init: create note type and deck ------------------------------------------


@word.command("init")
@collection_options
def init(
    native, target, llm, image_model, image_size, profile, image_profile, thinking
):
    """Create note type and deck in Anki."""

    async def _run():
        options = build_options(
            native,
            target,
            llm,
            image_model,
            image_size,
            profile,
            image_profile,
            thinking,
        )
        async with (
            anki_client_scope() as client,
            build_word_collection(client, options),
        ):
            pass

    asyncio.run(_run())
    click.echo("✓ Ready (word collection)")


# -- add: single word ---------------------------------------------------------


@word.command("add")
@click.argument("word")
@collection_options
def add(
    word, native, target, llm, image_model, image_size, profile, image_profile, thinking
):
    """Generate and push a single word card."""

    async def _run():
        options = build_options(
            native,
            target,
            llm,
            image_model,
            image_size,
            profile,
            image_profile,
            thinking,
        )
        async with (
            anki_client_scope() as client,
            build_word_collection(client, options) as collection,
        ):
            await collection.generate_and_add_note(word)

    asyncio.run(_run())
    click.echo(f"✓ Added: {word}")


# -- batch: multiple words, optionally from file ------------------------------


@word.command("batch")
@click.argument("words", nargs=-1, metavar="[WORD ...]")
@click.option(
    "--file", "-f", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option(
    "--rpm",
    default=8,
    show_default=True,
    help="Max requests per minute (match your AI provider's limit).",
)
@collection_options
def batch(
    words,
    file,
    native,
    target,
    llm,
    image_model,
    image_size,
    rpm,
    profile,
    image_profile,
    thinking,
):
    """Generate and push multiple word cards.

    Words can be passed as arguments, read from a file (whitespace-separated),
    or both at the same time.

    Examples:
      anki word batch apple banana cat
      anki word batch --file words.txt
      anki word batch --rpm 30 apple --file more.txt
    """
    all_words = list(words)
    if file:
        all_words += file.read_text(encoding="utf-8").split()

    if not all_words:
        raise click.UsageError("Provide at least one word via argument or --file.")

    success, failed = [], []

    async def _run():
        nonlocal success

        sem = asyncio.Semaphore(MAX_CONCURRENCY)
        limiter = StrictLimiter(rpm / 60)
        options = build_options(
            native,
            target,
            llm,
            image_model,
            image_size,
            profile,
            image_profile,
            thinking,
        )

        async def _process(w: str):
            nonlocal success
            async with sem:
                await limiter.wait()
                try:
                    await collection.generate_and_add_note(w)
                    success.append(w)
                except Exception as e:
                    failed.append((w, str(e)))

        async with (
            anki_client_scope() as client,
            build_word_collection(client, options) as collection,
        ):
            await asyncio.gather(*[_process(w) for w in all_words])

    total = len(all_words)
    click.echo(
        f"Processing {total} words (concurrency={MAX_CONCURRENCY}, rpm={rpm}) ..."
    )
    asyncio.run(_run())
    if len(success) == total:
        click.echo("✅ All words processed successfully!")
    else:
        click.echo(f"\n✅ {len(success)}/{total} succeeded")
        for s in success:
            click.echo(f"   • {s}")
    if failed:
        click.echo(f"\n❌ {len(failed)} failed")
    for s, reason in failed:
        click.echo(f"   • {s}: {reason}")
