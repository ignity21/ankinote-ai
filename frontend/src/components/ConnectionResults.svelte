<script lang="ts">
  import { ROUTES, type Route, type RouteCheck } from "../lib/api";
  import { t, type MessageKey } from "../lib/i18n.svelte";
  import type { ModelSetup } from "../lib/modelSetup.svelte";

  let { setup, results }: { setup: ModelSetup; results: Record<Route, RouteCheck> } = $props();

  const GLYPH = { ok: "✓", failed: "✗", unverified: "?", off: "–" } as const;

  function statusLabel(check: RouteCheck): string {
    if (check.status === "ok") return t(`model.status.${check.checked || "generated"}` as MessageKey);
    return t(`model.status.${check.status}` as MessageKey);
  }

  function message(route: Route, check: RouteCheck): string {
    if (check.status === "off") return t(`model.off.${route}` as MessageKey);
    // Listing can't tell a free-tier key from a paid one.
    if (check.status === "ok" && route === "image" && setup.routes.image.provider === "gemini") {
      return t("model.billingNote");
    }
    if (!check.code) return "";
    const name = setup.label(setup.routes[route].provider);
    return t(`model.err.${check.code}` as MessageKey, { name, model: check.model });
  }

  /** A bad key fails every route the same way; say it once. */
  function repeated(i: number): boolean {
    const [prev, here] = [ROUTES[i - 1], ROUTES[i]!];
    return !!prev && results[prev].code !== "" && results[prev].code === results[here].code
      && setup.routes[prev].provider === setup.routes[here].provider && results[here].code !== "model_not_found";
  }

  const anyListed = $derived(ROUTES.some((r) => results[r].checked === "listed"));
</script>

<ul class="results" aria-live="polite">
  {#each ROUTES as route, i (route)}
    {@const check = results[route]}
    {@const text = repeated(i) ? "" : message(route, check)}
    <li class={check.status}>
      <span class="route">{t(`model.route.${route}` as MessageKey)}</span>
      <span class="status"><span aria-hidden="true">{GLYPH[check.status]}</span> {statusLabel(check)}</span>
      <span class="model">{check.model.replace(/^[a-z]+\//, "")}</span>
      {#if text}<p class="msg">{text}</p>{/if}
      {#if check.detail && !repeated(i)}<p class="detail">{check.detail}</p>{/if}
    </li>
  {/each}
</ul>
{#if anyListed}<p class="note">{t("model.listedNote")}</p>{/if}
<p class="note">{t("model.changeLater")}</p>

<style>
  .results {
    list-style: none;
    margin: 0 0 8px;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--outer);
  }

  li {
    display: grid;
    grid-template-columns: 7em 9em minmax(0, 1fr);
    column-gap: 12px;
    align-items: baseline;
    padding: 10px 12px;
  }

  li + li {
    border-top: 1px solid var(--border);
  }

  .status,
  .model {
    font-family: var(--mono);
    font-size: 13px;
  }

  .model {
    overflow-wrap: anywhere;
    color: var(--muted);
  }

  .ok .status {
    color: var(--ok);
  }

  .failed .status {
    color: var(--err);
  }

  .unverified .status {
    color: var(--warn);
  }

  .off .status {
    color: var(--muted);
  }

  .msg,
  .detail {
    grid-column: 2 / -1;
    margin: 4px 0 0;
  }

  .detail {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
    overflow-wrap: anywhere;
  }

  .note + .note {
    margin-top: 4px;
  }

  @container app (max-width: 600px) {
    li {
      grid-template-columns: minmax(0, 1fr) auto;
    }

    .route {
      font-weight: 600;
    }

    .model,
    .msg,
    .detail {
      grid-column: 1 / -1;
    }
  }
</style>
