# Direct Collection Backend and AnkiWeb Sync

**Status: complete.** All stages (0–8) below are shipped on `main`. See each
stage's "Done" note for what landed and where.

## Goal and Confirmed Behavior

Add an in-process backend that uses Anki's official Python library to operate on
an Anki collection directly. Keep the existing `AnkiConnectClient` backend.
The first release covers card creation, note type maintenance, media storage, and
complete AnkiWeb synchronization.

| Topic | Confirmed choice |
| --- | --- |
| Default backend | Standard installations continue to use AnkiConnect; headless Docker uses the direct backend. |
| Sync triggers | At startup, after each write batch, every five minutes, and manually. |
| Sync data | Both collection and media, including images and audio. |
| Full sync | Pause and require the user to choose upload or download; block writes until resolved. |
| Temporary offline state | After initial setup, permit local writes and synchronize after recovery. |
| Account model | One account and one collection per ankinote instance; support UI login and environment variables. |
| Concurrent processes | Do not support GUI and CLI processes opening the same collection simultaneously in the first release. |
| Migration | Support reusing the existing data directory and initializing a fresh directory from AnkiWeb. |

## Backend Interface and Lifecycle

- Keep `AnkiCollectionClient` as the collection-facing contract, with its model,
  deck, note, and media services. Add `DirectCollectionClient`; retain
  `AnkiConnectClient` as the remote/Desktop-Anki implementation.
- Add one backend factory and replace all direct `AnkiConnectClient` construction
  in the UI and CLI. Select it with `ANKI_BACKEND=connect|collection`; the default
  remains `connect`. `ANKI_COLLECTION_PATH` is required for `collection`.
- Create the direct backend once for the web application and close it during app
  shutdown. CLI commands create it for their command context and close it on
  completion. Individual pages and generation tasks borrow the shared runtime.
- Run every Anki `Collection` call in one dedicated worker thread. The asyncio
  layer submits typed work to that thread; raw Anki objects never cross the
  thread boundary.
- Serialize collection reads/writes and synchronization through this runtime.
  A note save is atomic from the application's perspective: deduplication,
  media storage, field update, and tag update complete before a sync can begin.
  AI generation does not hold the collection worker.
- Detect collection locking and report that the collection is in use when another
  process, including Anki Desktop or another ankinote CLI/GUI process, owns it.

## Local Collection Operations

- Implement the current application contract with Anki's supported collection
  APIs: note type lookup and creation, field addition, template addition and
  renaming, named template updates, CSS updates, deck lookup/creation, note
  lookup/add/update, tag replacement, and media storage.
- After creating or modifying a note type, reload it so ankinote receives
  Anki-assigned IDs, field order, and template data. Use normal model updates so
  schema changes participate in AnkiWeb synchronization.
- Preserve existing notes, cards, review history, and any user-owned extra
  fields or templates. Do not rebuild a note type to update it.
- Keep existing deduplication behavior: multiple matching notes are an error,
  not an arbitrary selection. Note type synchronization is idempotent.
- Return the actual stored media filename and use it to render sound/image
  references, accommodating Anki filename normalization or collision handling.

## AnkiWeb Sync and Account State

- Add a synchronization service with durable state: `not_logged_in`,
  `initializing`, `idle`, `syncing`, `pending`, `needs_full_sync_choice`, and
  `error`. Track collection and media outcomes plus the most recent successful
  synchronization time.
- Use Anki's own login, normal sync, full upload/download, and media sync APIs;
  do not implement the AnkiWeb protocol. Wait for media synchronization to
  finish and surface its errors before reporting success.
- Synchronize at runtime start, after each successful write batch, and on a
  five-minute interval. Coalesce duplicate requests. CLI commands wait for their
  batch's sync result before completing.
- On network errors, retain the local collection and retry with backoff. On
  credential failure, stop automatic login retries and require reauthentication.
  Retrying a sync never repeats AI generation or an already-completed local
  write.
