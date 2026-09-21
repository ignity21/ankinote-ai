"""Tests for the phrase V2 collection."""

from types import SimpleNamespace
from typing import cast

import pytest

from ankinote.collections.phrase.collection import MediaReferences, PhraseCollection
from ankinote.collections.phrase.models import Example, PhraseModel, Sense
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
        self.ensured_fields: list[str] | None = None
        self.added_fields: list[str] = []

    async def exists(self, model_name: str) -> bool:
        return self.exists_result

    async def get(self, model_name: str) -> NoteModel | None:
        if not self.exists_result:
            return None
        return NoteModel(id=1, name=model_name, fields=[], templates=[], css="")

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

    async def add_field(self, model_name: str, field_name: str) -> None:
        self.added_fields.append(field_name)

    async def ensure_fields(self, model_name: str, field_names: list[str]) -> None:
        self.ensured_fields = field_names


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
) -> tuple[PhraseCollection, RecordingModelService]:
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
    collection = PhraseCollection(
        client,
        native_language=Language.CHINESE_S,
        target_language=target_language,
        text_model="phrase-model",
        text_service=cast(TextGenerationService, DummyTextService()),
    )
    return collection, models


def _build_model() -> PhraseModel:
    return PhraseModel(
        phrase="take off",
        difficulty="B1",
        core_meaning=Sense(
            target_text="to leave the ground and begin to fly",
            native_text="起飞",
        ),
        supporting_meanings=[
            Sense(
                target_text="to become successful very quickly",
                native_text="腾飞",
            )
        ],
        examples=[
            Example(
                sentence="The plane takes off at 6 PM.",
                translation="飞机下午6点起飞。",
                highlights=["takes off"],
            )
        ],
        usage_pattern="verb + particle (no object)",
        production_hint="飞机离开地面",
        confusions=[
            "Do not confuse with 'take off' (remove clothing) which is a different meaning."
        ],
        etymology_or_memory="Aviation metaphor that extends to careers and businesses.",
        associations=["take off (remove)", "landing", "touch down"],
    )


def test_phrase_model_accepts_japanese_ruby_schema():
    model = PhraseModel.model_validate(
        {
            "phrase": "一石二鳥",
            "difficulty": "N3",
            "core_meaning": {
                "target_text": "<一:いっ><石:せき><二:に><鳥:ちょう>という<意:い>で、<一:ひと>つの<行:こう><為:い>で<二:ふた>つの<利:り><益:えき>を<得:え>ること",
                "native_text": "一石二鸟",
            },
            "supporting_meanings": [],
            "examples": [
                {
                    "sentence": "この<仕:し><事:ごと>は<一:いっ><石:せき><二:に><鳥:ちょう>だ。",
                    "translation": "这份工作一举两得。",
                    "highlights": ["<一:いっ><石:せき><二:に><鳥:ちょう>"],
                }
            ],
            "usage_pattern": "固定表現",
            "production_hint": "一举两得",
            "confusions": [],
            "etymology_or_memory": "英語の 'kill two birds with one stone' に相当する英語のことわざ由来",
            "associations": ["<一:いっ><挙:きょ><両:りょう><得:とく>"],
        }
    )

    assert model.phrase == "一石二鳥"
    assert model.core_meaning.target_text.startswith("<一:いっ><石:せき>")
    assert model.usage_pattern == "固定表現"


def test_phrase_model_rejects_duplicate_supporting_meaning():
    with pytest.raises(ValueError, match="supporting_meanings"):
        PhraseModel(
            phrase="take off",
            difficulty="B1",
            core_meaning=Sense(
                target_text="to leave the ground",
                native_text="起飞",
            ),
            supporting_meanings=[
                Sense(
                    target_text="to leave the ground",
                    native_text="起飞",
                )
            ],
            examples=[
                Example(
                    sentence="The plane takes off.",
                    translation="飞机起飞。",
                    highlights=["takes off"],
                )
            ],
            usage_pattern=None,
            production_hint=None,
            confusions=[],
            etymology_or_memory=None,
            associations=[],
        )


