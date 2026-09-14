# STEM collection specifics

`stem` cards are language-agnostic (no `--native`/`--target`) and support generated diagrams.

## Options

```
--image-size <pixels>    # Image size in pixels (square); default 512
--image-model <id>       # Image model for diagram generation (default: gpt-image-1.5, low quality)
--type <auto|...>        # Force a specific card type instead of auto-detecting from the topic
```

`add` additionally accepts:

```
--image <path>           # Attach a local reference image alongside the generated content
```

`batch` rate limit default is 10 rpm (not the 60 used by `phrase`/`sentence`).
`--thinking` defaults to `high` for stem (unlike `word`/`phrase`/`sentence`, which default to off).

## Example

```bash
uv run ankinote stem add "What is a derivative?" --image-size 1024
uv run ankinote stem add "Explain the CAP theorem" --type auto --image ./diagram.png
```
