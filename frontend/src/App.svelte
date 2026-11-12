<script lang="ts">
  import TopBar from "./components/TopBar.svelte";
  import { t } from "./lib/i18n.svelte";
  import { router } from "./lib/router.svelte";
  import "./lib/theme.svelte";
  import Generate from "./routes/Generate.svelte";
  import Placeholder from "./routes/Placeholder.svelte";
  import Wizard from "./routes/Wizard.svelte";
</script>

<div class="app">
  <TopBar />
  <main>
    {#if router.path === "/"}
      <Generate />
    {:else if router.path === "/wizard"}
      <Wizard />
    {:else if router.path === "/notetypes"}
      <Placeholder title={t("nav.notetypes")} message={t("page.soon")} />
    {:else if router.path === "/settings"}
      <Placeholder title={t("nav.settings")} message={t("page.soon")} />
    {:else}
      <Placeholder title="404" message={t("notfound")} />
    {/if}
  </main>
</div>

<style>
  /* Layouts switch on this container's width, not on device type. */
  .app {
    container: app / inline-size;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    height: 100%;
    padding-bottom: env(safe-area-inset-bottom);
  }

  main {
    min-height: 0;
  }
</style>
