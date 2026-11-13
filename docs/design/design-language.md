# Design Language (1.0)

Status: direction B "tiling + named palettes" chosen 2026-11-12. The mocks
live on the private design canvas (rows C and D are the current ones); this
file is the source of truth when the two disagree.

One token set drives both the web UI and the Anki cards: the user picks a
palette and a light/dark mode once, and the cards they study look like the
preview they generated them in.

## Principles

- **Tiled panes, not cards.** The screen is split into gapped panes on a
  darker outer background, like a tiling window manager. Each pane's title
  sits in its top border. The pane that has focus gets the accent border;
  that is the only "active" signal, so don't add others.
- **Named palettes, not a brand colour.** Personality comes from four
  well-known editor palettes. The product has no colour of its own beyond
  the chosen palette's accent.
- **Monospace for the machine, sans for the human.** Status, counts, deck
  names, keys and pane titles are mono; everything a person reads or writes
  as language is sans.
- **Keyboard first on desktop, thumb first on phone.** Keyboard hints are
  shown on desktop and tablet and hidden on phone.
- **Errors say what happened and what to do next**, in the interface's voice
  ("The model didn't respond within 30 seconds. Select Regenerate to try
  again."). Empty states invite the next action.

## Palettes

Each palette defines the same 12 roles, in light and dark. Default palette
is Kanagawa; default mode follows the system.

| Role | Use |
| --- | --- |
| `--outer` | page background, the gaps between panes, input wells |
| `--tile` | pane background |
| `--border` | pane and control borders |
| `--fg` / `--muted` | body text / secondary text and pane titles |
| `--accent` | focus border, primary button, links, active workspace |
| `--accent2` | highlighted word in examples, emphasis in card bodies |
| `--ok` / `--warn` / `--err` | saved / in progress / failed |
| `--sel` | selected list row, active segment, chip fill |
| `--on-accent` | text on `--accent` fills |

| Palette | Mode | outer | tile | border | fg | muted | accent | accent2 | ok | warn | err | sel | on-accent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Kanagawa | dark | `#16161D` | `#1F1F28` | `#363646` | `#DCD7BA` | `#A3A08F` | `#7E9CD8` | `#E6C384` | `#98BB6C` | `#FFA066` | `#E46876` | `#2D4F67` | `#16161D` |
| Kanagawa | light | `#E4DCB0` | `#F2ECBC` | `#CFC79A` | `#545464` | `#6A6960` | `#4D699B` | `#A35100` | `#5A7140` | `#A35100` | `#B23548` | `#D7DCC8` | `#F2ECBC` |
| Tokyo Night | dark | `#16161E` | `#1A1B26` | `#2F334D` | `#C0CAF5` | `#9099C5` | `#7AA2F7` | `#E0AF68` | `#9ECE6A` | `#FF9E64` | `#F7768E` | `#283457` | `#16161E` |
| Tokyo Night | light | `#CDD2E2` | `#E1E2E7` | `#BFC4D8` | `#3760BF` | `#4F5679` | `#2960B8` | `#8C5A16` | `#4F6A2E` | `#964D08` | `#B8264F` | `#C4CDEB` | `#FFFFFF` |
| Gruvbox | dark | `#1D2021` | `#282828` | `#3C3836` | `#EBDBB2` | `#A89984` | `#FABD2F` | `#8EC07C` | `#B8BB26` | `#FE8019` | `#FD5F4A` | `#3C3836` | `#1D2021` |
| Gruvbox | light | `#EBDBB2` | `#FBF1C7` | `#D5C4A1` | `#3C3836` | `#665C54` | `#AF3A03` | `#076678` | `#6A660C` | `#9A5A0E` | `#9D0006` | `#EBDBB2` | `#FBF1C7` |
| Rosé Pine | dark | `#191724` | `#1F1D2E` | `#393552` | `#E0DEF4` | `#A6A3C2` | `#C4A7E7` | `#F6C177` | `#9CCFD8` | `#F6C177` | `#EB6F92` | `#2A273F` | `#191724` |
| Rosé Pine | light | `#F2E9E1` | `#FFFAF3` | `#DFDAD9` | `#575279` | `#6E6A8A` | `#7A6397` | `#A5546B` | `#286983` | `#A1650F` | `#A5546B` | `#F2E9E1` | `#FFFAF3` |

Several values are adjusted from the upstream palettes so every text role
(`fg` through `err`) reaches WCAG AA (4.5:1) on `--tile`, and `--on-accent`
reaches it on `--accent` (checked 2026-11-12; four values were darkened or
lightened from the first mock: Tokyo Night light accent and warn, Gruvbox
dark err, Gruvbox light ok). Re-check contrast whenever a value changes.

## Type

- Sans: IBM Plex Sans, then the system's Chinese face: `"PingFang SC",
  "Hiragino Sans GB", "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans
  SC", "Microsoft YaHei"`. Mono: IBM Plex Mono with the same CJK fallbacks.
  Text marked `lang="ja"`, `"ko"` or `"zh-Hant"` puts that language's faces
  first (Japanese kanji forms, a Hangul font). Self-host the Plex files (`woff2`, Latin subset plus IPA
  extensions); never load fonts from a CDN at runtime.
- UI body 15px / 1.5. Card body 16px / 1.6. Pane titles, status and keys
  13px mono (12px for `kbd`). Card headword 40–48px sans semibold. Sentence
  case everywhere; no all-caps labels.

## Shape and spacing

- Pane: 2px border, radius 10px, padding 22px top / 16px sides. Title is
  13px mono on the tile background, overlapping the top border at `left:12px`.
- Gaps between panes: 10px (8px on phone). Controls: radius 8px for
  buttons and inputs, 6px for chips and segments, 4px for `kbd` and tags.
- Touch targets: at least 44px tall for primary and secondary buttons,
  36px for segments and checkboxes.
- Focus: `outline: 2px solid var(--accent); outline-offset: 2px` on
  `:focus-visible`.

## Layout

Layouts switch on the app container's width (container queries), not on
device type.

| Width | Who | Generate page |
| --- | --- | --- |
| > 1000px | desktop, iPad landscape (1180) | left column 360px: input over queue; preview fills the right |
| 601–1000px | iPad portrait (820) | input spans the top; queue 250px left, preview right |
| ≤ 600px | phone | queue as a horizontal chip strip on top, preview in the middle, input pinned to the bottom with a send button |

The top bar holds the brand, workspaces (`1 Generate`, `2 Note types`,
`3 Settings`, switchable with the number keys), connection status and the
palette / mode / language switches.

## Interaction conventions

- Generating never blocks: each request becomes a queue row (glyph + word +
  status), and the preview follows the selected row. Batch input is one item
  per line.
- Preview shows the real card templates (Recognition / Recall / Spelling) and
  front/back, rendered with the same CSS that goes into Anki.
- Save, Regenerate and Edit stay visible under the preview at every size.
- Keys on desktop and tablet: `Ctrl+Enter` generates (plain `Enter` is a new
  line, because batch input is multi-line); `1`–`3` switch workspaces when
  focus is not in a text field. On phone, `Enter` in the single-line input
  generates.
- Missing capabilities degrade visibly, not silently: a card saved without
  images says "No image: no image model is set up."

## First-run wizard

Five steps. Desktop and tablet show a step list on the left (done steps can
be revisited); phone shows "Step 2 of 5" with a segmented progress bar.

1. **Connect an AI model.** Recommends one setup: Google Gemini for text,
   images and audio with a single AI Studio key (decided 2026-11-13). The
   step explains how to get the key, that image generation needs billing
   turned on for the key's project (Gemini's free tier draws no images), and
   that no other APIs or permissions are needed; then the key field and the
   model each route will use. "Test connection" lists text / image / audio,
   each with its model and "You can change models any time in Settings →
   Models." Text is checked with a real one-word request ("Works"); image and
   audio only against the provider's model list ("Available"), so testing
   never pays for an image. A Gemini image route that passes says that it
   still needs billing, since listing can't tell. Next stays disabled until
   text works. A collapsed "Use another provider, or choose models" section
   is the per-route editor Settings uses: each route can switch provider
   (with its own key), model, or be turned off. It offers what 0.x offered
   plus DeepSeek and the newer speech models: text from Gemini, OpenAI,
   Claude, DeepSeek or any OpenAI-compatible service; images from Gemini,
   OpenAI, FAL.AI or OpenAI-compatible; audio from Gemini, OpenAI or Google
   Cloud TTS. It opens by itself when a saved setup differs from the default,
   and its intro points users who can't reach Google to DeepSeek.
