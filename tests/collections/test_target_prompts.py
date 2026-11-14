"""Every target language has word, phrase and sentence prompts."""

from collections.abc import Callable

import pytest

from ankinote.collections.phrase.generator import (
    _load_prompt_template as phrase_prompt,
)
from ankinote.collections.sentence.generator import (
    _load_prompt_template as sentence_prompt,
)
from ankinote.collections.word.generator import _load_prompt_template as word_prompt
from ankinote.consts import (
    BETA_TARGET_LANGUAGES,
    RUBY_ANNOTATION_LANGUAGES,
    TARGET_LANGUAGES,
    Language,
)

LOADERS: dict[str, Callable[[Language], str]] = {
    "word": word_prompt,
    "phrase": phrase_prompt,
    "sentence": sentence_prompt,
}


def test_chinese_and_korean_are_targets() -> None:
    assert {Language.CHINESE_S, Language.CHINESE_T, Language.KOREAN} <= set(
        TARGET_LANGUAGES
    )
    assert BETA_TARGET_LANGUAGES <= set(TARGET_LANGUAGES)


@pytest.mark.parametrize("kind", LOADERS)
@pytest.mark.parametrize("target", TARGET_LANGUAGES)
def test_every_target_has_a_prompt(kind: str, target: Language) -> None:
    assert LOADERS[kind](target).strip()


@pytest.mark.parametrize("kind", LOADERS)
def test_both_chinese_scripts_share_one_prompt(kind: str) -> None:
    """The script to write in comes from the request, not the prompt file."""
    load = LOADERS[kind]
    assert load(Language.CHINESE_S) == load(Language.CHINESE_T)
    assert load(Language.CHINESE_S) != load(Language.JAPANESE)


@pytest.mark.parametrize("kind", LOADERS)
def test_chinese_prompts_annotate_each_character_with_pinyin(kind: str) -> None:
    assert "<汉:hàn><字:zì>" in LOADERS[kind](Language.CHINESE_S)


@pytest.mark.parametrize("kind", LOADERS)
def test_korean_prompts_use_topik_and_no_ruby(kind: str) -> None:
    prompt = LOADERS[kind](Language.KOREAN)
    assert "TOPIK" in prompt
    # Hangul is phonetic: cards show Korean as plain text, never as ruby.
    assert Language.KOREAN not in RUBY_ANNOTATION_LANGUAGES
