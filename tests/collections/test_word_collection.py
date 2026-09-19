"""Tests for the word v2 collection."""

from types import SimpleNamespace
from typing import cast

import pytest

from ankinote.collections.word.collection import MediaReferences, WordCollection
from ankinote.collections.word.generator import _build_image_user_prompt
from ankinote.collections.word.models import Example, Sense, WordModel
from ankinote.consts import Language
from ankinote.services.ai import ImageGenerationService, TextGenerationService
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


class DummyImageService:
    """Minimal image service stub for collection construction."""

    async def generate_image(self, *, prompt: str) -> bytes:  # pragma: no cover
        raise AssertionError("Image generation should not be used in these tests")


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
) -> tuple[WordCollection, RecordingModelService]:
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
    collection = WordCollection(
        client,
        native_language=Language.CHINESE_S,
        target_language=target_language,
        text_model="word-model",
        text_service=cast(TextGenerationService, DummyTextService()),
        image_service=cast(ImageGenerationService, DummyImageService()),
    )
    return collection, models


def _build_model() -> WordModel:
    return WordModel(
        lemma="test",
        part_of_speech="noun",
        pronunciation="/test/",
        difficulty="A1",
        morphology="plural tests",
        core_meaning=Sense(
            target_text="an exam or check",
            native_text="测试",
            is_visualizable=True,
        ),
        examples=[
            Example(
                sentence="The test starts now.",
                translation="测试现在开始。",
                highlights=["test"],
            )
        ],
        collocations=["take a test", "pass a test"],
        confusions=["Do not confuse with quiz in formal contexts."],
        etymology_or_memory="From Latin testum.",
    )


def test_word_model_accepts_japanese_ruby_schema():
    model = WordModel.model_validate(
        {
            "lemma": "招き猫",
            "part_of_speech": "名詞",
            "pronunciation": "まねきねこ",
            "difficulty": "N4",
            "morphology": None,
            "core_meaning": {
                "target_text": "<招:まね>き<猫:ねこ>の<置:お>き<物:もの>",
                "native_text": "招财猫",
                "is_visualizable": True,
            },
            "examples": [
                {
                    "sentence": "<店:みせ>に<招:まね>き<猫:ねこ>を<置:お>く。",
                    "translation": "把招财猫放在店里。",
                    "highlights": ["<招:まね>き<猫:ねこ>"],
                }
            ],
            "collocations": ["<招:まね>き<猫:ねこ>を<飾:かざ>る"],
            "confusions": [],
            "etymology_or_memory": None,
        }
    )

    assert model.lemma == "招き猫"
    assert model.core_meaning.target_text.startswith("<招:まね>")


def test_build_image_user_prompt_prefers_english_gloss_over_target_text():
    sense = Sense(
        target_text="雨や日差しを防ぐための道具",
        native_text="伞",
        image_gloss="a tool used to block rain or sunlight",
        is_visualizable=True,
    )

    prompt = _build_image_user_prompt("傘", sense)

    assert "a tool used to block rain or sunlight" in prompt
    assert "雨や日差しを防ぐための道具" not in prompt


def test_build_image_user_prompt_falls_back_to_target_text_when_gloss_missing():
    sense = Sense(target_text="a tool used to block rain", native_text="伞")

    prompt = _build_image_user_prompt("umbrella", sense)

    assert "a tool used to block rain" in prompt


def test_convert_to_note_type_renders_expected_html():
    collection, _ = _build_collection(Language.ENGLISH)
    note = collection._convert_to_note_type(
        _build_model(),
        MediaReferences(
            headword_audio="head.mp3",
            example_audios=["ex0.mp3"],
            images={0: "img0.png"},
        ),
    )

    assert note["lemma"] == "test"
    assert note["headword_audio"] == "[sound:head.mp3]"
    assert "an exam or check" in note["core_meaning"]
    assert "example-audio inline-audio" in note["examples"]
    assert "[sound:ex0.mp3]" in note["examples"]
    assert "img0.png" in note["image_refs"]
    assert "<figcaption>" not in note["image_refs"]
    assert note["user_notes"] == ""


