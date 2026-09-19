# Japanese Vocabulary Anki Card Generation

Return only valid JSON. No markdown. No comments.

Goal: generate compact learning data for Anki cards optimized for recognition, recall, and spelling.

Furigana rule:
- Add hiragana readings to every kanji individually with `<Kanji:reading>`.
- Correct: `<招:まね>き<猫:ねこ>`
- Wrong: `<招き猫:まねきねこ>`

```json
[
  {
    "lemma": "string without furigana",
    "part_of_speech": "名詞|動詞|形容詞|形容動詞|副詞|助詞|接続詞|感動詞",
    "pronunciation": "hiragana or null",
    "difficulty": "N5|N4|N3|N2|N1",
    "morphology": "活用・読み分け・送り仮名の要点。なければ null",
    "core_meaning": {
      "target_text": "この品詞の短い日本語の説明。よく使う語義が複数あれば最大3つ、'; ' で区切る。近い同義語は '、' でまとめる。漢字には必ず <Kanji:reading> を付ける。",
      "native_text": "母語での短い訳。target_text と同じ順序・同じ数で '; ' で区切る。",
      "image_gloss": "この語義の短い英語での説明（画像生成専用。必ず英語で書く）。target_text と同じ順序・同じ数で '; ' で区切る。",
      "is_visualizable": true
    },
    "examples": [
      {
        "sentence": "例文。漢字には必ず <Kanji:reading> を付ける。",
        "translation": "母語訳",
        "highlights": ["語形またはコロケーション。漢字には必ず <Kanji:reading> を付ける。"]
      }
    ],
    "collocations": ["よく使う組み合わせ。漢字には必ず <Kanji:reading> を付ける。"],
    "confusions": ["似た語との違いを母語で短く説明。日语を使うなら漢字は必ず <Kanji:reading> を字ごとに付ける。"],
    "etymology_or_memory": "必要なら母語で記憶フック。主要な母語訳・意味アンカーを文中に明示する。不要なら null"
  }
]
```

Rules:
- Return 1 to 2 records total for the queried word. Keep only the most common and worth-learning parts of speech.
- `core_meaning` covers only the queried part of speech. Include its 1 to 3 most common senses, `target_text`, `native_text`, and `image_gloss` sense-aligned and all separated by '; '.
- `image_gloss` must always be written in English regardless of the target or native language, even if that duplicates `target_text`. It exists only to drive an image-generation model and should be a short, concrete, literal description of the sense (not the word itself).
- `examples` must contain 1 to 2 high-value examples tied to the core meaning.
- `collocations` must contain 2 to 4 common combinations when available.
- `confusions` may contain 0 to 2 short native-language contrasts or misuse warnings.
- Prefer the user's native language in `confusions`. If you use Japanese anywhere in `confusions`, every kanji must use per-character `<Kanji:reading>` annotation. Never group multiple kanji inside one annotation block.
- `etymology_or_memory`, when present, must be written in the user's native language and should explicitly mention the main native-language meaning anchor.
- Prioritize learner value over exhaustive dictionary coverage.
- Keep Japanese wording at or below the stated JLPT difficulty level.
