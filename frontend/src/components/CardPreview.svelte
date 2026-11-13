<script lang="ts">
  import type { CardSide, DraftNote, MathError } from "../lib/api";
  import { t, type MessageKey } from "../lib/i18n.svelte";
  import { theme } from "../lib/theme.svelte";
  import en from "../lib/locales/en.json";
  import frameScript from "../lib/previewFrame.js?raw";
  import mathjaxUrl from "mathjax/es5/tex-svg-full.js?url";

  let {
    note,
    cards = note.cards,
    back = $bindable(false),
    night,
    onmath,
  }: {
    note: DraftNote;
    /** What to show instead of the note's cards (a live edit). */
    cards?: CardSide[];
    back?: boolean;
    /** Anki's night mode; follows the app's mode when omitted. */
    night?: boolean;
    /** Called after each typeset of a STEM card with what failed. */
    onmath?: (errors: MathError[]) => void;
  } = $props();

  let index = $state(0);
  let height = $state(320);
  let frame = $state<HTMLIFrameElement>();
  /** The frame document that said it's ready for content. */
  let readyDoc = $state("");

  const card = $derived(cards[Math.min(index, cards.length - 1)]!);
  const math = $derived(note.kind === "stem");

  // Anki's reviewer draws the replay button itself; this is its look, so the
  // card CSS (which only sizes the icon) previews the way Anki shows it.
  const CHROME = `
    body { margin: 0; }
    body.card { min-height: 0 !important; }
    .replay-button { display: inline-block; cursor: pointer; text-decoration: none; }
    .replay-button svg { width: 40px; height: 40px; }
    .replay-button svg circle { fill: #fff; stroke: #414141; stroke-width: 4px; }
    .replay-button svg path { fill: #414141; }
    .nightMode .replay-button svg circle { fill: #3a3a3a; stroke: #cfcfcf; }
    .nightMode .replay-button svg path { fill: #e8e8e8; }
    .preview-error { color: #c00; font-family: monospace; }
    mjx-container[jax="SVG"] > svg { overflow: visible; }
  `;

  /**
   * The frame the card shows in, as Anki would show it. Sandboxed without
   * same-origin, and the CSP lets only this page's own script (and MathJax,
   * which it loads) run: nothing in a field can reach the app. The card
   * itself is sent by message, so a change doesn't reload the frame.
   */
  const frameDoc = $derived.by(() => {
    const nonce = crypto.randomUUID();
    const origin = location.origin;
    const csp = [
      "default-src 'none'",
      `img-src ${origin} data:`,
      `media-src ${origin}`,
      `font-src ${origin} data:`,
      "style-src 'unsafe-inline'",
      `script-src 'nonce-${nonce}'`,
    ].join("; ");
    const mathjax = math ? new URL(mathjaxUrl, origin).href : "";
    const srcdoc = `<!doctype html><html data-doc="${nonce}" data-mathjax="${mathjax}"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<base href="${origin}/"><meta name="viewport" content="width=device-width">
<style>${CHROME}</style><style>${note.css}</style></head>
<body class="card"><div id="qa"></div>
<script nonce="${nonce}">${frameScript}<\/script></body></html>`;
    return { id: nonce, srcdoc };
  });

  // Send the card once the frame is ready, and again on every change.
  $effect(() => {
    const mode = (night ?? theme.dark) ? " nightMode night_mode" : "";
    const content = { html: back ? card.back : card.front, cls: `card card${index + 1}${mode}` };
    if (readyDoc !== frameDoc.id) return;
    frame?.contentWindow?.postMessage({ ankinotePreview: content }, "*");
  });

  function onMessage(event: MessageEvent) {
    if (!frame || event.source !== frame.contentWindow) return;
    const data = event.data as { doc?: string; height?: unknown; ready?: boolean; math?: MathError[] };
    if (data?.doc !== frameDoc.id) return;
    if (data.ready) readyDoc = data.doc;
    if (typeof data.height === "number" && data.height > 0) height = data.height;
    if (Array.isArray(data.math)) onmath?.(data.math);
  }

  function templateName(name: string): string {
    const key = `preview.template.${name}`;
    return key in en ? t(key as MessageKey) : name;
  }
</script>

<svelte:window onmessage={onMessage} />

<div class="preview">
  <div class="controls">
    {#if note.cards.length > 1}
      <div class="segments" role="radiogroup" aria-label={t("preview.template")}>
        {#each note.cards as c, i (c.name)}
          <button role="radio" aria-checked={index === i} class:on={index === i} onclick={() => (index = i)}>
            {templateName(c.name)}
          </button>
        {/each}
      </div>
    {:else}
      <span class="single">{templateName(card.name)}</span>
    {/if}
    <div class="segments" role="radiogroup" aria-label={t("preview.side")}>
      <button role="radio" aria-checked={!back} class:on={!back} onclick={() => (back = false)}>
        {t("preview.front")}
      </button>
      <button role="radio" aria-checked={back} class:on={back} onclick={() => (back = true)}>
        {t("preview.back")}
      </button>
    </div>
  </div>
  <iframe
    bind:this={frame}
    title={t("preview.frame", { name: templateName(card.name) })}
    sandbox="allow-scripts"
    srcdoc={frameDoc.srcdoc}
    style:height="{height}px"
  ></iframe>
</div>

<style>
  .preview {
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-width: 0;
  }

  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: space-between;
  }

  .single {
    align-self: center;
    font-family: var(--mono);
    font-size: 13px;
    color: var(--muted);
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
    cursor: pointer;
  }

  .segments button:hover {
    background: var(--tile);
  }

  .segments button.on {
    background: var(--sel);
  }

  iframe {
    display: block;
    width: 100%;
    min-height: 200px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--outer);
  }
</style>
