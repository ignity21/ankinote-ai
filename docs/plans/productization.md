# Productization Plan

Status: direction and scope confirmed 2026-11-12 (including Phase 2
languages and Phase 3 themes as scoped below); Phase 0 done 2026-11-12,
Phase 1 next. Direction and rationale live in
the [roadmap](../roadmap.md#productization-shorter-path-to-the-first-card);
this file is the work breakdown.

Goal: a new user reaches their first good card with one API key, one install
command, and no knowledge of note types, prompts, or model routes.

Sizes are relative: S = an evening, M = a few sessions, L = a multi-week effort.

## Phase 0 — Quick fixes (S)

Cheap, no design decisions, unblocks everything else.

- README: bring the backend and env-var sections in line with the code. The
  Anki backend and collection path are Settings fields
  (`settings.py: anki_backend`), and the storage secret is auto-generated
  (`get_or_create_storage_secret`); the README still presents all three as
  env-only and mentions a "built-in dev key".
- README: lead the install section with a single `uvx` command for the Web UI
  (uv fetches Python 3.14 itself, so the version requirement stops being a
  prerequisite). Confirm the exact invocation, including the `headless` extra.
- README: present the `collection` (headless) backend as the recommended path
  and `connect` as the alternative for people who already run Anki Desktop.

Done when: a reader following only the first screen of the README gets a
running Web UI.

Done 2026-11-12. The install line is
`uvx --from 'ankinote-ai[headless]' ankinote-gui`, verified from an empty
uv cache and Python dir: uv picks the newest managed CPython satisfying
`>=3.14`. Two code/deploy gaps surfaced and were fixed alongside:

- The GUI startup hook opened the backend from env only, so a `collection`
  backend chosen in Settings reverted to `connect` after a restart. It now
  applies `settings.json` first, like the CLI.
- Both compose stacks fell back to a fixed, public storage secret when
  `ANKINOTE_STORAGE_SECRET` was unset; they now pass it through empty, so the
  secret is generated and kept in the `ankinote-config` volume.

The `connect` backend is still the code default; making `collection` the
default is left to the Phase 1 wizard.

## Phase 1 — One key is enough (M)

The largest drop-off today: text, image, and TTS each need a separate
provider, and TTS is Google Cloud only (`services/tts.py`), which requires a
GCP project.

1. **TTS providers.** Put Google Cloud TTS behind a provider interface at the
   existing `SpeechSynthesizer` seam and add:
   - Gemini TTS (works with the same AI Studio key as text and image);
   - OpenAI TTS (same key as text and `gpt-image`).
   Check current model ids and per-language voice coverage against provider
   docs at implementation time. TTS becomes a profile-style setting like the
   text and image routes instead of a single Google key field.
2. **Graceful degradation.** With only a text key, cards are still created;
   missing image or audio is skipped without an error, and the result panel
   says which capability is not configured. Verify the card templates render
   cleanly with empty audio and image fields.
3. **One-key presets.** In Settings and the wizard: "Gemini (one key)" and
   "OpenAI (one key)" fill the text, image, and TTS routes from a single
   pasted key. Existing per-route profiles stay for advanced use.
4. **First-run wizard.** Shown when no provider profile exists: paste key →
   live test → choose Anki connection (headless + AnkiWeb login by default) →
   set native/target language → create note types → generate one sample card.
   Reuses the existing Settings handlers; no new persistence.
5. **CLI/TUI parity.** The TUI's TTS menu and `apply_env` follow the new TTS
   setting so both front ends keep sharing `settings.json`.

Open decision: a keyless fallback TTS (edge-tts) would make audio work with
zero setup, but it relies on an unofficial Microsoft endpoint that can break
without notice. Default recommendation: leave it out unless Phase 1 testing
shows the one-key presets are not enough.

Done when: a fresh install with one Gemini or one OpenAI key produces a word
card with image and audio, and with a text-only key (e.g. DeepSeek) produces
a card without them, both through the wizard alone.

## Phase 2 — Languages (M)

Confirmed 2026-11-12: add Chinese and Korean as targets, any native/target
pairing, Korean as beta.

Current state: the native language can already be any of the eight `Language`
values, and TTS language codes exist for all of them. Targets are limited to
English, French, Spanish, German, and Japanese (`consts.TARGET_LANGUAGES`).
So "any pair" only needs Chinese and Korean added as targets.

1. **Chinese as target** (Simplified and Traditional): new `chinese.md`
   prompts for `word`, `phrase`, and `sentence`; pinyin with tone marks as the
   pronunciation and as ruby (both variants are already in
   `RUBY_ANNOTATION_LANGUAGES`); HSK levels for difficulty; add to the three
   `_LANGUAGE_TO_FILENAME` maps and `TARGET_LANGUAGES`.
2. **Korean as target**: new `korean.md` prompts; TOPIK levels; decide whether
   Korean needs ruby at all (hanja glosses only where they aid memory).
   Ship labelled beta until a competent reader has reviewed sample output.
3. **Pair validation**: reject native == target; treat Simplified/Traditional
   as distinct natives but one learning direction.
4. **Quality gate**: a fixed list of about 20 words, 10 phrases, and 10
   sentences per target, generated with two native languages (Chinese and
   English) and reviewed by hand before the language leaves beta. Automated
   tests cover prompt loading and schema parsing only.
5. **English as native**: review the word/phrase/sentence prompts once with
   `native=English`; memory hooks and translations were tuned for Chinese
   natives.

Done when: all seven targets generate valid cards from both Chinese and
English natives, with ruby rendering correctly on desktop, AnkiDroid, and
AnkiMobile.

## Phase 3 — Card themes (S–M)

Confirmed 2026-11-12: curated palettes, light and dark chosen independently,
no layout variants or CSS editor.

Current state: each collection's `style.css` defines the same token set
(`--bg`, `--paper`, `--ink`, `--accent`, …) under `body` and
`body.nightMode`, so light and dark are already supported; the tokens are
duplicated per collection, and some colours are hard-coded outside them (for
example the gradient in `.card`).

1. Move remaining hard-coded colours and font stacks into tokens.
2. Extract palettes into shared theme files: the current "paper" look plus
   two or three more (e.g. a neutral minimal, a high-contrast, a dark-first).
   Each theme provides a light and a dark palette.
3. Settings: `card_theme_light` and `card_theme_dark`, chosen independently.
   `load_card_style` composes the light palette under `body` and the dark one
   under `body.nightMode`.
4. Card Types page: a theme picker with a live preview; applying it goes
   through the existing note-type sync, which already detects CSS drift.
5. Scope limit: palettes and fonts only. No layout variants, no in-app CSS
   editor; users who want more can edit the note type in Anki.

To verify first: that restyling an existing note type does not force a full
AnkiWeb sync on the headless backend (template/CSS edits should not, schema
changes do).

Done when: switching theme in the UI restyles existing cards on all clients
after a normal sync, with light and dark chosen separately.

## Phase 4 — Showcase and launch (S–M)

Last, so screenshots and the sample deck show the final themes and languages.

- Sample deck (`.apkg`) on AnkiWeb shared decks: a few dozen notes per note
  type across two or three target languages, linking back to the project.
- README first screen: a short GIF of "type a word on the phone → card
  appears in Anki", then the one-line install.
- Chinese README (`README.zh-CN.md`).
- One-click deploy templates for the headless stack (at least one PaaS and
  one NAS format) on top of `deploy/headless`.
- Announce: V2EX, 少数派, r/selfhosted, r/Anki, Anki forums. Check each
  community's self-promotion rules first.

## After launch, driven by feedback

- Prompt knobs (detail level, example count) and an override directory for
  the prompt `.md` files.
- Double-click desktop bundle for Windows/macOS.
- More targets (German is already supported; Italian and Portuguese fit the
  existing `latin_alphabet.md` prompt).

## Not planned

- Matching HyperTTS's provider coverage.
- A hosted multi-user service holding users' AnkiWeb and API credentials.
- Rewriting as an Anki add-on.
- Free-form prompt or template editing in the UI.
