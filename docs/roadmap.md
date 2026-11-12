# Roadmap

Unscheduled product directions. Nothing here is a commitment to a date,
framework, or API.

## STEM architecture (shipped)

The unified STEM schema has been replaced by four independent generation models,
prompts, field sets, and Anki note types:

- `AINote STEM Concept`: front, brief answer, detailed explanation, image.
- `AINote STEM Formula`: front, formula, meaning, variables, conditions, derivation, image.
- `AINote STEM Procedure`: front, summary, steps, conditions, image.
- `AINote STEM Example`: front, answer, solution steps, explanation, image.

All use `front` as the first field (Anki's default sort field), native Anki
tags, and the shared `AINote::STEM` deck and paper-card visual theme.
Structured variable/step lists render into their own storage fields.
There is no stored `card_type` field and no V2 suffix.

The common STEM entrypoint accepts automatic classification or an explicit type.
Automatic mode classifies first and then loads the selected type's prompt/schema;
explicit selection skips classification. All four GUI flows offer editable
previews before saving. Reference-image input and optional generated diagrams
remain available. Upserts are scoped by note type as well as front and deck.

The legacy `AINote STEM` is no longer created or updated. Existing legacy notes
are left alone; there is no automatic migration or deletion.

## Comparison card type (next)

Add `AINote STEM Comparison` with its own model, prompt, field set, and templates.
Contrast pairs such as L1 vs L2 regularization, bias vs variance, or TCP vs UDP.

- Structured `items` (name + definition) and `aspects` (aspect + per-item values).
- Render an aspect-by-aspect table, stacking vertically on narrow screens.
- Register the type in classification, CLI selection, and GUI management/preview.
- Reuse shared styling with `--badge-comparison-*` tokens.

## Progressive disclosure and rendering polish

- Allow detailed explanations/derivations to expand on demand. Verify
  `<details>` on Anki desktop and AnkiDroid before shipping; keep a visible
  fallback where unsupported.
- Shared MathJax macro configuration for common notation.
- Optional `common_mistakes` callout where appropriate, added to the relevant
  type's schema and template rather than a new card type.

Comparison is the next feature; rendering polish can be delivered independently.

## Thinking control (shipped; follow-ups)

`TextGenerationService.generate_text` now takes `reasoning_effort`. The language
generators (`word`, `phrase`, `sentence`) pass `DISABLE_REASONING`, which the
service turns into DeepSeek's OpenAI-format `extra_body={"thinking": {"type":
"disabled"}}` (DeepSeek enables thinking by default and its LiteLLM routing
discards a plain `reasoning_effort`). `stem` keeps thinking on.

All CLI commands now take `--thinking [off|low|medium|high|default]` to override
the per-collection default for a single run. `services.ai.resolve_thinking`
(with `THINKING_CHOICES`) maps the choice to a `reasoning_effort` value; it is
shared by the CLI (`cli/factory` re-exports it) and the STEM generation page in
the GUI, which exposes the same five levels as a dropdown.

Open items:

- DeepSeek ignores `temperature` while thinking is on, so `stem`'s
  `temperature=0.3` is currently a no-op. Decide whether `stem` should also
  disable thinking (regaining temperature control) or drop the unused argument.
- The `extra_body` thinking field is DeepSeek-specific. If another text
  provider is adopted, translate `DISABLE_REASONING` per provider instead.
- Disabling thinking made the model less consistent about the output contract
  (`word` occasionally returns a bare record instead of a JSON array; now
  tolerated in `generate_word_data`). Watch for similar contract slips in the
  other language generators and tighten prompts or parsing as needed.

Status: minor follow-ups; not scheduled.

## Productization: shorter path to the first card

Direction agreed 2026-11-12; work breakdown in
[plans/productization.md](plans/productization.md).

Positioning: a free, open, bring-your-own-key card maker for self-hosters and
heavy Anki users, not a general-purpose toolkit. The fixed prompts and note
types are the product. What holds adoption back is the distance between
hearing about the project and holding a first good card: three model routes
to configure, Google-Cloud-only TTS, several pieces of software to wire
together, and no way to see card quality before installing.

Principles:

- **Show the result before the install** — sample deck, GIF, Chinese README.
- **One key is enough** — a single Gemini or OpenAI key covers text, image,
  and audio; a text-only key still produces cards, without media.
- **One recommended path** — the headless `collection` backend with AnkiWeb
  sync ("add a word from the phone browser, it shows up on every Anki
  client"). `connect` stays as the alternative for existing Anki Desktop
  users.
- **Curated over configurable** — a few good themes and language pairs
  rather than open-ended editors.

Workstreams, in order (reordered 2026-11-12 for the 1.0 rewrite below):

1. README fixes and a one-line install (done, shipped in v0.6.5).
2. Design language: one token set (palettes, fonts) shared by the Web UI and
   the cards, plus mocks of the first-run wizard and the generate page.
   Direction chosen 2026-11-12; see [Design Language](design/design-language.md).
3. 1.0 rewrite: an API layer and the new frontend (wizard and generate pages
   first), alongside the backend one-key work — one-key presets, additional
   TTS providers, graceful degradation.
4. Languages: add Chinese and Korean as targets so English, Spanish, French,
   German, Japanese, Chinese, and Korean work in any native/target pairing.
5. Card themes: a small set of palettes, light and dark chosen independently,
   applied to the UI and the cards together.
6. Showcase and launch: sample deck, GIF, Chinese README, deploy templates.

Confirmed 2026-11-12 for workstreams 4 and 5:

- **Languages.** Any-pair support is a smaller step than it sounds: every
  language is already selectable as the native language and has a TTS code,
  so only Chinese and Korean are missing as targets. Chinese as a target has
  the most value — it widens the audience from "Chinese speakers learning a
  language" to "anyone learning Chinese", which is what makes the project
  promotable in English-speaking Anki communities. Korean ships as beta until
  a competent reader has reviewed its output. Existing prompts were tuned for
  Chinese natives and need one review pass with English as the native
  language.
- **Themes.** Light and dark are already supported through CSS tokens under
  `body` and `body.nightMode`; multi-theme means extracting those palettes
  and letting the light and dark one be picked separately. Scope is three or
  four curated palettes plus fonts — no layout variants and no in-app CSS
  editor.

Not planned: HyperTTS-level provider coverage, a hosted multi-user service,
an Anki add-on rewrite, free-form prompt/template editing in the UI.

Earlier questions, now settled: the CLI stays and shares `settings.json` with
the Web UI (shipped 2026-09-22); the Anki backend, collection path, and
storage secret no longer need env vars (shipped 2026-09-22).

### 1.0 rewrite (decided 2026-11-12)

0.x is frozen at v0.6.5; the `release/0.x` branch takes critical fixes only.
The 1.0 productization rewrite lives on the long-lived `feat/1.0` branch and
merges into `main` once its acceptance checks are green; until then `main`
stays at 0.x and runnable. (Changed 2026-11-12 from rewriting on `main`
directly.)

- **Frontend.** Product taste is part of the product, and the wizard, theme
  preview, and launch screenshots are the first impression. The NiceGUI UI is
  replaced by a JS/TS single-page app (Vite; framework chosen after the design
  mocks). It is built in CI and bundled into the wheel, so the `uvx` install
  needs no Node. The CLI/TUI stay and keep sharing `settings.json`.
- **Bold restructuring.** Backend structure and tests may change freely, and
  intermediate states need not run — only the finished 1.0 must.
- **Guardrails.**
  1. Before deleting a test, decide whether the behavior it guards still
     matters in 1.0; port it if so.
  2. Keep three to five end-to-end acceptance checks (fake LLM → temporary
     collection → word and STEM cards, plus the sync flow). They may go red
     briefly but must be green at every milestone.
  3. Never break existing cards: note type names and fields stay or get a
     migration (field changes force a full AnkiWeb sync), and 1.0 imports a
     0.x `settings.json`.

## Future major version: deployable web service

Explore evolving ankinote from a local CLI/NiceGUI application into a web
service that can be deployed to the public internet.

The web version must include user identity and access management as a
foundational concern, rather than an afterthought. Initial planning should
cover:

- user registration, sign-in, sign-out, and secure session management;
- account recovery and verification flows;
- authorization and strict per-user data isolation;
- secure storage and handling of user-provided AI-provider credentials, if
  supported;
- deployment, HTTPS, secrets management, observability, and abuse/rate-limit
  controls;
- how web users create and synchronize cards with Anki, without assuming a
  publicly reachable AnkiConnect instance.

2026-09-15: previously set aside to keep the product single-user; back on the
table as a maybe-later if the single-user product gains traction (see the
productization section above). Still no architecture work started.

Status: idea only; not scheduled and not a commitment to a specific framework
or authentication provider.
