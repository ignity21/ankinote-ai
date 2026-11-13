<script lang="ts">
  import CardPreview from "./CardPreview.svelte";
  import { cardTheme, PREVIEW_TYPES, type PreviewType } from "../lib/cardTheme.svelte";
  import { t, type MessageKey } from "../lib/i18n.svelte";
  import en from "../lib/locales/en.json";
  import { palettes, theme } from "../lib/theme.svelte";

  const modes = ["light", "dark"] as const;
  const sample = $derived(cardTheme.samples[cardTheme.sampleKey()]);
  /** The last sample that loaded, shown while the next one is on its way. */
  let shown = $state<Exclude<typeof sample, "failed" | undefined>>();
  const app = $derived(palettes.find((p) => p.id === theme.palette)!);
  const matchesApp = $derived(cardTheme.light === app.id && cardTheme.dark === app.id);

  $effect(() => {
    if (cardTheme.saved) void cardTheme.sample();
  });

  $effect(() => {
    if (sample && sample !== "failed") shown = sample;
  });

  function nameOf(id: string): string {
    return palettes.find((p) => p.id === id)?.name ?? id;
  }

  function typeName(key: PreviewType): string {
    return key === "stem_concept" ? t("generate.kind.stem") : t(`generate.kind.${key}`);
  }

  /** The palette's own colours, so each tile previews itself. */
  function swatchStyle(values: Record<string, string>): string {
    return Object.entries(values)
      .map(([role, value]) => `--s-${role}: ${value}`)
      .join("; ");
  }

  function matchApp() {
    cardTheme.pick("light", app.id);
    cardTheme.pick("dark", app.id);
    cardTheme.night = theme.dark;
  }

  function failureText(code: string, detail: string): string {
    const own = `notetypes.err.${code}`;
    const anki = `anki.err.${code}`;
    const key = own in en ? own : anki in en ? anki : "anki.err.error";
    return t(key as MessageKey, { url: detail, path: "", detail });
  }
</script>

