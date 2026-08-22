# Agent Instructions

This file is the entry point for coding agents working in this repository.
Keep it short and operational; put detailed, topic-specific documentation in
the documents linked below.

## Project overview

`ankinote-ai` is a Python 3.13+ application that generates AI-assisted Anki
cards for words, phrases, sentences, and STEM concepts. It can generate text,
audio, and images, then synchronise notes with Anki through AnkiConnect.

The main runtime code is under `src/ankinote/`. The CLI is exposed as
`ankinote`, and the NiceGUI application as `ankinote-gui`.

## Repository map

- `src/ankinote/cli/`: Click CLI commands and command wiring.
- `src/ankinote/collections/`: card models, generators, prompts, and templates.
- `src/ankinote/services/`: AI, TTS, and AnkiConnect integrations.
- `src/ankinote/ui/`: NiceGUI application.
- `tests/`: pytest tests, organised by service, collection, CLI, and utility.
- `examples/`: examples for APIs, collections, and card generators.
- `scripts/`: language-list conversion and initialisation helpers.
- `docs/`: project design notes and supporting documentation.
- `skills/ankinote-cli/SKILL.md`: detailed CLI usage for agents.
- `CONVENTIONS.md`: Python and code-style conventions.
- `PLANS.md`: known future work and technical debt.

## Development commands

Run commands from the repository root:

```bash
uv sync                    # install/update the project environment
uv run pytest              # run the test suite
uv run ruff format         # format Python code
uv run ruff check --fix    # lint and apply safe fixes
uv run basedpyright       # run static type checking
make pre-commit            # format, lint, and type-check
uv build                   # build distribution artifacts
```

Prefer the narrowest relevant test while iterating, for example:

```bash
uv run pytest tests/services/test_ai.py
uv run pytest tests/collections/test_word_collection.py
```

Do not run commands that call external AI providers or modify an Anki
collection unless the task explicitly requires it. Unit tests should mock
external services where practical.

## Implementation guidelines

1. Read the relevant existing code, tests, `CONVENTIONS.md`, and any linked
   skill before changing behaviour.
2. Keep changes focused. Preserve existing public CLI behaviour unless the
   task explicitly asks for a breaking change.
3. Add or update tests for behaviour changes, especially around prompts,
   generated card fields, async code, rate limiting, and external services.
4. Keep secrets out of source, tests, logs, commits, and documentation. Use
   `.env` locally and `.env.example` for documenting configuration names.
5. Treat prompts, HTML templates, CSS, and generated field names as public
   interfaces: inspect their consumers before changing them.
6. Use the existing dependency and packaging setup (`uv`, `pyproject.toml`,
   Hatchling). Do not introduce another package manager or build system.
7. Update documentation when a command, configuration variable, public API,
   or user-visible workflow changes.

For Python style and type-annotation rules, follow `CONVENTIONS.md`. Use
English for code, identifiers, and code comments.

## Verification and handoff

Before handing off a change:

- inspect `git diff` and `git status`;
- run the relevant tests;
- run `make pre-commit` when the change affects Python code;
- report any checks that could not be run and why;
- mention external prerequisites such as AnkiConnect or API keys when they
  affect verification.

Do not discard unrelated working-tree changes. Avoid destructive git commands
unless the user explicitly requests them.

## Documentation precedence

When instructions overlap, use this order:

1. Direct user request.
2. Repository-level safety and contribution guidance in this file.
3. More specific documentation for the area being changed, such as
   `CONVENTIONS.md` or `skills/ankinote-cli/SKILL.md`.
4. General project documentation such as `README.md` and `PLANS.md`.

If repository behaviour and documentation disagree, verify the behaviour in
the code and tests, then update the stale documentation when appropriate.
