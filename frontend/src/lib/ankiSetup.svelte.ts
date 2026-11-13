/**
 * State for "Connect Anki": built-in Anki synced with AnkiWeb (recommended)
 * or Anki Desktop through AnkiConnect. Once connected and writable, the
 * note types and decks are set up automatically. Shared by the wizard and,
 * later, Settings → Anki.
 */
import {
  api,
  ApiError,
  type AnkiBackend,
  type AnkiStatus,
  type Direction,
  type NoteTypeItem,
} from "./api";

export type Action = "" | "load" | "connect" | "login" | "logout" | "sync" | "full" | "types";

/** Where an error happened decides where the step shows it. */
export type Failure = { scope: "connect" | "login" | "sync" | "types"; code: string; detail: string };

const POLL_MS = 1000;

export class AnkiSetup {
  status = $state<AnkiStatus | null>(null);
  loadError = $state(false);
  choice = $state<AnkiBackend>("collection");

  email = $state("");
  password = $state("");
  direction = $state<Direction | "">("");

  action = $state<Action>("load");
  failure = $state<Failure | null>(null);
  noteTypes = $state<NoteTypeItem[] | null>(null);

  private disposed = false;
  private polling = false;

  readonly sync = $derived(this.status?.sync ?? null);
  /** The chosen backend is the one in use (and, built-in, it's open). */
  readonly live = $derived(
    this.status !== null &&
      this.status.backend === this.choice &&
      (this.choice === "connect" || this.status.open),
  );
  /** Syncing with AnkiWeb, or a full upload/download, is running. */
  readonly syncing = $derived(
    !!this.status?.busy || this.sync?.state === "syncing" || this.sync?.state === "initializing",
  );
  readonly loggedIn = $derived(
    this.live && this.choice === "collection" && !!this.status?.account &&
      this.sync?.state !== "not_logged_in" && this.sync?.error !== "credentials",
  );
  readonly ready = $derived(
    this.live &&
      this.action === "" &&
      this.noteTypes !== null &&
      this.noteTypes.every((n) => n.state === "synced"),
  );

  async load() {
    try {
      this.status = await api.anki();
    } catch {
      this.loadError = true;
      return;
    } finally {
      this.action = "";
    }
    this.choice = this.status.builtin_available ? this.status.choice : "connect";
    if (!this.live) return;
    if (this.syncing) void this.poll();
    else if (this.choice === "collection" ? this.status.writable : true) await this.listNoteTypes();
  }

  select(choice: AnkiBackend) {
    if (choice === this.choice || this.action) return;
    this.choice = choice;
    this.failure = null;
    this.noteTypes = null;
  }

  dispose() {
    this.disposed = true;
  }

  private async run(action: Action, scope: Failure["scope"], work: () => Promise<void>) {
    if (this.action) return;
    this.action = action;
    this.failure = null;
    try {
      await work();
    } catch (error) {
      this.failure =
        error instanceof ApiError
          ? { scope, code: error.code, detail: error.detail }
          : { scope, code: "server", detail: "" };
    } finally {
      this.action = "";
    }
  }

  /** Open the built-in collection unless it already is. */
  private async ensureBuiltin() {
    if (this.status?.backend === "collection" && this.status.open) return;
    this.noteTypes = null;
    this.status = await api.setAnkiBackend("collection");
  }

  /** Built-in with a deployment-set account: opening it logs in and syncs. */
  async connectBuiltin() {
    await this.run("connect", "connect", async () => {
      await this.ensureBuiltin();
      if (this.status?.sync?.error === "credentials") this.status = await api.ankiSync();
    });
    await this.afterSync();
  }

  async login() {
    if (!this.email.trim() || !this.password) {
      this.failure = { scope: "login", code: "fields", detail: "" };
      return;
    }
    await this.run("login", "login", async () => {
      await this.ensureBuiltin();
      try {
        this.status = await api.ankiLogin(this.email.trim(), this.password);
      } finally {
        // Sent once; never kept, whether it worked or not.
        this.password = "";
      }
    });
    await this.afterSync();
  }

  async logout() {
    await this.run("logout", "sync", async () => {
      this.status = await api.ankiLogout();
      this.noteTypes = null;
    });
  }

  async retrySync() {
    await this.run("sync", "sync", async () => {
      this.status = await api.ankiSync();
    });
    await this.afterSync();
  }

  async fullSync(direction: Direction) {
    await this.run("full", "sync", async () => {
      this.status = await api.ankiFullSync(direction);
    });
    this.direction = "";
    await this.afterSync();
  }

  async connectDesktop() {
    await this.run("connect", "connect", async () => {
      this.noteTypes = null;
      this.status = await api.setAnkiBackend("connect");
    });
    if (this.failure) {
      // The choice was saved even though Anki didn't answer.
      this.status = await api.anki().catch(() => this.status);
      return;
    }
    await this.prepare();
  }

  /** After any sync-changing call: wait it out, then set up note types. */
  private async afterSync() {
    if (this.syncing) await this.poll();
    if (this.live && this.status?.writable && this.sync?.state !== "not_logged_in") {
      await this.prepare();
    }
  }

  private async poll() {
    if (this.polling) return;
    this.polling = true;
    try {
      while (!this.disposed && this.syncing) {
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
        try {
          this.status = await api.anki();
        } catch {
          // Server hiccup: keep the last status and try again.
        }
      }
    } finally {
      this.polling = false;
    }
  }

  private async listNoteTypes() {
    await this.run("types", "types", async () => {
      this.noteTypes = await api.noteTypes();
    });
    if (this.noteTypes?.some((n) => n.state !== "synced")) await this.prepare();
  }

  async prepare() {
    await this.run("types", "types", async () => {
      this.noteTypes = await api.prepareNoteTypes();
    });
  }
}
