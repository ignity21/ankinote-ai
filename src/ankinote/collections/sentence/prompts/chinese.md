# Chinese Sentence Anki Card Generation
Generate **one** JSON object for the given target-language Chinese sentence.
Return **only** valid JSON, no markdown, no comments.

## Pinyin Format
Give every Chinese character its own `<字:pinyin>` block, pinyin lowercase with tone marks, never tone numbers.

e.g.
-- ✅ Correct: `<汉:hàn><字:zì>` (Each character has its own block)
-- ❌ WRONG: `<汉字:hànzì>` (Do NOT group characters)

- Neutral tone has no mark: `<东:dōng><西:xi>`.
- Polyphonic characters take the reading used in context: `<银:yín><行:háng>`, `<行:xíng><人:rén>`.
- Write citation tones; do not mark tone sandhi (一, 不, third tone).
- Never annotate punctuation, digits, or Latin letters.
- For a sentence in Traditional characters (`Chinese(Traditional)`), use Taiwan standard readings where they differ.

## Json Output
```json
{
  "target_sentence": "The input Chinese sentence, unchanged except for a <字:pinyin> block on every character.",
  "native_sentence": "A faithful, natural translation of the input in the user's native language.",
  "notes": ["short observations in user's native language. Cover nuance, register, common pitfalls, context, and any HSK4+ grammar points. Any Chinese quoted carries <字:pinyin>."],
  "phrases": [{
    "phrase": "useful Chinese phrase or collocation from the sentence, with <字:pinyin> on every character",
    "translation": "the phrase in user's native language",
    "example": "a simple Chinese example sentence using the phrase, with <字:pinyin> on every character"
  }]
}
```

## Field Rules
| Field | Constraint |
|---|---|
| `target_sentence` | Mirror the input exactly, in its own script (do not convert Simplified and Traditional), and annotate every character. Do not correct colloquial or non-standard structures; explain them in `notes` instead. |
| `native_sentence` | Produce a faithful, natural translation of the input in the user's native language. |
| `notes` | 0–3 items; useful observations about the target sentence in user's native language. |
| `phrases` | 0–3 entries; useful Chinese phrases or collocations from the target sentence, in the sentence's script, with translations and example sentences. |

## General Guidelines
- Native-language text is never annotated, even when the native language is Japanese.
- Prefer contemporary, common usage; avoid archaic or overly formal expressions.
- Never return `null` for any field.
