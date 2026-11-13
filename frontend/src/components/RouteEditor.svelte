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
</script>

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
      <label class="field model">
        <span class="label">{t("model.model")}</span>
        <input
          class="input mono"
          list={`${id}-models`}
          bind:value={r.model}
          autocomplete="off"
          spellcheck="false"
          autocapitalize="off"
        />
        <datalist id={`${id}-models`}>
          {#each r.options as option (option)}<option value={option}></option>{/each}
        </datalist>
      </label>
    {/if}
  </div>

  {#if r.provider === OFF}
    <p class="note">{t(`model.off.${route}` as MessageKey)}</p>
  {:else}
    <p class="note" aria-live="polite">
      {#if r.optionsLoading}
        {t("model.loadingModels")}
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
