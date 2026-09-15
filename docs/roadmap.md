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

## Productization: single GUI-only surface

Direction under consideration, nothing decided or scheduled: shrink ankinote
to one clear entry point — the Web UI — instead of a CLI + GUI + env-var
config split.

- **Drop the CLI?** Open question: `.agents/skills/ankinote-cli/SKILL.md`
  currently makes `ankinote` the integration point for AI coding assistants
  (batch card generation via agent), not just a terminal feature. Cutting the
  CLI removes that path unless it's replaced — a documented HTTP API is the
  natural substitute, since the Web UI already runs on FastAPI (NiceGUI).
  Whether to keep an automation surface at all depends on who the
  productized version is for.
- **Remove the remaining env vars; configure everything from Settings.**
  Checked 2026-09-15: mostly feasible without a redesign.
  `services/anki_factory.py` already isolates backend selection behind one
  seam (`resolve_backend()` / `start_anki_backend()` / `stop_anki_backend()`),
  and `ui/config.py`'s `apply_env()` already pushes Settings-page values into
  the same `envs` object those functions read from — so a live
  `ANKI_BACKEND` / `ANKI_COLLECTION_PATH` switch in the Settings page (stop
  the current backend, apply the new values, start the new one) is UI work
  on an existing seam, not new plumbing. `ANKINOTE_HOST`/`PORT` and
  `ANKINOTE_STORAGE_SECRET` can't become Settings fields — the GUI needs them
  before there's any UI to configure from — but the storage secret at least
  could be auto-generated and persisted on first run instead of required as
  an env var, making it invisible to the user in practice.
- **Rewrite the UI as a real JS/TS frontend?** Raised, not decided either
  way. NiceGUI is Python-server-driven (Vue/Quasar over WebSocket, no
  standalone REST API today); a real SPA would mean building a formal API
  first — which would also give the CLI-removal question an automation
  alternative — plus a full UI rewrite: the highest-cost of these options for
  what is currently a single-maintainer Python codebase. Only worth it if
  NiceGUI is structurally blocking something specific (offline PWA, native
  packaging, a frontend hire), not on its own.

Status: idea only; not scheduled. Explicitly parked until the user has
thought it through — do not start implementation from this section alone.

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
