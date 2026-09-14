# Troubleshooting

- **"AnkiConnect not available"**: Make sure Anki is running and the AnkiConnect addon is installed. If instead using the in-process collection backend, check `ANKI_BACKEND=collection` and `ANKI_COLLECTION_PATH` are set correctly — see [anki-sync.md](anki-sync.md).
- **"API key not found"**: Set at least one provider key (`DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `XAI_API_KEY`) in the environment or `.env` file.
- **Model not found**: The default model strings resolve to provider-specific IDs. Override with `--llm` (text) or `--image-model` (images) if needed.
- **AnkiWeb sync fails**: Confirm `anki login` succeeded (`ankinote anki status`) and that `ANKI_BACKEND=collection` is set — sync only applies to the in-process backend.
