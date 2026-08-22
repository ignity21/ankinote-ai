# Future Plans

## 0. Card-generation GUI roadmap

### Current baseline

The word-card generator is the only collection exposed through the NiceGUI
application today. The phrase and sentence collection implementations already
exist under `src/ankinote/collections/`, including prompts, text generation,
TTS, Anki note types/templates, CLI commands, batch commands, and collection
tests. The next milestone is therefore primarily an integration and
consistency effort, rather than a second implementation of those collections.

### Product and design direction

- **Audience:** language learners who capture vocabulary, reusable expressions,
  and production sentences while studying.
- **Page job:** turn one or many learner-provided items into Anki notes while
  making the item type and batch progress unambiguous.
- **Information architecture:** treat Word, Phrase & Idiom, and Sentence as
  three distinct learning lanes in the shared navigation. Each lane keeps the
  same familiar generate flow, but uses labels and examples appropriate to the
  item it accepts.
- **Visual direction:** preserve the existing app shell and settings workflow;
  add a compact card-type marker (word / expression / sentence) next to each
  page title and in results. This is the single signature device: it gives a
  batch containing similar-looking text a visible learning purpose without
  introducing decorative UI.
- **Accessibility and motion:** all controls retain visible keyboard focus;
  per-item status must be understandable without colour; loading state is
  textual and respects reduced-motion preferences.

The first design pass deliberately does **not** introduce a generic dashboard,
large hero, or a separate visual theme per card type: those would make a small,
task-focused tool harder to scan and would diverge from the established Word
flow. The distinction is carried by the learner's chosen card type, its input
copy, and the result marker instead.

### Phase 1 — Phrase and idiom collection audit and contract lock

The repository already models phrases and idioms together in `PhraseCollection`
and `PhraseModel`; retain that single collection unless a later requirement
needs materially different card behaviour for idioms.

1. Compare phrase collection behaviour against the Word collection contract:
   Anki note-type upsert, deck creation, update identity, media naming,
   language/ruby conversion, tags, prompt loading, and error propagation.
2. Confirm the learning-card contract for expressions: recognition and recall
   templates, core/supporting meanings, examples and audio, usage pattern,
   production hint, confusions, and memory associations. Make only targeted
   model/template/prompt changes where the audit finds a learner-facing gap.
3. Add or amend focused tests for every changed contract, including English and
   Japanese rendering where applicable. Keep the public CLI `phrase add` and
   `phrase batch` behaviour compatible.

**Done when:** `PhraseCollection.generate_and_add_note()` is ready to be used
by the GUI with the same lifecycle guarantees as words, and all focused phrase
tests pass.

### Phase 2 — Shared GUI batch-generation foundation

Before adding a second copy of `word_page`, extract only the page-level pieces
that are truly shared:

1. A typed page/workflow configuration for labels, examples, collection
   construction, accepted input, and optional controls (such as Word's image
   switch).
2. Common input normalization: combine the single input and one-item-per-line
   batch input, trim blank lines, preserve source order, and reject an empty
   submission with a useful message.
3. Common bounded-concurrency runner: create one shared Anki collection context
   per submission, use the selected parallelism, preserve result order while
   reporting completion as tasks finish, and isolate failures to their item.
4. A reusable, accessible result row with pending, success, and failure states;
   the final summary reports succeeded and failed counts.
5. Keep Word behaviour unchanged while migrating it onto the shared foundation;
   add unit tests around normalization and runner-result mapping so future card
   types do not fork this logic again.

**Done when:** Word generation has unchanged user-visible behaviour and its
batch workflow is reusable without knowing Word-specific details.

### Phase 3 — Phrase & Idiom GUI

1. Add a `/phrases` page and navigation entry, labelled **Phrase & Idiom Cards**.
2. Use an expression-specific single input and one-expression-per-line batch
   input. Examples should make clear that multi-word expressions are valid,
   such as `look forward to` and `once in a blue moon`.
3. Reuse the shared language selectors, provider/settings loading, parallelism
   control, cancellation-safe loading state, and per-item status rows.
4. Construct `PhraseCollection` with the current native/target languages and
   configured text model/service. Do not show Word's image-generation control:
   the existing phrase card contract generates text and audio only.
5. Verify with mocked UI/workflow tests plus a manual smoke test against a
   running AnkiConnect instance when credentials are available.

**Done when:** a learner can submit one or many phrases/idioms from the GUI,
receive independent per-item outcomes, and find generated notes in
`AINote::Phrases`.

### Phase 4 — Sentence GUI

Sentence cards use the same batch workflow, but their input contract differs:
the learner enters sentences in the **target language** and the model creates
the native-language prompt and learning notes for a production card.

1. Add `/sentences` and the corresponding navigation entry.
2. Use precise copy: “Target-language sentence” and “One target-language
   sentence per line”, with an example matching the selected/default language.
3. Build `SentenceCollection` through the same configured service path and
   reuse the shared status and batch-runner components unchanged.
4. Add coverage for sentence-specific validation and ensure the GUI consistently
   presents the input as target-language text.

**Done when:** one or many target-language sentences generate independently and
appear as production cards in `AINote::Sentences`.

### Phase 5 — Final integration and documentation

1. Run focused collection and UI tests, then the full test suite, formatting,
   linting, and static checks.
2. Update README screenshots/instructions and the GUI navigation description;
   document that expression and sentence workflows require the same AnkiConnect
   and provider configuration as Word cards.
3. Perform a manual three-lane smoke test (one Word, one Phrase/Idiom, one
   Sentence) with AnkiConnect, checking deck creation, note updates, audio,
   batch partial failure, and language direction.
4. Inspect the final diff to ensure no provider key, Anki collection data, or
   unrelated worktree change is included.

### Delivery order and dependencies

```
Phrase contract audit
        │
        ▼
Shared GUI batch foundation ──► Word regression coverage
        │
        ├────────► Phrase & Idiom GUI
        │
        └────────► Sentence GUI
                    │
                    ▼
           End-to-end verification + documentation
```

Phrase and Sentence GUI work can be implemented in close succession after the
shared foundation, but should not each copy the current Word page. A separate
“idiom collection” is intentionally not planned: phrases and idioms share the
same current generation and card contract, and a separate type would add Anki
migration and UI complexity without a stated learning benefit.

## 1. CLI reference (completed)

A reference file (`skills/ankinote-cli/SKILL.md`) documents the full `ankinote` CLI surface.
Any agent or human working in this repo can use it to understand how to operate
cards directly.

## 2. CLI Review

### Duplicated batch logic
The `batch` command in `word`, `phrase`, `sentence`, and `stem` share the same
pattern (RPM limiting, concurrency control, file reading). Extract a shared
`batch` decorator or mixin.

### Dead code
`src/ankinote/cli/math.py` and `src/ankinote/collections/math/` are no longer
registered in the CLI but still in the tree. Decide whether to keep or remove.

## 3. PyPI Release

### Prerequisites
- Dependencies: litellm, google-cloud-texttospeech, httpx, pydantic, etc.
  Install experience needs to be smooth.
- API key docs: GEMINI_API_KEY, GOOGLE_TTS_KEY, ANKI_CONNECT_URL
- AnkiConnect is an external dependency — users need to install the Anki addon
  separately.
- CLI and docs should be in English if targeting international users.

### Considerations
- Project is already structured with pyproject.toml, CLI entrypoint, version
- Public release means maintaining backward compatibility
- Consider a `--dry-run` mode that generates cards without pushing to Anki
