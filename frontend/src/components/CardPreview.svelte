<script lang="ts">
  import type { DraftNote } from "../lib/api";
  import { t, type MessageKey } from "../lib/i18n.svelte";
  import { theme } from "../lib/theme.svelte";
  import en from "../lib/locales/en.json";

  let { note }: { note: DraftNote } = $props();

  let index = $state(0);
  let back = $state(false);
  let height = $state(320);
  let frame = $state<HTMLIFrameElement>();

  const card = $derived(note.cards[Math.min(index, note.cards.length - 1)]!);

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
  `;

  /**
   * The card as Anki would show it. Sandboxed without same-origin, and the
   * CSP lets only this page's own script run: it plays sounds and reports
   * the height, and nothing in a field can reach the app.
   */
  const srcdoc = $derived.by(() => {
    const nonce = crypto.randomUUID();
    const origin = location.origin;
    const night = theme.dark ? " nightMode night_mode" : "";
    const csp = [
      "default-src 'none'",
      `img-src ${origin} data:`,
      `media-src ${origin}`,
      `font-src ${origin} data:`,
      "style-src 'unsafe-inline'",
      `script-src 'nonce-${nonce}'`,
    ].join("; ");
    return `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<base href="${origin}/"><meta name="viewport" content="width=device-width">
<style>${CHROME}</style><style>${note.css}</style></head>
<body class="card card${index + 1}${night}"><div id="qa">${back ? card.back : card.front}</div>
<script nonce="${nonce}">
  const post = () => parent.postMessage(
    { ankinotePreviewHeight: Math.ceil(document.body.getBoundingClientRect().height) }, "*");
  new ResizeObserver(post).observe(document.body);
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".replay-button[data-src]");
    if (!button) return;
    event.preventDefault();
    new Audio(button.dataset.src).play();
  });
<\/script></body></html>`;
  });

  function onMessage(event: MessageEvent) {
    if (!frame || event.source !== frame.contentWindow) return;
    const value = (event.data as { ankinotePreviewHeight?: unknown })?.ankinotePreviewHeight;
    if (typeof value === "number" && value > 0) height = value;
  }

  function templateName(name: string): string {
    const key = `preview.template.${name}`;
    return key in en ? t(key as MessageKey) : name;
  }
</script>

<svelte:window onmessage={onMessage} />

<div class="preview">
  <div class="controls">
    <div class="segments" role="radiogroup" aria-label={t("preview.template")}>
      {#each note.cards as c, i (c.name)}
        <button role="radio" aria-checked={index === i} class:on={index === i} onclick={() => (index = i)}>
          {templateName(c.name)}
        </button>
      {/each}
    </div>
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
    {srcdoc}
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
