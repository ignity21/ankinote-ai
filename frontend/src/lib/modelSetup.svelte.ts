/**
 * State for "Connect an AI model": the recommended provider (Gemini) serves
 * every route with one key; "Advanced" points any route at another provider
 * with its own key, or turns pictures and audio off. Shared by the wizard
 * and, later, Settings → Models.
 */
import { t } from "./i18n.svelte";
import {
  api,
  DraftError,
  ROUTES,
  type Provider,
  type Route,
  type RouteCheck,
  type RouteIn,
  type RoutesIn,
  type Settings,
} from "./api";

export const CUSTOM = "custom";
export const OFF = "off";

export type RouteState = {
  /** A provider id, or OFF (image and speech only). */
  provider: string;
  model: string;
  /** Only used when this route's provider differs from the main one. */
  apiKey: string;
  baseUrl: string;
  options: string[];
  optionsLoading: boolean;
};

function emptyRoute(): RouteState {
  return { provider: OFF, model: "", apiKey: "", baseUrl: "", options: [], optionsLoading: false };
}

export class ModelSetup {
  providers = $state<Provider[]>([]);
  saved = $state<Settings | null>(null);
  loadError = $state(false);

  /** The recommended provider; its key is the one the wizard asks for. */
  main = $state("");
  apiKey = $state("");
  routes = $state<Record<Route, RouteState>>({
    text: emptyRoute(),
    image: emptyRoute(),
    speech: emptyRoute(),
  });

  results = $state<Record<Route, RouteCheck> | null>(null);
  /** The payload the results belong to; editing anything invalidates them. */
  private resultsFor = $state("");
  private savedFor = $state("");
  testing = $state(false);
  saving = $state(false);
  draftError = $state<DraftError | null>(null);
  failed = $state(false);

  readonly payload = $derived(this.buildPayload());
  private readonly payloadKey = $derived(JSON.stringify(this.payload));
  readonly current = $derived(this.results !== null && this.resultsFor === this.payloadKey);
  readonly unchangedSave = $derived(
    this.saved !== null && !this.saved.needs_setup && this.savedFor === this.payloadKey,
  );
  readonly canContinue = $derived(
    this.unchangedSave || (this.current && this.results?.text.status === "ok"),
  );
  /** Whether any route uses the main provider's key. */
  readonly usesMain = $derived(ROUTES.some((route) => this.sameAsMain(route)));
  /** Whether anything differs from the one-key default, so "Advanced" opens. */
  readonly customized = $derived(
    ROUTES.some((route) => {
      const r = this.routes[route];
      return r.provider !== this.main || r.model.trim() !== this.recommended(route);
    }),
  );
  /** Every route that's on has a model, a key and (custom) an address. */
  readonly ready = $derived(ROUTES.every((route) => this.routeReady(route)));

  provider(id: string): Provider | undefined {
    return this.providers.find((p) => p.id === id);
  }

  /** Display name; the custom endpoint's name is a description, so it's translated. */
  label(id: string): string {
    return id === CUSTOM ? t("model.custom") : (this.provider(id)?.label ?? "");
  }

  get mainProvider(): Provider | undefined {
    return this.provider(this.main);
  }

  /** Providers that can serve `route`. The custom endpoint can serve any. */
  providersFor(route: Route): Provider[] {
    return this.providers.filter((p) => p.id === CUSTOM || p.models[route]);
  }

  /** The hint for a saved key of this provider, e.g. "…a1b2". */
  savedKeyHint(providerId: string, baseUrl = ""): string {
    const views = this.saved ? Object.values(this.saved.models) : [];
    const view = views.find(
      (v) => v && v.key_hint && v.provider === providerId && (providerId !== CUSTOM || v.base_url === baseUrl),
    );
    return view?.key_hint ?? "";
  }

  sameAsMain(route: Route): boolean {
    return this.routes[route].provider === this.main;
  }

  /** Whether this route can be tested and saved as it stands. */
  routeReady(route: Route): boolean {
    const r = this.routes[route];
    if (r.provider === OFF) return route !== "text";
    if (!r.model.trim()) return false;
    if (r.provider === CUSTOM) return r.baseUrl.trim() !== "";
    const key = this.sameAsMain(route) ? this.apiKey : r.apiKey;
    return key.trim() !== "" || this.savedKeyHint(r.provider) !== "";
  }

