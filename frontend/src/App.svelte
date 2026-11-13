<script lang="ts">
  import TopBar from "./components/TopBar.svelte";
  import { t } from "./lib/i18n.svelte";
  import { router } from "./lib/router.svelte";
  import "./lib/theme.svelte";
  import Generate from "./routes/Generate.svelte";
  import NoteTypes from "./routes/NoteTypes.svelte";
  import Placeholder from "./routes/Placeholder.svelte";
  import Settings from "./routes/Settings.svelte";
  import Wizard from "./routes/Wizard.svelte";
  import { api } from "./lib/api";

  // A fresh install has no working text model yet: start in the wizard.
  api
    .settings()
    .then((s) => {
      if (s.needs_setup && router.path === "/") router.go("/wizard");
    })
    .catch(() => {
      // The top bar already shows the server as unreachable.
    });
</script>

<div class="app">
  <TopBar />
  <main>
    {#if router.path === "/"}
      <Generate />
    {:else if router.path === "/wizard"}
      <Wizard />
    {:else if router.path === "/notetypes" || router.path.startsWith("/notetypes/")}
      <NoteTypes />
    {:else if router.path === "/settings" || router.path.startsWith("/settings/")}
      <Settings />
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