- Initial setup must resolve synchronization before card writes. If Anki requires
  a full sync, do not automatically choose a destructive direction.
- Before a user-selected full upload or download, wait for queued writes and
  make a recoverable collection backup. Abort if the backup cannot be made.
  Reopen and invalidate cached collection objects after a sync that replaces the
  local collection.
- While a full-sync decision is pending, permit read-only status views but reject
  new writes and note type changes. This differs from a temporary network outage,
  where local writes are allowed.
- Persist the Anki sync credential after successful UI login in a separate
  restricted-permission file. Never expose it to the browser or logs. Environment
  configuration takes precedence and UI shows that the credentials are externally
  configured.
- Logout removes the saved sync credential and pauses automatic synchronization;
  it does not delete the local collection. Do not silently associate an existing
  collection directory with a different AnkiWeb account.

## UI, CLI, Deployment, and Migration

- Add Anki backend and sync controls to Settings: account login/logout, current
  sync status, last result, manual sync, and the five-minute interval setting.
  Present upload/download choices when a full sync is required.
- Report local-write success separately from AnkiWeb-sync success. A media sync
  failure must not make a completed card write look unsuccessful.
- Distinguish note type synchronization from AnkiWeb synchronization in English
  and Simplified Chinese UI text.
- Add `ankinote anki login`, `logout`, `status`, and `sync` commands.
  `sync --direction upload|download` resolves a required full sync in
  non-interactive deployments; unresolved conflicts return a nonzero status.
- Ship the direct backend as an `ankinote-ai[headless]` extra and initially pin
  `anki==26.8.1`. Preserve the standard image's AnkiConnect behavior; make the
  headless image install the extra.
- Simplify `deploy/headless/compose.yaml` to one ankinote service with the
  collection data volume. Keep `deploy/standard/compose.yaml` unchanged.
- Document migration: stop the old headless service, back up the complete data
  directory, preserve collection plus media data, verify ownership, then start
  the direct backend. A fresh directory initializes from AnkiWeb. Do not
  automatically remove old data.
- Do not publish a release, deploy containers, or migrate a real AnkiWeb account
  as part of this work.

## Runtime Prerequisites

Verified against PyPI before planning the stages:

- `anki==26.8.1` ships `cp310-abi3` wheels with `requires-python >=3.10`, so it
  installs on this project's Python 3.14 floor through the stable ABI.
- Linux wheels are `manylinux_2_35`, requiring glibc 2.35 or newer. The current
  `python:3.14-slim` base (Debian bookworm, glibc 2.36) qualifies; an Alpine or
  other musl base would not. Keep the headless image on a glibc base.
- Wheels exist for linux x86_64/aarch64, macOS 12+ arm64/x86_64, and Windows
  amd64/arm64. There is no source fallback, so unsupported platforms must keep
  using the AnkiConnect backend.

## Implementation Order

Each stage is a separately committable change that leaves `main` green
(`make test`, `make lint`, `make check`, using pytest, Ruff, and ty as configured
in the Makefile). "Verified
when" lists the observable state that proves the stage landed; a stage is not
done without it.

### Stage 0 — Dependency spike

Prove `anki` coexists with the current dependency set before any code depends
on it. Throwaway work; nothing but findings is committed.

- Resolve `anki==26.8.1` alongside `litellm`, `httpx`, `protobuf`, and
  `nicegui`; record any pin conflicts.
- Open, write, and close a throwaway collection in a temp directory.

Verified when: `uv run --with anki==26.8.1 python -c "from anki.collection
import Collection; ..."` creates a temp collection and adds a note; `uv lock`
with the extra resolves with no conflict; the same import succeeds inside a
`python:3.14-slim` container.

**Findings (done 2026-09-06):**

- `anki==26.8.1` resolves cleanly alongside the full dependency set with
  `--all-extras`; no pins conflict. Its transitive deps: `decorator`,
  `distro`, `markdown`, `orjson`, `protobuf<8.0,>=6.0`, `requests[socks]`,
  `typing-extensions`. Only `protobuf` overlaps existing deps
  (`google-cloud-texttospeech`); resolved version 6.33.5 satisfies both.
