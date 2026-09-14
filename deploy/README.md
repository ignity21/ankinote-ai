# Deploying the AnkiNote web GUI

Published images (multi-arch `amd64` + `arm64`), tags `latest`, `<major>.<minor>`,
`<version>`:

- `ghcr.io/ignity21/ankinote-ai`
- `ignity21/ankinote-ai` (Docker Hub)

Two ready-made stacks:

| Directory | Use it when |
| --- | --- |
| [`standard/`](standard/) | You already run AnkiConnect — the Anki desktop app on the host, or one elsewhere. |
| [`headless/`](headless/) | You want a self-contained stack with no Anki desktop app and no AnkiConnect. The GUI keeps its own Anki collection and syncs it straight with AnkiWeb. |

Each directory is standalone:

```bash
cd deploy/standard        # or deploy/headless
cp .env.example .env      # set ANKINOTE_STORAGE_SECRET (+ AnkiWeb login for headless)
docker compose up -d      # http://localhost:8080
```

The published image bundles the `anki` library, so `headless/` needs no extra
build. Both stacks use the same image; only the environment differs.

**AI provider keys are configured in the web UI**, not in `.env` — open the
Settings page after first launch and add your text/image provider profiles and the
Google TTS key. They persist in the `ankinote-config` volume.

## `standard/`

The container reaches your AnkiConnect via `ANKI_CONNECT_URL` (default
`http://host.docker.internal:8765`, i.e. the host). In the AnkiConnect add-on
config (Tools -> Add-ons -> AnkiConnect -> Config) set `"webBindAddress": "0.0.0.0"`
and add the container origin to `"webCorsOriginList"` (or use `"*"`), then restart
Anki.

## `headless/`

One `ankinote` service, no sidecar. It runs with `ANKI_BACKEND=collection`, opens
an Anki collection at `/data/collection.anki2` in-process, and synchronizes it
directly with AnkiWeb — at startup, after every card save, and every five
minutes. The collection, its media, the credential-free sync state, and the
backups taken before a full sync all live in the `anki-data` volume.

Set `ANKIWEB_USERNAME` / `ANKIWEB_PASSWORD` in `.env` to sign in from the
deployment environment; the password is passed through the environment and never
written to disk. They are optional — leave them blank and use the **AnkiWeb
sync** panel on the Settings page instead. Either way, a brand-new collection
cannot save cards until its first AnkiWeb sync completes; if AnkiWeb already has
data you will be asked to choose an upload or download once on the Settings page.

To use an existing collection directory instead of the named volume, see the
commented bind mount in `headless/compose.yaml`. Open a given collection from
only one process at a time — do not point Anki desktop at the same directory
while the stack is running. Migrating from an AnkiConnect deployment: see
[Migrating to the headless stack](#migrating-to-the-headless-stack).

## Config & secrets

- Provider profiles and API keys entered on the Settings page persist in the
  `ankinote-config` volume (`/config` in the container) — there is no need to put
  them in `.env`.
- `ANKINOTE_STORAGE_SECRET` signs the GUI session cookie — generate one with
  `openssl rand -hex 32`. Defaults to a shared built-in value if unset.
- `ANKINOTE_PUBLISH` sets the published address/port (default `127.0.0.1:8080`).
  Use `8080` to bind all interfaces, `127.0.0.1:9000` for a different port.
- `headless/` optionally takes `ANKIWEB_USERNAME` / `ANKIWEB_PASSWORD` to sign in
  to AnkiWeb without using the Settings page. When set they take precedence over
  a login entered in the UI, and the password is never persisted.

## Customizing beyond `.env`

For structural changes — an extra volume, another service, a different network —
drop a `compose.override.yaml` next to the stack's `compose.yaml`. Compose loads
and merges it automatically on `docker compose up`; it is gitignored.

```yaml
# deploy/standard/compose.override.yaml
services:
  ankinote:
    volumes:
      - ./media:/media
```

Note list merges *append* (e.g. a `ports:` entry in the override is added, not
replaced) — for the published port use `ANKINOTE_PUBLISH` instead.
- `ANKINOTE_IMAGE` overrides the image/tag (default
  `ghcr.io/ignity21/ankinote-ai:latest`).

## Building locally

The image installs a released version straight from PyPI, with the `headless`
extra:

```bash
docker build --build-arg ANKINOTE_VERSION=0.3.1 -t ankinote-ai ../..
```

(run from either stack directory; the build context is the repo root). Each
`compose.yaml` has a commented `build:` block for `docker compose build`.

## Migrating to the headless stack

Moving from an AnkiConnect deployment (`standard/`, or a previous headless stack
that ran `glechic/anki-connect-server`) to the in-process backend:

1. **Sync the source collection to AnkiWeb** so nothing is only local. In Anki
   desktop press `Y`; a bundled AnkiConnect server syncs on its own.
2. **Stop the old stack** (`docker compose down`). Leave its volumes in place
   until the new stack is verified.
3. **Start `headless/`** with `ANKIWEB_USERNAME` / `ANKIWEB_PASSWORD` set, or
   log in on the Settings page. The empty `anki-data` volume pulls the whole
   collection from AnkiWeb on first sync; when prompted for a data source,
   choose **download**.
4. **Verify** on the Settings page that the last full sync just completed, then
   open a card page and confirm your decks and note types are present.
5. Only then remove the old stack's volumes.

Rehearse against a copy first: `docker run --rm -v OLD_VOLUME:/from -v $PWD:/to
alpine cp /from/collection.anki2 /to/` gives you a throwaway collection file to
bind-mount into a scratch `headless/` stack (`- ./collection.anki2:/data/collection.anki2`).
The migration never deletes cards; a full download replaces the local
collection with AnkiWeb's copy, and `headless/` takes a backup into
`anki-data/collection.anki2.backups/` before it does.
