# Repository Guidelines

## Project Context

- Source lives in `src/ankinote/`; tests live in `tests/`.
- For collection backend or AnkiWeb sync changes, consult the confirmed design in [Direct Collection Backend and AnkiWeb Sync](docs/plans/direct-collection-backend.md).
- Use `README.md` for configuration and document new integration settings there. Keep credentials and `.env` files out of commits.

## Development

Use `uv` for dependencies and execution. Treat `pyproject.toml` as the source of truth for Python compatibility and tool settings; `Makefile` defines task shortcuts.

- Tests: `uv run pytest [path]`.
- Formatting: `uv run ruff format [path]`.
- Lint: `uv run ruff check [path]`.
- Types: `uv run ty check`.

For implementation tasks, continue through relevant verification and fix failures caused by the change. Choose checks proportional to the affected behavior; documentation-only edits do not need the Python suite. Rerun affected checks after fixes, and broaden coverage when shared behavior or unresolved failures warrant it. Routine local edits and checks within the requested scope need no separate confirmation.

Before fixing a bug, first write a test that reproduces it; the fix isn't done until that test goes green.

PRs should explain the resulting behavior and verification, with screenshots or sample output when useful for UI, card, or CLI changes.

## Maintaining These Instructions

- Record durable, project-specific guidance that changes how work should be done. Keep task progress and one-off discoveries in plans or issues.
- Prefer updating or removing an existing rule to appending another. Remove stale, duplicate, conflicting, or generic advice; link to authoritative configuration instead of copying it.
- Keep guidance short and state when it applies. Move detailed workflows into linked docs or skills with narrow trigger descriptions, read as needed.
- Describe outcomes and concrete decision boundaries, leaving routine implementation choices to the agent. Add approval requirements only for actions that actually need user authorization; preserve authorization already given for the task.