  async load() {
    try {
      const [providers, saved] = await Promise.all([api.providers(), api.settings()]);
      this.providers = providers;
      this.saved = saved;
    } catch {
      this.loadError = true;
      return;
    }
    const main = this.providers.find((p) => p.recommended)?.id ?? this.providers[0]?.id ?? "";
    const text = this.saved?.models.text;
    if (this.saved && !this.saved.needs_setup && text && this.provider(text.provider)) {
      this.main = main;
      for (const route of ROUTES) {
        const view = this.saved.models[route];
        const known = view && this.provider(view.provider);
        this.routes[route] = known
          ? {
              ...emptyRoute(),
              provider: view.provider,
              model: view.model,
              baseUrl: view.provider === CUSTOM ? view.base_url : "",
            }
          : emptyRoute();
      }
      this.savedFor = JSON.stringify(this.buildPayload());
    } else {
      this.select(main);
    }
  }

  /** Pick the main provider; every route resets to its recommended model. */
  select(id: string) {
    this.main = id;
    const provider = this.provider(id);
    for (const route of ROUTES) {
      const model = provider?.models[route];
      if (model) this.routes[route] = { ...emptyRoute(), provider: id, model };
      else if (id === CUSTOM && route === "text") this.routes[route] = { ...emptyRoute(), provider: id };
      else this.routes[route] = emptyRoute();
    }
    this.draftError = null;
  }

  /** Point one route at another provider, using its recommended model. */
  setRouteProvider(route: Route, id: string) {
    const model = id === OFF ? "" : (this.provider(id)?.models[route] ?? "");
    this.routes[route] = { ...emptyRoute(), provider: id, model };
    void this.loadOptions(route);
  }

  recommended(route: Route): string {
    return this.provider(this.routes[route].provider)?.models[route] ?? "";
  }

  private routeIn(route: Route): RouteIn | null {
    const r = this.routes[route];
    if (r.provider === OFF || !r.provider) return null;
    const key = r.provider === this.main ? this.apiKey : r.apiKey;
    return {
      provider: r.provider,
      model: r.model.trim(),
      base_url: r.provider === CUSTOM ? r.baseUrl.trim() : "",
      api_key: key.trim() || null,
    };
  }

  private buildPayload(): RoutesIn {
    return {
      text: this.routeIn("text") ?? { provider: this.main, model: "", base_url: "", api_key: null },
      image: this.routeIn("image"),
      speech: this.routeIn("speech"),
    };
  }

  /** Fill a route's model suggestions from what the provider lists for this key. */
  async loadOptions(route: Route) {
    const target = this.routeIn(route);
    const r = this.routes[route];
    if (!target || (!target.api_key && target.provider !== CUSTOM && !this.savedKeyHint(target.provider))) {
      r.options = [];
      return;
    }
    if (target.provider === CUSTOM && !target.base_url) return;
    r.optionsLoading = true;
    try {
      const list = await api.listModels(route, target);
      r.options = list.models;
    } catch {
      r.options = [];
    } finally {
      r.optionsLoading = false;
    }
  }

  async test() {
    this.testing = true;
    this.failed = false;
    this.draftError = null;
    const sent = this.payloadKey;
    try {
      this.results = await api.testModels(this.payload);
      this.resultsFor = sent;
    } catch (error) {
      this.results = null;
      if (error instanceof DraftError) this.draftError = error;
      else this.failed = true;
    } finally {
      this.testing = false;
    }
  }

  /** Save the routes; true when there is nothing left to do on this step. */
  async save(): Promise<boolean> {
    if (this.unchangedSave) return true;
    this.saving = true;
    this.failed = false;
    try {
      this.saved = await api.saveModels(this.payload);
      this.apiKey = "";
      for (const route of ROUTES) this.routes[route].apiKey = "";
      this.savedFor = this.payloadKey;
      return true;
    } catch (error) {
      if (error instanceof DraftError) this.draftError = error;
      else this.failed = true;
      return false;
    } finally {
      this.saving = false;
    }
  }
}
