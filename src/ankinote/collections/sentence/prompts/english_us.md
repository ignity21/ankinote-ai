# US English Sentence Anki Card Generation
Return **only** valid JSON object, no markdown, no comments. The *input* you receive will be the **target-language sentence**.

```json
{
  "target_sentence": "The input sentence in the target language (mirror back exactly as provided).",
  "native_sentence": "A faithful, natural translation of the input in the user's native language.",
  "notes": ["Optional important usage notes about the target sentence."],
  "phrases": [{
    "phrase": "useful target language phrase or collocation",
    "translation": "the phrase in user's native language",
    "example": "a simple example sentence in the target language"
  }]
}
```

## Field Rules
- `target_sentence` — mirror the target-language input back exactly as provided. Do not correct colloquial or non-standard structures; explain them in `notes` instead.
- `native_sentence` — produce a faithful, natural translation of the input in the user's native language.
- `notes` — short, worthy-of-attention observations in the user's native language only (can be empty `[]`). Cover nuance, register, common pitfalls, context, and any B1+ grammar points present in the target sentence.
- `phrases` — useful expressions or collocations extracted from the target sentence; each phrase is in the target language, with a translation and a simple example sentence in the target language (can be empty `[]`).

## General Guidelines
- Prefer contemporary, common usage; avoid archaic or overly formal expressions.
- Never return `null` for any field.
- Output **only** valid JSON — no markdown, no comments, no extra keys or text.
