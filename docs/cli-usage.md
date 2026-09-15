# AnkiNote CLI — Usage Guide

The CLI (`ankinote`) is a scriptable, batch-friendly way to generate
AI-powered Anki flashcards from the terminal. Unlike the Web UI, it's
configured with a `.env` file / environment variables rather than in-browser
settings. If you don't need scripting or batch runs, the Web UI is the
easier way to get started — see the main [README](../README.md).

## Configuration

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
variables described in the [README's Web UI section](../README.md#what-still-needs-to-be-set-outside-the-browser)
apply the same way to the CLI — the in-process backend and AnkiWeb sync
aren't web-UI-only features.

> **No `ankinote config`/`ankinote settings` command yet.** There's currently
> no CLI subcommand to set API keys — only `.env` / environment variables, plus
> `ankinote anki login|logout|status|sync` for AnkiWeb. A generic config
> subcommand has been sketched in the past but never implemented; see
> [`docs/plans/`](plans/) if you pick this up — worth adding a plan doc for
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