2. **Connect Anki.** Built-in Anki with AnkiWeb login (recommended) or Anki
   Desktop via AnkiConnect. The password is used once to log in; only the
   login token AnkiWeb returns is stored (`anki_sync_driver.py` keeps the
   hkey and endpoint). After connecting, note types and decks are created
   automatically and the step shows the list with "Your existing cards are
   not changed."
   Built 2026-11-13: Built-in is preselected unless Anki Desktop was saved
   before. The first AnkiWeb sync of a fresh collection usually needs a full
   sync: when Anki offers one direction (the other side is empty) the step
   explains it and offers a single "Download from AnkiWeb" / "Upload to
   AnkiWeb" button; when both directions are possible it asks which
   collection to keep, with nothing preselected, and the button names what
   gets replaced. A deployment-set AnkiWeb account (`ANKIWEB_USERNAME`)
   hides the login form. Anki Desktop shows the AnkiConnect setup steps
   (add-on code `2055492159`) and the address it uses.
3. **Languages.** Native ("Language you know best") and target ("Language
   you're learning") as two radio-tile grids, each language named in itself
   (`日本語`, `Français`) with its name in the interface language below.
   The native's own tile is disabled in the target grid ("Your language"),
   and picking a native that equals the target clears the target. A fresh
   install (saved pair still the factory Chinese (Simplified) → English)
   preselects the native from the browser language. An example card
   ("moon" in the target, its meaning in the native) updates live; beta
   targets carry a `beta` tag and a note. Built 2026-11-13.
4. **Appearance** (skippable). Palette swatches and follow system / light /
   dark; the whole app re-themes live. Built 2026-11-13: each palette is a
   radio tile with a miniature pane drawn in its own colours (for the mode
   currently showing) and a one-line note on where it comes from; mode is a
   three-way segment. Skip puts back the palette and mode the user had when
   the step opened. The choice is kept in the browser, like the top-bar
   switches; it isn't in `settings.json` yet.
5. **First card.** Generate a sample word, preview it, save it to Anki; the
   wizard ends on the saved confirmation.

The canvas mock still shows six steps with a separate "Prepare note types"
step; the flow above supersedes it.

## Cards

- The card CSS is generated from the same palette tokens: light values on
  `.card`, dark values under `.nightMode .card, .night_mode .card` so Anki's
  own night mode switches them on every client.
- Card fonts ship as collection media (`_IBMPlexSans-*.woff2`; the leading
  underscore keeps Anki's "check media" from deleting them) so AnkiDroid and
  AnkiMobile render the same type offline.
- Note fields and card templates stay as they are; any field change is
  proposed to the project owner before it is made. Field HTML has
  class names baked in at generation time, so the new CSS must style every
  class selector the current `card_templates/*/style.css` files style.
- Restyling updates every existing card of that note type at once. Mark the
  CSS with `/* ankinote-style: 1.0 */` instead of bumping note-type names.
- To verify before shipping: a CSS-only note-type update does not force a
  full AnkiWeb sync.