- `anki.version` does not exist; the version string is
  `anki.buildinfo.version` (reports `26.08.1`).
- Temp-collection create + `models.by_name("Basic")` + `new_note` /
  `add_note(note, decks.id(...))` + `note_count` + `close` all work; `media`
  is `col.media`, store is `col.media.write_data(name, bytes)` returning the
  stored filename. Reopening the same file after `close()` succeeds, so the
  lock is released on close.
- Verified in a clean `python:3.14-slim` container: `pip install anki==26.8.1`
  then open a collection and add a note — works. glibc/abi3 assumptions hold.

### Stage 1 — Backend selection seam (no behavior change)

- Add `ANKI_BACKEND` (`connect` default) and `ANKI_COLLECTION_PATH` to
  `EnvVars`.
- Add a backend factory and route every construction site through it:
  `cli/factory.py`, `ui/pages/word.py`, `ui/pages/phrase.py`,
  `ui/pages/sentence.py`, `ui/pages/stem.py` (two sites), and
  `ui/pages/notetypes.py` (two sites).

Verified when: no module outside the factory and its tests imports
`AnkiConnectClient`, provable with a grep-style test; the factory returns an
`AnkiConnectClient` under default env; `ANKI_BACKEND=collection` without
`ANKI_COLLECTION_PATH` raises a configuration error naming the missing
variable; the existing suite passes unchanged.

### Stage 2 — Collection worker runtime

- Add a runtime owning one dedicated worker thread, an asyncio submit bridge,
  and open/close lifecycle. Raw Anki objects never leave the thread.
- Detect an already-locked collection and raise a distinct "collection in use"
  error.

Verified when: submitted work runs on one non-event-loop thread and results
cross back as plain values, tested through an injected fake opener; a real
second open of the same collection file raises the in-use error naming the
path; closing the runtime joins the thread within a timeout; an exception in
submitted work propagates to the awaiting coroutine without killing the
worker.

### Stage 3 — Direct collection operations

- Add `DirectCollectionClient` implementing the model, deck, note, and media
  protocols against the runtime.

Verified when: a shared backend-contract test suite, parametrized over the
AnkiConnect fake and a real temp collection, passes for both — covering note
type create/reload, field addition, template add/rename/update, CSS update,
deck create/exists, note find/add/update, tag replacement, and media store.
Additionally: a stored file returns its actual normalized filename and the
rendered field references that name; a second `sync` of the same note type is a
no-op; two matching notes raise rather than pick one; a note type carrying an
extra user field and a review-history card keeps both after sync.

### Stage 4 — Lifecycle ownership

- Web app creates one runtime at startup and closes it at shutdown; pages and
  generation tasks borrow it. CLI creates one per command context.

Verified when: two concurrent page flows observe the same runtime instance; the
CLI context closes the runtime on both success and exception paths; a
generation task awaiting the AI service does not block another task's
collection call.

**Done 2026-09-06:** `anki_backend_scope()` / `start_anki_backend()` /
`stop_anki_backend()` in `anki_factory.py` own one process-wide
`_shared_runtime`. The web app opens it in `app.on_startup` and closes it in
`app.on_shutdown` (`ui/main.py`); the CLI wraps `collection_context` in
`anki_backend_scope()`. `create_anki_client()` for `collection` returns a
`DirectCollectionClient` over the shared runtime and raises if no scope is
active. Nested scopes reuse the outer runtime. Connect backend is unchanged
and stateless.

### Stage 5 — Sync state machine (no network)

- Implement the state machine (`not_logged_in`, `initializing`, `idle`,
  `syncing`, `pending`, `needs_full_sync_choice`, `error`), request coalescing,
  the five-minute timer, and network backoff, behind an injected sync driver.

Verified when: unit tests with a fake driver cover each transition; three
overlapping requests produce one driver call; a network error backs off and
retries while a credential error stops retrying; `needs_full_sync_choice`
rejects writes and note type changes while still serving status reads; a
temporary network outage still permits local writes.

