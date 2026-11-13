<script lang="ts">
  import Pane from "../components/Pane.svelte";
  import AnkiStep from "./wizard/AnkiStep.svelte";
  import AppearanceStep from "./wizard/AppearanceStep.svelte";
  import LanguageStep from "./wizard/LanguageStep.svelte";
  import ModelStep from "./wizard/ModelStep.svelte";
  import { t } from "../lib/i18n.svelte";
  import { link, router } from "../lib/router.svelte";
  import { SECTIONS, settingsSection } from "../lib/settings";

  // The wizard's steps, each saving in place: errors elsewhere link straight
  // to a section (/settings/models, /settings/anki…).
  const section = $derived(settingsSection(router.path));
</script>

<div class="settings">
  <Pane title={t("nav.settings")} area="nav">
    <nav class="sections" aria-label={t("nav.settings")}>
      {#each SECTIONS as s (s)}
        <a
          href="/settings/{s}"
          onclick={link}
          class:on={s === section}
          aria-current={s === section ? "page" : undefined}
        >
          {t(`settings.section.${s}`)}
        </a>
      {/each}
    </nav>
    <p class="again">
      <a href="/wizard" onclick={link}>{t("settings.wizard")}</a>
    </p>
  </Pane>

  <Pane title={t(`settings.section.${section}`)} area="body">
    <div class="body">
      <!-- Keyed so leaving a section drops its unsaved edits. -->
      {#key section}
        {#if section === "models"}
          <ModelStep settings />
        {:else if section === "anki"}
          <AnkiStep settings />
        {:else if section === "languages"}
          <LanguageStep settings />
        {:else}
          <AppearanceStep settings />
        {/if}
      {/key}
    </div>
  </Pane>
</div>

<style>
  .settings {
    display: grid;
    gap: var(--gap);
    height: 100%;
    padding: 2px 10px 10px;
    grid-template-columns: 240px minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr);
    grid-template-areas: "nav body";
  }

  .sections {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .sections a {
    display: flex;
    align-items: center;
    min-height: 40px;
    padding: 8px 10px;
    border-radius: 6px;
    color: inherit;
    text-decoration: none;
  }

  .sections a:hover {
    background: var(--outer);
  }

  .sections a.on {
    background: var(--sel);
  }

  .again {
    margin: 16px 0 0;
    padding: 12px 10px 0;
    border-top: 1px solid var(--border);
    font-size: 14px;
  }

  .again a {
    color: var(--accent);
  }

  /* The pane title overlaps the border, so scroll inside, not on the pane. */
  .body {
    height: 100%;
    overflow-y: auto;
    margin: -4px -8px 0;
    padding: 4px 8px 0;
  }

  @container app (max-width: 1000px) {
    .settings {
      grid-template-columns: 200px minmax(0, 1fr);
    }
  }

  /* Phone: the sections become a scrolling strip above the section. */
  @container app (max-width: 600px) {
    .settings {
      padding: 0 8px 8px;
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: auto minmax(0, 1fr);
      grid-template-areas:
        "nav"
        "body";
    }

    .sections {
      flex-direction: row;
      overflow-x: auto;
      gap: 4px;
    }

    .sections a {
      flex: none;
      min-height: 36px;
      padding: 6px 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      white-space: nowrap;
    }

    .sections a.on {
      border-color: var(--accent);
    }

    .again {
      display: none;
    }
  }
</style>
