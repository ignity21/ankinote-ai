"""Tests for generator audio integration through the narrow TTS protocol."""

import pytest

from ankinote.collections.common import MediaGap
from ankinote.collections.phrase.generator import PhraseGenerator
from ankinote.collections.phrase.models import Example as PhraseExample
from ankinote.collections.phrase.models import PhraseModel
from ankinote.collections.sentence.generator import SentenceGenerator
from ankinote.collections.sentence.models import SentenceModel
from ankinote.collections.word.generator import WordGenerator
from ankinote.collections.word.models import Example as WordExample
from ankinote.collections.word.models import Sense, WordModel
from ankinote.consts import Language


class FakeTextService:
    """Unused in these tests; present to satisfy generator wiring."""

    async def generate_text(self, **kwargs) -> str:  # pragma: no cover
        raise AssertionError("Text generation should not be used in media-only tests")


class FakeImageService:
    """Deterministic fake used to verify optional image generation."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate_image(self, *, prompt: str) -> bytes:
        self.calls.append(prompt)
        return f"image:{len(self.calls)}".encode()


class FakeSpeechSynthesizer:
    """Deterministic fake used to verify generator interactions."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.calls.append(text)
        return f"audio:{text}".encode()


class TestWordGenerator:
    """Media generation tests for word cards."""

    @pytest.mark.asyncio
    async def test_generate_media_uses_speech_protocol(self):
        synth = FakeSpeechSynthesizer()
        generator = WordGenerator(
            tts_service=synth,
            text_service=FakeTextService(),
            image_service=FakeImageService(),
            text_model="text-model",
        )
        word_model = WordModel(
            lemma="test",
            part_of_speech="noun",
            pronunciation=None,
            difficulty="A1",
            morphology="plural tests",
            core_meaning=Sense(
                target_text="an exam or check",
                native_text="测试",
                is_visualizable=False,
            ),
            examples=[
                WordExample(
                    sentence="a test example",
                    translation="例句",
                    highlights=[],
                )
            ],
            collocations=["take a test"],
            confusions=[],
            etymology_or_memory=None,
        )

        media = await generator.generate_media(word_model, Language.ENGLISH)

        assert media.headword_audio == b"audio:test"
        assert media.example_audios == [b"audio:a test example"]
        assert synth.calls == ["test", "a test example"]

    @pytest.mark.asyncio
    async def test_generate_media_sends_scene_prompt_without_lemma(self):
        images = FakeImageService()
        generator = WordGenerator(
            tts_service=FakeSpeechSynthesizer(),
            text_service=FakeTextService(),
            image_service=images,
            text_model="text-model",
        )
        word_model = WordModel(
            lemma="umbrella",
            part_of_speech="noun",
            difficulty="A2",
            core_meaning=Sense(
                target_text="a folding canopy that keeps off rain",
                native_text="伞",
                image_prompt="A man holding an open blue umbrella in the rain",
                is_visualizable=True,
            ),
            examples=[WordExample(sentence="Take an umbrella.", translation="带伞。")],
        )

        media = await generator.generate_media(word_model, Language.ENGLISH)

        assert media.images == {0: b"image:1"}
        assert len(images.calls) == 1
        assert "A man holding an open blue umbrella in the rain" in images.calls[0]
        assert "Lemma" not in images.calls[0]

    @pytest.mark.asyncio
    async def test_generate_media_skips_image_without_scene_prompt(self):
        images = FakeImageService()
        generator = WordGenerator(
            tts_service=FakeSpeechSynthesizer(),
            text_service=FakeTextService(),
            image_service=images,
            text_model="text-model",
        )
        word_model = WordModel(
            lemma="retarded",
            part_of_speech="adjective",
            difficulty="B2",
            core_meaning=Sense(
                target_text="slow in development",
                native_text="发展迟缓的",
                is_visualizable=True,
            ),
            examples=[
                WordExample(sentence="Growth was retarded.", translation="生长受阻。")
            ],
        )

        media = await generator.generate_media(word_model, Language.ENGLISH)

        assert media.images == {}
        assert images.calls == []

    @pytest.mark.asyncio
    async def test_no_speech_service_makes_a_card_without_audio(self):
        generator = WordGenerator(
            tts_service=None,
            text_service=FakeTextService(),
            image_service=None,
            text_model="text-model",
        )

        media = await generator.generate_media(_umbrella(), Language.ENGLISH)

        assert media.headword_audio is None
        assert media.example_audios == []
        assert media.gaps == [MediaGap("audio", "not_set_up")]

    @pytest.mark.asyncio
    async def test_failing_speech_drops_all_audio_and_says_why(self):
        generator = WordGenerator(
            tts_service=FailingSpeechSynthesizer(fail_on="Take an umbrella."),
            text_service=FakeTextService(),
            image_service=FakeImageService(),
            text_model="text-model",
        )

        media = await generator.generate_media(_umbrella(), Language.ENGLISH)

        # Half the audio would leave example buttons pointing at nothing.
        assert media.headword_audio is None
        assert media.example_audios == []
        assert media.gaps == [MediaGap("audio", "failed", "quota exceeded")]
        assert media.images == {0: b"image:1"}

    @pytest.mark.asyncio
    async def test_failing_image_keeps_the_card_and_says_why(self):
        generator = WordGenerator(
            tts_service=FakeSpeechSynthesizer(),
            text_service=FakeTextService(),
            image_service=FailingImageService(),
            text_model="text-model",
        )

        media = await generator.generate_media(_umbrella(), Language.ENGLISH)

        assert media.images == {}
        assert media.headword_audio == b"audio:umbrella"
        assert media.gaps == [MediaGap("image", "failed", "billing required")]


