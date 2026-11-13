/**
 * State for the Note types workspace: ankinote's note types as this release
 * defines them (always available), how each stands in Anki (needs Anki), a
 * sample note of each, and setting one or all of them up.
 */
import { api, ApiError, type DraftNote, type NoteTypeInfo, type NoteTypeItem } from "./api";

export type Failure = { code: string; detail: string };

function failure(error: unknown): Failure {
  return error instanceof ApiError ? { code: error.code, detail: error.detail } : { code: "server", detail: "" };
}

class NoteTypes {
  types = $state<NoteTypeInfo[] | null>(null);
  loadError = $state(false);

  /** By key; null until Anki answered. */
  status = $state<Record<string, NoteTypeItem> | null>(null);
  statusError = $state<Failure | null>(null);
  checking = $state(false);

  /** The type being set up, "all", or "". */
  busy = $state("");
  /** Why setting up failed, and for which type ("all" for all). */
  setupError = $state<(Failure & { key: string }) | null>(null);
  /** What the last setup did, by key. */
  results = $state<Record<string, NoteTypeItem["result"]>>({});

  samples = $state<Record<string, DraftNote | "failed">>({});

  readonly pending = $derived(
    this.status ? Object.values(this.status).filter((s) => s.state !== "synced" || !s.deck_exists) : [],
  );

  /** Called on each visit: the list once, Anki's state every time. */
  async load() {
    if (!this.types) {
      try {
        this.types = await api.noteTypeInfo();
        this.loadError = false;
      } catch {
        this.loadError = true;
        return;
      }
    }
    this.setupError = null;
    await this.check();
  }

  async check() {
    if (this.checking || this.busy) return;
    this.checking = true;
    try {
      const items = await api.noteTypes();
      this.status = Object.fromEntries(items.map((item) => [item.key, item]));
      this.statusError = null;
      // What a setup did is old news once Anki has been read again.
      this.results = {};
    } catch (error) {
      this.status = null;
      this.statusError = failure(error);
    } finally {
      this.checking = false;
    }
  }

  async sample(key: string) {
    if (this.samples[key] && this.samples[key] !== "failed") return;
    try {
      this.samples[key] = await api.noteTypeSample(key);
    } catch {
      this.samples[key] = "failed";
    }
  }

  async setUp(key: string) {
    await this.run(key, async () => {
      const item = await api.prepareNoteType(key);
      this.status = { ...this.status, [key]: item };
      this.results[key] = item.result;
    });
  }

  async setUpAll() {
    await this.run("all", async () => {
      const items = await api.prepareNoteTypes();
      this.status = Object.fromEntries(items.map((item) => [item.key, item]));
      this.results = Object.fromEntries(items.map((item) => [item.key, item.result]));
    });
  }

  private async run(key: string, work: () => Promise<void>) {
    if (this.busy || this.checking) return;
    this.busy = key;
    this.setupError = null;
    try {
      await work();
    } catch (error) {
      this.setupError = { key, ...failure(error) };
    } finally {
      this.busy = "";
    }
  }
}

export const noteTypes = new NoteTypes();