def test_core_meaning_splits_multiple_senses_into_rows():
    collection, _ = _build_collection(Language.ENGLISH)
    model = _build_model()
    model.core_meaning = Sense(
        target_text="an exam; a trial of quality",
        native_text="考试；试验",
        is_visualizable=False,
    )
    note = collection._convert_to_note_type(
        model,
        MediaReferences(headword_audio="h.mp3", example_audios=[], images={}),
    )

    assert note["core_meaning"].count("meaning-row") == 2
    assert "an exam" in note["core_meaning"]
    assert "试验" in note["core_meaning"]
    assert ";" not in note["core_meaning"]


def test_convert_to_note_type_renders_ruby_for_japanese():
    collection, _ = _build_collection(Language.JAPANESE)
    note = collection._convert_to_note_type(
        WordModel(
            lemma="招き猫",
            part_of_speech="名詞",
            pronunciation="まねきねこ",
            difficulty="N4",
            morphology=None,
            core_meaning=Sense(
                target_text="<招:まね>き<猫:ねこ>の<置:お>き<物:もの>",
                native_text="招财猫",
                is_visualizable=True,
            ),
            examples=[
                Example(
                    sentence="「<店:みせ>に<招:まね>き<猫:ねこ>を<置:お>く。」",
                    translation="把招财猫放在店里。",
                    highlights=["<招:まね>き<猫:ねこ>"],
                ),
                Example(
                    sentence="「<招:まね>き<猫:ねこ>を<飾:かざ>ると<縁起:えんぎ>が<良:よ>い。」",
                    translation="摆放招财猫很吉利。",
                    highlights=[
                        "<招:まね>き<猫:ねこ>",
                        "<飾:かざ>る",
                        "<縁起:えんぎ>が<良:よ>い",
                    ],
                ),
            ],
            collocations=["<招:まね>き<猫:ねこ>を<飾:かざ>る"],
            confusions=[
                "<招:まね>く（よぶ）とは<意味:いみ>が<違:ちが>う",
                "中文里常作招财摆件理解",
            ],
            etymology_or_memory=None,
        ),
        MediaReferences(
            headword_audio="head.mp3",
            example_audios=["ex0.mp3"],
            images={0: "img0.png"},
        ),
    )

    assert "<ruby>招<rt>まね</rt></ruby>" in note["core_meaning"]
    assert "example-highlight" in note["examples"]
    assert "「" not in note["examples"]
    assert "」" not in note["examples"]
    assert (
        "<span class='example-highlight'><ruby>飾<rt>かざ</rt></ruby>る</span>"
        in note["examples"]
    )
    assert (
        "<span class='example-highlight'><ruby>招<rt>まね</rt></ruby>き<ruby>猫<rt>ねこ</rt></ruby></span>"
        not in note["examples"]
    )
    assert "<ruby>意味<rt>いみ</rt></ruby>" in note["confusions"]
    assert "中文里常作招财摆件理解" in note["confusions"]


@pytest.mark.asyncio
async def test_ensure_note_type_exists_registers_v2_templates():
    collection, models = _build_collection(Language.ENGLISH)

    await collection._ensure_note_type_exists()

    created = models.created
    assert created is not None
    assert created["model_name"] == "AINote Word V2"
    assert created["fields"] == [
        "lemma",
        "part_of_speech",
        "pronunciation",
        "headword_audio",
        "difficulty",
        "morphology",
        "core_meaning",
        "examples",
        "example_audio_refs",
        "collocations",
        "confusions",
        "etymology_or_memory",
        "image_refs",
        "user_notes",
    ]
    templates = cast(list[dict[str, str]], created["templates"])
    assert [template["Name"] for template in templates] == [
        "Recognition",
        "Recall",
        "Spelling",
    ]
    assert ".lemma-stage" in cast(str, created["css"])

    spelling_front = next(t for t in templates if t["Name"] == "Spelling")["Front"]
    # The Spelling prompt is audio + meaning; the example sentence spells the
    # word out, so it must not appear on the front.
    assert "core_meaning" in spelling_front
    assert "headword_audio" in spelling_front
    assert "examples" not in spelling_front


@pytest.mark.asyncio
async def test_ensure_note_type_exists_updates_existing_model():
    collection, models = _build_collection(Language.ENGLISH)
    models.exists_result = True

    await collection._ensure_note_type_exists()

    assert models.created is None
    assert len(models.updated_templates) == 3
    assert models.updated_css is not None
