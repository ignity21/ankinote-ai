# Chinese Vocabulary Anki Card Generation

Return only valid JSON. No markdown. No comments.

Goal: generate compact learning data for Anki cards optimized for recognition, recall, and spelling.

Script rule:
- Write every Chinese string in the script the target language names: Simplified characters for `Chinese(Simplified)`, Traditional characters for `Chinese(Traditional)`. If the queried word is in the other script, convert it.
- For `Chinese(Simplified)` use mainland Putonghua words and readings; for `Chinese(Traditional)` use Taiwan Mandarin words and readings (e.g. 計程車, 垃圾 lèsè).

Pinyin rule:
- Give every Chinese character its own `<字:pinyin>` block, pinyin lowercase with tone marks (ā á ǎ à, ǖ ǘ ǚ ǜ), never tone numbers.
- Correct: `<汉:hàn><字:zì>`
- Wrong: `<汉字:hànzì>`, `<汉:han4><字:zi4>`
- Neutral tone has no mark: `<东:dōng><西:xi>` (thing).
- Polyphonic characters take the reading used in this word: `<银:yín><行:háng>`.
- Write citation tones; do not mark tone sandhi: `<你:nǐ><好:hǎo>`, `<一:yī><样:yàng>`, `<不:bù><是:shì>`.
- Erhua: `<一:yī><点:diǎn><儿:r>`.
- Never annotate punctuation, digits, or Latin letters.

```json
[
  {
    "lemma": "the word in the target script, without pinyin",
    "part_of_speech": "名词|动词|形容词|副词|量词|代词|数词|介词|连词|助词|叹词 (in the target script, e.g. 名詞 for Traditional)",
    "pronunciation": "pinyin of the whole word with tone marks, syllables joined as in a dictionary (e.g. 'xuéxí', 'xī'ān')",
    "difficulty": "HSK1|HSK2|HSK3|HSK4|HSK5|HSK6|HSK7-9",
    "morphology": "Short Chinese note on the measure word a noun takes, separable-verb use (见了一次面), or reduplication, with <字:pinyin> on every character; or null",
    "core_meaning": {
      "target_text": "Short Chinese definition(s) for this part of speech, with <字:pinyin> on every character. If the POS has several distinct common senses, give up to 3, separated by '; '. Join close synonyms of one sense with '、'.",
      "native_text": "Native-language translation(s), in the same order and count as target_text, separated by '; '.",
      "is_visualizable": true,
      "image_prompt": "One English sentence describing a concrete scene that depicts the most common sense, or null"
    },
    "examples": [
      {
        "sentence": "One high-value Chinese example sentence using the word, with <字:pinyin> on every character.",
        "translation": "Native-language translation.",
        "highlights": ["collocation or pattern exactly as it appears in sentence, with <字:pinyin> on every character"]
      }
    ],
    "collocations": ["high-frequency combination with <字:pinyin> on every character"],
    "confusions": ["brief native-language contrast with a similar word; any Chinese quoted carries <字:pinyin>"],
    "etymology_or_memory": "Optional memory hook in the user's native language, e.g. the characters' parts or meanings. Explicitly include the main native-language meaning anchor. Any Chinese quoted carries <字:pinyin>. Or null"
  }
]
```

Rules:
- Return 1 to 2 records total for the queried word. Keep only the most common and worth-learning parts of speech.
- `core_meaning` covers only the queried part of speech. Include its 1 to 3 most common senses, `target_text` and `native_text` sense-aligned and separated by '; '. Keep each sense short and memorable.
- Every Chinese character in `core_meaning.target_text`, `morphology`, `examples[].sentence`, `examples[].highlights`, and `collocations`, and every Chinese word quoted in `confusions` and `etymology_or_memory`, carries its own `<字:pinyin>` block. Native-language text is never annotated, even when the native language is Japanese.
- `highlights` must match the annotated text in `sentence` character for character, including the pinyin blocks.
- `is_visualizable` is true only when the single most common sense can be recognized from a picture alone: a concrete object, creature, place, physical action, or visible state (e.g. umbrella, climb, crowded, exhausted). Set it to false for abstract, evaluative, grammatical, or function words, for senses that only make sense with words or numbers, and for slurs or offensive senses.
- `image_prompt` is an English scene description for a text-to-image model, written in English regardless of the target or native language, or null when `is_visualizable` is false. Depict only the single most common sense. Write one sentence of at most 30 words naming the main subject, what it is doing, and minimal setting, e.g. "A tired man slumped on a sofa, eyes half closed, yawning". For adjectives and verbs, show a person, animal, or object that clearly displays the quality or action.
- `image_prompt` must describe only what is visible. Never include the lemma, its translation, quotation marks, or style words. Avoid anything that usually carries writing, such as signs, books, screens, documents, labels, packaging, or banners, since the image model will fill them with garbled text.
- `examples` must contain 1 to 2 high-value examples tied to the core meaning.
- `collocations` must contain 2 to 4 common combinations when available; for nouns, include the usual measure word (e.g. 一本书).
- `confusions` may contain 0 to 2 items about near-synonyms, easily confused characters, or common misuse. Mention a mainland/Taiwan usage difference only when a learner would meet it.
- `etymology_or_memory`, when present, must be written in the user's native language and should explicitly mention the main native-language meaning anchor.
- Prefer concise, learner-friendly wording over dictionary-style detail.
- Keep every Chinese string at or below the stated HSK level.
