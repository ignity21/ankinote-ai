"""STEM collection management for Anki."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Self

from loguru import logger

from ankinote.collections.common import MediaGap
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


@dataclass
class StemMedia:
    """A card's diagram, or the gap that says why it has none."""

    image: bytes | None = None
    gaps: list[MediaGap] = field(default_factory=list)


@dataclass
class StemCardData:
    """A generated (possibly edited) card and its media, not yet in Anki."""

    model: StemCard
    media: StemMedia


def anki_tags(tags: list[str]) -> list[str]:
    """``tags`` as Anki keeps them: it splits on spaces, so words join with ``_``."""
    joined = ("_".join(tag.split()) for tag in tags)
    return list(dict.fromkeys(tag for tag in joined if tag))


def _image_name(image: bytes) -> str:
    """Named by content, so a diagram keeps its name when the card is edited."""
    return f"stem_{hashlib.md5(image).hexdigest()[:12]}.png"


class StemCollection:
    """Manages STEM knowledge notes in Anki.

    Covers concept definitions, formulas/theorems, and step-by-step
    procedures across Math, Statistics, Finance, Computer Science,
    Programming, and Machine Learning.
    """

    def __init__(
        self,
        anki_client: AnkiCollectionClient | None,
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
            anki_client: Anki client; None for a collection that only
                generates (writing to Anki then fails)
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

    @property
    def _anki(self) -> AnkiCollectionClient:
        if self._anki_client is None:
            raise RuntimeError("This StemCollection was built without an Anki client")
        return self._anki_client

    @property
    def notetype_name(self) -> str:
        """The selected type's note type; a collection for drafts has one type."""
        if self.card_type is None:
            raise ValueError("No card type selected")
        return note_type_name(self.card_type)

    def card_templates(self) -> list[dict[str, str]]:
        """The selected type's one card template, as Anki stores it."""
        if self.card_type is None:
            raise ValueError("No card type selected")
        return [
            {
                "Name": "Card 1",
                "Front": load_template(f"{self.card_type}/front.html"),
                "Back": load_template(f"{self.card_type}/back.html"),
            }
        ]

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
        async with anki_write_batch(self._anki):
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
        exists = await self._anki.models.exists(notetype_name)
        if not exists:
            await self._anki.models.create(
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

        await self._anki.models.ensure_fields(notetype_name, fields)
        await self._anki.models.update_templates(
            notetype_name,
            [
                TemplateUpsert(
                    name="Card 1",
                    question_format=front_template,
                    answer_format=back_template,
                )
            ],
        )
        await self._anki.models.update_styling(notetype_name, style)
        logger.success(f"Updated note type: {notetype_name}")

    async def _ensure_deck_exists(self) -> int:
        """Ensure the deck exists in Anki, create it if it doesn't."""
        deck_id = await self._anki.decks.create(self.deck_name)
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

        async with anki_write_batch(self._anki):
            image_filename: str | None = None
            if image_bytes is not None:
                card_hash = hashlib.md5(image_key.encode()).hexdigest()[:12]
                image_filename = f"stem_{card_hash}.png"
                await self._anki.media.store_file(image_filename, image_bytes)
                logger.info(f"Stored diagram: {image_filename}")

            note_data = self._build_note_data(stem_model, image_filename)
            all_tags = anki_tags([*(tags or []), *stem_model.tags, "AI-generated"])
            return await self._upsert_note(
                notetype_name, note_data, all_tags, stem_model.front
            )

    # -- Drafts: generate, edit or rewrite, preview, then save -----------------

    async def generate_cards(self, topic: str) -> list[StemCardData]:
        """One card for ``topic``, with its diagram when it wants one."""
        model = await self.generate_model(topic)
        return [StemCardData(model=model, media=await self._diagram(model))]

    async def rewrite_card(
        self,
        card: StemCardData,
        topic: str,
        instruction: str,
        *,
        card_type: CardType | None = None,
    ) -> StemCardData:
        """``card`` rewritten by the model as ``instruction`` asks.

        The diagram is kept while the new card asks for the same one.
        """
        model = await self._generator.rewrite(
            topic,
            card.model,
            instruction,
            card_type=card_type,
            reasoning_effort=self._reasoning_effort,
        )
        return StemCardData(model=model, media=await self._diagram(model, card))

    async def revise_card(self, card: StemCardData, model: StemCard) -> StemCardData:
        """``card`` with edited fields; edits never touch the diagram."""
        return StemCardData(model=model, media=card.media)

    async def _diagram(
        self, model: StemCard, previous: StemCardData | None = None
    ) -> StemMedia:
        description = model.image_description
        if not description:
            return StemMedia()
        if (
            previous is not None
            and previous.media.image is not None
            and previous.model.image_description == description
        ):
            return StemMedia(image=previous.media.image)
        if self._generator._image_service is None:
            return StemMedia(gaps=[MediaGap("image", "not_set_up")])
        try:
            return StemMedia(image=await self._generator.generate_image(description))
        except Exception as exc:
            logger.warning(f"Diagram failed, card made without it: {exc}")
            return StemMedia(gaps=[MediaGap("image", "failed", str(exc))])

    def note_fields(self, card: StemCardData) -> dict[str, str]:
        image = card.media.image
        return self._build_note_data(
            card.model, _image_name(image) if image is not None else None
        )

    def note_tags(self, card: StemCardData) -> list[str]:
        return anki_tags([*card.model.tags, "AI-generated"])

    def media_files(self, card: StemCardData) -> dict[str, bytes]:
        image = card.media.image
        return {_image_name(image): image} if image is not None else {}

    async def save_card(
        self, card: StemCardData, /, *, replaces: StemCardData | None = None
    ) -> int:
        """Write ``card`` to Anki; returns the note id.

        ``replaces`` is the card saved from the same draft before: its note
        is updated even if the front has changed since. Otherwise a note with
        the same front (and type) is updated, else a new one is added.
        """
        model = card.model
        notetype_name = note_type_name(model.card_type)
        async with anki_write_batch(self._anki):
            image_name = None
            if card.media.image is not None:
                # Anki may keep it under another name if that one is taken.
                image_name = await self._anki.media.store_file(
                    _image_name(card.media.image), card.media.image
                ) or _image_name(card.media.image)
            fields = self._build_note_data(model, image_name)
            tags = self.note_tags(card)
            if (
                replaces is not None
                and replaces.model.card_type == model.card_type
                and replaces.model.front != model.front
            ):
                note_id = await self._anki.notes.find(
                    deck_name=self.deck_name,
                    unique_fields={"front": replaces.model.front},
                    model_name=notetype_name,
                )
                if note_id is not None:
                    await self._anki.notes.update_fields(note_id, fields)
                    await self._anki.notes.update_tags(note_id, tags)
                    return note_id
            return await self._upsert_note(notetype_name, fields, tags, model.front)

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
        note_id = await self._anki.notes.find(
            deck_name=self.deck_name,
            unique_fields={"front": front},
            model_name=notetype_name,
        )
        if note_id is not None:
            await self._anki.notes.update_fields(note_id, note_data)
            await self._anki.notes.update_tags(note_id, tags)
            logger.info(f"Updated note {note_id}")
            return note_id
        note_id = await self._anki.notes.add(
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
