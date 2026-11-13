<script lang="ts">
  import type { FormField, FormRow } from "../lib/api";
  import type { Editing } from "../lib/generate.svelte";
  import { t, type MessageKey } from "../lib/i18n.svelte";
  import en from "../lib/locales/en.json";

  let { editing }: { editing: Editing } = $props();

  let root = $state<HTMLElement>();

  // Start typing straight away.
  $effect(() => {
    root?.querySelector<HTMLElement>("input, textarea")?.focus();
  });

  function known(key: string): key is MessageKey {
    return key in en;
  }

  function label(key: string): string {
    const name = `edit.field.${key}`;
    return known(name) ? t(name) : key;
  }

  function column(name: string): string {
    const key = `edit.col.${name}`;
    return known(key) ? t(key) : name;
  }

  const failure = $derived(editing.failure);
  /** The field a refused edit is about. */
  const badKey = $derived(failure && failure.code !== "draft_gone" ? failure.detail : "");

  // A refused edit may be about a field far below; show the message.
  $effect(() => {
    if (failure) root?.querySelector(".error")?.scrollIntoView({ block: "nearest" });
  });

  function errorText(): string {
    if (!failure) return "";
    const field = editing.note.form.find((f) => f.key === failure.detail);
    const limit = field && (field.type === "lines" || field.type === "rows") ? field : null;
    const code = failure.code === "blank" && field?.type === "rows" ? "blankRow" : failure.code;
    const key = `edit.err.${code}`;
    return t(known(key) ? key : "edit.err.error", {
      field: label(failure.detail),
      min: limit?.min ?? 0,
      max: limit?.max ?? 0,
      detail: failure.detail,
    });
  }

  function text(key: string): string {
    return editing.values[key] as string;
  }

  function rows(field: FormField): FormRow[] {
    return editing.values[field.key] as FormRow[];
  }

  function addRow(field: FormField & { type: "rows" }) {
    const list = rows(field);
    list.push({ cells: Object.fromEntries(field.columns.map((c) => [c, ""])) });
    // Focus the new row's first cell once it's drawn.
    queueMicrotask(() =>
      root
        ?.querySelector<HTMLElement>(`[data-rows="${field.key}"] .item:last-of-type textarea`)
        ?.focus(),
    );
  }

  function hint(field: FormField): string {
    if (field.type === "lines") {
      return field.max ? t("edit.linesMax", { max: field.max }) : t("edit.lines");
    }
    return "";
  }
</script>

<div class="editor" bind:this={root}>
  {#if failure}
    <p class="error" role="alert">{errorText()}</p>
  {/if}
  <p class="note">{t("edit.intro")}</p>

  {#each editing.note.form as field (field.key)}
    {#if field.type === "text" || field.type === "area"}
      <label class="field" data-key={field.key}>
        <span class="label">
          {label(field.key)}
          {#if !field.required}<span class="opt">{t("edit.optional")}</span>{/if}
        </span>
        {#if field.type === "area"}
          <textarea
            class="input"
            rows="2"
            bind:value={() => text(field.key), (v) => (editing.values[field.key] = v)}
            aria-invalid={badKey === field.key}
            disabled={editing.applying}
          ></textarea>
        {:else}
          <input
            class="input"
            bind:value={() => text(field.key), (v) => (editing.values[field.key] = v)}
            aria-invalid={badKey === field.key}
            disabled={editing.applying}
            autocomplete="off"
          />
        {/if}
      </label>
    {:else if field.type === "lines"}
      <label class="field" data-key={field.key}>
        <span class="label">{label(field.key)} <span class="opt">{hint(field)}</span></span>
        <textarea
          class="input"
          rows="2"
          bind:value={() => text(field.key), (v) => (editing.values[field.key] = v)}
          aria-invalid={badKey === field.key}
          disabled={editing.applying}
        ></textarea>
      </label>
    {:else if field.type === "rows"}
      {@const list = rows(field)}
      <fieldset class="rows" class:bad={badKey === field.key} data-rows={field.key}>
        <legend class="label">{label(field.key)}</legend>
        {#each list as row, i (row)}
          <div class="item">
            <span class="num" aria-hidden="true">{i + 1}</span>
            <div class="cells">
              {#each field.columns as name (name)}
                <label class="field">
                  <span class="label">{column(name)}</span>
                  <textarea
                    class="input"
                    rows="1"
                    bind:value={row.cells[name]}
                    disabled={editing.applying}
                  ></textarea>
                </label>
              {/each}
            </div>
            <button
              type="button"
              class="link remove"
              onclick={() => list.splice(i, 1)}
              disabled={editing.applying || list.length <= field.min}
              aria-label={t("edit.removeN", { field: label(field.key), n: i + 1 })}
            >
              {t("edit.remove")}
            </button>
          </div>
        {/each}
        {#if field.max === null || list.length < field.max}
          <button type="button" class="secondary small" onclick={() => addRow(field)} disabled={editing.applying}>
            + {t("edit.add")}
          </button>
        {/if}
      </fieldset>
    {/if}
  {/each}
</div>

<style>
  .editor {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .error {
    margin: 0;
    color: var(--err);
  }

  .opt {
    margin-left: 6px;
    font-size: 12px;
    opacity: 0.8;
  }

  textarea.input {
    min-height: 44px;
    resize: vertical;
    field-sizing: content;
    max-height: 40vh;
    line-height: 1.5;
  }

  [aria-invalid="true"].input,
  fieldset.bad {
    border-color: var(--err);
  }

  .rows {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin: 0;
    padding: 10px 12px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    min-width: 0;
  }

  .rows > legend {
    padding: 0 4px;
    font-size: 13px;
    color: var(--muted);
  }

  .item {
    display: grid;
    grid-template-columns: 20px minmax(0, 1fr) auto;
    gap: 8px;
    align-items: start;
  }

  .item + .item {
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }

  .num {
    padding-top: 30px;
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
    text-align: right;
  }

  .cells {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }

  .remove {
    min-height: 36px;
    margin-top: 22px;
    font-size: 14px;
  }

  .remove:disabled {
    color: var(--muted);
    text-decoration: none;
    cursor: not-allowed;
  }

  .small {
    align-self: flex-start;
    min-height: 36px;
    padding: 0 12px;
    font-size: 14px;
  }

  @container app (max-width: 600px) {
    .item {
      grid-template-columns: minmax(0, 1fr) auto;
    }

    .num {
      display: none;
    }
  }
</style>
