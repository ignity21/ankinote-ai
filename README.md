# ankinote

<p align="center">
  <a href="https://pypi.org/project/ankinote-ai/"><img src="https://img.shields.io/pypi/v/ankinote-ai?color=blue&logo=pypi&logoColor=white" alt="PyPI version"></a>
  <a href="https://pypi.org/project/ankinote-ai/"><img src="https://img.shields.io/pypi/pyversions/ankinote-ai?color=blue&logo=python&logoColor=white" alt="Python versions"></a>
  <a href="https://github.com/ignity21/ankinote-ai/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/ankinote-ai?color=blue" alt="License"></a>
  <a href="https://codecov.io/gh/ignity21/ankinote-ai"><img src="https://img.shields.io/codecov/c/github/ignity21/ankinote-ai?logo=codecov&logoColor=white" alt="Codecov"></a>
</p>

> AI-powered Anki card generator — vocabulary, phrases, sentences, and STEM concepts

## 📖 About

ankinote is an automated Anki flashcard generator that uses litellm to support a wide range of AI providers — Gemini, GPT, Claude, DeepSeek, and more — for generating definitions, examples, mnemonics, and images, then syncs directly with Anki through AnkiConnect.

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
- Anki with [AnkiConnect](https://ankiweb.net/shared/info/2055492159) plugin installed
- An API key for at least one AI provider (see Configuration below)

### Installation

```bash
# Install from PyPI
uv pip install ankinote-ai

# Or install the CLI as an isolated uv tool
uv tool install ankinote-ai

# Configure API credentials
# Create a .env file in your working directory and add your API keys
```

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

The in-process backend requires `ankinote-ai[headless]`,
`ANKI_BACKEND=collection`, and `ANKI_COLLECTION_PATH` pointing to a collection
file (for example `/data/collection.anki2`). Set both `ANKIWEB_USERNAME` and
`ANKIWEB_PASSWORD` to configure AnkiWeb externally. These override a saved login;
the password is never written to the credential file. The default backend remains
AnkiConnect.

The direct backend synchronizes at startup, after each note save or note-type
setup batch, and every five minutes. A fresh collection blocks writes until its
initial collection sync completes. An initialized collection remains writable
when offline; collection and media sync outcomes are tracked separately. A
required full sync blocks writes until an explicit upload/download choice is
resolved. The Settings page has an **AnkiWeb sync** panel for login/logout,
status, manual sync, the sync interval, and the upload/download choice; the
`ankinote anki login|logout|status|sync` commands cover the same from the CLI.

Beside the collection file, `.sync.json` stores credential-free status,
`.credentials.json` stores saved login credentials with mode `0600`, `.account`
retains an account binding after logout, and `.backups/` holds recoverable
collection backups made before full sync. Logout removes the saved credential
and pauses synchronization without deleting the collection or media. Externally
configured credentials apply again on process restart. Use a different data
directory to switch accounts. Open a collection from only one process at a time.

### Fal images in the web UI

For Word and STEM cards, select a `Fal` image provider profile with base URL
`https://fal.run` and your Fal API key (or set `FAL_AI_API_KEY`). These profiles
call Fal's model endpoints directly. Use a full endpoint such as
`fal-ai/z-image/turbo`; `z-image/turbo` and the LiteLLM-style
`fal_ai/fal-ai/z-image/turbo` are also accepted. `image_size` controls the maximum
edge of the downloaded image, preserving its aspect ratio.

The provider editor's refresh button lists active `text-to-image` endpoint IDs
from Fal's Platform API. It works without a key and uses the saved Fal key for a
higher rate limit when one is available; inference still uses `https://fal.run`.

### Run the web GUI with Docker

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
AnkiConnect host setup, and building locally.

Container env vars:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANKI_BACKEND` | `connect` | `connect` (AnkiConnect) or `collection` (in-process, used by `deploy/headless`) |
| `ANKI_CONNECT_URL` | `http://host.docker.internal:8765` | Where AnkiConnect lives (`connect` backend) |
| `ANKI_COLLECTION_PATH` | – | Collection file to open; required for `ANKI_BACKEND=collection` |
| `ANKIWEB_USERNAME` / `ANKIWEB_PASSWORD` | – | Optional AnkiWeb login for the `collection` backend; overrides a UI login, password never stored |
| `ANKINOTE_STORAGE_SECRET` | (built-in) | NiceGUI session-signing key — set a random value |
| `ANKINOTE_HOST` / `ANKINOTE_PORT` | `0.0.0.0` / `8080` | Bind address inside the container |
| `ANKINOTE_SHOW` | `false` in the image | Whether to open a browser on start |

The published image bundles the `anki` library, so both backends work without a
custom build. `ANKI_CONNECT_URL` is also honoured when running ankinote outside
Docker (e.g. a remote Anki).

# ankinote CLI - Usage Guide

## Overview

The ankinote CLI is a powerful command-line tool for generating AI-powered Anki flashcards with automatic definitions, examples, pronunciations, audio, and images.

## Commands

The CLI currently provides four collection entrypoints. Run `ankinote <type> --help` or
`ankinote <type> <command> --help` for the complete, current option list.

### Word cards

```bash
# Create the word note type and deck in Anki
ankinote word init

# Add one word
ankinote word add serendipity

# Add multiple words, either as arguments or from a file
ankinote word batch serendipity ephemeral eloquent
ankinote word batch --file words.txt
```

### Phrase cards

```bash
ankinote phrase init
ankinote phrase add "look after"
ankinote phrase batch "focus on" "call off"
ankinote phrase batch --file phrases.txt
```

### Sentence cards

The sentence argument should be in the native language; the target-language
version is generated for the card back.

```bash
ankinote sentence init
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

## Troubleshooting

### Error: "AnkiConnect not available"
- Make sure Anki is running
- Check that AnkiConnect add-on is installed
- Verify AnkiConnect is listening on port 8765

### Error: "No images found"
- Some STEM topics may not need a generated diagram
- Check the configured image model with `ankinote stem add --help`

### Error: "API key not found"
- Check your configuration file
- Ensure environment variables are set
- Verify API keys are valid

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
- [Skill](skills/ankinote-cli/SKILL.md) — for using ankinote with AI coding assistants

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details
