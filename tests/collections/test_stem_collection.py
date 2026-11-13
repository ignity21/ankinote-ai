"""STEM type isolation, rendering, generation, and media contracts."""

import json
import re
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from ankinote.collections.stem.collection import (
    StemCardData,
    StemCollection,
    StemMedia,
)
from ankinote.collections.stem.generator import StemGenerator
from ankinote.collections.stem.models import (
    CARD_ADAPTER,
    NOTE_FIELDS,
    CardType,
    ConceptModel,
    ExampleModel,
    FormulaModel,
    ProcedureModel,
)
from ankinote.collections.stem.templates import load_template
from ankinote.services.ai import (
    GenerationTimeoutError,
    ImageGenerationService,
    TextGenerationService,
)
from ankinote.services.anki import AnkiCollectionClient

CARDS = [
    ConceptModel(
        front="Entropy?",
        back_brief="Uncertainty.",
        back_detail="An explanation.",
        tags=["Physics"],
    ),
    FormulaModel(
        front="Newton's law?",
        latex="F=ma",
        meaning="Force.",
        variables=[{"symbol": "F", "description": "Force"}],
        conditions="Inertial frame.",
        derivation="",
        tags=["Physics"],
    ),
    ProcedureModel(
        front="Solve a linear equation?",
        summary="Isolate x.",
        steps=["Subtract constant.", "Divide coefficient."],
        conditions="Nonzero coefficient.",
        tags=["Math"],
    ),
    ExampleModel(
        front="Solve 2x+3=11.",
        answer="x=4",
        steps=["Subtract 3.", "Divide by 2."],
        explanation="Inverse operations.",
        tags=["Math"],
    ),
]


def _make_collection(**kwargs) -> StemCollection:
    return StemCollection(
        cast(AnkiCollectionClient, object()),
        text_model="test",
        text_service=cast(TextGenerationService, object()),
        **kwargs,
    )


@pytest.mark.parametrize("model", CARDS)
def test_storage_fields_and_templates_are_type_specific(model):
    fields = _make_collection()._build_note_data(model, "diagram.png")
    assert list(fields) == list(NOTE_FIELDS[model.card_type])
    assert next(iter(fields)) == "front"
    assert "card_type" not in fields
    assert "tags" not in fields
    assert all(isinstance(value, str) for value in fields.values())
    assert "diagram.png" in fields["image"]
    for side in ("front", "back"):
        template = load_template(f"{model.card_type}/{side}.html")
        refs = set(re.findall(r"{{[#/^]?([^}]+)}}", template))
        assert refs <= set(fields) | {"FrontSide", "Tags"}
    assert "{{card_type}}" not in load_template(f"{model.card_type}/front.html")


def test_structured_content_stays_in_separate_fields():
    formula = _make_collection()._build_note_data(CARDS[1], None)
    assert formula["latex"] == "F=ma"
    assert "symbol-table" in formula["variables"]
    assert formula["conditions"] == "Inertial frame."
    assert "back_detail" not in formula
    example = _make_collection()._build_note_data(CARDS[3], None)
    assert "step-list" in example["steps"]
    assert example["answer"] == "x=4"
    assert "Subtract" not in example["explanation"]


def test_incompatible_fields_and_incomplete_solutions_are_rejected():
    with pytest.raises(ValidationError):
        ConceptModel.model_validate({**CARDS[0].model_dump(), "steps": ["irrelevant"]})
    with pytest.raises(ValidationError):
        ExampleModel.model_validate({**CARDS[3].model_dump(), "steps": []})
    with pytest.raises(ValidationError):
        FormulaModel.model_validate({**CARDS[1].model_dump(), "latex": ""})


@pytest.mark.parametrize("model", CARDS)
async def test_explicit_type_uses_one_call_and_its_own_schema(model):
    service = SimpleNamespace(
        generate_text=AsyncMock(return_value=model.model_dump_json())
    )
    generator = StemGenerator(cast(TextGenerationService, service), "test")
    result = await generator.generate(model.front, card_type=model.card_type)
    assert type(result) is type(model)
    service.generate_text.assert_awaited_once()
    system = service.generate_text.await_args.kwargs["messages"][0]["content"]
    assert type(model).__name__ in system
    assert (
        f"Generate a {model.card_type}" in system or model.card_type == CardType.EXAMPLE
    )


