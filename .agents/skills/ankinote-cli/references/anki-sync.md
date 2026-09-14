# Anki backend and AnkiWeb sync

Ankinote talks to Anki through one of two backends, selected via `ANKI_BACKEND`:

- `connect` (default): uses [AnkiConnect](https://ankiweb.net/shared/info/2055492159) against a running Anki instance. `ANKI_CONNECT_URL` defaults to `http://localhost:8765`.
- `collection`: in-process `DirectCollectionClient` that opens a `.anki2` collection file directly — no running Anki instance needed. Requires `ANKI_COLLECTION_PATH`. Used for headless/deploy setups (see README.md).

## AnkiWeb sync (collection backend only)

```
uv run ankinote anki login    # prompts for AnkiWeb credentials, or set ANKIWEB_USERNAME/ANKIWEB_PASSWORD
uv run ankinote anki status
uv run ankinote anki sync
uv run ankinote anki logout
```

Relevant env vars: `ANKI_BACKEND`, `ANKI_COLLECTION_PATH`, `ANKIWEB_USERNAME`, `ANKIWEB_PASSWORD`.