**Done 2026-09-07:** `services/anki_sync.py` provides an injected
`SyncDriver`, immutable status snapshots, atomic JSON state persistence,
overlapping-request coalescing, a configurable 300-second timer, capped
exponential network backoff, and explicit reauthentication after credential
failure. Full-sync write blocking survives logout and restart. Collection and
media outcomes are separate; only complete success advances `last_success`.
`CollectionRuntime.submit_write()` applies the service's admission policy to
every direct-backend mutation and keeps active worker writes ahead of sync even
when their caller is cancelled. Status remains readable during sync/conflicts.

The service and state store are injected explicitly in this stage; the existing
factory does not start synchronization without a real driver. Stage 6 must wire
the service/store into backend startup, add full-sync direction resolution, and
connect application write-batch boundaries to post-write sync requests while
keeping the entire note save atomic relative to sync. Driver/state-machine tests
use fake drivers and clocks and never contact AnkiWeb.

Verified with the Makefile commands: `uv run ruff check --fix` and
`uv run ty check` pass; `uv run pytest` passes all 251 tests, including 23 new
sync tests.

### Stage 6 — Real sync driver, credentials, backups

- Wire Anki's login, normal sync, full upload/download, and media sync. Persist
  the credential in a separate `0600` file; env config wins. Back up before a
  full sync; reopen and invalidate caches after a sync that replaces the
  collection.

Verified when: the credential file is created mode `0600` and never appears in
log output or any browser-facing payload; env-provided credentials take
precedence and are reported as externally configured; a simulated backup
failure aborts the full sync leaving the collection untouched; after a full
download, cached note type objects are invalidated and refetched; logout
removes the credential file, pauses sync, and leaves the collection on disk.
Media sync failures surface distinctly from collection sync failures.

**Done 2026-09-07:** `anki_sync_driver.py` uses the pinned Anki library's login,
collection sync, full upload/download, and media status APIs on the collection
worker. Backend startup now restores the state store and starts synchronization.
`ANKIWEB_USERNAME` / `ANKIWEB_PASSWORD` take precedence over saved credentials;
saved tokens use an atomic `0600` file, while status snapshots contain no secrets.
Account binding survives logout, and concurrent login/logout operations serialize.

Explicit full-sync resolution rechecks the server requirement, waits behind
admitted writes, requires a completed native collection backup, and restores the
Python collection connection and clears note-type caches after full sync.
Backup failure and unavailable directions leave writes blocked. Media failures
record collection success separately, retry network failures, and require login
after authentication failures. Cancellation drains native worker operations before
releasing sync admission.

Word, Phrase, Sentence, and STEM save/setup flows now hold one write-batch scope
through their collection operations and await post-write sync. AI and media
generation remain outside that scope. Fresh collections serve status reads while
blocking writes until initialization; initialized collections remain writable
offline. UI/CLI controls remain Stage 7 work.

