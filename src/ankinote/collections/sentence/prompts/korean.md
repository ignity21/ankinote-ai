# Korean Sentence Anki Card Generation
Return **only** valid JSON object, no markdown, no comments. The *input* you receive will be the **target-language Korean sentence**.

Write Korean in Hangul. Never add readings, hanja, or any `<...>` annotation inside Korean text.

```json
{
  "target_sentence": "The input Korean sentence (mirror back exactly as provided).",
  "native_sentence": "A faithful, natural translation of the input in the user's native language.",
  "notes": ["Short observations in the user's native language: speech level (해요체, 합쇼체, 반말), particles, conjugation, nuance, and any TOPIK3+ grammar pattern (e.g. -(으)ㄹ 수밖에 없다)."],
  "phrases": [{
    "phrase": "useful Korean phrase or collocation from the sentence, in dictionary form",
    "translation": "the phrase in user's native language",
    "example": "a simple Korean example sentence using the phrase, in 해요체"
  }]
}
```

## Field Rules
- `target_sentence` — mirror the Korean input back exactly as provided, spacing included. Do not correct colloquial or non-standard structures; explain them in `notes` instead.
- `native_sentence` — produce a faithful, natural translation of the input in the user's native language.
- `notes` — 0–3 short, worthy-of-attention observations in the user's native language only (can be empty `[]`). Always name the speech level when it matters for reuse.
- `phrases` — 0–3 useful expressions or collocations from the target sentence, each with a translation and a simple Korean example sentence (can be empty `[]`).

## General Guidelines
- Prefer contemporary, common usage; avoid archaic or overly formal expressions.
- Never return `null` for any field.
- Output **only** valid JSON — no markdown, no comments, no extra keys or text.
