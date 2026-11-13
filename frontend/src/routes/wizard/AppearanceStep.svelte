<script lang="ts">
  import StepNav from "../../components/StepNav.svelte";
  import { t, type MessageKey } from "../../lib/i18n.svelte";
  import { palettes, theme, type Mode } from "../../lib/theme.svelte";

  let { onback, onnext }: { onback: () => void; onnext: () => void } = $props();

  const modes: Mode[] = ["system", "light", "dark"];

  // Choices apply live; Skip puts back what the user had on arrival.
  const entry = { palette: theme.palette, mode: theme.mode };

  function skip() {
    theme.palette = entry.palette;
    theme.mode = entry.mode;
    onnext();
  }

  /** The palette's own colours, so each swatch previews itself. */
  function swatchStyle(values: Record<string, string>): string {
    return Object.entries(values)
      .map(([role, value]) => `--s-${role}: ${value}`)
      .join("; ");
  }
</script>

<p class="intro">{t("appearance.intro")}</p>

<fieldset>
  <legend>{t("appearance.palette")}</legend>
  <div class="grid">
    {#each palettes as p (p.id)}
      {@const values = theme.dark ? p.dark : p.light}
      <label class="opt">
        <input
          type="radio"
          name="palette"
          value={p.id}
          checked={theme.palette === p.id}
          onchange={() => (theme.palette = p.id)}
        />
        <span class="swatch" style={swatchStyle(values)} aria-hidden="true">
          <span class="mini">
            <span class="mini-title">{p.name.toLowerCase()}</span>
            <span class="mini-word">moon <span class="mini-sound">/muːn/</span></span>
            <span class="mini-line">the <b>moon</b> rose</span>
            <span class="mini-foot">
              <span class="mini-button"></span>
              <span class="dot ok"></span><span class="dot warn"></span><span class="dot err"></span>
            </span>
          </span>
        </span>
        <span class="name">{p.name}</span>
        <span class="sub">{t(`appearance.why.${p.id}` as MessageKey)}</span>
      </label>
    {/each}
  </div>
</fieldset>

<fieldset>
  <legend>{t("appearance.mode")}</legend>
  <div class="segments">
    {#each modes as mode (mode)}
      <label class="seg">
        <input
          type="radio"
          name="mode"
          value={mode}
          checked={theme.mode === mode}
          onchange={() => (theme.mode = mode)}
        />
        {t(`bar.mode.${mode}`)}
      </label>
    {/each}
  </div>
  {#if theme.mode === "system"}
    <p class="note">
      {t("appearance.system", { mode: t(theme.dark ? "appearance.system.dark" : "appearance.system.light") })}
    </p>
  {/if}
</fieldset>

<StepNav {onback} onskip={skip} {onnext} hint={t("appearance.skipNote")} />

<style>
  .intro {
    max-width: 62ch;
    margin: 0 0 20px;
  }

  fieldset {
    margin: 0 0 20px;
    padding: 0;
    border: 0;
    min-width: 0;
  }

  legend {
    padding: 0;
    margin-bottom: 10px;
    font-weight: 600;
  }

  .grid {
    display: grid;
    /* Four across on desktop, two on a phone. */
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 10px;
    max-width: 980px;
  }

  .opt {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px 8px 10px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--outer);
    cursor: pointer;
  }

  /* The radio stays focusable and announced; the tile is what shows. */
  .opt input,
  .seg input {
    position: absolute;
    opacity: 0;
    width: 1px;
    height: 1px;
    margin: 0;
  }

  .opt:hover {
    border-color: var(--muted);
  }

  .opt:has(input:checked) {
    border-color: var(--accent);
    background: var(--sel);
  }

  .opt:has(input:focus-visible),
  .seg:has(input:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .name {
    margin-top: 6px;
    padding: 0 4px;
    font-weight: 600;
  }

  .sub {
    padding: 0 4px;
    font-size: 13px;
    color: var(--muted);
  }

  /* A tiny tiled pane drawn in the palette's own colours. */
  .swatch {
    display: block;
    padding: 12px 8px 8px;
    border-radius: 6px;
    background: var(--s-outer);
  }

  .mini {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 12px 10px 8px;
    border: 2px solid var(--s-accent);
    border-radius: 7px;
    background: var(--s-tile);
    color: var(--s-fg);
    font-size: 13px;
    line-height: 1.35;
  }

  .mini-title {
    position: absolute;
    top: -9px;
    left: 8px;
    padding: 0 4px;
    background: var(--s-tile);
    color: var(--s-muted);
    font-family: var(--mono);
    font-size: 11px;
    line-height: 16px;
  }

  .mini-word {
    font-size: 17px;
    font-weight: 600;
  }

  .mini-sound {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 400;
    color: var(--s-muted);
  }

  .mini-line b {
    font-weight: 600;
    color: var(--s-accent2);
  }

  .mini-foot {
    display: flex;
    align-items: center;
    gap: 5px;
    margin-top: 6px;
  }

  .mini-button {
    width: 44px;
    height: 12px;
    margin-right: auto;
    border-radius: 3px;
    background: var(--s-accent);
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .dot.ok {
    background: var(--s-ok);
  }

  .dot.warn {
    background: var(--s-warn);
  }

  .dot.err {
    background: var(--s-err);
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

  .seg {
    display: inline-flex;
    align-items: center;
    min-height: 36px;
    padding: 0 14px;
    border-radius: 6px;
    cursor: pointer;
  }

  .seg:hover {
    background: var(--tile);
  }

  .seg:has(input:checked) {
    background: var(--sel);
  }

  fieldset > .note {
    margin: 8px 0 0;
  }
</style>