async def test_auto_classifies_then_generates_with_reference_in_both_calls():
    service = SimpleNamespace(
        generate_text=AsyncMock(
            side_effect=[
                '{"card_type":"example"}',
                CARDS[3].model_dump_json(),
            ]
        )
    )
    generator = StemGenerator(cast(TextGenerationService, service), "test")
    result = await generator.generate("Solve this", reference_image=b"photo")
    assert isinstance(result, ExampleModel)
    assert service.generate_text.await_count == 2
    for call in service.generate_text.await_args_list:
        parts = call.kwargs["messages"][1]["content"]
        assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert (
        "ExampleModel"
        in service.generate_text.await_args_list[1].kwargs["messages"][0]["content"]
    )


async def test_explicit_type_rejects_wrong_type_response():
    service = SimpleNamespace(
        generate_text=AsyncMock(return_value=CARDS[0].model_dump_json())
    )
    generator = StemGenerator(cast(TextGenerationService, service), "test")
    with pytest.raises(ValidationError):
        await generator.generate("topic", card_type=CardType.EXAMPLE)


async def test_same_front_is_scoped_to_note_type_for_insert_and_update():
    notes = SimpleNamespace(
        find=AsyncMock(side_effect=[None, 17]),
        add=AsyncMock(return_value=42),
        update_fields=AsyncMock(),
        update_tags=AsyncMock(),
    )
    collection = StemCollection(
        cast(AnkiCollectionClient, SimpleNamespace(notes=notes)),
        text_model="test",
        text_service=cast(TextGenerationService, object()),
    )
    concept = CARDS[0]
    example = CARDS[3].model_copy(update={"front": concept.front})
    await collection.add_note(concept)
    await collection.add_note(example)
    assert notes.find.await_args_list[0].kwargs["model_name"] == "AINote STEM Concept"
    assert notes.find.await_args_list[1].kwargs["model_name"] == "AINote STEM Example"
    assert notes.add.await_args.kwargs["model_name"] == "AINote STEM Concept"
    assert notes.update_fields.await_args.args[0] == 17
    assert "answer" in notes.update_fields.await_args.args[1]


async def test_selected_collection_rejects_other_type_before_writing():
    with pytest.raises(ValueError, match="does not match"):
        await _make_collection(card_type=CardType.CONCEPT).add_note(CARDS[3])


