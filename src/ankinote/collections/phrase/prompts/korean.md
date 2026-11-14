# Korean Phrase / Idiom Anki Card Generation

Return only valid JSON. No markdown. No comments.

Goal: generate compact learning data for Anki cards optimized for recognition and recall. No spelling or image cards.

Write Korean in Hangul with standard spacing (띄어쓰기). Never add readings, hanja, or any `<...>` annotation inside Korean text. Hanja for a 사자성어 or Sino-Korean word belong only in `etymology_or_memory`.

```json
{
  "phrase": "the phrase in Hangul, in its dictionary form (e.g. '발이 넓다')",
  "difficulty": "TOPIK1|TOPIK2|TOPIK3|TOPIK4|TOPIK5|TOPIK6",
  "core_meaning": {
    "target_text": "Korean explanation of the phrase meaning.",
    "native_text": "Native-language translation of the core meaning."
  },
  "supporting_meanings": [
    {
      "target_text": "Korean gloss for a secondary useful sense.",
      "native_text": "Native-language translation."
    }
  ],
  "examples": [
    {
      "sentence": "Natural Korean sentence containing the phrase, in 해요체 unless the phrase belongs to another register.",
      "translation": "Native-language translation.",
      "highlights": ["the phrase exactly as conjugated in sentence"]
    }
  ],
  "usage_pattern": "Short Korean pattern, e.g. 'N이/가 발이 넓다', or the register it belongs to. Null for simple phrases.",
  "production_hint": "A short cue in the user's native language that helps recall the phrase without revealing it.",
  "confusions": ["Brief contrast with a similar phrase or common misuse, in user's native language."],
  "etymology_or_memory": "Optional origin or memory hook in the user's native language, mentioning the main native-language meaning. For a 사자성어, start with its hanja, e.g. '일석이조 (一石二鳥)'. Or null.",
  "associations": ["Related or contrastive Korean phrases, one per item"]
}
```

## Rules
- `level ≤ difficulty` means "Calibrate examples and notes to the phrase's TOPIK level: use only vocabulary and grammar ≤ that difficulty"

| Field | Constraint |
|---|---|
| `core_meaning` | Exactly one primary sense. Keep it short and memorable. |
| `supporting_meanings` | 0–2 brief secondary sense summaries. Do not duplicate core meaning. |
| `examples` | 1–3 items; sentence must be `level ≤ difficulty`; `highlights` must match the conjugated form and particles in `sentence` exactly. |
| `usage_pattern` | Provide for 관용구, 속담, 사자성어, and fixed frames. Use `null` for simple phrases. |
| `production_hint` | Must help recall the phrase but must not contain the phrase itself. |
| `confusions` | 0–2 items about near-synonyms, look-alike phrases, or common misuse. |
| `etymology_or_memory` | When present, written in user's native language, explicitly mentioning the main native-language meaning anchor. |
| `associations` | 0–5 items; near-synonyms, antonyms, or common alternatives. |
- Prefer concise, learner-friendly wording over dictionary-style detail.
