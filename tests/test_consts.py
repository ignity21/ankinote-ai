"""Language choices and pair rules."""

import pytest

from ankinote.consts import (
    NATIVE_LANGUAGES,
    TARGET_LANGUAGES,
    Language,
    language_pair_error,
)


def test_every_real_language_can_be_native() -> None:
    assert Language.OTHER not in NATIVE_LANGUAGES
    assert set(NATIVE_LANGUAGES) == set(Language) - {Language.OTHER}


@pytest.mark.parametrize("target", TARGET_LANGUAGES)
def test_any_other_native_pairs_with_a_target(target: Language) -> None:
    chinese = {Language.CHINESE_S, Language.CHINESE_T}
    for native in NATIVE_LANGUAGES:
        if native != target and {native, target} != chinese:
            assert language_pair_error(native, target) is None


@pytest.mark.parametrize(
    ("native", "target", "code"),
    [
        (Language.ENGLISH, Language.ENGLISH, "same_language"),
        # Simplified and Traditional are distinct natives but one language.
        (Language.CHINESE_T, Language.CHINESE_S, "same_language"),
        (Language.CHINESE_S, Language.CHINESE_T, "same_language"),
        (Language.OTHER, Language.ENGLISH, "not_native"),
        (Language.ENGLISH, Language.OTHER, "not_target"),
    ],
)
def test_invalid_pairs(native: Language, target: Language, code: str) -> None:
    assert language_pair_error(native, target) == code
