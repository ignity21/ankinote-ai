/**
 * State for "Languages": the native language cards explain in and the
 * target language they teach. Shared by the wizard and Settings → Languages.
 */
import { api, ApiError, type Languages } from "./api";
import { browserNative, sameLanguage } from "./languages";

/** What a fresh install has saved before anyone chose. */
const FACTORY = { native: "Chinese(Simplified)", target: "English" };

export class LanguageSetup {
  options = $state<Languages | null>(null);
  loadError = $state(false);
  native = $state<string | null>(null);
  target = $state<string | null>(null);
  saving = $state(false);
  /** Server error code: same_language, not_target, not_native, or "server". */
  failure = $state("");
  /** The pair in settings.json. */
  saved = $state<{ native: string; target: string } | null>(null);

  readonly ready = $derived(
    this.native !== null && this.target !== null && !sameLanguage(this.native, this.target),
  );
  readonly changed = $derived(
    this.saved !== null && (this.native !== this.saved.native || this.target !== this.saved.target),
  );

  /** `guess`: a fresh install starts from the browser's language (the wizard). */
  async load({ guess = true } = {}) {
    try {
      this.options = await api.languages();
    } catch {
      this.loadError = true;
      return;
    }
    const { native, target, natives, targets } = this.options;
    this.saved = { native, target };
    this.native = natives.includes(native) ? native : null;
    this.target = targets.some((t) => t.id === target) ? target : null;

    // The factory pair is what nobody chose yet: start from the browser's
    // language instead, so an English reader isn't offered Chinese first.
    const browser = guess ? browserNative() : null;
    if (native === FACTORY.native && target === FACTORY.target && browser && natives.includes(browser)) {
      this.native = browser;
    }
    if (this.native && this.target && sameLanguage(this.native, this.target)) this.target = null;
  }

  pickNative(id: string) {
    this.native = id;
    this.failure = "";
    // Learning your own language isn't a choice; let the user pick again.
    if (this.target && sameLanguage(id, this.target)) this.target = null;
  }

  pickTarget(id: string) {
    this.target = id;
    this.failure = "";
  }

  async save(): Promise<boolean> {
    if (!this.ready || this.saving) return false;
    this.saving = true;
    this.failure = "";
    try {
      const settings = await api.patchSettings({ native_language: this.native!, target_language: this.target! });
      this.saved = { native: settings.defaults.native_language, target: settings.defaults.target_language };
      return true;
    } catch (error) {
      this.failure = error instanceof ApiError && error.status === 422 ? error.code : "server";
      return false;
    } finally {
      this.saving = false;
    }
  }
}
