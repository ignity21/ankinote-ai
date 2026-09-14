"""CLI commands for STEM card generation."""

import asyncio
import mimetypes
from pathlib import Path

import click
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ankinote.cli.factory import (
    THINKING_CHOICES,
    StemCollectionOptions,
    anki_client_scope,
    build_stem_collection,
    resolve_thinking,
)
from ankinote.collections.stem import CardType
from ankinote.services.ai import DEFAULT_AI_SERVICE_CONFIG

console = Console()


def collection_options(f):
    """Decorator for common collection options."""
    f = click.option(
        "--llm",
        default=None,
        show_default=DEFAULT_AI_SERVICE_CONFIG.text_model,
        help="LLM model ID for content generation",
    )(f)
    f = click.option(
        "--image-model",
        default=None,
        show_default=DEFAULT_AI_SERVICE_CONFIG.image_model,
        help="Image model ID for diagram generation",
    )(f)
    f = click.option(
        "--image-size",
        default=None,
        show_default=DEFAULT_AI_SERVICE_CONFIG.image_size,
        type=int,
        help="Image size in pixels (square)",
    )(f)
    f = click.option(
        "--thinking",
        default=None,
        type=click.Choice(THINKING_CHOICES),
        help=(
            "Override the model's extended-thinking level for this run "
            "(default: high, for STEM cards)."
        ),
    )(f)
    f = click.option(
        "--type",
        "card_type",
        type=click.Choice(["auto", *(str(kind) for kind in CardType)]),
        default="auto",
        show_default=True,
    )(f)
    return f


def build_options(
    llm: str | None,
    image_model: str | None,
    image_size: int | None,
    thinking: str | None = None,
    card_type: str = "auto",
) -> StemCollectionOptions:
    """Convert CLI parameters to typed collection options."""
    return StemCollectionOptions(
        llm_model=llm,
        image_model=image_model,
        image_size=image_size,
        reasoning_effort=resolve_thinking(thinking, unset="high"),
        card_type=None if card_type == "auto" else CardType(card_type),
    )


@click.group("stem")
def stem():
    """STEM knowledge cards (Math, CS, Finance, ML, ...)."""


@stem.command("init")
@collection_options
def init(llm, image_model, image_size, thinking, card_type):
    """Create note type and deck in Anki."""

    async def _run():
        options = build_options(llm, image_model, image_size, thinking, card_type)
        async with (
            anki_client_scope() as client,
            build_stem_collection(client, options) as collection,
        ):
            console.print(
                f"[green]\u2713[/green] Initialized STEM collection: {collection.deck_name}"
            )

    asyncio.run(_run())


@stem.command("add")
@click.argument("topic")
@click.option(
    "--image",
    "image_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Reference image (e.g. a photographed problem) for the AI to solve "
        "from. Requires a vision-capable --llm model."
    ),
)
@collection_options
def add(topic, image_path, llm, image_model, image_size, thinking, card_type):
    """Generate and push a single STEM card.

    TOPIC is any question or concept (e.g. "What is a derivative?",
    "请解释平行线的概念", "State Bayes' theorem").
    """
    reference_image = image_path.read_bytes() if image_path else None
    reference_image_mime = (
        image_path and mimetypes.guess_type(image_path.name)[0]
    ) or "image/png"

    async def _run():
        options = build_options(llm, image_model, image_size, thinking, card_type)
        async with (
            anki_client_scope() as client,
            build_stem_collection(client, options) as collection,
        ):
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"Generating STEM card for: {topic[:50]}...", total=None
                )
                note_id = await collection.generate_and_add_note(
                    topic,
                    reference_image=reference_image,
                    reference_image_mime=reference_image_mime,
                )
                progress.update(task, completed=True)

            console.print(f"[green]\u2713[/green] Created/updated note {note_id}")

    asyncio.run(_run())


@stem.command("batch")
@click.argument("topics", nargs=-1)
@click.option(
    "--file",
    type=click.Path(exists=True, path_type=Path),
    help="File containing topics (one per line)",
)
@collection_options
@click.option(
    "--rpm",
    default=10,
    type=int,
    help="Requests per minute limit",
)
def batch(topics, file, llm, image_model, image_size, rpm, thinking, card_type):
    """Generate and push multiple STEM cards.

    Topics can be passed as arguments, read from a file (one per line),
    or both at the same time.

    Examples:
      anki stem add "What is a derivative?"
      anki stem batch --file topics.txt
      anki stem batch "What is entropy?" --file more_topics.txt
    """
    all_topics = list(topics)
    if file:
        all_topics.extend(
            line.strip()
            for line in file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

    if not all_topics:
        console.print("[red]Error:[/red] No topics provided")
        return

    console.print(f"[cyan]Processing {len(all_topics)} topic(s)...[/cyan]")

    success = 0

    async def _run():
        nonlocal success
        options = build_options(llm, image_model, image_size, thinking, card_type)

        async with (
            anki_client_scope() as client,
            build_stem_collection(client, options) as collection,
        ):
            delay = 60.0 / rpm if rpm > 0 else 0

            async def _process(q: str):
                nonlocal success
                try:
                    with console.status(f"[bold cyan]Generating: {q[:50]}..."):
                        note_id = await collection.generate_and_add_note(q)
                    console.print(f"[green]\u2713[/green] Note {note_id}: {q[:60]}...")
                    success += 1
                except Exception as e:
                    logger.error(f"Failed to process '{q}': {e}")
                    console.print(f"[red]\u2717[/red] Failed: {q[:60]}...")

            for i, topic in enumerate(all_topics):
                await _process(topic)
                if delay > 0 and i < len(all_topics) - 1:
                    await asyncio.sleep(delay)

    asyncio.run(_run())

    console.print(
        f"\n[bold]Summary:[/bold] {success}/{len(all_topics)} cards successfully created"
    )
