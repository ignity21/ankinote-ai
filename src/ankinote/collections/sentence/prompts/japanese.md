# Japanese Sentence Anki Card Generation
Generate **one** JSON object for the given target-language Japanese sentence.
Return **only** valid JSON, no markdown, no comments.

## Furigana Format
Add hiragana readings to each kanji individually using the format `<Kanji:reading>`.

e.g.
-- ✅ Correct: `<商:しょう><売:ばい><繁:はん><盛:じょう>` (Each kanji has its own block)
-- ❌ WRONG: `<商売繁盛:しょうばいはんじょう>` (Do NOT group kanji)

-- ✅ Correct: `<縁:えん><起:ぎ><物:もの>`
-- ❌ WRONG: `<縁起物:えんぎもの>` (Do NOT group kanji)

## Json Output
```json
{
  "target_sentence": "The input Japanese sentence, with <Kanji:reading> annotations added where needed.",
  "native_sentence": "A faithful, natural translation of the input in the user's native language.",
  "notes": ["short observations in user's native language. Cover nuance, register, common pitfalls, context, and any JLPT N3+ grammar points. All in native language."],
  "phrases": [{
    "phrase": "useful Japanese phrase or collocation with <Kanji:reading>",
    "translation": "the phrase in user's native language",
    "example": "a simple example sentence in Japanese using the phrase, with <Kanji:reading>"
  }]
}
```
## Field Rules
| Field | Constraint |
|---|---|
| `target_sentence` | mirror the input Japanese sentence and apply furigana annotations to all kanji. Do not correct colloquial or non-standard structures; explain them in `notes` instead. |
| `native_sentence` | produce a faithful, natural translation of the input in the user's native language. |
| `notes` | 0–3 items; useful observations about the target sentence in user's native language. |
| `phrases` | 0–3 entries; useful Japanese phrases or collocations from the target sentence, with translations and example sentences. |
