# AnkiNote

<p align="center">
  <img src="src/ankinote/ui/static/ankinote-logo.svg" width="96" alt="AnkiNote logo">
</p>

<p align="center">
  <a href="https://pypi.org/project/ankinote-ai/"><img src="https://img.shields.io/pypi/v/ankinote-ai?color=blue&logo=pypi&logoColor=white" alt="PyPI version"></a>
  <a href="https://pypi.org/project/ankinote-ai/"><img src="https://img.shields.io/pypi/pyversions/ankinote-ai?color=blue&logo=python&logoColor=white" alt="Python versions"></a>
  <a href="https://github.com/ignity21/ankinote-ai/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/ankinote-ai?color=blue" alt="License"></a>
  <a href="https://codecov.io/gh/ignity21/ankinote-ai"><img src="https://img.shields.io/codecov/c/github/ignity21/ankinote-ai?logo=codecov&logoColor=white" alt="Codecov"></a>
</p>

> AI-powered Anki card generator — vocabulary, phrases, sentences, and STEM concepts

## 📖 About

AnkiNote is an automated Anki flashcard generator that uses litellm to support a wide range of AI providers — Gemini, GPT, Claude, DeepSeek, and more — for generating definitions, examples, mnemonics, and images, then syncs directly with Anki through AnkiConnect.

## ✨ Features

- 🤖 **Multi-Provider AI** - Powered by litellm, supporting Gemini, GPT, Claude, DeepSeek, and more for text and image generation
- 🔊 **Audio Generation** - Text-to-Speech using Google Cloud TTS API
- 🖼️ **AI Image Generation** - Automatic image generation via Google AI (Gemini)
- 🔄 **Direct Anki Sync** - Seamless integration with Anki through AnkiConnect plugin
- 📝 **Dual-Direction Cards** - Supports both word→definition and definition→word learning modes
- 🎨 **Beautiful Templates** - Built-in Light/Dark mode responsive card templates
- ⚡ **Batch Processing** - Generate multiple cards from word lists efficiently
- 🌐 **Multi-Language** - Japanese, English (US), and extensible for more languages
- 🧮 **STEM Concepts** - Math, science, and programming concept cards with MathJax rendering

## 🚀 Quick Start

### Prerequisites

