"""Tests for unified AI service usage across generators."""

from collections.abc import Sequence

import pytest

from ankinote.collections.math.generator import MathGenerator
from ankinote.collections.math.models import Example as MathExample
from ankinote.collections.math.models import MathModel
from ankinote.collections.phrase.generator import PhraseGenerator
from ankinote.collections.sentence.generator import SentenceGenerator
from ankinote.collections.stem.generator import StemGenerator
from ankinote.collections.word.generator import WordGenerator
from ankinote.consts import Language
from ankinote.services.ai import TextMessage


class FakeTextService:
    """Record text generation requests and return queued responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def generate_text(
        self,
        *,
        model_id: str,
        messages: Sequence[TextMessage],
        temperature: float,
    ) -> str:
        self.calls.append(
            {
                "model_id": model_id,
                "messages": messages,
                "temperature": temperature,
            }
        )
        return self._responses.pop(0)


class FakeImageService:
    """Record image prompts and return deterministic bytes."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate_image(self, *, prompt: str) -> bytes:
        self.calls.append(prompt)
        return b"image-bytes"


class FakeSpeechSynthesizer:
    """Minimal synth fake for generator construction."""

    async def synthesize(self, text: str) -> bytes:  # pragma: no cover
        return text.encode()


@pytest.mark.asyncio
async def test_word_generator_uses_unified_text_service():
    text_service = FakeTextService(
        [
            """
            [
              {
                "lemma": "test",
                "part_of_speech": "noun",
                "pronunciation": null,
                "difficulty": "A1",
                "morphology": "plural tests",
                "core_meaning": {
                  "target_text": "an exam or check",
                  "native_text": "测试",
                  "is_visualizable": false
                },
                "supporting_meanings": [],
                "examples": [{"sentence": "The test starts now.", "translation": "测试现在开始。", "highlights": ["test"]}],
                "collocations": ["take a test", "pass a test"],
                "confusions": [],
                "etymology_or_memory": null,
                "production_hint": "school check"
              }
            ]
            """
        ]
    )
    generator = WordGenerator(
        tts_service=FakeSpeechSynthesizer(),
        text_service=text_service,
        image_service=FakeImageService(),
        text_model_id="word-model",
    )

    models = await generator.generate_word_data(
        "test",
        Language.ENGLISH,
        Language.CHINESE_S,
    )

    assert models[0].lemma == "test"
    assert text_service.calls[0]["model_id"] == "word-model"
    messages = text_service.calls[0]["messages"]
    assert isinstance(messages, list)
    assert (
        "Goal: Create concise Anki cards optimized for recognition, recall, and spelling."
        in messages[1]["content"]
    )


@pytest.mark.asyncio
async def test_word_generator_accepts_fenced_json():
    text_service = FakeTextService(
        [
            """```json
            [
              {
                "lemma": "harvest",
                "part_of_speech": "noun",
                "pronunciation": "/ˈhɑːrvɪst/",
                "difficulty": "B1",
                "morphology": null,
                "core_meaning": {
                  "target_text": "the season of gathering crops",
                  "native_text": "收获季节",
                  "is_visualizable": true
                },
                "supporting_meanings": [],
                "examples": [{"sentence": "The harvest was early this year.", "translation": "今年收成很早。", "highlights": ["harvest"]}],
                "collocations": ["good harvest", "rice harvest"],
                "confusions": [],
                "etymology_or_memory": null,
                "production_hint": "time when farmers gather crops"
              }
            ]
            ```"""
        ]
    )
    generator = WordGenerator(
        tts_service=FakeSpeechSynthesizer(),
        text_service=text_service,
        image_service=FakeImageService(),
        text_model_id="word-model",
    )

    models = await generator.generate_word_data(
        "harvest",
        Language.ENGLISH,
        Language.CHINESE_S,
    )

    assert models[0].lemma == "harvest"