class FailingSpeechSynthesizer:
    def __init__(self, fail_on: str) -> None:
        self._fail_on = fail_on

    async def synthesize(self, text: str) -> bytes:
        if text == self._fail_on:
            raise RuntimeError("quota exceeded")
        return f"audio:{text}".encode()


class FailingImageService:
    async def generate_image(self, *, prompt: str) -> bytes:
        raise RuntimeError("billing required")


def _umbrella() -> WordModel:
    return WordModel(
        lemma="umbrella",
        part_of_speech="noun",
        difficulty="A2",
        core_meaning=Sense(
            target_text="a folding canopy that keeps off rain",
            native_text="伞",
            image_prompt="A man holding an open blue umbrella in the rain",
            is_visualizable=True,
        ),
        examples=[WordExample(sentence="Take an umbrella.", translation="带伞。")],
    )


class TestPhraseGenerator:
    """Media generation tests for phrase cards."""

    @pytest.mark.asyncio
    async def test_generate_media_uses_speech_protocol(self):
        synth = FakeSpeechSynthesizer()
        generator = PhraseGenerator(
            tts_service=synth,
            text_service=FakeTextService(),
            text_model="text-model",
        )
        phrase_model = PhraseModel(
            phrase="take off",
            difficulty="B1",
            core_meaning={"target_text": "to leave the ground", "native_text": "起飞"},
            supporting_meanings=[],
            examples=[
                PhraseExample(
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

        media = await generator.generate_media(phrase_model, Language.ENGLISH)

        assert media.phrase_audio == b"audio:take off"
        assert media.example_audios == [b"audio:The plane takes off."]
        assert synth.calls == ["take off", "The plane takes off."]


class TestSentenceGenerator:
    """Media generation tests for sentence cards."""

    @pytest.mark.asyncio
    async def test_generate_media_uses_speech_protocol(self):
        synth = FakeSpeechSynthesizer()
        generator = SentenceGenerator(
            tts_service=synth,
            text_service=FakeTextService(),
            text_model="text-model",
        )
        sentence_model = SentenceModel(
            target_sentence="This is a test.",
            native_sentence="这是一个测试。",
        )

        media = await generator.generate_media(sentence_model, Language.ENGLISH)

        assert media.sentence_audio == b"audio:This is a test."
        assert synth.calls == ["This is a test."]
