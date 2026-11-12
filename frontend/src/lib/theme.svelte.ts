import tokens from "$themes/palettes.json";

export type Mode = "system" | "light" | "dark";
export type PaletteId = keyof typeof tokens.palettes;

export const palettes = Object.entries(tokens.palettes).map(([id, p]) => ({
  id: id as PaletteId,
  name: p.name,
  light: p.light as Record<string, string>,
  dark: p.dark as Record<string, string>,
}));

const STORAGE_KEY = "ankinote.theme";
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

function load(): { palette: PaletteId; mode: Mode } {
  const fallback = { palette: tokens.default as PaletteId, mode: "system" as Mode };
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    if (saved && saved.palette in tokens.palettes && ["system", "light", "dark"].includes(saved.mode)) {
      return saved;
    }
  } catch {
    // Storage blocked or corrupt: use the defaults.
  }
  return fallback;
}

class Theme {
  palette = $state<PaletteId>(load().palette);
  mode = $state<Mode>(load().mode);
  #systemDark = $state(systemDark.matches);

  dark = $derived(this.mode === "dark" || (this.mode === "system" && this.#systemDark));

  constructor() {
    systemDark.addEventListener("change", (e) => (this.#systemDark = e.matches));
    $effect.root(() => {
      $effect(() => this.#apply());
    });
  }

  cyclePalette() {
    const ids = palettes.map((p) => p.id);
    this.palette = ids[(ids.indexOf(this.palette) + 1) % ids.length]!;
  }

  #apply() {
    const values = tokens.palettes[this.palette][this.dark ? "dark" : "light"];
    const root = document.documentElement;
    for (const [role, value] of Object.entries(values)) {
      root.style.setProperty(`--${role}`, value);
    }
    root.style.colorScheme = this.dark ? "dark" : "light";
    root.dataset.theme = this.dark ? "dark" : "light";
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ palette: this.palette, mode: this.mode }));
    } catch {
      // Not persisted; the choice still applies for this visit.
    }
  }
}

export const theme = new Theme();
