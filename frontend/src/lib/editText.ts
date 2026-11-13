/** Words for the field editor: field and column names, and refused edits. */
import type { FormField } from "./api";
import type { Failure } from "./generate.svelte";
import { t, type MessageKey } from "./i18n.svelte";
import en from "./locales/en.json";

function known(key: string): key is MessageKey {
  return key in en;
}

export function fieldLabel(key: string): string {
  const name = `edit.field.${key}`;
  return known(name) ? t(name) : key;
}

export function columnLabel(name: string): string {
  const key = `edit.col.${name}`;
  return known(key) ? t(key) : name;
}

/** Why an edit was refused, naming the field (from `form`) it's about. */
export function editErrorText(form: FormField[], failure: Failure): string {
  const field = form.find((f) => f.key === failure.detail);
  const limit = field && (field.type === "lines" || field.type === "rows") ? field : null;
  const code = failure.code === "blank" && field?.type === "rows" ? "blankRow" : failure.code;
  const key = `edit.err.${code}`;
  return t(known(key) ? key : "edit.err.error", {
    field: fieldLabel(failure.detail),
    min: limit?.min ?? 0,
    max: limit?.max ?? 0,
    detail: failure.detail,
  });
}
