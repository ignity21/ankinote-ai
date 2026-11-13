export type Health = { status: "ok"; version: string };

export type Route = "text" | "image" | "speech";
export const ROUTES: Route[] = ["text", "image", "speech"];

export type Provider = {
  id: string;
  label: string;
  recommended: boolean;
  models: Partial<Record<Route, string>>;
  base_url: string;
  key_url: string;
};

export type RouteView = {
  profile: string;
  provider: string;
  model: string;
  base_url: string;
  key_hint: string;
  follows_preset: boolean;
};

export type Settings = {
  needs_setup: boolean;
  ui_language: string;
  defaults: { native_language: string; target_language: string; generate_image: boolean };
  anki_backend: string;
  anki_collection_path: string;
  models: Record<Route, RouteView | null>;
};

/** One route as sent to the server. `api_key: null` keeps the saved key. */
export type RouteIn = { provider: string; model: string; base_url: string; api_key: string | null };
export type RoutesIn = { text: RouteIn; image: RouteIn | null; speech: RouteIn | null };

export type FailureCode =
  | ""
  | "auth"
  | "api_disabled"
  | "billing"
  | "model_not_found"
  | "quota"
  | "timeout"
  | "unreachable"
  | "cannot_list"
  | "error";

export type RouteCheck = {
  status: "ok" | "failed" | "unverified" | "off";
  model: string;
  checked: "generated" | "listed" | "";
  code: FailureCode;
  detail: string;
};

export type ModelList = { models: string[]; code: FailureCode; detail: string };

export type AnkiBackend = "collection" | "connect";
export type Direction = "upload" | "download";

export type SyncView = {
  state:
    | "not_logged_in"
    | "initializing"
    | "idle"
    | "syncing"
    | "pending"
    | "needs_full_sync_choice"
    | "error";
  initialized: boolean;
  full_sync_required: boolean;
  directions: Direction[];
  /** network, credentials, media, backup, full_sync_required, state_store, driver… */
  error: string | null;
  last_success: string | null;
  result: { collection_ok: boolean; media_ok: boolean } | null;
};

export type AnkiStatus = {
  /** The backend in use now. */
  backend: AnkiBackend;
  /** What the step preselects: the backend in use, else the recommendation. */
  choice: AnkiBackend;
  builtin_available: boolean;
  connect_url: string;
  collection_path: string;
  /** Whether the built-in collection is open. */
  open: boolean;
  open_error: { code: string; detail: string } | null;
  account: string | null;
  account_managed: boolean;
  sync: SyncView | null;
  /** A full upload or download is running. */
  busy: boolean;
  writable: boolean;
  /** Cards in ankinote's collection, only while a full-sync choice is pending. */
  local_cards: number | null;
};

export type NoteTypeItem = {
  key: string;
  name: string;
  deck: string;
  state: "synced" | "update" | "missing";
  result?: "created" | "updated" | "unchanged";
};

export type Languages = {
  native: string;
  target: string;
  natives: string[];
  targets: { id: string; beta: boolean }[];
};

/** A 422 from the server about one route's draft (unknown provider, missing key…). */
export class DraftError extends Error {
  constructor(
    readonly code: "key_missing" | "invalid",
    readonly route: Route,
    message: string,
  ) {
    super(message);
  }
}

/** Any other error reply: `code` says what went wrong (see the endpoint). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly detail: string,
  ) {
    super(`${status} ${code}`);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const { detail } = await response.json().catch(() => ({ detail: null }));
    if (response.status === 422 && detail && typeof detail === "object" && "route" in detail) {
      throw new DraftError(detail.code, detail.route, detail.message);
    }
    if (detail && typeof detail === "object" && "code" in detail) {
      throw new ApiError(response.status, detail.code, detail.detail ?? "");
    }
    throw new ApiError(response.status, "error", "");
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("GET", "/api/health"),
  settings: () => request<Settings>("GET", "/api/settings"),
  patchSettings: (patch: Partial<Settings["defaults"]> & { ui_language?: string }) =>
    request<Settings>("PATCH", "/api/settings", patch),
  languages: () => request<Languages>("GET", "/api/languages"),
  providers: () => request<Provider[]>("GET", "/api/models/providers"),
  saveModels: (routes: RoutesIn) => request<Settings>("PUT", "/api/models", routes),
  testModels: (routes: RoutesIn) =>
    request<Record<Route, RouteCheck>>("POST", "/api/models/test", routes),
  listModels: (route: Route, target: RouteIn) =>
    request<ModelList>("POST", "/api/models/list", { route, target }),
  anki: () => request<AnkiStatus>("GET", "/api/anki"),
  setAnkiBackend: (backend: AnkiBackend) =>
    request<AnkiStatus>("PUT", "/api/anki/backend", { backend }),
  ankiLogin: (email: string, password: string) =>
    request<AnkiStatus>("POST", "/api/anki/login", { email, password }),
  ankiLogout: () => request<AnkiStatus>("POST", "/api/anki/logout"),
  ankiSync: () => request<AnkiStatus>("POST", "/api/anki/sync"),
  ankiFullSync: (direction: Direction) =>
    request<AnkiStatus>("POST", "/api/anki/full-sync", { direction }),
  noteTypes: () => request<NoteTypeItem[]>("GET", "/api/anki/note-types"),
  prepareNoteTypes: () => request<NoteTypeItem[]>("POST", "/api/anki/note-types"),
};
