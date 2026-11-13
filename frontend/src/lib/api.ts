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

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 422) {
    const { detail } = await response.json();
    if (detail && typeof detail === "object" && "route" in detail) {
      throw new DraftError(detail.code, detail.route, detail.message);
    }
  }
  if (!response.ok) throw new Error(`${method} ${path} returned ${response.status}`);
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("GET", "/api/health"),
  settings: () => request<Settings>("GET", "/api/settings"),
  patchSettings: (patch: Partial<Settings["defaults"]> & { ui_language?: string }) =>
    request<Settings>("PATCH", "/api/settings", patch),
  providers: () => request<Provider[]>("GET", "/api/models/providers"),
  saveModels: (routes: RoutesIn) => request<Settings>("PUT", "/api/models", routes),
  testModels: (routes: RoutesIn) =>
    request<Record<Route, RouteCheck>>("POST", "/api/models/test", routes),
  listModels: (route: Route, target: RouteIn) =>
    request<ModelList>("POST", "/api/models/list", { route, target }),
};
