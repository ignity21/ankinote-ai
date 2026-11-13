import { api, ApiError, type CardTheme, type CardThemeSaved, type DraftNote } from "./api";
import { noteTypes } from "./noteTypes.svelte";
import { theme } from "./theme.svelte";

export type Failure = { code: string; detail: string };

/** The sample note types the preview offers. */
export const PREVIEW_TYPES = ["word", "phrase", "sentence", "stem_concept"] as const;
export type PreviewType = (typeof PREVIEW_TYPES)[number];

/**
 * The card theme on the Note types page: what's saved, the choice being
 * tried (previewed, not saved), and samples rendered with that choice.
 */
class CardThemeChoice {
  saved = $state<CardTheme | null>(null);
  loadError = $state(false);

  /** The palettes being tried; equal to `saved` until the user picks one. */
  light = $state("");
  dark = $state("");

  /** What the preview shows: which note type, and which of Anki's modes. */
  previewType = $state<PreviewType>("word");
  night = $state(false);

  busy = $state(false);
  saveError = $state(false);
  /** What the last Apply did. */
  outcome = $state<CardThemeSaved | null>(null);

  /** Samples by `type:light:dark`. */
  samples = $state<Record<string, DraftNote | "failed">>({});

  readonly changed = $derived(
    !!this.saved && (this.light !== this.saved.light || this.dark !== this.saved.dark),
  );

  /** Called on each visit: unapplied choices from an earlier visit are dropped. */
  async load() {
    this.outcome = null;
    this.saveError = false;
    try {
      const { light, dark } = await api.cardTheme();
      this.saved = { light, dark };
      this.light = light;
      this.dark = dark;
      this.night = theme.dark;
      this.loadError = false;
    } catch {
      this.loadError = true;
    }
  }

  pick(mode: "light" | "dark", palette: string) {
    this[mode] = palette;
    // Show the mode just changed, so the pick is visible.
    this.night = mode === "dark";
    this.outcome = null;
  }

  revert() {
    if (!this.saved) return;
    this.light = this.saved.light;
    this.dark = this.saved.dark;
  }

  sampleKey(): string {
    return `${this.previewType}:${this.light}:${this.dark}`;
  }

  async sample() {
    const key = this.sampleKey();
    if (this.samples[key] && this.samples[key] !== "failed") return;
    try {
      const note = await api.noteTypeSample(this.previewType, { light: this.light, dark: this.dark });
      this.samples[key] = note;
    } catch {
      this.samples[key] = "failed";
    }
  }

  async apply() {
    if (this.busy || !this.changed) return;
    this.busy = true;
    this.saveError = false;
    try {
      const result = await api.saveCardTheme({ light: this.light, dark: this.dark });
      this.saved = { light: result.light, dark: result.dark };
      this.outcome = result;
      // Samples on the rest of the page were drawn in the old theme.
      noteTypes.samples = {};
      void noteTypes.check();
    } catch (error) {
      this.saveError = true;
      if (!(error instanceof ApiError)) console.error(error);
    } finally {
      this.busy = false;
    }
  }
}

export const cardTheme = new CardThemeChoice();