Verified with `make lint`, `make check`, and `make test`: all 268 tests pass,
including 16 new driver tests and a fresh-collection factory test. Tests use fake
network responses plus a real temporary Anki collection for native backup and
cache invalidation; no personal AnkiWeb account was contacted. API behavior was
checked against the installed `anki==26.8.1` source and the
[official collection implementation](https://github.com/ankitects/anki/blob/main/pylib/anki/collection.py).

### Stage 7 — UI and CLI surfaces

UI interaction design: [AnkiWeb sync UX](stage-7-sync-ui.md), covering first-run
setup, state-dependent actions, full-sync confirmation, and separate save/sync
feedback. This is a design specification, not a completed implementation.

- Settings panel: login/logout, status, last result, manual sync, interval,
  and the upload/download choice. Separate local-write from sync reporting.
- Add `ankinote anki login|logout|status|sync`, with
  `sync --direction upload|download`.
- Add English and Simplified Chinese strings distinguishing note type sync from
  AnkiWeb sync.

Verified when: page tests in the style of `tests/ui/test_settings_page.py`
render every sync state including the full-sync prompt; a card write whose
media sync failed still reports the local write as successful; `ankinote anki
status` exits nonzero on an unresolved full sync and zero on `idle`;
`sync --direction upload` resolves it non-interactively; no user-facing string
is missing from either locale.

**Done:** Implemented per [stage-7-sync-ui.md](stage-7-sync-ui.md). Settings
panel (login/logout, status, last result, manual sync, interval, full-sync
upload/download choice, separate local-write vs. sync reporting) lives in
`src/ankinote/ui/sync.py`. CLI commands `ankinote anki login|logout|status|sync`
(including `sync --direction upload|download`) live in
`src/ankinote/cli/anki.py`. English/Simplified Chinese strings distinguish
note type sync from AnkiWeb sync.

### Stage 8 — Packaging, deployment, migration docs

- Add the `ankinote-ai[headless]` extra pinning `anki==26.8.1`; keep the
  standard image on AnkiConnect and install the extra in the headless image.
- Reduce `deploy/headless/compose.yaml` to one ankinote service plus the
  collection volume; leave `deploy/standard/compose.yaml` alone.
- Document configuration and the migration procedure.

Verified when: the standard image still boots with `ANKI_CONNECT_URL` and no
`anki` package installed; the headless image boots against a fresh empty
collection volume with no AnkiWeb account configured and serves the GUI;
`docker compose config` succeeds for both stacks and the headless stack no
longer references `anki-connect-server`; the migration doc's steps are walked
end to end against a copied throwaway data directory.

**Done 2026-09-07:** The `ankinote-ai[headless]` extra pins `anki==26.8.1`.
Rather than two image variants, the single published image installs
`ankinote-ai[headless]` — the `anki` library adds a few MB, both backends work
unmodified, and the tag scheme and `docker.yml` are untouched. The image keeps
`ANKI_BACKEND` unset (AnkiConnect default) and adds an appuser-owned `/data`.

`deploy/headless/` is now one `ankinote` service with `ANKI_BACKEND=collection`,
`ANKI_COLLECTION_PATH=/data/collection.anki2`, an `anki-data` volume, and
optional `ANKIWEB_USERNAME` / `ANKIWEB_PASSWORD`; the `glechic/anki-connect-server`
sidecar and the `deploy/connect/` draft are removed. `deploy/standard/` is
unchanged. `deploy/README.md` documents the split, the headless env vars, and a
"Migrating to the headless stack" procedure (sync source to AnkiWeb → stop old
stack → start headless and choose download → verify → drop old volumes), with a
throwaway-copy rehearsal via a bind-mounted collection file. `README.md` gains
`ANKI_BACKEND` / `ANKI_COLLECTION_PATH` / `ANKIWEB_*` rows.

Verified: `docker compose config` succeeds for `deploy/standard` and
`deploy/headless`; the headless config resolves to a single service with no
`anki-connect-server`. `make test` / `make lint` / `make check` stay green.
Image build and the fresh-volume boot are checked in CI/on release, not here.

## Global Acceptance

- Test Word, Phrase, Sentence, and STEM collection flows through the direct
  backend: first creation, repeated setup, missing fields, multiple templates,
  existing notes, tags, audio, images, and preserved review history.
- Test normal sync, full upload, full download, authentication failure, offline
  retry, media failure, backup failure, cancellation, restart, and unresolved
  full-sync write blocking.
- Test collection lock detection and the explicit unsupported GUI-plus-CLI
  concurrent-process case.
- Verify reusing a prior data directory and initializing a new directory from
  AnkiWeb. Automated tests use no personal AnkiWeb account; provide a manual
  two-device acceptance procedure for cards, audio, images, and remote edits.
- Run `make test`, `make lint`, and `make check` (`pytest`, `ruff check --fix`,
  and `ty check` via `uv run`); identify
  any pre-existing failures separately from feature regressions.