def test_convert_to_note_type_renders_expected_html():
    collection, _ = _build_collection(Language.ENGLISH)
    note = collection._convert_to_note_type(
        _build_model(),
        MediaReferences(
            phrase_audio="phrase.mp3",
            example_audios=["ex0.mp3"],
        ),
    )

    assert note["phrase"] == "take off"
    assert note["pron_audio"] == "[sound:phrase.mp3]"
    assert "to leave the ground and begin to fly" in note["core_meaning"]
    assert "起飞" in note["core_meaning"]
    assert note["translations"] == "腾飞"
    assert "example-audio inline-audio" in note["examples"]
    assert "[sound:ex0.mp3]" in note["examples"]
    assert "verb + particle (no object)" in note["usage_pattern"]
    assert "飞机离开地面" in note["production_hint"]
    assert "Do not confuse" in note["confusions"]
    assert "association-chip" in note["associations"]
    assert "take off (remove)" in note["associations"]
    assert note["user_notes"] == ""
    assert note["target_language"] == "English"


def test_convert_to_note_type_renders_ruby_for_japanese():
    collection, _ = _build_collection(Language.JAPANESE)
    note = collection._convert_to_note_type(
        PhraseModel(
            phrase="一石二鳥",
            difficulty="N3",
            core_meaning=Sense(
                target_text="<一:いっ><石:せき><二:に><鳥:ちょう>という<意:い>で、<一:ひと>つの<行:こう><為:い>で<二:ふた>つの<利:り><益:えき>",
                native_text="一石二鸟",
            ),
            supporting_meanings=[],
            examples=[
                Example(
                    sentence="「この<仕:し><事:ごと>は<一:いっ><石:せき><二:に><鳥:ちょう>だ。」",
                    translation="这份工作一举两得。",
                    highlights=["<一:いっ><石:せき><二:に><鳥:ちょう>"],
                )
            ],
            usage_pattern="固定表現",
            production_hint="一举两得",
            confusions=[],
            etymology_or_memory=None,
            associations=["<一:いっ><挙:きょ><両:りょう><得:とく>"],
        ),
        MediaReferences(
            phrase_audio="phrase.mp3",
            example_audios=["ex0.mp3"],
        ),
    )

    assert "<ruby>一<rt>いっ</rt></ruby>" in note["core_meaning"]
    # The phrase itself is not highlighted (same as Word V2 behavior)
    assert "example-highlight" not in note["examples"]
    assert "「" not in note["examples"]
    assert "」" not in note["examples"]
    assert "<ruby>一<rt>いっ</rt></ruby>" in note["associations"]


@pytest.mark.asyncio
async def test_ensure_note_type_exists_registers_v2_templates():
    collection, models = _build_collection(Language.ENGLISH)

    await collection._ensure_note_type_exists()

    created = models.created
    assert created is not None
    assert created["model_name"] == "AINote Phrase V2"
    assert created["fields"] == [
        "phrase",
        "pron_audio",
        "difficulty",
        "core_meaning",
        "sense_notes",
        "translations",
        "examples",
        "example_audio_refs",
        "usage_pattern",
        "confusions",
        "etymology_or_memory",
        "associations",
        "production_hint",
        "user_notes",
        "target_language",
    ]
    templates = cast(list[dict[str, str]], created["templates"])
    assert [template["Name"] for template in templates] == [
        "Recognition",
        "Recall",
    ]
    assert ".phrase-stage" in cast(str, created["css"])

    recall_front = next(t for t in templates if t["Name"] == "Recall")["Front"]
    assert "{{target_language}}" in recall_front


@pytest.mark.asyncio
async def test_ensure_note_type_exists_updates_existing_model():
    collection, models = _build_collection(Language.ENGLISH)
    models.exists_result = True

    await collection._ensure_note_type_exists()

    assert models.created is None
    assert models.ensured_fields == [
        "phrase",
        "pron_audio",
        "difficulty",
        "core_meaning",
        "sense_notes",
        "translations",
        "examples",
        "example_audio_refs",
        "usage_pattern",
        "confusions",
        "etymology_or_memory",
        "associations",
        "production_hint",
        "user_notes",
        "target_language",
    ]
    assert len(models.updated_templates) == 2
    assert models.updated_css is not None
