# Korean Vocabulary Anki Card Generation

Return only valid JSON. No markdown. No comments.

Goal: generate compact learning data for Anki cards optimized for recognition, recall, and spelling.

Writing rule:
- Write Korean in Hangul with standard spacing (띄어쓰기). Never add readings, hanja, or any `<...>` annotation inside Korean text: Hangul is read as written.
- Hanja for Sino-Korean words (한자어) belong only in `etymology_or_memory`.

```json
[
  {
    "lemma": "dictionary form in Hangul (verbs and adjectives end in -다)",
    "part_of_speech": "명사|동사|형용사|부사|대명사|수사|관형사|조사|감탄사|의존 명사",
    "pronunciation": "Revised Romanization of the spoken form, preceded by the standard pronunciation in Hangul brackets when sound changes make it differ from the spelling, e.g. 'dal' for 달, '[궁물] gungmul' for 국물, '[익따] ikda' for 읽다",
    "difficulty": "TOPIK1|TOPIK2|TOPIK3|TOPIK4|TOPIK5|TOPIK6",
    "morphology": "Short Korean note: for verbs and adjectives the polite present and past (읽어요, 읽었어요) and the irregular class if any (ㅂ 불규칙); for nouns the usual counter if notable; or null",
    "core_meaning": {
      "target_text": "Short Korean definition(s) for this part of speech. If the POS has several distinct common senses, give up to 3, separated by '; '. Join close synonyms of one sense with '、'.",
      "native_text": "Native-language translation(s), in the same order and count as target_text, separated by '; '.",
      "is_visualizable": true,
      "image_prompt": "One English sentence describing a concrete scene that depicts the most common sense, or null"
    },
    "examples": [
      {
        "sentence": "One high-value Korean example sentence using the word, in 해요체 unless the word belongs to another register.",
        "translation": "Native-language translation.",
        "highlights": ["the conjugated form or collocation exactly as it appears in sentence"]
      }
    ],
    "collocations": ["high-frequency combination with its particle, e.g. 책을 읽다"],
    "confusions": ["brief native-language contrast with a similar word or common misuse"],
    "etymology_or_memory": "Optional memory hook in the user's native language. For a Sino-Korean word, start with its hanja and each syllable's meaning, e.g. '學校 (학교): 學 learn + 校 school'. Explicitly include the main native-language meaning anchor. Or null"
  }
]
```

Rules:
- Return 1 to 2 records total for the queried word. Keep only the most common and worth-learning parts of speech.
- `core_meaning` covers only the queried part of speech. Include its 1 to 3 most common senses, `target_text` and `native_text` sense-aligned and separated by '; '. Keep each sense short and memorable.
- `highlights` must match the text in `sentence` exactly, including particles and endings as conjugated there.
- `is_visualizable` is true only when the single most common sense can be recognized from a picture alone: a concrete object, creature, place, physical action, or visible state (e.g. umbrella, climb, crowded, exhausted). Set it to false for abstract, evaluative, grammatical, or function words, for senses that only make sense with words or numbers, and for slurs or offensive senses.
- `image_prompt` is an English scene description for a text-to-image model, written in English regardless of the target or native language, or null when `is_visualizable` is false. Depict only the single most common sense. Write one sentence of at most 30 words naming the main subject, what it is doing, and minimal setting, e.g. "A tired man slumped on a sofa, eyes half closed, yawning". For adjectives and verbs, show a person, animal, or object that clearly displays the quality or action.
- `image_prompt` must describe only what is visible. Never include the lemma, its translation, quotation marks, or style words. Avoid anything that usually carries writing, such as signs, books, screens, documents, labels, packaging, or banners, since the image model will fill them with garbled text.
- `examples` must contain 1 to 2 high-value examples tied to the core meaning.
- `collocations` must contain 2 to 4 common combinations when available, each with the particle it usually takes.
- `confusions` may contain 0 to 2 items about near-synonyms, native-Korean vs Sino-Korean pairs, or common misuse.
- `etymology_or_memory`, when present, must be written in the user's native language and should explicitly mention the main native-language meaning anchor.
- Prefer concise, learner-friendly wording over dictionary-style detail.
- Keep every Korean string at or below the stated TOPIK level.
