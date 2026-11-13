/**
 * State for "Languages": the native language cards explain in and the
 * target language they teach. Shared by the wizard and, later, Settings.
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

  readonly ready = $derived(
    this.native !== null && this.target !== null && !sameLanguage(this.native, this.target),
  );

  async load() {
    try {
      this.options = await api.languages();
    } catch {
      this.loadError = true;
      return;
    }
    const { native, target, natives, targets } = this.options;
    this.native = natives.includes(native) ? native : null;
    this.target = targets.some((t) => t.id === target) ? target : null;

    // The factory pair is what nobody chose yet: start from the browser's
    // language instead, so an English reader isn't offered Chinese first.
    const guess = browserNative();
    if (native === FACTORY.native && target === FACTORY.target && guess && natives.includes(guess)) {
      this.native = guess;
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
      await api.patchSettings({ native_language: this.native!, target_language: this.target! });
      return true;
    } catch (error) {
      this.failure = error instanceof ApiError && error.status === 422 ? error.code : "server";
      return false;
    } finally {
      this.saving = false;
    }
  }
}
