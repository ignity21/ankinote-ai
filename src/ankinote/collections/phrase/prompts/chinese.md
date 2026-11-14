# Chinese Phrase / Idiom Anki Card Generation

Return only valid JSON. No markdown. No comments.

Goal: generate compact learning data for Anki cards optimized for recognition and recall. No spelling or image cards.

## Script
Write every Chinese string in the script the target language names: Simplified characters for `Chinese(Simplified)`, Traditional characters for `Chinese(Traditional)`. If the queried phrase is in the other script, convert it. For `Chinese(Traditional)` prefer Taiwan Mandarin usage and readings.

## Pinyin Format
Give every Chinese character its own `<字:pinyin>` block, pinyin lowercase with tone marks, never tone numbers.

e.g.
-- ✅ Correct: `<汉:hàn><字:zì>` (Each character has its own block)
-- ❌ WRONG: `<汉字:hànzì>` (Do NOT group characters)
-- ✅ Correct: `<画:huà><蛇:shé><添:tiān><足:zú>`
-- ❌ WRONG: `<画蛇添足:huàshétiānzú>`

- Neutral tone has no mark: `<东:dōng><西:xi>`.
- Polyphonic characters take the reading used here: `<银:yín><行:háng>` vs `<行:xíng><人:rén>`.
- Write citation tones; do not mark tone sandhi (一, 不, third tone).
- Never annotate punctuation, digits, or Latin letters.

## JSON Output
```json
{
  "phrase": "the phrase in the target script, without pinyin (e.g. '画蛇添足')",
  "difficulty": "HSK1|HSK2|HSK3|HSK4|HSK5|HSK6|HSK7-9",
  "core_meaning": {
    "target_text": "Chinese explanation of the phrase meaning, with <字:pinyin> on every character.",
    "native_text": "Native-language translation of the core meaning."
  },
  "supporting_meanings": [
    {
      "target_text": "Short Chinese gloss for a secondary useful sense, with <字:pinyin> on every character.",
      "native_text": "Native-language translation."
    }
  ],
  "examples": [
    {
      "sentence": "Natural Chinese sentence containing the phrase, with <字:pinyin> on every character.",
      "translation": "Native-language translation.",
      "highlights": ["the phrase exactly as it appears in sentence, pinyin blocks included"]
    }
  ],
  "usage_pattern": "Short Chinese pattern with <字:pinyin>, e.g. '对……刮目相看', or the phrase's role (作谓语、作定语). Null for simple phrases.",
  "production_hint": "A short cue in the user's native language that helps recall the phrase without revealing it.",
  "confusions": ["Brief native-language contrast with a similar phrase or common misuse; any Chinese quoted carries <字:pinyin>."],
  "etymology_or_memory": "Optional origin story (e.g. the source of a 成语) or memory hook in the user's native language, mentioning the main native-language meaning; any Chinese quoted carries <字:pinyin>. Or null.",
  "associations": ["Related or contrastive Chinese phrases, one per item, with <字:pinyin> on every character"]
}
```

## Field Rules
- `level ≤ difficulty` means "Calibrate examples and notes to the phrase's HSK level: use only vocabulary and grammar ≤ that difficulty"

| Field | Constraint |
|---|---|
| `core_meaning` | Exactly one primary sense. Keep it short and memorable. |
| `supporting_meanings` | 0–2 brief secondary sense summaries. Do not duplicate core meaning. |
| `examples` | 1–3 items; sentence must be `level ≤ difficulty`; `highlights` must match `sentence` character for character, pinyin blocks included. |
| `usage_pattern` | Provide for 成语, 惯用语, and fixed frames. Use `null` for simple phrases. |
| `production_hint` | Must help recall the phrase but must not contain the phrase itself. |
| `confusions` | 0–2 items about near-synonyms, look-alike phrases, or common misuse. |
| `etymology_or_memory` | When present, written in user's native language, explicitly mentioning the main native-language meaning anchor. |
| `associations` | 0–5 items; near-synonyms, antonyms, or common alternatives. |
- Native-language text is never annotated, even when the native language is Japanese.
- Prefer concise, learner-friendly wording over dictionary-style detail.
