/** Settings' sections, each at /settings/<section>; /settings opens the first. */
export const SECTIONS = ["models", "anki", "languages", "appearance"] as const;
export type Section = (typeof SECTIONS)[number];

export function settingsSection(path: string): Section {
  const name = path.replace(/^\/settings\/?/, "").split("/")[0];
  return (SECTIONS as readonly string[]).includes(name ?? "") ? (name as Section) : SECTIONS[0];
}

/**
 * The section that fixes a failure code from generating or saving, if any:
 * model problems → Models, Anki not reachable → Anki.
 */
export function sectionFor(code: string): Section | null {
  if (["no_text_model", "auth", "billing", "model_not_found", "audio_not_set_up", "not_set_up"].includes(code)) {
    return "models";
  }
  if (["write_blocked", "not_open"].includes(code)) return "anki";
  return null;
}