@pytest.mark.asyncio
async def test_generator_attaches_reference_image_to_user_message():
    """A reference image is sent as a vision content part, not lost as text."""
    payload = _CONCEPT_PAYLOAD

    class FakeTextService:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def generate_text(self, **kwargs):
            self.calls.append(kwargs)
            return payload

    text_service = FakeTextService()
    generator = StemGenerator(
        text_service=cast(TextGenerationService, text_service),
        text_model="stem-model",
    )

    await generator.generate(
        "solve the problem in the photo",
        reference_image=b"fake-png-bytes",
        reference_image_mime="image/png",
    )

    user_message = text_service.calls[0]["messages"][1]
    assert user_message["role"] == "user"
    content = user_message["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_generator_without_reference_image_sends_plain_text():
    class FakeTextService:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def generate_text(self, **kwargs):
            self.calls.append(kwargs)
            return _CONCEPT_PAYLOAD

    text_service = FakeTextService()
    generator = StemGenerator(
        text_service=cast(TextGenerationService, text_service),
        text_model="stem-model",
    )

    await generator.generate("what is entropy")

    user_message = text_service.calls[0]["messages"][1]
    assert isinstance(user_message["content"], str)


# -- generate_model / add_note split ---------------------------------------------


class _RecordingTextService:
    def __init__(self, payload: str) -> None:
        self._payload = payload
        self.calls: list[dict[str, object]] = []

    async def generate_text(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return self._payload


class _RecordingImageService:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate_image(self, *, prompt: str) -> bytes:
        self.prompts.append(prompt)
        return b"generated-bytes"


def _recording_anki_client() -> SimpleNamespace:
    stored: list[tuple[str, bytes]] = []
    added: list[dict[str, object]] = []

    async def store_file(filename: str, data: bytes) -> str:
        stored.append((filename, data))
        return filename

    async def find(
        *, deck_name: str, unique_fields: dict[str, str], model_name: str
    ) -> int | None:
        return None

    async def add(**kwargs: object) -> int:
        added.append(kwargs)
        return 42

    return SimpleNamespace(
        media=SimpleNamespace(store_file=store_file),
        notes=SimpleNamespace(find=find, add=add),
        _stored=stored,
        _added=added,
    )


_CONCEPT_PAYLOAD = json.dumps(
    {
        "card_type": "concept",
        "front": "What is entropy?",
        "back_brief": "A measure of disorder.",
        "back_detail": "Entropy quantifies uncertainty.",
        "tags": ["Physics"],
    }
)


@pytest.mark.asyncio
async def test_generate_model_threads_reasoning_effort():
    text_service = _RecordingTextService(_CONCEPT_PAYLOAD)
    collection = StemCollection(
        cast(AnkiCollectionClient, object()),
        text_model="stem-model",
        text_service=cast(TextGenerationService, text_service),
        reasoning_effort="high",
    )

    model = await collection.generate_model("entropy")

    assert model.card_type.value == "concept"
    assert text_service.calls[0]["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_generate_model_threads_reference_image():
    text_service = _RecordingTextService(_CONCEPT_PAYLOAD)
    collection = StemCollection(
        cast(AnkiCollectionClient, object()),
        text_model="stem-model",
        text_service=cast(TextGenerationService, text_service),
    )

    await collection.generate_model(
        "solve this", reference_image=b"bytes", reference_image_mime="image/jpeg"
    )

    user_message = text_service.calls[0]["messages"][1]
    content = user_message["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_add_note_stores_supplied_image_without_calling_service():
    anki = _recording_anki_client()
    image_service = _RecordingImageService()
    collection = StemCollection(
        cast(AnkiCollectionClient, anki),
        text_model="stem-model",
        text_service=cast(TextGenerationService, object()),
        image_service=cast(ImageGenerationService, image_service),
    )
    model = CARD_ADAPTER.validate_python(json.loads(_CONCEPT_PAYLOAD))

    note_id = await collection.add_note(model, topic="entropy", image_bytes=b"png")

    assert note_id == 42
    assert len(anki._stored) == 1
    name, data = anki._stored[0]
    assert name.startswith("stem_") and name.endswith(".png") and data == b"png"
    assert image_service.prompts == []
    fields = anki._added[0]["fields"]
    assert "<img src='" in fields["image"]


@pytest.mark.asyncio
async def test_add_note_generates_image_from_description():
    anki = _recording_anki_client()
    image_service = _RecordingImageService()
    collection = StemCollection(
        cast(AnkiCollectionClient, anki),
        text_model="stem-model",
        text_service=cast(TextGenerationService, object()),
        image_service=cast(ImageGenerationService, image_service),
    )
    model = CARD_ADAPTER.validate_python(
        {**json.loads(_CONCEPT_PAYLOAD), "image_description": "a diagram"}
    )

    await collection.add_note(model, topic="entropy")

    assert image_service.prompts and "a diagram" in image_service.prompts[0]
    assert anki._stored and anki._stored[0][1] == b"generated-bytes"


@pytest.mark.asyncio
async def test_add_note_reports_non_fatal_diagram_failure() -> None:
    class TimeoutImageService:
        async def generate_image(self, *, prompt: str) -> bytes:
            raise GenerationTimeoutError("Image generation", 180)

    anki = _recording_anki_client()
    collection = StemCollection(
        cast(AnkiCollectionClient, anki),
        text_model="stem-model",
        text_service=cast(TextGenerationService, object()),
        image_service=cast(ImageGenerationService, TimeoutImageService()),
    )
    errors: list[Exception] = []
    model = CARD_ADAPTER.validate_python(
        {**json.loads(_CONCEPT_PAYLOAD), "image_description": "a diagram"}
    )

    note_id = await collection.add_note(
        model, topic="entropy", on_image_error=errors.append
    )

    assert note_id == 42
    assert len(errors) == 1
    assert str(errors[0]) == "Image generation timed out after 180 seconds"
    assert anki._stored == []


@pytest.mark.asyncio
async def test_generate_and_add_note_composes_generate_and_add():
    anki = _recording_anki_client()
    text_service = _RecordingTextService(_CONCEPT_PAYLOAD)
    collection = StemCollection(
        cast(AnkiCollectionClient, anki),
        text_model="stem-model",
        text_service=cast(TextGenerationService, text_service),
    )

    note_id = await collection.generate_and_add_note("entropy", tags=["Extra"])

    assert note_id == 42
    assert "Extra" in anki._added[0]["tags"]
    assert "AI-generated" in anki._added[0]["tags"]


@pytest.mark.asyncio
async def test_multi_word_tags_stay_one_tag_in_anki():
    """Anki splits tags on spaces, so "Machine Learning" became two tags."""
    anki = _recording_anki_client()
    collection = StemCollection(
        cast(AnkiCollectionClient, anki),
        text_model="stem-model",
        text_service=cast(TextGenerationService, object()),
    )
    model = CARDS[0].model_copy(update={"tags": ["Machine Learning", " Math "]})

    await collection.add_note(model, tags=["My  Extra"])

    assert anki._added[0]["tags"] == [
        "My_Extra",
        "Machine_Learning",
        "Math",
        "AI-generated",
    ]


# -- Drafts: generate_cards / rewrite_card / save_card -----------------------


def _draft_collection(text: str, image_service=None, anki=None) -> StemCollection:
    return StemCollection(
        cast(AnkiCollectionClient, anki),
        text_model="stem-model",
        text_service=cast(TextGenerationService, _RecordingTextService(text)),
        image_service=cast(ImageGenerationService, image_service),
    )


_WITH_DIAGRAM = json.dumps(
    {**json.loads(_CONCEPT_PAYLOAD), "image_description": "a diagram"}
)


async def test_a_wanted_diagram_without_an_image_model_is_a_gap():
    collection = _draft_collection(_WITH_DIAGRAM)
    [card] = await collection.generate_cards("entropy")

    assert card.media.image is None
    assert [(g.kind, g.reason) for g in card.media.gaps] == [("image", "not_set_up")]
    assert collection.note_fields(card)["image"] == ""


async def test_no_diagram_wanted_is_no_gap():
    images = _RecordingImageService()
    [card] = await _draft_collection(_CONCEPT_PAYLOAD, images).generate_cards("e")

    assert card.media == StemMedia()
    assert images.prompts == []


async def test_a_failed_diagram_is_a_gap_and_the_card_is_still_made():
    class Failing:
        async def generate_image(self, *, prompt: str) -> bytes:
            raise RuntimeError("quota")

    [card] = await _draft_collection(_WITH_DIAGRAM, Failing()).generate_cards("e")

    assert card.model.front == "What is entropy?"
    assert [(g.reason, g.detail) for g in card.media.gaps] == [("failed", "quota")]


async def test_the_diagram_is_named_by_content_so_edits_keep_it():
    images = _RecordingImageService()
    collection = _draft_collection(_WITH_DIAGRAM, images)
    [card] = await collection.generate_cards("entropy")
    edited = await collection.revise_card(
        card, card.model.model_copy(update={"front": "Define entropy."})
    )

    [name] = collection.media_files(card)
    assert collection.media_files(edited) == {name: b"generated-bytes"}
    assert name in collection.note_fields(edited)["image"]


async def test_rewrite_sends_the_card_and_instruction_and_can_change_type():
    formula = CARDS[1].model_copy(update={"image_description": "a diagram"})
    text = _RecordingTextService(CARDS[3].model_dump_json())
    images = _RecordingImageService()
    collection = StemCollection(
        None,
        text_model="stem-model",
        text_service=cast(TextGenerationService, text),
        image_service=cast(ImageGenerationService, images),
    )
    card = StemCardData(model=formula, media=StemMedia(image=b"old"))

    result = await collection.rewrite_card(
        card, "newton", "用一个具体例子", card_type=CardType.EXAMPLE
    )

    assert isinstance(result.model, ExampleModel)
    [call] = text.calls  # an explicit type skips classification
    system, user = call["messages"]
    assert "ExampleModel" in system["content"]
    assert "Topic: newton" in user["content"]
    assert '"latex": "F=ma"' in user["content"]
    assert "Turn it into a example card." in user["content"]
    assert "Instruction: 用一个具体例子" in user["content"]
    # The new card wants no diagram, so the old one goes.
    assert result.media == StemMedia()


async def test_rewrite_keeps_the_diagram_while_its_description_stays():
    same = CARDS[0].model_copy(update={"image_description": "a diagram"})
    images = _RecordingImageService()
    collection = _draft_collection(same.model_dump_json(), images)
    card = StemCardData(model=same, media=StemMedia(image=b"old"))

    result = await collection.rewrite_card(card, "entropy", "shorter")

    assert result.media.image == b"old"
    assert images.prompts == []
    user = collection._generator._text_service.calls[0]["messages"][1]["content"]
    assert "Turn it into" not in user


def _saving_anki(found: dict[str, int]) -> SimpleNamespace:
    calls: dict[str, list] = {"add": [], "update": [], "tags": [], "stored": []}

    async def store_file(filename: str, data: bytes) -> str:
        calls["stored"].append(filename)
        return "renamed.png"

    async def find(*, deck_name, unique_fields, model_name) -> int | None:
        return found.get(f"{model_name}|{unique_fields['front']}")

    async def add(**kwargs) -> int:
        calls["add"].append(kwargs)
        return 7

    async def update_fields(note_id, fields) -> None:
        calls["update"].append((note_id, fields))

    async def update_tags(note_id, tags) -> None:
        calls["tags"].append((note_id, tags))

    return SimpleNamespace(
        media=SimpleNamespace(store_file=store_file),
        notes=SimpleNamespace(
            find=find, add=add, update_fields=update_fields, update_tags=update_tags
        ),
        calls=calls,
    )


async def test_saving_uses_the_media_name_anki_gives_and_anki_tags():
    anki = _saving_anki({})
    collection = _draft_collection("", anki=anki)
    model = CARDS[0].model_copy(update={"tags": ["Machine Learning"]})
    card = StemCardData(model=model, media=StemMedia(image=b"png"))

    assert await collection.save_card(card) == 7

    [added] = anki.calls["add"]
    assert added["model_name"] == "AINote STEM Concept"
    assert added["tags"] == ["Machine_Learning", "AI-generated"]
    assert "src='renamed.png'" in added["fields"]["image"]


async def test_saving_again_after_the_front_changed_updates_the_same_note():
    anki = _saving_anki({"AINote STEM Concept|Entropy?": 5})
    collection = _draft_collection("", anki=anki)
    saved = StemCardData(model=CARDS[0], media=StemMedia())
    edited = StemCardData(
        model=CARDS[0].model_copy(update={"front": "Define entropy."}),
        media=StemMedia(),
    )

    assert await collection.save_card(edited, replaces=saved) == 5

    assert anki.calls["add"] == []
    [(note_id, fields)] = anki.calls["update"]
    assert (note_id, fields["front"]) == (5, "Define entropy.")


async def test_a_new_type_after_saving_makes_a_new_note():
    anki = _saving_anki({"AINote STEM Formula|Newton's law?": 5})
    collection = _draft_collection("", anki=anki)
    saved = StemCardData(model=CARDS[1], media=StemMedia())
    example = CARDS[3].model_copy(update={"front": "Newton's law?"})

    note_id = await collection.save_card(
        StemCardData(model=example, media=StemMedia()), replaces=saved
    )

    assert note_id == 7
    assert anki.calls["add"][0]["model_name"] == "AINote STEM Example"


def test_a_draft_collection_renders_its_selected_type():
    collection = _make_collection(card_type=CardType.PROCEDURE)

    [template] = collection.card_templates()

    assert collection.notetype_name == "AINote STEM Procedure"
    assert "badge-procedure" in template["Front"]
    assert "{{steps}}" in template["Back"]
    with pytest.raises(ValueError, match="No card type"):
        _ = _make_collection().notetype_name