@pytest.mark.asyncio
async def test_phrase_generator_uses_unified_text_service():
    text_service = FakeTextService(
        [
            """
            {
              "phrase": "take off",
              "difficulty": "B1",
              "core_meaning": {"target_text": "to leave the ground", "native_text": "起飞"},
              "supporting_meanings": [],
              "examples": [{"sentence": "The plane takes off.", "translation": "飞机起飞。", "highlights": ["takes off"]}],
              "usage_pattern": "verb + particle",
              "production_hint": "飞机离开地面",
              "confusions": [],
              "etymology_or_memory": null,
              "associations": ["take off (remove)"]
            }
            """
        ]
    )
    generator = PhraseGenerator(
        tts_service=FakeSpeechSynthesizer(),
        text_service=text_service,
        text_model_id="phrase-model",
    )

    model = await generator.generate_phrase_data(
        "take off",
        Language.ENGLISH,
        Language.CHINESE_S,
    )

    assert model.phrase == "take off"
    assert text_service.calls[0]["model_id"] == "phrase-model"


@pytest.mark.asyncio
async def test_sentence_generator_uses_unified_text_service():
    text_service = FakeTextService(
        [
            """
            {
              "target_sentence": "This is a test.",
              "native_sentence": "这是一个测试。",
              "notes": [],
              "phrases": []
            }
            """
        ]
    )
    generator = SentenceGenerator(
        tts_service=FakeSpeechSynthesizer(),
        text_service=text_service,
        text_model_id="sentence-model",
    )

    model = await generator.generate_sentence_data(
        target_sentence="This is a test.",
        target_lang=Language.ENGLISH,
        native_lang=Language.CHINESE_S,
    )

    assert model.target_sentence == "This is a test."
    assert text_service.calls[0]["model_id"] == "sentence-model"
    assert (
        "Target sentence: This is a test."
        in text_service.calls[0]["messages"][1]["content"]
    )


@pytest.mark.asyncio
async def test_math_generator_uses_unified_services():
    text_service = FakeTextService(
        [
            """
            {
              "front": "What is a derivative?",
              "explanation": "A derivative measures rate of change.",
              "key_points": ["rate of change"],
              "examples": [{"problem": "f(x)=x^2", "solution": "f'(x)=2x", "is_visualizable": true}],
              "related_concepts": ["limits"],
              "difficulty": "intermediate",
              "tags": ["calculus"]
            }
            """
        ]
    )
    image_service = FakeImageService()
    generator = MathGenerator(
        text_service=text_service,
        image_service=image_service,
        text_model_id="math-model",
    )

    model = await generator.generate_math_data("What is a derivative?")
    media = await generator.generate_media(
        MathModel(
            front=model.front,
            explanation="Use a graph to visualize the tangent line.",
            key_points=model.key_points,
            examples=[
                MathExample(
                    problem="f(x)=x^2",
                    solution="Plot the parabola and tangent.",
                    is_visualizable=True,
                )
            ],
            related_concepts=model.related_concepts,
            difficulty=model.difficulty,
            tags=model.tags,
        )
    )

    assert model.front == "What is a derivative?"
    assert text_service.calls[0]["model_id"] == "math-model"
    assert media.explanation_images == [b"image-bytes"]
    assert media.example_images == {0: b"image-bytes"}
    assert len(image_service.calls) == 2


@pytest.mark.asyncio
async def test_stem_generator_uses_unified_text_service():
    text_service = FakeTextService(
        [
            """
            {
              "card_type": "concept",
              "front": "What is a vector space?",
              "back_brief": "A set closed under vector addition and scalar multiplication.",
              "back_detail": "It satisfies the vector space axioms over a field.",
              "tags": ["Math", "Linear Algebra"],
              "image_description": null
            }
            """
        ]
    )
    generator = StemGenerator(
        text_service=text_service,
        text_model_id="stem-model",
    )

    model = await generator.generate("vector space")

    assert model.card_type.value == "concept"
    assert model.tags == ["Math", "Linear Algebra"]
    assert model.image_description is None
    assert text_service.calls[0]["model_id"] == "stem-model"
