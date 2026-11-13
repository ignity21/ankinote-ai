/**
 * The Generate workspace's session: every line of input becomes a queue
 * row that generates in the background (a few at a time), and the preview
 * follows the selected row. Nothing reaches Anki until a row is saved.
 *
 * The session lives at module level, so switching workspaces keeps it; a
 * reload starts a new one (drafts are in the server's memory anyway).
 */
import { api, ApiError, type DraftNote, type Kind, type SavedNote } from "./api";

/** Providers rate-limit; two at a time keeps a batch moving without 429s. */
const CONCURRENCY = 2;
const STORAGE_KEY = "ankinote.generate";

export type RowState = "queued" | "generating" | "ready" | "saving" | "saved" | "failed";
export type Failure = { code: string; detail: string; during: "generate" | "save" };

export class Row {
  readonly id = crypto.randomUUID();
  state = $state<RowState>("queued");
  /** One note per part of speech for a word. */
  notes = $state<DraftNote[]>([]);
  /** Which of `notes` the preview shows. */
  pick = $state(0);
  startedAt = $state(0);
  failure = $state<Failure | null>(null);
  saved = $state<SavedNote | null>(null);

  constructor(
    readonly kind: Kind,
    readonly text: string,
  ) {}

  get note(): DraftNote | null {
    return this.notes[this.pick] ?? null;
  }

  /** Has a preview that can be saved (again). */
  get saveable(): boolean {
    return this.notes.length > 0 && (this.state === "ready" || this.state === "saved");
  }

  get busy(): boolean {
    return this.state === "queued" || this.state === "generating" || this.state === "saving";
  }
}

type Stored = { kind: Kind; image: boolean; audio: boolean };

function stored(): Partial<Stored> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Partial<Stored>;
  } catch {
    return {};
  }
}

class Session {
  rows = $state<Row[]>([]);
  selectedId = $state<string | null>(null);
  kind = $state<Kind>(stored().kind ?? "word");
  image = $state(stored().image ?? true);
  audio = $state(stored().audio ?? true);
  /** False when no image model is set up: the switch is off and disabled. */
  imageAvailable = $state(true);
  /** Ticks every second while something generates, for elapsed times. */
  now = $state(Date.now());

  #timer: ReturnType<typeof setInterval> | null = null;
  #saving: Promise<unknown> = Promise.resolve();
  #settingsLoaded = false;

  readonly selected = $derived(this.rows.find((r) => r.id === this.selectedId) ?? null);
  readonly readyCount = $derived(this.rows.filter((r) => r.state === "ready").length);

  constructor() {
    $effect.root(() => {
      $effect(() => {
        const value: Stored = { kind: this.kind, image: this.image, audio: this.audio };
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
        } catch {
          // Not persisted.
        }
      });
    });
  }

  /** Learn which media can be made; the switches follow it. */
  async load() {
    if (this.#settingsLoaded) return;
    try {
      const settings = await api.settings();
      this.#settingsLoaded = true;
      this.imageAvailable = settings.models.image !== null;
      if (stored().image === undefined) this.image = settings.defaults.generate_image;
    } catch {
      // Keep the switches as they are; a failed request shows on the row.
    }
  }

  /** Queue one row per non-empty line; returns how many were added. */
  add(input: string): number {
    const seen = new Set<string>();
    const lines = input
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line && !seen.has(line) && (seen.add(line), true));
    const rows = lines.map((line) => new Row(this.kind, line));
    if (!rows.length) return 0;
    this.rows.push(...rows);
    // Follow the new input unless the user is looking at a finished card.
    if (!this.selected || !this.selected.saveable) this.selectedId = rows[0]!.id;
    this.#pump();
    return rows.length;
  }

  select(row: Row) {
    this.selectedId = row.id;
  }

  /** Move the selection up (-1) or down (+1) the queue. */
  step(delta: number) {
    if (!this.rows.length) return;
    const index = this.rows.findIndex((r) => r.id === this.selectedId);
    const next = index < 0 ? 0 : Math.min(Math.max(index + delta, 0), this.rows.length - 1);
    this.selectedId = this.rows[next]!.id;
  }

  regenerate(row: Row) {
    if (row.busy) return;
    row.state = "queued";
    row.failure = null;
    this.#pump();
  }

  /** Remove a row that isn't working; its draft stays on the server until evicted. */
  remove(row: Row) {
    if (row.busy) return;
    const index = this.rows.indexOf(row);
    this.rows.splice(index, 1);
    if (this.selectedId === row.id) {
      this.selectedId = (this.rows[index] ?? this.rows[index - 1])?.id ?? null;
    }
  }

  /** Save every note of `row`; saves run one at a time. */
  save(row: Row): Promise<void> {
    if (!row.saveable) return Promise.resolve();
    row.state = "saving";
    row.failure = null;
    const run = this.#saving.then(async () => {
      try {
        let last: SavedNote | null = null;
        for (const note of row.notes) {
          last = await api.saveDraft(note.id);
          note.note_id = last.note_id;
        }
        row.saved = last;
        row.state = "saved";
      } catch (error) {
        row.failure = describe(error, "save");
        row.state = "ready";
      }
    });
    this.#saving = run;
    return run;
  }

  saveAllReady() {
    for (const row of this.rows) if (row.state === "ready") void this.save(row);
  }

  #pump() {
    let running = this.rows.filter((r) => r.state === "generating").length;
    for (const row of this.rows) {
      if (running >= CONCURRENCY) break;
      if (row.state !== "queued") continue;
      running += 1;
      void this.#generate(row);
    }
    this.#tick();
  }

  async #generate(row: Row) {
    row.state = "generating";
    row.startedAt = Date.now();
    row.saved = null;
    const image = row.kind === "word" && this.image && this.imageAvailable;
    const media = { image, audio: this.audio };
    try {
      row.notes = (await api.generate(row.kind, row.text, media)).notes;
      row.pick = 0;
      row.state = "ready";
    } catch (error) {
      row.failure = describe(error, "generate");
      row.state = "failed";
    }
    this.#pump();
  }

  #tick() {
    const active = this.rows.some((r) => r.state === "generating");
    if (active && !this.#timer) {
      this.now = Date.now();
      this.#timer = setInterval(() => (this.now = Date.now()), 1000);
    } else if (!active && this.#timer) {
      clearInterval(this.#timer);
      this.#timer = null;
    }
  }
}

function describe(error: unknown, during: Failure["during"]): Failure {
  if (error instanceof ApiError) return { code: error.code, detail: error.detail, during };
  return { code: "server", detail: "", during };
}

export const session = new Session();
