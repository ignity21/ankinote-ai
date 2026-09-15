# Phrase / Idiom Anki Card Generation

Return only valid JSON. No markdown. No comments.

Goal: generate compact learning data for Anki cards optimized for recognition and recall. No spelling or image cards.

```json
{
  "phrase": "string",
  "difficulty": "A1|A2|B1|B2|C1|C2",
  "core_meaning": {
    "target_text": "Target-language explanation of the phrase meaning.",
    "native_text": "Native-language translation of the core meaning."
  },
  "supporting_meanings": [
    {
      "target_text": "Target-language gloss for a secondary useful sense.",
      "native_text": "Native-language translation."
    }
  ],
  "examples": [
    {
      "sentence": "Natural target-language sentence containing the phrase.",
      "translation": "Native-language translation.",
      "highlights": ["exact surface form of the phrase as it appears in sentence"]
    }
  ],
  "usage_pattern": "Grammar pattern or usage context, e.g. 'verb + object', 'fixed expression', 'followed by gerund'. Omit if obvious.",
  "production_hint": "A short cue in the user's native language that helps recall the phrase without revealing it.",
  "confusions": ["Brief contrast with a similar phrase or common misuse, in user's native language."],
  "etymology_or_memory": "Optional memory hook or origin story in the user's native language. Mention the main native-language meaning. Or null.",
  "associations": ["Related or contrastive phrases, one per item"]
}
```

## Rules
- `level ≤ difficulty` means "Calibrate examples and notes to the phrase's CEFR level: use only vocabulary and grammar ≤ that difficulty"

| Field | Constraint |
|---|---|
| `core_meaning` | Exactly one primary sense. Keep it short and memorable. |
| `supporting_meanings` | 0–2 brief secondary sense summaries. Do not duplicate core meaning. |
| `examples` | 1–3 items; sentence must be `level ≤ difficulty`; `highlights` must match exact casing/inflection in `sentence` |
| `usage_pattern` | Provide for idioms, multi-word verbs, and fixed expressions. Use `null` for simple phrases. |
| `production_hint` | Must help recall the phrase but must not contain the phrase itself. |
| `confusions` | 0–2 items about near-synonyms, false friends, or common misuse. |
| `etymology_or_memory` | When present, written in user's native language, explicitly mentioning the main native-language meaning anchor. |
| `associations` | 0–5 items; near-synonyms, contrastive pairs, or common alternatives. |
- Prefer concise, learner-friendly wording over dictionary-style detail.
