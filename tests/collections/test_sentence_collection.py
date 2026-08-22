"""Tests for the sentence V2 collection."""

from types import SimpleNamespace
from typing import cast

import pytest

from ankinote.collections.sentence.collection import MediaReferences, SentenceCollection
from ankinote.collections.sentence.models import PhraseModel, SentenceModel
from ankinote.consts import Language
from ankinote.services.ai import TextGenerationService
from ankinote.services.anki import (
    AnkiCollectionClient,
    AnkiDeckService,
    AnkiMediaService,
    AnkiModelService,
    AnkiNoteService,
    NoteModel,
)


class DummyTextService:
    """Minimal text service stub for collection construction."""

    async def generate_text(self, **kwargs: object) -> str:  # pragma: no cover
        raise AssertionError("Text generation should not be used in these tests")


class RecordingModelService:
    """Record note type creation requests."""

    def __init__(self) -> None:
        self.created: dict[str, object] | None = None
        self.updated_templates: list[object] = []
        self.updated_css: str | None = None
        self.exists_result = False

    async def exists(self, model_name: str) -> bool:
        return self.exists_result

    async def create(
        self,
        model_name: str,
        fields: list[str],
        templates: list[dict[str, str]],
        css: str,
        is_cloze: bool,
    ) -> NoteModel:
        self.created = {
            "model_name": model_name,
            "fields": fields,
            "templates": templates,
            "css": css,
            "is_cloze": is_cloze,
        }
        return NoteModel(id=1, name=model_name)

    async def update_templates(self, model_name: str, templates: list[object]) -> None:
        self.updated_templates = templates

    async def update_styling(self, model_name: str, css: str) -> None:
        self.updated_css = css


class DummyDeckService:
    """Deck stub for protocol completeness."""

    async def create(self, deck_name: str) -> int:  # pragma: no cover
        return 1


class DummyNoteService:
    """Note stub for protocol completeness."""

    async def find(  # pragma: no cover
        self,
        deck_name: str,
        unique_fields: dict[str, str],
    ) -> int | None:
        return None

    async def add(  # pragma: no cover
        self,
        deck_name: str,
        model_name: str,
        fields: dict[str, str],
        tags: list[str] | None = None,
        allow_duplicate: bool = False,
    ) -> int:
        return 1

    async def update_fields(
        self, note_id: int, fields: dict[str, str]
    ) -> None:  # pragma: no cover
        return None

    async def update_tags(
        self, note_id: int, tags: list[str]
    ) -> None:  # pragma: no cover
        return None


class DummyMediaService:
    """Media stub for protocol completeness."""

    async def store_file(self, filename: str, data: bytes) -> str:  # pragma: no cover
        return filename


def _build_collection(
    target_language: Language,
) -> tuple[SentenceCollection, RecordingModelService]:
    models = RecordingModelService()
    client = cast(
        AnkiCollectionClient,
        SimpleNamespace(
            models=cast(AnkiModelService, models),
            decks=cast(AnkiDeckService, DummyDeckService()),
            notes=cast(AnkiNoteService, DummyNoteService()),
            media=cast(AnkiMediaService, DummyMediaService()),
        ),
    )
    collection = SentenceCollection(
        client,
        native_language=Language.CHINESE_S,
        target_language=target_language,
        text_model_id="sentence-model",
        text_service=cast(TextGenerationService, DummyTextService()),
    )
    return collection, models


def _build_model() -> SentenceModel:
    return SentenceModel(
        target_sentence="I overslept this morning.",
        native_sentence="我今天早上睡过头了。",
        notes=[
            "睡过头 (shuì guò tóu) is the standard way to say 'oversleep'.",
            "今天早上 (jīntiān zǎoshang) is a time phrase that can be placed at the start or end.",
        ],
        phrases=[
            PhraseModel(
                phrase="oversleep",
                translation="睡过头",
                example="I often oversleep on weekends.",
            ),
            PhraseModel(
                phrase="this morning",
                translation="今天早上",
                example="I had a meeting this morning.",
            ),
        ],
    )


def test_convert_to_note_type_renders_expected_html():
    collection, _ = _build_collection(Language.ENGLISH)
    note = collection._convert_to_note_type(
        _build_model(),
        MediaReferences(pron_audio="sentence_abc123.mp3"),
    )

    assert note["target_sentence"] == "I overslept this morning."
    assert note["native_sentence"] == "我今天早上睡过头了。"
    assert note["pron_audio"] == "[sound:sentence_abc123.mp3]"
    assert "睡过头" in note["notes"]
    assert "今天早上" in note["notes"]
    assert "oversleep" in note["phrases"]
    assert "睡过头" in note["phrases"]
    assert "I often oversleep on weekends." in note["phrases"]
    assert note["user_notes"] == ""


def test_convert_to_note_type_renders_ruby_for_japanese():
    collection, _ = _build_collection(Language.JAPANESE)
    note = collection._convert_to_note_type(
        SentenceModel(
            target_sentence="<今:こん><朝:ちょう>は<寝:ね><坊:ぼう>した。",
            native_sentence="今天早上睡过头了。",
            notes=[],
            phrases=[
                PhraseModel(
                    phrase="<寝:ね><坊:ぼう>",
                    translation="睡过头",
                    example="<毎:まい><朝:あさ><寝:ね><坊:ぼう>し<て:て>しまう。",
                ),
            ],
        ),
        MediaReferences(pron_audio="sentence_abc.mp3"),
    )

    assert "<ruby>今<rt>こん</rt></ruby>" in note["target_sentence"]
    assert "<ruby>寝<rt>ね</rt></ruby>" in note["phrases"]


@pytest.mark.asyncio
async def test_ensure_note_type_exists_registers_v2_templates():
    collection, models = _build_collection(Language.ENGLISH)

    await collection._ensure_note_type_exists()

    created = models.created
    assert created is not None
    assert created["model_name"] == "AINote Sentence V2"
    assert created["fields"] == [
        "target_sentence",
        "native_sentence",
        "pron_audio",
        "notes",
        "phrases",
        "user_notes",
    ]
    templates = cast(list[dict[str, str]], created["templates"])
    assert [template["Name"] for template in templates] == [
        "Production",
    ]
    assert "{{native_sentence}}" in templates[0]["Front"]
    assert "{{target_sentence}}" in templates[0]["Back"]
    assert ".sentence-stage" in cast(str, created["css"])


@pytest.mark.asyncio
async def test_ensure_note_type_exists_updates_existing_model():
    collection, models = _build_collection(Language.ENGLISH)
    models.exists_result = True

    await collection._ensure_note_type_exists()

    assert models.created is None
    assert len(models.updated_templates) == 1
    assert models.updated_css is not None