<div class="picker">
  {#if cardTheme.loadError}
    <p class="intro">{t("cardtheme.intro")}</p>
    <p class="error" role="alert">{t("cardtheme.err.load")}</p>
  {:else if cardTheme.saved}
    <div class="choose">
      <p class="intro">{t("cardtheme.intro")}</p>
      {#each modes as mode (mode)}
        <fieldset>
          <legend>{t(`cardtheme.${mode}`)}</legend>
          <div class="tiles">
            {#each palettes as p (p.id)}
              <label class="tile" class:on={cardTheme[mode] === p.id}>
                <input
                  type="radio"
                  name="card-{mode}"
                  value={p.id}
                  checked={cardTheme[mode] === p.id}
                  onchange={() => cardTheme.pick(mode, p.id)}
                />
                <span class="swatch" style={swatchStyle(p[mode])} aria-hidden="true">
                  <span class="mini-word">moon</span>
                  <span class="mini-line">the <b>moon</b> rose</span>
                  <span class="mini-bar"></span>
                </span>
                <span class="name">{p.name}</span>
              </label>
            {/each}
          </div>
        </fieldset>
      {/each}

      {#if !matchesApp}
        <button class="link" onclick={matchApp}>{t("cardtheme.matchApp", { name: app.name })}</button>
      {/if}

      <div class="apply" aria-live="polite">
        <div class="row">
          <button class="primary" onclick={() => cardTheme.apply()} disabled={!cardTheme.changed || cardTheme.busy}>
            {cardTheme.busy ? t("cardtheme.applying") : t("cardtheme.apply")}
          </button>
          {#if cardTheme.changed && !cardTheme.busy}
            <button class="secondary" onclick={() => cardTheme.revert()}>{t("cardtheme.revert")}</button>
          {/if}
        </div>
        {#if cardTheme.saveError}
          <p class="error" role="alert">{t("cardtheme.err.save")}</p>
        {:else if cardTheme.outcome?.anki}
          <p class="warn" role="status">
            {t("cardtheme.savedOnly", {
              reason: failureText(cardTheme.outcome.anki.code, cardTheme.outcome.anki.detail),
            })}
          </p>
        {:else if cardTheme.outcome}
          <p class="done" role="status">
            <span aria-hidden="true">✓</span>
            {cardTheme.outcome.restyled.length
              ? t("cardtheme.done", { n: cardTheme.outcome.restyled.length })
              : t("cardtheme.doneNone")}
          </p>
        {:else}
          <p class="note">{cardTheme.changed ? t("cardtheme.applyNote") : t("cardtheme.unchanged")}</p>
        {/if}
      </div>
    </div>

    <section class="preview" aria-labelledby="theme-preview">
      <div class="preview-head">
        <h3 id="theme-preview" class="label">{t("cardtheme.preview")}</h3>
        <div class="segments" role="radiogroup" aria-label={t("cardtheme.previewType")}>
          {#each PREVIEW_TYPES as key (key)}
            <button
              role="radio"
              aria-checked={cardTheme.previewType === key}
              class:on={cardTheme.previewType === key}
              onclick={() => (cardTheme.previewType = key)}
            >
              {typeName(key)}
            </button>
          {/each}
        </div>
        <div class="segments" role="radiogroup" aria-label={t("cardtheme.previewMode")}>
          {#each modes as mode (mode)}
            <button
              role="radio"
              aria-checked={cardTheme.night === (mode === "dark")}
              class:on={cardTheme.night === (mode === "dark")}
              onclick={() => (cardTheme.night = mode === "dark")}
            >
              {t(`cardtheme.mode.${mode}`)} · {nameOf(cardTheme[mode])}
            </button>
          {/each}
        </div>
      </div>
      {#if sample === "failed"}
        <p class="error" role="alert">{t("notetypes.err.sample")}</p>
      {:else if shown}
        {#key shown.kind}
          <CardPreview note={shown} night={cardTheme.night} />
        {/key}
      {:else}
        <p class="note">{t("notetypes.sampleLoading")}</p>
      {/if}
    </section>
  {:else}
    <p class="intro">{t("cardtheme.intro")}</p>
    <p class="note">{t("notetypes.loading")}</p>
  {/if}
</div>

<style>
  .picker,
  .choose {
    display: flex;
    flex-direction: column;
    gap: 18px;
  }

  .picker {
    padding-bottom: 8px;
  }

  .intro {
    max-width: 62ch;
    margin: 0;
  }

  .note,
  .error,
  .warn,
  .done {
    margin: 0;
    font-size: 14px;
  }

  .note {
    color: var(--muted);
  }

  .error {
    color: var(--err);
  }

  .warn {
    color: var(--warn);
  }

  .done span {
    color: var(--ok);
  }

  fieldset {
    margin: 0;
    padding: 0;
    border: 0;
    min-width: 0;
  }

  legend {
    padding: 0;
    margin-bottom: 8px;
    font-weight: 600;
  }

  .tiles {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
  }

  .tile {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 6px;
    border: 2px solid var(--border);
    border-radius: 8px;
    cursor: pointer;
  }

  .tile.on {
    border-color: var(--accent);
  }

  .tile:has(input:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .tile input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }

  /* A card in miniature, in the palette's own colours. */
  .swatch {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px 10px;
    border-radius: 6px;
    background: var(--s-outer);
    color: var(--s-fg);
    box-shadow: inset 0 0 0 1px var(--s-border);
  }

  .mini-word {
    font-size: 18px;
    font-weight: 600;
    line-height: 1.2;
  }

  .mini-line {
    font-size: 12px;
    color: var(--s-muted);
  }

  .mini-line b {
    color: var(--s-accent2);
    font-weight: 600;
  }

  .mini-bar {
    width: 40%;
    height: 3px;
    margin-top: 4px;
    border-radius: 2px;
    background: var(--s-accent);
  }

  .name {
    font-size: 13px;
    padding: 0 2px;
  }

  .link {
    align-self: flex-start;
    margin-top: -8px;
    padding: 0;
    border: 0;
    background: none;
    color: var(--accent);
    font: inherit;
    font-size: 14px;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .apply {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px 0;
    border-block: 1px solid var(--border);
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .primary:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .preview {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }

  .preview-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 12px;
  }

  .segments {
    display: inline-flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 3px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--outer);
  }

  .segments button {
    min-height: 36px;
    padding: 0 12px;
    border: 0;
    border-radius: 6px;
    background: none;
    color: inherit;
    font: inherit;
    font-size: 14px;
    cursor: pointer;
  }

  .segments button:hover {
    background: var(--tile);
  }

  .segments button.on {
    background: var(--sel);
  }

  .label {
    margin: 0;
    font-size: 13px;
    font-weight: 400;
    color: var(--muted);
  }

  /* Wide: choices on the left, the card they make beside them. */
  @container app (min-width: 1001px) {
    .picker {
      display: grid;
      grid-template-columns: minmax(320px, 400px) minmax(0, 1fr);
      gap: 24px;
      align-items: start;
    }

    .tiles {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .preview {
      position: sticky;
      top: 0;
    }
  }

  @container app (max-width: 760px) {
    .tiles {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
