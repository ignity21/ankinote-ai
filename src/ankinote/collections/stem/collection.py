"""STEM collection management for Anki."""

import hashlib
from collections.abc import Callable
from typing import Self

from loguru import logger

from ankinote.services.ai import ImageGenerationService, TextGenerationService
from ankinote.services.anki import AnkiCollectionClient, TemplateUpsert
from ankinote.services.anki_batch import anki_write_batch

from .generator import StemGenerator
from .models import (
    NOTE_FIELDS,
    CardType,
    ExampleModel,
    FormulaModel,
    ProcedureModel,
    StemCard,
    note_type_name,
)
from .templates import load_card_style, load_template


class StemCollection:
    """Manages STEM knowledge notes in Anki.

    Covers concept definitions, formulas/theorems, and step-by-step
    procedures across Math, Statistics, Finance, Computer Science,
    Programming, and Machine Learning.
    """

    def __init__(
        self,
        anki_client: AnkiCollectionClient,
        *,
        card_type: CardType | None = None,
        deck_name: str = "AINote::STEM",
        text_model: str,
        text_service: TextGenerationService,
        image_service: ImageGenerationService | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        """Initialize StemCollection.

        Args:
            anki_client: AnkiConnect client instance
            card_type: Selected type, or None for automatic classification
            deck_name: Name of the Anki deck to add notes to
            text_model: The LLM model used to generate content
            text_service: Shared text generation service
            image_service: Optional image generation service for diagrams
            reasoning_effort: Extended-thinking level forwarded to the provider;
                ``None`` keeps the provider default (thinking on)
        """
        self.card_type = card_type
        self.deck_name = deck_name
        self._anki_client = anki_client
        self._reasoning_effort = reasoning_effort
        self._generator = StemGenerator(
            text_service=text_service,
            text_model=text_model,
            image_service=image_service,
        )

    async def __aenter__(self) -> Self:
        """Async context manager entry: ensure note type and deck exist."""
        await self._ensure_note_type_exists()
        await self._ensure_deck_exists()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""

    async def ensure_in_anki(self) -> None:
        """Create or update this note type and its deck in Anki.

        Idempotent equivalent of the CLI ``init`` command: creates the note
        type with the current fields, templates and styling when missing, or
        refreshes templates, styling and missing fields when it already exists,
        then ensures the deck is present. Does not start TTS or LLM services,
        so it is safe to call from the GUI setup flow.
        """
        async with anki_write_batch(self._anki_client):
            await self._ensure_note_type_exists()
            await self._ensure_deck_exists()

    async def _ensure_note_type_exists(self) -> None:
        """Initialize the selected type, or all four for the automatic entrypoint."""
        for card_type in [self.card_type] if self.card_type else list(CardType):
            await self._sync_note_type(card_type)

    async def _sync_note_type(self, card_type: CardType) -> None:
        """Ensure the note type exists in Anki, creating or updating it."""
        fields = list(NOTE_FIELDS[card_type])
        notetype_name = note_type_name(card_type)
        front_template = load_template(f"{card_type}/front.html")
        back_template = load_template(f"{card_type}/back.html")
        style = load_card_style()
        exists = await self._anki_client.models.exists(notetype_name)
        if not exists:
            await self._anki_client.models.create(
                model_name=notetype_name,
                fields=fields,
                templates=[
                    {
                        "Name": "Card 1",
                        "Front": front_template,
                        "Back": back_template,
                    },
                ],
                css=style,
                is_cloze=False,
            )
            logger.success(f"Created note type: {notetype_name}")
            return

        await self._anki_client.models.ensure_fields(notetype_name, fields)
        await self._anki_client.models.update_templates(
            notetype_name,
            [
                TemplateUpsert(
                    name="Card 1",
                    question_format=front_template,
                    answer_format=back_template,
                )
            ],
        )
        await self._anki_client.models.update_styling(notetype_name, style)
        logger.success(f"Updated note type: {notetype_name}")

    async def _ensure_deck_exists(self) -> int:
        """Ensure the deck exists in Anki, create it if it doesn't."""
        deck_id = await self._anki_client.decks.create(self.deck_name)
        logger.success(f"Ensured deck exists: {self.deck_name}")
        return deck_id

    async def generate_and_add_note(
        self,
        topic: str,
        tags: list[str] | None = None,
        reference_image: bytes | None = None,
        reference_image_mime: str = "image/png",
    ) -> int:
        """Generate a STEM card and add/update note in Anki.

        This method:
        1. Uses LLM to generate structured card data (auto-detects card type)
        2. Generates a diagram if the AI determines one is needed
        3. Creates or updates the note in Anki

        Args:
            topic: The user's question or concept (e.g. "What is a derivative?")
            tags: Optional additional tags to apply
            reference_image: Optional source material (e.g. a photographed
                problem) for the AI to read and solve from; requires a
                vision-capable text model.
            reference_image_mime: MIME type of ``reference_image``.

        Returns:
            Note ID
        """
        logger.info(f"Starting generation for STEM card: {topic[:50]}...")
        stem_model = await self.generate_model(
            topic,
            reference_image=reference_image,
            reference_image_mime=reference_image_mime,
        )
        return await self.add_note(stem_model, topic=topic, tags=tags)

    async def generate_model(
        self,
        topic: str,
        reference_image: bytes | None = None,
        reference_image_mime: str = "image/png",
    ) -> StemCard:
        """Generate structured STEM card data via the LLM (no Anki write).

        The card type (concept, formula, procedure, example) is auto-detected.
        Callers that want a preview/edit step run this, let the user adjust
        the result, then pass the model to :meth:`add_note`.

        ``reference_image``, when supplied, is source material for the AI to
        solve from (e.g. a photographed problem); it requires a
        vision-capable text model.
        """
        return await self._generator.generate(
            topic,
            reasoning_effort=self._reasoning_effort,
            reference_image=reference_image,
            reference_image_mime=reference_image_mime,
            card_type=self.card_type,
        )

    async def generate_diagram(self, description: str) -> bytes:
        """Generate a diagram image from a description.

        Raises:
            RuntimeError: if no image service was configured.
        """
        return await self._generator.generate_image(description)

    async def add_note(
        self,
        stem_model: StemCard,
        *,
        topic: str | None = None,
        image_bytes: bytes | None = None,
        tags: list[str] | None = None,
        on_image_error: Callable[[Exception], None] | None = None,
    ) -> int:
        """Add or update an Anki note from a (possibly edited) ``StemCard``.

        Args:
            stem_model: The card data to store.
            topic: Original prompt, used only to derive the image filename;
                falls back to ``stem_model.front``.
            image_bytes: A pre-generated diagram to store as-is. When omitted, a
                diagram is generated from ``stem_model.image_description`` if that
                is set and an image service is configured.
            tags: Optional additional tags to apply.
            on_image_error: Optional callback for a non-fatal diagram failure.

        Returns:
            Note ID
        """
        if self.card_type is not None and stem_model.card_type != self.card_type:
            raise ValueError("Card type does not match the selected collection")
        notetype_name = note_type_name(stem_model.card_type)
        image_key = f"{stem_model.card_type}:{topic or stem_model.front}"
        image_bytes = await self._resolve_image_bytes(
            stem_model, image_bytes, on_image_error
        )

        async with anki_write_batch(self._anki_client):
            image_filename: str | None = None
            if image_bytes is not None:
                card_hash = hashlib.md5(image_key.encode()).hexdigest()[:12]
                image_filename = f"stem_{card_hash}.png"
                await self._anki_client.media.store_file(image_filename, image_bytes)
                logger.info(f"Stored diagram: {image_filename}")

            note_data = self._build_note_data(stem_model, image_filename)
            all_tags = [*(tags or []), *stem_model.tags, "AI-generated"]
            return await self._upsert_note(
                notetype_name, note_data, all_tags, stem_model.front
            )

    async def _resolve_image_bytes(
        self,
        stem_model: StemCard,
        image_bytes: bytes | None,
        on_image_error: Callable[[Exception], None] | None,
    ) -> bytes | None:
        """Use the caller's bytes as-is, else generate a diagram from the model."""
        if image_bytes is not None or not (
            stem_model.image_description and self._generator._image_service
        ):
            return image_bytes
        try:
            return await self._generator.generate_image(stem_model.image_description)
        except Exception as exc:
            logger.warning(f"Image generation failed: {exc}")
            if on_image_error is not None:
                on_image_error(exc)
            return None

    async def _upsert_note(
        self,
        notetype_name: str,
        note_data: dict[str, str],
        tags: list[str],
        front: str,
    ) -> int:
        """Update the note with a matching front, else create a new one."""
        note_id = await self._anki_client.notes.find(
            deck_name=self.deck_name,
            unique_fields={"front": front},
            model_name=notetype_name,
        )
        if note_id is not None:
            await self._anki_client.notes.update_fields(note_id, note_data)
            await self._anki_client.notes.update_tags(note_id, tags)
            logger.info(f"Updated note {note_id}")
            return note_id
        note_id = await self._anki_client.notes.add(
            deck_name=self.deck_name,
            model_name=notetype_name,
            fields=note_data,
            tags=tags,
            allow_duplicate=False,
        )
        logger.info(f"Created note {note_id}")
        return note_id

    def _build_note_data(
        self,
        stem_model: StemCard,
        image_filename: str | None,
    ) -> dict[str, str]:
        """Render each structured value into its own Anki field."""
        values = stem_model.model_dump()
        fields = {
            name: str(values[name])
            for name in NOTE_FIELDS[stem_model.card_type]
            if name not in {"image", "variables", "steps"}
        }
        if isinstance(stem_model, FormulaModel):
            rows = "".join(
                f"<tr><td class='symbol-cell'>\\({v.symbol}\\)</td>"
                + f"<td>{v.description}</td></tr>"
                for v in stem_model.variables
            )
            fields["variables"] = (
                f"<table class='symbol-table'>{rows}</table>" if rows else ""
            )
        if isinstance(stem_model, (ProcedureModel, ExampleModel)):
            items = "".join(f"<li>{step}</li>" for step in stem_model.steps)
            fields["steps"] = f"<ol class='step-list'>{items}</ol>"
        fields["image"] = (
            f"<img src='{image_filename}' class='diagram'>" if image_filename else ""
        )
        return {name: fields[name] for name in NOTE_FIELDS[stem_model.card_type]}
