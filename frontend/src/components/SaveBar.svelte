<script lang="ts">
  import { t } from "../lib/i18n.svelte";

  /** Settings' footer for a section: one Save button, or what's already saved. */
  let {
    onsave,
    changed,
    canSave = true,
    busy = false,
    saved = false,
    hint = "",
  }: {
    onsave: () => void;
    /** Whether the section differs from what's saved. */
    changed: boolean;
    /** Whether the change can be saved as it stands (tested, complete…). */
    canSave?: boolean;
    busy?: boolean;
    /** Just saved: say so until the next change. */
    saved?: boolean;
    hint?: string;
  } = $props();
</script>

<div class="bar">
  <p class="status" role="status">
    {#if busy}
      {t("wizard.saving")}
    {:else if changed}
      {hint || t("settings.unsaved")}
    {:else if saved}
      <span class="ok" aria-hidden="true">✓</span> {t("settings.saved")}
    {/if}
  </p>
  <button class="primary" disabled={!changed || !canSave || busy} onclick={onsave}>
    {t("settings.save")}
  </button>
</div>

<style>
  .bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    margin-top: 24px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }

  .status {
    flex: 1 1 200px;
    margin: 0;
    color: var(--muted);
  }

  .ok {
    color: var(--ok);
  }

  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