- Python 3.14+
- [uv](https://github.com/astral-sh/uv) package manager
- Anki with [AnkiConnect](https://ankiweb.net/shared/info/2055492159) plugin installed, **or** the in-process (headless) backend — see below

### Installation

```bash
# Install from PyPI
uv pip install ankinote-ai

# Or install the CLI/GUI as an isolated uv tool
uv tool install ankinote-ai
```

AnkiNote has two front ends that share the same card-generation engine:

- **Web UI** (`ankinote-gui`) — everything, including AI provider keys, is
  configured from the browser. No `.env` file needed. Start here if you're new.
- **CLI** (`ankinote`) — scriptable, batch-friendly, configured via `.env` /
  environment variables. See [CLI usage](#ankinote-cli---usage-guide) below.

---

## 🖥️ Web UI

### Launching

```bash
# From a uv-managed checkout
uv run ankinote-gui

# Or, if installed as a tool / into a venv
ankinote-gui
```

This opens `http://localhost:8080` in a browser (set `ANKINOTE_SHOW=false` to
skip auto-open, e.g. on a headless server). The UI has six pages, reachable
from the left drawer: **Word**, **Phrases**, **Sentences**, **STEM**, **Card
Types** (note type + deck setup), and **Settings**.

### Configuration — all in the Settings page

Nothing needs to be in a `.env` file for web UI use; every credential lives in
the browser-saved settings file and is applied to the process at save time.

- **Generation route (text)** and **Image route** — each is a rack of named
  provider profiles. Pick a vendor template (OpenAI, Anthropic, Gemini, Fal,
  etc.) or "Custom / Other" for any OpenAI-compatible endpoint, then fill in
  base URL, model (with a refresh button to fetch live model IDs), and API
  key. Multiple profiles per vendor are supported (e.g. two OpenAI accounts),
  and you switch which one is active by clicking its pill.
  - For Fal image generation, use a `Fal` profile with base URL
    `https://fal.run` and your Fal API key, with a full endpoint id such as
    `fal-ai/z-image/turbo`.
- **TTS (Google Cloud)** — paste the Google Cloud TTS API key.
- **Defaults** — native/target language and whether image generation is on by
  default for new cards.
- **AnkiWeb sync** — shown when the in-process backend is active (see below):
  login/logout, sync status, manual sync, sync interval, and the
  upload/download choice on a required full sync.
- **Backup & transfer** — export all provider profiles + the TTS key as a
  passphrase-encrypted JSON bundle (scrypt + AES-256-GCM), and import one back
  in, merged by profile name. Useful for moving settings between machines or
  backing them up.

### What still needs to be set outside the browser

A few things are process-level, not per-user settings, so they're still env
vars:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANKINOTE_HOST` / `ANKINOTE_PORT` | `0.0.0.0` / `8080` | Bind address for the web server |
| `ANKINOTE_STORAGE_SECRET` | built-in dev key | NiceGUI session-signing key — set a random value for anything beyond local use |
| `ANKINOTE_SHOW` | `true` | Whether to auto-open a browser tab on start |
| `ANKI_BACKEND` | `connect` | `connect` (talk to an existing Anki via AnkiConnect) or `collection` (in-process/headless) |
| `ANKI_CONNECT_URL` | `http://localhost:8765` | Where AnkiConnect lives (`connect` backend) |
| `ANKI_COLLECTION_PATH` | – | Collection file to open; required for `ANKI_BACKEND=collection`. Suggested: `~/.local/share/ankinote/collection.anki2` |
| `ANKIWEB_USERNAME` / `ANKIWEB_PASSWORD` | – | Optional: configure the `collection` backend's AnkiWeb login externally instead of through the Settings page; overrides a UI login, password never persisted to disk |

The in-process (`collection`) backend additionally requires the
`ankinote-ai[headless]` extra. It synchronizes with AnkiWeb at startup, after
each note save or note-type setup batch, and every five minutes. A fresh
collection blocks writes until its initial sync completes; an initialized
collection remains writable offline. A required full sync blocks writes until
you resolve the upload/download choice, in the Settings page or via
`ankinote anki sync`.

Data is stored in the directory containing the collection file (e.g.,
`~/.local/share/ankinote/`). Beside the collection file, `.sync.json` stores
credential-free status, `.credentials.json` stores saved login credentials with
mode `0600`, `.account` retains an account binding after logout, and `.backups/`
holds recoverable collection backups made before full sync. Logout removes the
saved credential and pauses synchronization without deleting the collection or
media. Use a different data directory to switch accounts. Open a collection from
only one process at a time.

### Run the web UI with Docker

Published images (multi-arch `amd64` + `arm64`): `ghcr.io/ignity21/ankinote-ai`
and `ignity21/ankinote-ai` (Docker Hub), tags `latest`, `<major>.<minor>`, and the
exact version.

Two ready-made compose stacks under [`deploy/`](deploy/):

```bash
cd deploy/standard        # GUI + an AnkiConnect you already run
# or: cd deploy/headless  # GUI with the in-process Anki backend, syncs to AnkiWeb
cp .env.example .env      # set ANKINOTE_STORAGE_SECRET (+ AnkiWeb login for headless)
docker compose up -d      # http://localhost:8080
```

AI provider keys are added in the web UI (Settings page), not `.env`. See
[`deploy/README.md`](deploy/README.md) for the difference between the stacks, the
AnkiConnect host setup, and building locally. The published image bundles the
`anki` library, so both backends work without a custom build.

---

# AnkiNote CLI - Usage Guide

## Overview

The AnkiNote CLI is a scriptable, batch-friendly way to generate AI-powered
Anki flashcards from the terminal. Unlike the web UI, it's configured with a
`.env` file / environment variables rather than in-browser settings.

### Configuration

Create a `.env` file with your API keys. At minimum, you need one AI provider key and the Google TTS key:

```env
# At least one AI provider (for text and image generation)
DEEPSEEK_API_KEY=your_deepseek_key
# GEMINI_API_KEY=your_gemini_key
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# XAI_API_KEY=xai-...          # for xAI image models

# Google Cloud TTS (for audio generation)
GOOGLE_TTS_KEY=your_tts_api_key

# AnkiConnect (defaults to http://localhost:8765)
ANKI_CONNECT_URL=http://localhost:8765
```

The `ANKI_BACKEND`, `ANKI_COLLECTION_PATH`, and `ANKIWEB_USERNAME`/`ANKIWEB_PASSWORD`
variables described above for the web UI apply the same way to the CLI — the
in-process backend and AnkiWeb sync aren't web-UI-only features.

> **No `ankinote config`/`ankinote settings` command yet.** There's currently
> no CLI subcommand to set API keys — only `.env` / environment variables, plus
> `ankinote anki login|logout|status|sync` for AnkiWeb. A generic config
> subcommand has been sketched in the past but never implemented; see
> [`docs/plans/`](docs/plans/) if you pick this up — worth adding a plan doc for
> it before starting.

## Commands

The CLI currently provides four collection entrypoints. Run `ankinote <type> --help` or
`ankinote <type> <command> --help` for the complete, current option list.

### Word, phrase, and sentence cards

`word`, `phrase`, and `sentence` all follow the same `init` / `add` / `batch`
shape — `init` creates the note type and deck, `add` takes one item, `batch`
takes several (as arguments or `--file`):

```bash
ankinote word init
ankinote word add serendipity
ankinote word batch serendipity ephemeral eloquent
ankinote word batch --file words.txt

ankinote phrase add "look after"
ankinote phrase batch --file phrases.txt

# sentence argument is in the native language; the target-language version
# is generated for the card back
ankinote sentence add "我今天起晚了。"
ankinote sentence batch --file sentences.txt
```

### STEM cards

```bash
ankinote stem init
ankinote stem add "What is a derivative?"
ankinote stem add "State Newton's second law" --type formula
ankinote stem add "How do I invert a matrix?" --type procedure
ankinote stem add "Solve the problem in this photo" --type example --image problem.png
ankinote stem batch --file topics.txt
ankinote stem batch --file problems.txt --type example
```

STEM uses four independent note types: `AINote STEM Concept`, `AINote STEM
Formula`, `AINote STEM Procedure`, and `AINote STEM Example`, all in the
`AINote::STEM` deck. Each has its own fields and templates, with `front` first
for duplicate detection and default sorting. Formula variables, solution steps,
and images are stored in dedicated fields; tags use Anki's native tag store.

`--type auto` (the default) first classifies the request, then generates with the
selected type's schema and prompt. Choosing a type skips that extra AI request.
`stem init` initializes all four types; `stem init --type concept` initializes
only Concept. The GUI supports the same type selection and previews every type
for editing before saving, including variables, steps, tags, and diagram prompts.

The old `AINote STEM` type is no longer managed. Existing test notes are left
untouched; this change does not migrate or delete them. Initialize the new types
using `ankinote stem init` or the GUI's Card Types page.

### Common options

Language-learning commands accept `--native`, `--target`, and `--llm`.
Batch commands also accept `--file` and `--rpm`. STEM commands accept
`--llm`, and can additionally configure diagram generation with
`--image-model` and `--image-size`.

`--llm` and `--image-model` take any model id LiteLLM recognizes; the
provider is inferred from the id and its key is read from the matching
environment variable. Defaults are `gpt-5.6-luna` for text and
`gpt-image-1.5` (quality `low`) for images — neither default matters much
in practice since any provider works, including fal.ai. Examples:

- `--llm`: `gpt-5.6-luna`, `deepseek/deepseek-v4-flash`, `gemini/gemini-2.5-pro`,
  `claude-sonnet-4-20250514`
- `--image-model`: `gpt-image-1.5`, `gemini/gemini-3.1-flash-lite-image`,
  `fal_ai/fal-ai/flux/schnell`, `xai/grok-2-image`

For example:

```bash
ankinote word add serendipity --native English --target 'Chinese(Simplified)'
ankinote word batch --file words.txt --rpm 30
ankinote stem add "State Bayes' theorem" --image-model gpt-image-1 --image-size 1024
```

## Getting Help

```bash
# General help
ankinote --help

# Command-specific help
ankinote word --help
ankinote phrase --help
ankinote sentence --help
ankinote stem --help
ankinote word batch --help
```

## 📦 Tech Stack

- **Language**: Python 3.14+
- **Package Manager**: uv
- **AI/ML**: litellm (OpenAI, Gemini, Claude, DeepSeek, fal.ai, etc.)
- **TTS**: Google Cloud Text-to-Speech API
- **Image Generation**: OpenAI (gpt-image), Gemini, fal.ai
- **Anki Integration**: AnkiConnect
- **Card Templates**: HTML + CSS

## 🔧 API Services

### AI Provider (via litellm)
- Text generation for definitions, examples, and mnemonics
- Image generation (Gemini) for card visuals
- Supports Gemini, GPT, Claude, DeepSeek, Qwen, and more

### Google Cloud TTS
- High-quality audio generation
- Multiple voice options

### AnkiConnect
- Direct communication with Anki
- Real-time card creation
- Deck management

## 📝 Usage Examples

### Single Word

```python
from ankinote import CardGenerator

generator = CardGenerator()
card = generator.generate("ephemeral")
generator.add_to_anki(card, deck="Vocabulary")
```

### Batch Processing

```python
words = ["ephemeral", "serendipity", "eloquent"]
for word in words:
    card = generator.generate(word)
    generator.add_to_anki(card)
```

## 🛠️ Development

```bash
# Clone the repository
git clone https://github.com/ignity21/ankinote-ai.git
cd ankinote-ai

# Install the project and development dependencies
uv sync

# Run tests
make test

# Format code
make format

# Type checking
make check
```

## Documentation
- [Note Types](docs/NoteType.md)
- [Skill](skills/ankinote-cli/SKILL.md) — for using AnkiNote with AI coding assistants

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details
