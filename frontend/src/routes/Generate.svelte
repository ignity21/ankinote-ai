<script lang="ts">
  import CardPreview from "../components/CardPreview.svelte";
  import Pane from "../components/Pane.svelte";
  import { KINDS, type MediaGap, type SavedNote } from "../lib/api";
  import { session, type Row } from "../lib/generate.svelte";
  import { t, type MessageKey } from "../lib/i18n.svelte";
  import en from "../lib/locales/en.json";

  void session.load();

  let input = $state("");
  let width = $state(1200);
  let field = $state<HTMLTextAreaElement | HTMLInputElement>();
  let queueList = $state<HTMLUListElement>();

  /** Matches the CSS container query: a phone gets a single-line input. */
  const phone = $derived(width <= 600);
  const lines = $derived(input.split("\n").filter((line) => line.trim()).length);
  const row = $derived(session.selected);
  const note = $derived(row?.note ?? null);

  function submit() {
    if (session.add(input)) input = "";
    field?.focus();
  }

  function message(prefix: string, code: string, vars: Record<string, string> = {}): string {
    const key = `${prefix}.${code}`;
    return t((key in en ? key : `${prefix}.error`) as MessageKey, vars);
  }

  function failureText(r: Row): string {
    const f = r.failure;
    if (!f) return "";
    return message(f.during === "generate" ? "generate.err" : "generate.saveErr", f.code, {
      detail: f.detail,
    });
  }

  function seconds(r: Row): number {
    return Math.max(0, Math.round((session.now - r.startedAt) / 1000));
  }

  function status(r: Row): string {
    if (r.state === "generating") return t("generate.state.generating", { s: seconds(r) });
    if (r.state === "ready" && r.failure) return t("generate.state.unsaved");
    return t(`generate.state.${r.state}` as MessageKey);
  }

  /** What the queue row says under the word: missing media, in short. */
  function shortGaps(r: Row): string {
    const kinds = new Set(r.notes.flatMap((n) => n.gaps.map((g) => g.kind)));
    return [...kinds].map((kind) => t(`generate.short.${kind}`)).join(" · ");
  }

  function gapText(gap: MediaGap): string {
    return t(`gap.${gap.kind}.${gap.reason}` as MessageKey, { detail: gap.detail });
  }

  function syncText(saved: SavedNote): string {
    const sync = saved.sync;
    if (!sync) return t("sync.desktop");
    if (sync.error) return t("sync.error");
    if (sync.state === "idle") return t("sync.done");
    return t("sync.pending");
  }

  function onFieldKey(event: KeyboardEvent) {
    const send = phone ? !event.shiftKey : event.ctrlKey || event.metaKey;
    if (event.key === "Enter" && send && !event.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  function inTextField(target: EventTarget | null): boolean {
    return target instanceof HTMLElement && !!target.closest("input, textarea, select, [contenteditable]");
  }

  function onKey(event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      if (row) void session.save(row);
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey || inTextField(event.target)) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!session.rows.length) return;
      event.preventDefault();
      session.step(event.key === "ArrowDown" ? 1 : -1);
      queueList?.querySelector<HTMLElement>(`[data-id="${session.selectedId}"]`)?.focus();
    } else if (event.key === "r" && row) {
      session.regenerate(row);
    }
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="work" bind:clientWidth={width}>
  <Pane title={t("generate.input")} area="input">
    <form
      class="ask"
      onsubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div class="kinds" role="radiogroup" aria-label={t("generate.kind")}>
        {#each KINDS as kind (kind)}
          <button
            type="button"
            role="radio"
            aria-checked={session.kind === kind}
            class:on={session.kind === kind}
            onclick={() => {
              session.kind = kind;
              field?.focus();
            }}
          >
            {t(`generate.kind.${kind}`)}
          </button>
        {/each}
      </div>

      <label class="prompt">
        <span class="mark" aria-hidden="true">&gt;</span>
        {#if phone}
          <input
            bind:this={field}
            bind:value={input}
            onkeydown={onFieldKey}
            placeholder={t(`generate.placeholderPhone.${session.kind}`)}
            aria-label={t("generate.input")}
            autocomplete="off"
            spellcheck="false"
          />
        {:else}
          <textarea
            bind:this={field}
            bind:value={input}
            onkeydown={onFieldKey}
            placeholder={t(`generate.placeholder.${session.kind}`)}
            aria-label={t("generate.input")}
            spellcheck="false"
          ></textarea>
        {/if}
        {#if phone}
          <button class="send" type="submit" disabled={!lines} aria-label={t("generate.submit")}>
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
              <path d="M2 8h11M9 3.5 13.5 8 9 12.5" fill="none" stroke="currentColor" stroke-width="1.8" />
            </svg>
          </button>
        {/if}
      </label>

      <div class="opts">
        {#if session.kind === "word"}
          <label title={session.imageAvailable ? "" : t("generate.imageOff")}>
            <input
              type="checkbox"
              checked={session.image && session.imageAvailable}
              disabled={!session.imageAvailable}
              onchange={(e) => (session.image = e.currentTarget.checked)}
            />
            {t("generate.image")}
          </label>
        {/if}
        <label>
          <input type="checkbox" bind:checked={session.audio} />
          {t("generate.audio")}
        </label>
        {#if session.kind === "word" && !session.imageAvailable}
          <span class="note off">{t("generate.imageOff")}</span>
        {/if}
      </div>

      {#if !phone}
        <div class="row">
          <button class="primary" type="submit" disabled={!lines}>
            {lines > 1 ? t("generate.submitN", { n: lines }) : t("generate.submit")}
            <kbd class="hint">Ctrl ↵</kbd>
          </button>
          <span class="note">{t("generate.lineHint")}</span>
        </div>
      {/if}
    </form>
  </Pane>

  <Pane title={t("generate.queue")} area="queue" fill>
    {#if session.rows.length}
      <ul class="queue" bind:this={queueList}>
        {#each session.rows as r (r.id)}
          <li>
            <button
              class="qi {r.state}"
              class:on={r.id === session.selectedId}
              class:unsaved={r.state === "ready" && r.failure}
              data-id={r.id}
              aria-current={r.id === session.selectedId ? "true" : undefined}
              onclick={() => session.select(r)}
            >
              <span class="glyph" aria-hidden="true">
                {#if r.state === "generating" || r.state === "saving"}
                  <span class="spin"></span>
                {:else if r.state === "saved"}✓{:else if r.state === "failed"}✗{:else if r.state === "queued"}○{:else}●{/if}
              </span>
              <span class="qw">{r.text}</span>
              <span class="qs">{status(r)}</span>
              {#if r.state === "ready" || r.state === "saved"}
                {@const gaps = shortGaps(r)}
                {#if gaps}<span class="qn">{gaps}</span>{/if}
              {/if}
            </button>
          </li>
        {/each}
      </ul>
      <div class="qfoot">
        <span class="keys">{t("generate.queueKeys")}</span>
        {#if session.readyCount > 1}
          <button class="secondary small" onclick={() => session.saveAllReady()}>
            {t("generate.saveAll", { n: session.readyCount })}
          </button>
        {/if}
      </div>
    {:else}
      <p class="empty">{t("generate.queueEmpty")}</p>
    {/if}
  </Pane>

  <Pane title={row ? t("generate.previewOf", { text: row.text }) : t("generate.preview")} area="preview" fill>
    <div class="stage">
      {#if !row}
        <p class="empty">{t("generate.previewEmpty")}</p>
      {:else if row.state === "queued"}
        <p class="note">{t("generate.waiting")}</p>
      {:else if row.state === "generating"}
        <div class="working" role="status">
          <p class="mono">{t("generate.generating", { text: row.text, s: seconds(row) })}</p>
          <p class="note">{t(`generate.patience.${row.kind}`)}</p>
        </div>
      {:else if row.state === "failed"}
        <p class="error" role="alert">{failureText(row)}</p>
      {:else if note}
        {#if row.notes.length > 1}
          <div class="pos" role="radiogroup" aria-label={t("generate.pos")}>
            {#each row.notes as n, i (n.id)}
              <button role="radio" aria-checked={row.pick === i} class:on={row.pick === i} onclick={() => (row.pick = i)}>
                {n.variant}
              </button>
            {/each}
          </div>
        {/if}
        {#if note.gaps.length}
          <ul class="gaps">
            {#each note.gaps as gap (gap.kind)}
              <li>{gapText(gap)}</li>
            {/each}
          </ul>
        {/if}
        <CardPreview {note} />
      {/if}
    </div>

    {#if row && (row.saveable || row.state === "saving" || row.state === "failed")}
      <div class="actions">
        {#if row.failure && row.state !== "failed"}
          <p class="error" role="alert">{failureText(row)}</p>
        {:else if row.state === "saved" && row.saved}
          <p class="note" role="status">
            <span class="ok" aria-hidden="true">✓</span>
            {t("generate.saved", { deck: row.saved.deck })}
            {syncText(row.saved)}
          </p>
        {:else if note}
          <p class="note">{t("generate.where", { deck: note.deck, type: note.note_type })}</p>
        {/if}
        <div class="buttons">
          {#if row.state !== "failed"}
            <button
              class={row.state === "saved" ? "secondary" : "primary"}
              onclick={() => session.save(row)}
              disabled={!row.saveable}
            >
              {row.state === "saving"
                ? t("generate.saving")
                : row.state === "saved"
                  ? t("generate.saveAgain")
                  : t("generate.save")}
              <kbd class="hint">Ctrl S</kbd>
            </button>
          {/if}
          <button
            class={row.state === "failed" ? "primary" : "secondary"}
            onclick={() => session.regenerate(row)}
            disabled={row.busy}
          >
            {t("generate.regen")} <kbd class="hint">R</kbd>
          </button>
        </div>
      </div>
    {/if}
  </Pane>
</div>

<style>
  .work {
    display: grid;
    gap: var(--gap);
    height: 100%;
    padding: 2px 10px 10px;
    grid-template-columns: 360px minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    grid-template-areas:
      "input preview"
      "queue preview";
  }

  .ask {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .kinds {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 3px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--outer);
  }

  .kinds button {
    flex: 1;
    min-height: 36px;
    padding: 0 10px;
    border: 0;
    border-radius: 6px;
    background: none;
    color: var(--muted);
    cursor: pointer;
  }

  .kinds button:hover {
    color: var(--fg);
  }

  .kinds button.on {
    background: var(--sel);
    color: var(--fg);
  }

  .prompt {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--outer);
  }

  .prompt:focus-within {
    border-color: var(--accent);
  }

  .mark {
    font-family: var(--mono);
    color: var(--accent);
    line-height: 1.6;
  }

  textarea,
  .prompt input {
    flex: 1;
    min-width: 0;
    padding: 0;
    border: 0;
    background: none;
    outline: none;
    font-family: var(--mono);
    line-height: 1.6;
  }

  textarea {
    min-height: 84px;
    max-height: 30vh;
    resize: vertical;
  }

  textarea::placeholder,
  .prompt input::placeholder {
    color: var(--muted);
  }

  .send {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    margin: -10px -8px -10px 0;
    border: 0;
    border-radius: 8px;
    background: var(--accent);
    color: var(--on-accent);
    cursor: pointer;
  }

  .send:disabled {
    background: var(--border);
    color: var(--muted);
    cursor: not-allowed;
  }

  .prompt:has(.send) {
    align-items: center;
  }

  .opts {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0 16px;
  }

  .opts label {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 36px;
    color: var(--muted);
    cursor: pointer;
  }

  .opts label:has(input:disabled) {
    cursor: not-allowed;
    opacity: 0.6;
  }

  .opts input {
    width: 16px;
    height: 16px;
    accent-color: var(--accent);
  }

  .note.off {
    margin: 0;
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .row .note {
    margin: 0;
  }

  .primary:disabled,
  .secondary:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  /* Queue */
  .queue {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    margin: 0 -8px;
    padding: 0 8px;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .qi {
    display: grid;
    grid-template-columns: 18px minmax(0, 1fr) auto;
    grid-template-areas:
      "g w s"
      ". n n";
    align-items: center;
    gap: 0 8px;
    width: 100%;
    min-height: 36px;
    padding: 6px 8px;
    border: 0;
    border-radius: 6px;
    background: none;
    text-align: left;
    cursor: pointer;
  }

  .qi:hover {
    background: var(--outer);
  }

  .qi.on {
    background: var(--sel);
  }

  .glyph {
    grid-area: g;
    display: grid;
    place-items: center;
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
  }

  .qi.ready .glyph {
    color: var(--accent);
  }

  .qi.saved .glyph {
    color: var(--ok);
  }

  .qi.failed .glyph,
  .qi.unsaved .glyph {
    color: var(--err);
  }

  .qw {
    grid-area: w;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .qs {
    grid-area: s;
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
  }

  .qi.generating .qs,
  .qi.saving .qs {
    color: var(--warn);
  }

  .qi.failed .qs,
  .qi.unsaved .qs {
    color: var(--err);
  }

  .qn {
    grid-area: n;
    font-size: 13px;
    color: var(--muted);
  }

  .spin {
    width: 10px;
    height: 10px;
    border: 2px solid var(--warn);
    border-right-color: transparent;
    border-radius: 50%;
    animation: spin 0.9s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .qfoot {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-top: 10px;
  }

  .keys {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
  }

  .small {
    min-height: 36px;
    padding: 0 12px;
    font-size: 14px;
  }

  /* Preview */
  .stage {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin: 0 -8px;
    padding: 2px 8px 8px;
  }

  .stage p {
    margin: 0;
  }

  .mono {
    font-family: var(--mono);
    font-size: 13px;
  }

  .working .mono {
    color: var(--warn);
  }

  .working .note {
    margin-top: 4px;
  }

  .pos {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .pos button {
    min-height: 36px;
    padding: 0 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--outer);
    font-family: var(--mono);
    font-size: 13px;
    cursor: pointer;
  }

  .pos button.on {
    border-color: var(--accent);
    background: var(--sel);
  }

  .gaps {
    margin: 0;
    padding: 10px 12px 10px 28px;
    border: 1px solid var(--border);
    border-left: 3px solid var(--warn);
    border-radius: 6px;
    background: var(--outer);
    font-size: 14px;
  }

  .gaps li + li {
    margin-top: 4px;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 10px 16px;
    padding-top: 12px;
    margin-top: 4px;
    border-top: 1px solid var(--border);
  }

  .actions p {
    flex: 1 1 260px;
    margin: 0;
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-left: auto;
  }

  .ok {
    color: var(--ok);
    font-family: var(--mono);
  }

  .error {
    color: var(--err);
  }

  @media (prefers-reduced-motion: reduce) {
    .spin {
      animation: none;
    }
  }

  @container app (max-width: 1000px) {
    .work {
      grid-template-columns: 250px minmax(0, 1fr);
      grid-template-areas:
        "input input"
        "queue preview";
    }

    textarea {
      min-height: 60px;
    }
  }

  @container app (max-width: 600px) {
    .work {
      padding: 0 8px 8px;
      gap: 8px;
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: auto minmax(0, 1fr) auto;
      grid-template-areas: "queue" "preview" "input";
    }

    .queue {
      flex-direction: row;
      overflow-x: auto;
      overflow-y: hidden;
      gap: 6px;
    }

    .queue li {
      flex: none;
    }

    .qi {
      grid-template-columns: auto auto;
      grid-template-areas: "g w";
      min-height: 36px;
      border: 1px solid var(--border);
    }

    .qi.on {
      border-color: var(--accent);
    }

    .qs,
    .qn,
    .qfoot .keys {
      display: none;
    }

    .qfoot:not(:has(button)) {
      display: none;
    }

    .hint {
      display: none;
    }

    .buttons {
      width: 100%;
    }

    .buttons button {
      flex: 1;
    }
  }
</style>
