import en from "./locales/en.json";
import zh from "./locales/zh-CN.json";

const catalogs = { en, "zh-CN": zh } as const;
export type Locale = keyof typeof catalogs;
export type MessageKey = keyof typeof en;

const STORAGE_KEY = "ankinote.locale";

function initial(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && saved in catalogs) return saved as Locale;
  } catch {
    // Storage blocked: fall through to the browser language.
  }
  return navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en";
}

class I18n {
  locale = $state<Locale>(initial());

  constructor() {
    $effect.root(() => {
      $effect(() => {
        document.documentElement.lang = this.locale;
        try {
          localStorage.setItem(STORAGE_KEY, this.locale);
        } catch {
          // Not persisted.
        }
      });
    });
  }

  toggle() {
    this.locale = this.locale === "en" ? "zh-CN" : "en";
  }
}

export const i18n = new I18n();

/** Translate `key`, replacing `{name}` placeholders from `vars`. */
export function t(key: MessageKey, vars: Record<string, string | number> = {}): string {
  // A missing key shows itself rather than crashing the page.
  const text: string = catalogs[i18n.locale][key] ?? en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`));
}
