# Vocabulary Anki Card Generation

Return only valid JSON. No markdown. No comments.

Goal: generate compact learning data for Anki cards optimized for recognition, recall, and spelling.

```json
[
  {
    "lemma": "string",
    "part_of_speech": "noun|verb|adjective|adverb|other; use the standard part-of-speech category for the target language (e.g. include 'phrasal verb' only if the target language has genuine phrasal or separable verbs)",
    "pronunciation": "/IPA/ or null; use standard IPA for the target language",
    "difficulty": "A1|A2|B1|B2|C1|C2",
    "morphology": "Short morphology note such as plural, past tense, comparative, stress pattern, or null",
    "core_meaning": {
      "target_text": "Short target-language definition(s) for this part of speech. If the POS has several distinct common senses, give up to 3, separated by '; '. Join close synonyms of one sense with '、'.",
      "native_text": "Native-language translation(s), in the same order and count as target_text, separated by '; '.",
      "image_gloss": "Short English gloss(es) of this sense, used only for image generation. Same order and count as target_text, separated by '; '. Write in English even if it duplicates target_text (e.g. when the target language is already English).",
      "is_visualizable": true
    },
    "examples": [
      {
        "sentence": "One high-value target-language example sentence using the lemma or an inflected form.",
        "translation": "Native-language translation.",
        "highlights": ["useful collocation or inflected form"]
      }
    ],
    "collocations": ["high-frequency phrase", "another phrase"],
    "confusions": ["brief contrast with a similar word"],
    "etymology_or_memory": "Optional memory hook in the user's native language. Explicitly include the main native-language translation or meaning anchor, or null"
  }
]
```

Rules:
- Return 1 to 2 records total for the queried word. Keep only the most common and worth-learning parts of speech.
- `core_meaning` covers only the queried part of speech. Include its 1 to 3 most common senses, `target_text`, `native_text`, and `image_gloss` sense-aligned and all separated by '; '. Keep each sense short and memorable.
- `image_gloss` must always be written in English regardless of the target or native language. It exists only to drive an image-generation model and should be a short, concrete, literal description of the sense (not the word itself).
- `examples` must contain 1 to 2 high-value examples tied to the core meaning.
- `collocations` must contain 2 to 4 common combinations when available.
- `confusions` may contain 0 to 2 items about near-synonyms, false friends, or common misuse.
- `etymology_or_memory`, when present, must be written in the user's native language and should explicitly mention the main native-language meaning anchor.
- Prefer concise, learner-friendly wording over dictionary-style detail.
- Keep every target-language string at or below the stated difficulty level.
