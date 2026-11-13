/**
 * Display data for the languages ankinote knows. Ids are the server's
 * `Language` values; which ones are offered comes from `GET /api/languages`.
 */

/** Each language named in itself, the way language pickers list them. */
export const ENDONYM: Record<string, string> = {
  English: "English",
  "Chinese(Simplified)": "简体中文",
  "Chinese(Traditional)": "繁體中文",
  Japanese: "日本語",
  French: "Français",
  Spanish: "Español",
  German: "Deutsch",
  Korean: "한국어",
};

/** BCP 47 tag for `lang` attributes, so each name renders with its own glyphs. */
export const LANG_TAG: Record<string, string> = {
  English: "en",
  "Chinese(Simplified)": "zh-Hans",
  "Chinese(Traditional)": "zh-Hant",
  Japanese: "ja",
  French: "fr",
  Spanish: "es",
  German: "de",
  Korean: "ko",
};

/**
 * One word shown on the example card: "moon" as a card for each target
 * shows it (headword and pronunciation), and the meaning each native sees.
 */
export const SAMPLE_WORD: Record<string, { word: string; sound: string }> = {
  English: { word: "moon", sound: "/muːn/" },
  French: { word: "la lune", sound: "/lyn/" },
  Spanish: { word: "la luna", sound: "/ˈluna/" },
  German: { word: "der Mond", sound: "/moːnt/" },
  Japanese: { word: "月", sound: "つき" },
  "Chinese(Simplified)": { word: "月亮", sound: "yuèliang" },
  "Chinese(Traditional)": { word: "月亮", sound: "yuèliang" },
  Korean: { word: "달", sound: "/tal/" },
};

export const SAMPLE_MEANING: Record<string, string> = {
  English: "moon",
  "Chinese(Simplified)": "月亮",
  "Chinese(Traditional)": "月亮",
  Japanese: "月",
  French: "lune",
  Spanish: "luna",
  German: "Mond",
  Korean: "달",
};

/** Mirrors the server's `language_pair_error`: Simplified/Traditional are one language to learn. */
export function sameLanguage(a: string, b: string): boolean {
  return a === b || (a.startsWith("Chinese") && b.startsWith("Chinese"));
}

/** The native language the browser suggests, if ankinote knows it. */
export function browserNative(tags: readonly string[] = navigator.languages): string | null {
  for (const raw of tags) {
    const tag = raw.toLowerCase();
    if (tag.startsWith("zh")) {
      return /-(hant|tw|hk|mo)\b/.test(tag) ? "Chinese(Traditional)" : "Chinese(Simplified)";
    }
    const base = tag.split("-")[0];
    const match = Object.entries(LANG_TAG).find(([, t]) => t === base);
    if (match) return match[0];
  }
  return null;
}
