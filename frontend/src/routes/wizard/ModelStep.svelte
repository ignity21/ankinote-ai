<script lang="ts">
  import { ROUTES } from "../../lib/api";
  import ConnectionResults from "../../components/ConnectionResults.svelte";
  import RouteEditor from "../../components/RouteEditor.svelte";
  import StepNav from "../../components/StepNav.svelte";
  import { t, type MessageKey } from "../../lib/i18n.svelte";
  import { ModelSetup } from "../../lib/modelSetup.svelte";

  let { onnext }: { onnext: () => void } = $props();

  const setup = new ModelSetup();
  let showKey = $state(false);
  let advanced = $state(false);

  setup.load().then(() => {
    // A saved setup that isn't the one-key default opens "Advanced" so it shows.
    advanced = setup.customized;
  });

  const main = $derived(setup.mainProvider);
  const savedHint = $derived(setup.savedKeyHint(setup.main));
  const mainRoutes = $derived(ROUTES.filter((route) => setup.sameAsMain(route)));

  function refreshOptions() {
    if (advanced) for (const route of ROUTES) void setup.loadOptions(route);
  }

  function toggleAdvanced(event: Event) {
    advanced = (event.currentTarget as HTMLDetailsElement).open;
    refreshOptions();
  }

  async function next() {
    if (await setup.save()) onnext();
  }

  const hint = $derived.by(() => {
    if (setup.canContinue) return "";
    if (setup.current && setup.results?.text.status !== "ok") return t("model.textFailed");
    return t("model.testFirst");
  });

  const errorText = $derived.by(() => {
    const error = setup.draftError;
    if (error) {
      return t(`model.err.${error.code}` as MessageKey, {
        route: t(`model.route.${error.route}` as MessageKey),
      });
    }
    return setup.failed ? t("model.err.server") : "";
  });
</script>

<p class="intro">{t("model.intro")}</p>

{#if setup.loadError}
  <p class="error" role="alert">{t("model.err.load")}</p>
{:else if main}
  {#if setup.usesMain}
    <section class="howto" aria-labelledby="howto-title">
      <h2 id="howto-title" class="label">{t("model.howTo")}</h2>
      <ol>
        <li>
          {t("model.howTo.key")}
          {#if main.key_url}
            <a href={main.key_url} target="_blank" rel="noreferrer">{t("model.howTo.open")} ↗</a>
          {/if}
        </li>
        {#if mainRoutes.includes("image")}<li>{t("model.howTo.billing")}</li>{/if}
      </ol>
      <p class="note">{t("model.howTo.noApis")}</p>
    </section>

    <div class="field key">
      <label class="label" for="api-key">{t("model.routeKey", { name: setup.label(main.id) })}</label>
      <div class="key-row">
        <input
          id="api-key"
          class="input mono"
          type={showKey ? "text" : "password"}
          bind:value={setup.apiKey}
          autocomplete="off"
          spellcheck="false"
          autocapitalize="off"
          placeholder={savedHint ? t("model.keySaved", { hint: savedHint }) : ""}
          onchange={refreshOptions}
        />
        <button class="secondary" type="button" onclick={() => (showKey = !showKey)} aria-pressed={showKey}>
          {showKey ? t("model.hide") : t("model.show")}
        </button>
      </div>
    </div>

    <div class="plan">
      <span class="label">{t("model.plan")}</span>
      <ul>
        {#each mainRoutes as route (route)}
          <li>
            <span>{t(`model.route.${route}` as MessageKey)}</span>
            <span class="model">{setup.routes[route].model.replace(/^[a-z]+\//, "")}</span>
          </li>
        {/each}
      </ul>
    </div>
  {:else}
    <p class="note">{t("model.mainUnused")}</p>
  {/if}

  <details class="advanced" open={advanced} ontoggle={toggleAdvanced}>
    <summary>{t("model.advanced")}</summary>
    <p class="note">{t("model.advancedIntro")}</p>
    {#each ROUTES as route (route)}
      <RouteEditor {setup} {route} />
    {/each}
  </details>

  <div class="test">
    <button
      class={setup.current ? "secondary" : "primary"}
      disabled={!setup.ready || setup.testing}
      onclick={() => setup.test()}
    >
      {setup.testing ? t("model.testing") : setup.results ? t("model.retest") : t("model.test")}
    </button>
  </div>

  {#if errorText}<p class="error" role="alert">{errorText}</p>{/if}

  {#if setup.current && setup.results}
    <ConnectionResults {setup} results={setup.results} />
  {/if}
{/if}

<StepNav {hint} onnext={next} nextDisabled={!setup.canContinue} busy={setup.saving} />

<style>
  .intro {
    max-width: 62ch;
    margin: 0 0 20px;
  }

  .label {
    font-size: 13px;
    font-weight: 400;
    color: var(--muted);
  }

  .howto {
    max-width: 62ch;
    margin: 0 0 20px;
    padding: 12px 16px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--outer);
  }

  .howto h2 {
    margin: 0 0 6px;
  }

  .howto ol {
    margin: 0 0 8px;
    padding-left: 1.4em;
  }

  .howto li + li {
    margin-top: 6px;
  }

  .howto a {
    color: var(--accent);
    white-space: nowrap;
  }

  .key {
    max-width: 620px;
  }

  .key-row {
    display: flex;
    gap: 8px;
  }

  .key-row .input {
    flex: 1;
    min-width: 0;
  }

  .plan {
    margin: 16px 0 0;
    max-width: 620px;
  }

  .plan ul {
    list-style: none;
    margin: 4px 0 0;
    padding: 0;
  }

  .plan li {
    display: grid;
    grid-template-columns: 7em minmax(0, 1fr);
    column-gap: 12px;
    padding: 2px 0;
  }

  .plan .model {
    font-family: var(--mono);
    font-size: 13px;
    color: var(--muted);
    overflow-wrap: anywhere;
  }

  .advanced {
    margin: 20px 0 0;
    max-width: 760px;
  }

  .advanced summary {
    display: inline-flex;
    align-items: center;
    min-height: 36px;
    color: var(--accent);
    cursor: pointer;
  }

  .advanced summary::before {
    content: "▸";
    width: 1.2em;
    font-family: var(--mono);
  }

  .advanced[open] summary::before {
    content: "▾";
  }

  .advanced > .note {
    margin: 4px 0 12px;
    max-width: 62ch;
  }

  .advanced :global(.route) {
    margin-top: 12px;
  }

  .test {
    margin: 20px 0 12px;
  }

  .test button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .error {
    margin: 0 0 12px;
    color: var(--err);
  }
</style>
