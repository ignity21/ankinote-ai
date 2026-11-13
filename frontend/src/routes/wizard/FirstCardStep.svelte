<script lang="ts">
  import CardPreview from "../../components/CardPreview.svelte";
  import StepNav from "../../components/StepNav.svelte";
  import type { MediaGap, SavedNote } from "../../lib/api";
  import { FirstCard } from "../../lib/firstCard.svelte";
  import { t, type MessageKey } from "../../lib/i18n.svelte";
  import { LANG_TAG } from "../../lib/languages";
  import en from "../../lib/locales/en.json";

  let { onback, onnext }: { onback: () => void; onnext: () => void } = $props();

  const card = new FirstCard();
  void card.load();

  const note = $derived(card.note);

  function message(prefix: string, code: string, vars: Record<string, string> = {}): string {
    const key = `${prefix}.${code}`;
    return t((key in en ? key : `${prefix}.error`) as MessageKey, vars);
  }

  const errorText = $derived.by(() => {
    const f = card.failure;
    if (!f) return "";
    return message(f.during === "generate" ? "first.gen" : "first.save", f.code, { detail: f.detail });
  });

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

  function submit(event: SubmitEvent) {
    event.preventDefault();
    void card.generate();
  }
</script>

<p class="intro">{t("first.intro")}</p>

<div class="wrap">
  <div class="layout">
    <div class="side ask-area">
      <form class="ask" onsubmit={submit}>
        <label class="field">
          <span class="label">{t("first.word")}</span>
          <input
            class="input"
            bind:value={card.word}
            lang={card.target ? LANG_TAG[card.target] : undefined}
            maxlength="100"
            autocomplete="off"
            spellcheck="false"
            disabled={card.generating}
          />
        </label>
        <button
          class={card.notes.length ? "secondary" : "primary"}
          type="submit"
          disabled={!card.word.trim() || card.generating || card.saving}
        >
          {card.notes.length ? t("first.again") : t("first.generate")}
        </button>
      </form>

      {#if card.generating}
        <div class="working" role="status">
          <p class="mono">{t("first.generating", { word: card.word.trim(), s: card.elapsed })}</p>
          <p class="note">{t("first.patience")}</p>
        </div>
      {/if}

      {#if errorText}<p class="error" role="alert">{errorText}</p>{/if}

      {#if note && !card.generating}
        {#if card.notes.length > 1}
          <div class="pos" role="radiogroup" aria-label={t("first.pos")}>
            {#each card.notes as n, i (n.id)}
              <button role="radio" aria-checked={card.selected === i} class:on={card.selected === i} onclick={() => (card.selected = i)}>
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
      {/if}
    </div>

    <div class="main">
      {#if note && !card.generating}
        <CardPreview {note} />
      {:else}
        <div class="placeholder" aria-hidden="true">
          <span class="mono">{card.generating ? "…" : t("first.previewEmpty")}</span>
        </div>
      {/if}
    </div>

    <div class="side save-area">
      {#if note && !card.generating}
        {#if card.saved}
          <div class="saved" role="status">
            <p><span class="ok" aria-hidden="true">✓</span> {t("first.saved", { word: note.headword, deck: card.saved.deck })}</p>
            <p class="note">{syncText(card.saved)}</p>
          </div>
        {:else}
          <div class="save">
            <button class="primary" onclick={() => card.save()} disabled={card.saving}>
              {card.saving ? t("first.saving") : t("first.save")}
            </button>
            <p class="note">
              {t("first.where", { deck: note.deck, type: note.note_type })}
            </p>
          </div>
        {/if}
      {/if}
    </div>
  </div>
</div>

<StepNav
  {onback}
  {onnext}
  last
  nextDisabled={!card.saved}
  hint={card.saved ? "" : t("first.hint")}
/>

<style>
  .intro {
    max-width: 62ch;
    margin: 0 0 20px;
  }

  .wrap {
    container: step / inline-size;
  }

  /* Narrow: word, preview, then save, so the card is seen before saving. */
  .layout {
    display: grid;
    gap: 20px;
    max-width: 1100px;
    grid-template-areas: "ask" "main" "save";
  }

  @container step (min-width: 760px) {
    .layout {
      grid-template-columns: 300px minmax(0, 1fr);
      grid-template-rows: auto 1fr;
      grid-template-areas: "ask main" "save main";
      align-items: start;
    }
  }

  .ask-area {
    grid-area: ask;
  }

  .save-area {
    grid-area: save;
  }

  .save-area:empty {
    display: none;
  }

  .side {
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-width: 0;
  }

  .ask {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .ask button {
    align-self: flex-start;
  }

  .mono {
    font-family: var(--mono);
    font-size: 13px;
  }

  .working p,
  .saved p,
  .save p {
    margin: 0;
  }

  .working .mono {
    color: var(--warn);
  }

  .working .note,
  .saved .note,
  .save .note {
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

  .saved {
    padding: 12px;
    border: 1px solid var(--ok);
    border-radius: 8px;
    background: var(--outer);
  }

  .ok {
    color: var(--ok);
    font-family: var(--mono);
  }

  .main {
    grid-area: main;
    min-width: 0;
  }

  .placeholder {
    display: grid;
    place-items: center;
    min-height: 280px;
    border: 1px dashed var(--border);
    border-radius: 8px;
    color: var(--muted);
    text-align: center;
    padding: 16px;
  }

  .error {
    margin: 0;
    color: var(--err);
  }
</style>
