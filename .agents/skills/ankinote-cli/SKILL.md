---
name: ankinote-cli
description: Use the ankinote CLI to generate and push Anki cards. Use when the task involves creating, batching, or initializing Anki cards for vocabulary, sentences, phrases, or STEM topics through the ankinote command-line tool.
---

# Ankinote CLI

Generate AI-powered Anki cards from the terminal via litellm (OpenAI, DeepSeek, Gemini, fal.ai, or any configured provider), optionally generate images/diagrams, and push cards to Anki.

## Prerequisites

- Anki running with [AnkiConnect](https://ankiweb.net/shared/info/2055492159) installed (default backend), or the in-process collection backend configured — see [references/anki-sync.md](references/anki-sync.md) if not using AnkiConnect.
- One provider API key set (e.g. `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, or `FAL_AI_API_KEY`); litellm picks whichever matches the model.
- Project installed: `uv sync`

## Commands

### Global structure

```
ankinote [--version] <collection> <command> [args...]
ankinote anki <login|logout|status|sync>   # AnkiWeb sync — see references/anki-sync.md
```

Four card collections: `word`, `phrase`, `sentence`, `stem`. Each has three subcommands: `add`, `batch`, `init`.

Run `uv run ankinote --help` for the full list.

### Collection overview

| Collection | Purpose | Input | Image support |
|---|---|---|---|
| `word` | Vocabulary cards (word + definition) | A single word per card | Yes (generated) |
| `phrase` | Phrase/sentence cards | A phrase or short sentence | No |
| `sentence` | Production-direction sentence cards (V2) | A sentence in the **target** language; AI generates the native-language translation shown on the front | No |
| `stem` | STEM knowledge cards (Math, CS, Finance, ML, ...) | Any question or concept (e.g. "What is a derivative?", "State Bayes' theorem") | Yes (diagrams) — see [references/stem.md](references/stem.md) for its extra options |

### Common options

All collections accept `--llm` to override the default model (currently `gpt-5.6-luna`; not load-bearing — any litellm-routable model works, including fal.ai's).
`word` and `stem` accept `--image-model` (defaults to `gpt-image-1.5` at `low` quality, 512px) and `--image-size <pixels>`.
Language-aware collections (`word`, `phrase`, `sentence` — not `stem`, which is language-agnostic) accept `--native` and `--target`:

```
--native [English|Chinese(Simplified)|Chinese(Traditional)|Japanese|French|Spanish|German|Korean|other]
--target [English|Chinese(Simplified)|Chinese(Traditional)|Japanese|French|Spanish|German|Korean|other]
```

Defaults: `--native Chinese(Simplified) --target English`.

All collections accept `--thinking [off|low|medium|high|default]` to override the
model's extended-thinking level for that run. Omitted, `word`/`phrase`/`sentence`
disable thinking (the default text model doesn't need it) and `stem` defaults to
`high`. `off` disables it, `default` forces the provider default, and the named
levels are passed through as `reasoning_effort`.

### `add` — Single card

```
uv run ankinote word add <word>
uv run ankinote sentence add <sentence>
uv run ankinote phrase add <phrase>
uv run ankinote stem add <topic>
```

### `batch` — Multiple cards

```
uv run ankinote word batch <word1> <word2> ...
uv run ankinote sentence batch --file sentences.txt
uv run ankinote phrase batch "call off" --file more.txt
uv run ankinote stem batch --file topics.txt
```

Accepts inline arguments, `--file <path>` (one item per line), or both.
Use `--rpm <N>` to set the rate limit (defaults: 8 for `word`, 60 for `phrase`/`sentence`, 10 for `stem`).

### `init` — Create note type and deck

```
uv run ankinote word init
uv run ankinote sentence init
uv run ankinote phrase init
uv run ankinote stem init
```

Must be run once before adding cards to a new collection. Creates the note type and deck in Anki.

## Workflows

### First-time setup

```bash
uv run ankinote word init
uv run ankinote word add serendipity
```

### Batch import from file

```bash
cat > words.txt << EOF
ephemeral
eloquent
ubiquitous
EOF
uv run ankinote word batch --file words.txt --rpm 30
```

For STEM-specific workflows (diagrams, reference images, card-type selection), see [references/stem.md](references/stem.md).

## Troubleshooting

See [references/troubleshooting.md](references/troubleshooting.md).
