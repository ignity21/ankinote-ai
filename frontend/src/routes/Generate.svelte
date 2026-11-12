<script lang="ts">
  import Pane from "../components/Pane.svelte";
  import { t } from "../lib/i18n.svelte";

  let input = $state("");

  function onKey(event: KeyboardEvent) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      // Wired to the generate API in the next step.
    }
  }
</script>

<div class="work">
  <Pane title={t("generate.input")} area="input">
    <label class="prompt">
      <span class="mark" aria-hidden="true">&gt;</span>
      <textarea
        bind:value={input}
        onkeydown={onKey}
        placeholder={t("generate.placeholder")}
        aria-label={t("generate.input")}
      ></textarea>
    </label>
    <div class="row">
      <button class="primary" disabled={!input.trim()}>
        {t("generate.submit")}
        <kbd class="hint">Ctrl ↵</kbd>
      </button>
    </div>
  </Pane>

  <Pane title={t("generate.queue")} area="queue">
    <p class="empty">{t("generate.queueEmpty")}</p>
  </Pane>

  <Pane title={t("generate.preview")} area="preview">
    <p class="empty">{t("generate.previewEmpty")}</p>
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

  .prompt {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--outer);
  }

  .mark {
    font-family: var(--mono);
    color: var(--accent);
    line-height: 1.6;
  }

  textarea {
    flex: 1;
    min-width: 0;
    min-height: 84px;
    padding: 0;
    border: 0;
    background: none;
    resize: none;
    outline: none;
    font-family: var(--mono);
    line-height: 1.6;
  }

  textarea::placeholder {
    color: var(--muted);
  }

  .row {
    display: flex;
    justify-content: flex-end;
    margin-top: 10px;
  }

  .primary:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  @container app (max-width: 1000px) {
    .work {
      grid-template-columns: 250px minmax(0, 1fr);
      grid-template-areas:
        "input input"
        "queue preview";
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

    textarea {
      min-height: 0;
    }

    .hint {
      display: none;
    }
  }
</style>
