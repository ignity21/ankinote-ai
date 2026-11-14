<script lang="ts">
  import type { Route } from "../lib/api";
  import { t, type MessageKey } from "../lib/i18n.svelte";
  import { CUSTOM, OFF, type ModelSetup } from "../lib/modelSetup.svelte";

  let { setup, route }: { setup: ModelSetup; route: Route } = $props();

  const r = $derived(setup.routes[route]);
  const choices = $derived(setup.providersFor(route));
  const same = $derived(setup.sameAsMain(route));
  const recommended = $derived(setup.recommended(route));
  const savedHint = $derived(
    !same && r.provider !== OFF ? setup.savedKeyHint(r.provider, r.baseUrl.trim()) : "",
  );
  const id = $derived(`route-${route}`);
  const keyUrl = $derived(r.provider === OFF ? "" : (setup.provider(r.provider)?.key_url ?? ""));

  // The datalist only suggests ids matching what's typed, so a filled-in model
  // hides the rest; this menu lists them all.
  let menuOpen = $state(false);
  let combo = $state<HTMLElement>();

  async function fetchModels() {
    await setup.loadOptions(route);
    menuOpen = r.options.length > 0;
  }

  function pick(option: string) {
    r.model = option;
    menuOpen = false;
  }

  function closeOutside(event: MouseEvent) {
    if (menuOpen && combo && !combo.contains(event.target as Node)) menuOpen = false;
  }
</script>

<svelte:window onclick={closeOutside} onkeydown={(e) => e.key === "Escape" && (menuOpen = false)} />

<fieldset class="route">
  <legend>{t(`model.route.${route}` as MessageKey)}</legend>

  <div class="row">
    <label class="field provider">
      <span class="label">{t("model.provider")}</span>
      <select
        class="input"
        value={r.provider}
        onchange={(e) => setup.setRouteProvider(route, e.currentTarget.value)}
      >
        {#each choices as p (p.id)}
          <option value={p.id}>{setup.label(p.id)}</option>
        {/each}
        {#if route !== "text"}<option value={OFF}>{t("model.off")}</option>{/if}
      </select>
    </label>

    {#if r.provider !== OFF}
      <div class="field model">
        <label class="label" for={`${id}-model`}>{t("model.model")}</label>
        <div class="combo" bind:this={combo}>
          <input
            id={`${id}-model`}
            class="input mono"
            list={`${id}-models`}
            bind:value={r.model}
            autocomplete="off"
            spellcheck="false"
            autocapitalize="off"
          />
          <button
            type="button"
            class="secondary fetch"
            class:spinning={r.optionsLoading}
            disabled={r.optionsLoading || !setup.canListOptions(route)}
            onclick={fetchModels}
            title={t("model.fetchModels")}
            aria-label={t("model.fetchModels")}
            aria-expanded={menuOpen}
            aria-controls={`${id}-menu`}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path
                d="M20 12a8 8 0 1 1-2.34-5.66M20 4v4.5h-4.5"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>
          {#if menuOpen}
            <ul class="menu" id={`${id}-menu`} role="listbox" aria-label={t("model.model")}>
              {#each r.options as option (option)}
                <li role="option" aria-selected={option === r.model.trim()}>
                  <button type="button" class="mono" onclick={() => pick(option)}>
                    {option}
                    {#if option === recommended}<span class="tag">{t("model.recommendedTag")}</span>{/if}
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
        <datalist id={`${id}-models`}>
          {#each r.options as option (option)}<option value={option}></option>{/each}
        </datalist>
      </div>
    {/if}
  </div>

  {#if r.provider === OFF}
    <p class="note">{t(`model.off.${route}` as MessageKey)}</p>
  {:else}
    <p class="note" aria-live="polite">
      {#if r.optionsLoading}
        {t("model.loadingModels")}
      {:else if r.optionsFailed}
        {t("model.fetchFailed")}
      {:else if recommended && r.model.trim() === recommended}
        {t("model.isRecommended")}
      {:else if recommended}
        <button class="link" onclick={() => (r.model = recommended)}>
          {t("model.useRecommended", { model: recommended.replace(/^[a-z]+\//, "") })}
        </button>
      {/if}
      {#if same}<span class="same"> · {t("model.sameKey")}</span>{/if}
    </p>

    {#if !same}
      <div class="row">
        {#if r.provider === CUSTOM}
          <label class="field">
            <span class="label">{t("model.baseUrl")}</span>
            <input
              class="input mono"
              type="url"
              bind:value={r.baseUrl}
              placeholder="http://localhost:11434/v1"
              onchange={() => setup.loadOptions(route)}
            />
          </label>
        {/if}
        <label class="field">
          <span class="label">
            {r.provider === CUSTOM ? t("model.keyOptional") : t("model.routeKey", { name: setup.label(r.provider) })}
          </span>
          <input
            class="input mono"
            type="password"
            bind:value={r.apiKey}
            autocomplete="off"
            placeholder={savedHint ? t("model.keySaved", { hint: savedHint }) : ""}
            onchange={() => setup.loadOptions(route)}
          />
        </label>
      </div>
      {#if r.provider === "google_tts"}<p class="note">{t("model.hint.google_tts")}</p>{/if}
      {#if keyUrl}
        <a class="note key-link" href={keyUrl} target="_blank" rel="noreferrer">
          {t("model.getKey", { name: setup.label(r.provider) })} ↗
        </a>
      {/if}
    {/if}
  {/if}
</fieldset>

<style>
  .route {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0;
    padding: 14px 0 0;
    border: 0;
    border-top: 1px solid var(--border);
    min-width: 0;
  }

  legend {
    float: left;
    width: 100%;
    padding: 0;
    margin-bottom: 4px;
    font-weight: 600;
  }

  .row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 10px;
  }

  .row:has(.provider) {
    grid-template-columns: 200px minmax(0, 1fr);
  }

  .combo {
    position: relative;
    display: flex;
    gap: 6px;
  }

  .fetch {
    flex: none;
    width: 44px;
    padding: 0;
  }

  .fetch:disabled {
    cursor: default;
    opacity: 0.5;
  }

  .fetch.spinning svg {
    animation: spin 0.9s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .menu {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    z-index: 10;
    max-height: 280px;
    overflow-y: auto;
    margin: 0;
    padding: 4px;
    list-style: none;
    background: var(--tile);
    border: 1px solid var(--border);
    border-radius: 8px;
  }

  .menu button {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    width: 100%;
    min-height: 40px;
    padding: 8px 10px;
    border: 0;
    border-radius: 6px;
    background: none;
    font-family: var(--mono);
    font-size: 14px;
    text-align: left;
    cursor: pointer;
  }

  .menu button:hover,
  .menu button:focus-visible {
    background: var(--sel);
    outline-offset: -2px;
  }

  .menu [aria-selected="true"] button {
    color: var(--accent);
  }

  .tag {
    flex: none;
    font-family: var(--sans);
    font-size: 12px;
    color: var(--muted);
  }

  .key-link {
    align-self: flex-start;
    color: var(--accent);
  }

  @container app (max-width: 600px) {
    .row,
    .row:has(.provider) {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
