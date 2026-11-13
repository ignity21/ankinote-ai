/**
 * State for "First card": generate one word, preview it, save it to Anki.
 * Generating can take a minute (text, then audio and image), so it counts
 * the seconds; a failed save keeps the draft, so nothing is regenerated.
 */
import { api, ApiError, type DraftNote, type SavedNote } from "./api";
import { SAMPLE_WORD } from "./languages";

export class FirstCard {
  word = $state("");
  target = $state<string | null>(null);
  generating = $state(false);
  elapsed = $state(0);
  notes = $state<DraftNote[]>([]);
  selected = $state(0);
  saving = $state(false);
  saved = $state<SavedNote | null>(null);
  /** Error code from the server ("server" when it didn't answer), and its detail. */
  failure = $state<{ code: string; detail: string; during: "generate" | "save" } | null>(null);

  readonly note = $derived(this.notes[this.selected] ?? null);

  async load() {
    try {
      const { target } = await api.languages();
      this.target = target;
      if (!this.word) this.word = SAMPLE_WORD[target]?.word ?? "";
    } catch {
      // The word field still works; it just starts empty.
    }
  }

  async generate() {
    const word = this.word.trim();
    if (!word || this.generating) return;
    this.generating = true;
    this.failure = null;
    this.saved = null;
    this.elapsed = 0;
    const timer = setInterval(() => (this.elapsed += 1), 1000);
    try {
      this.notes = (await api.generateWord(word)).notes;
      this.selected = 0;
    } catch (error) {
      this.failure = describe(error, "generate");
    } finally {
      clearInterval(timer);
      this.generating = false;
    }
  }

  /** Save every note the word produced (one per part of speech). */
  async save() {
    if (!this.notes.length || this.saving) return;
    this.saving = true;
    this.failure = null;
    try {
      let last: SavedNote | null = null;
      for (const note of this.notes) {
        last = await api.saveDraft(note.id);
        note.note_id = last.note_id;
      }
      this.saved = last;
    } catch (error) {
      this.failure = describe(error, "save");
    } finally {
      this.saving = false;
    }
  }
}

function describe(error: unknown, during: "generate" | "save") {
  if (error instanceof ApiError) return { code: error.code, detail: error.detail, during };
  return { code: "server", detail: "", during };
}
