<script lang="ts">
  import CardPreview from "../components/CardPreview.svelte";
  import CardThemePicker from "../components/CardThemePicker.svelte";
  import Pane from "../components/Pane.svelte";
  import type { NoteTypeInfo, NoteTypeItem } from "../lib/api";
  import { t, type MessageKey } from "../lib/i18n.svelte";
  import en from "../lib/locales/en.json";
  import { noteTypes, type Failure } from "../lib/noteTypes.svelte";
  import { link, router } from "../lib/router.svelte";
  import { sectionFor } from "../lib/settings";
  import { cardTheme } from "../lib/cardTheme.svelte";
  import { palettes } from "../lib/theme.svelte";

  // Anki's state is read again on every visit: it may have changed in Anki.
  void noteTypes.load();
  // Each visit starts from the saved card theme; untried picks are dropped.
  void cardTheme.load();

  /** The list entry above the note types that opens the card theme. */
  const THEME = "theme";

  let list = $state<HTMLUListElement>();

  const types = $derived(noteTypes.types ?? []);
  const wanted = $derived(router.path.replace(/^\/notetypes\/?/, "").split("/")[0] ?? "");
  const showTheme = $derived(wanted === THEME);
  const info = $derived(showTheme ? undefined : (types.find((n) => n.key === wanted) ?? types[0]));
  const themeLabel = $derived.by(() => {
    const saved = cardTheme.saved;
    if (!saved) return "";
    const name = (id: string) => palettes.find((p) => p.id === id)?.name ?? id;
    return saved.light === saved.dark
      ? name(saved.light)
      : t("cardtheme.both", { light: name(saved.light), dark: name(saved.dark) });
  });
  const status = $derived(info && noteTypes.status ? noteTypes.status[info.key] : undefined);
  const sample = $derived(info ? noteTypes.samples[info.key] : undefined);
  const result = $derived(info ? noteTypes.results[info.key] : undefined);
  const busy = $derived(!!noteTypes.busy || noteTypes.checking);

  $effect(() => {
    if (info) void noteTypes.sample(info.key);
  });

  function name(type: NoteTypeInfo): string {
    return type.stem_type ? t(`stem.type.${type.stem_type}`) : t(`generate.kind.${type.kind}`);
  }

  function fullName(type: NoteTypeInfo): string {
    return type.stem_type ? `${t("generate.kind.stem")} · ${name(type)}` : name(type);
  }

  function needsSetUp(item: NoteTypeItem): boolean {
    return item.state !== "synced" || !item.deck_exists;
  }

  /** The list's status mark: ✓ up to date, ! needs an update, + not created. */
  function mark(item: NoteTypeItem | undefined): { glyph: string; tone: string; text: string } {
    if (!item) {
      return noteTypes.checking
        ? { glyph: "…", tone: "muted", text: "" }
        : { glyph: "·", tone: "muted", text: "" };
    }
    const done = noteTypes.results[item.key];
    if (item.state === "missing") return { glyph: "+", tone: "new", text: t("anki.types.missing") };
    if (needsSetUp(item)) return { glyph: "!", tone: "warn", text: t("anki.types.update") };
    const text = done && done !== "unchanged" ? t(`anki.types.${done}`) : t("anki.types.synced");
    return { glyph: "✓", tone: "ok", text };
  }

  /** What setting the selected type up would change, in words. */
  const changes = $derived.by((): string[] => {
    if (!status || status.state === "missing") return [];
    const out: string[] = [];
    if (status.missing_fields.length) {
      out.push(t("notetypes.change.fields", { names: status.missing_fields.join(", ") }));
    }
    if (status.missing_templates.length) {
      const names = status.missing_templates.map(templateName).join(", ");
      out.push(t("notetypes.change.templates", { names }));
    }
    if (status.css_differs) out.push(t("notetypes.change.css"));
    if (!status.deck_exists) out.push(t("notetypes.change.deck", { deck: status.deck }));
    return out;
  });

  function templateName(template: string): string {
    const key = `preview.template.${template}`;
    return key in en ? t(key as MessageKey) : template;
  }

  function errorText(failure: Failure): string {
    const own = `notetypes.err.${failure.code}`;
    const anki = `anki.err.${failure.code}`;
    const key = own in en ? own : anki in en ? anki : "anki.err.error";
    return t(key as MessageKey, { url: failure.detail, path: "", detail: failure.detail });
  }

  function select(key: string) {
    router.go(`/notetypes/${key}`);
  }

  function onKey(event: KeyboardEvent) {
    if (event.ctrlKey || event.metaKey || event.altKey || !types.length) return;
    const target = event.target as HTMLElement;
    if (target.closest("input, textarea, select, [contenteditable]")) return;
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const keys = [THEME, ...types.map((type) => type.key)];
    const i = keys.indexOf(info?.key ?? THEME) + (event.key === "ArrowDown" ? 1 : -1);
    const next = keys[Math.max(0, Math.min(keys.length - 1, i))]!;
    select(next);
    list?.querySelector<HTMLElement>(`[data-key="${next}"]`)?.focus();
  }
</script>

<svelte:window onkeydown={onKey} />

{#snippet goFix(code: string)}
  {@const section = sectionFor(code)}
  {#if section}
    <a class="go" href="/settings/{section}" onclick={link}>
      {t("settings.open", { section: t(`settings.section.${section}`) })}
    </a>
  {/if}
{/snippet}

<div class="page">
  <Pane title={t("nav.notetypes")} area="list" fill>
    {#if noteTypes.loadError}
      <p class="error" role="alert">{t("notetypes.err.load")}</p>
    {:else}
      <ul class="types" bind:this={list} aria-label={t("nav.notetypes")}>
        <li>
          <a
            href="/notetypes/{THEME}"
            onclick={link}
            data-key={THEME}
            class="type theme"
            class:on={showTheme}
            aria-current={showTheme ? "page" : undefined}
          >
            <span class="glyph new" aria-hidden="true">◐</span>
            <span class="tname">{t("cardtheme.title")}</span>
            <span class="tstate muted">{themeLabel}</span>
          </a>
        </li>
        <li class="divider" aria-hidden="true"></li>
        {#each types as type, i (type.key)}
          {@const m = mark(noteTypes.status?.[type.key])}
          {#if type.stem_type && !types[i - 1]?.stem_type}
            <li class="group" aria-hidden="true">{t("generate.kind.stem")}</li>
          {/if}
          <li>
            <a
              href="/notetypes/{type.key}"
              onclick={link}
              data-key={type.key}
              class="type"
              class:on={type === info}
              class:sub={!!type.stem_type}
              aria-current={type === info ? "page" : undefined}
            >
              <span class="glyph {m.tone}" aria-hidden="true">{m.glyph}</span>
              <span class="tname">{name(type)}</span>
              <span class="tstate {m.tone}">{m.text}</span>
            </a>
          </li>
        {/each}
      </ul>

      <div class="foot" aria-live="polite">
        {#if noteTypes.statusError}
          <p class="error" role="alert">
            {errorText(noteTypes.statusError)}
            {@render goFix(noteTypes.statusError.code)}
          </p>
        {:else if noteTypes.status}
          <p class="note">
            {noteTypes.pending.length
              ? t("notetypes.summary.todo", { n: noteTypes.pending.length })
              : t("notetypes.summary.ok")}
          </p>
        {:else if noteTypes.checking}
          <p class="note">{t("notetypes.checking")}</p>
        {/if}
        {#if noteTypes.setupError?.key === "all"}
          <p class="error" role="alert">
            {errorText(noteTypes.setupError)}
            {@render goFix(noteTypes.setupError.code)}
          </p>
        {/if}
        <div class="actions">
          {#if noteTypes.pending.length > 1}
            <button class="primary" onclick={() => noteTypes.setUpAll()} disabled={busy}>
              {noteTypes.busy === "all"
                ? t("notetypes.working")
                : t("notetypes.updateAll", { n: noteTypes.pending.length })}
            </button>
          {/if}
          <button class="secondary" onclick={() => noteTypes.check()} disabled={busy}>
            {noteTypes.checking ? t("notetypes.checking") : t("notetypes.recheck")}
          </button>
        </div>
      </div>
    {/if}
  </Pane>

  <Pane title={showTheme ? t("cardtheme.title") : info ? fullName(info) : t("nav.notetypes")} area="detail">
    <div class="body">
      {#if showTheme}
        <CardThemePicker />
      {:else if info}
        <p class="ident mono">
          <span title={t("notetypes.ankiName")}>{info.name}</span>
          <span class="sep" aria-hidden="true">·</span>
          <span title={t("notetypes.deck")}>{info.deck}</span>
        </p>

        <section class="state" aria-busy={noteTypes.busy === info.key || noteTypes.checking}>
          {#if status}
            {@const m = mark(status)}
            <p class="state-line {m.tone}">
              <span class="glyph" aria-hidden="true">{m.glyph}</span>
              {t(`notetypes.state.${status.state === "synced" && !status.deck_exists ? "deck" : status.state}`)}
            </p>
            {#if changes.length}
              <ul class="changes">
                {#each changes as change (change)}
                  <li>{change}</li>
                {/each}
              </ul>
            {/if}
            {#if needsSetUp(status)}
              <div class="row">
                <button class="primary" onclick={() => noteTypes.setUp(info.key)} disabled={busy}>
                  {noteTypes.busy === info.key
                    ? t("notetypes.working")
                    : t(status.state === "missing" ? "notetypes.create" : "notetypes.update")}
                </button>
                <span class="note">
                  {status.state === "missing"
                    ? t("notetypes.createNote", { deck: info.deck })
                    : t("notetypes.safe")}
                </span>
              </div>
            {:else if result && result !== "unchanged"}
              <p class="note">{t(`notetypes.result.${result}`)}</p>
            {/if}
          {:else if noteTypes.checking}
            <p class="note">{t("notetypes.checking")}</p>
          {:else if noteTypes.statusError}
            <p class="note">{t("notetypes.unknown")}</p>
          {/if}
          {#if noteTypes.setupError && noteTypes.setupError.key === info.key}
            <p class="error" role="alert">
              {errorText(noteTypes.setupError)}
              {@render goFix(noteTypes.setupError.code)}
            </p>
          {/if}
        </section>

        <div class="cols">
          <section class="sample" aria-labelledby="sample-title">
            <h3 id="sample-title" class="label">{t("notetypes.sample")}</h3>
            {#if sample === "failed"}
              <p class="error" role="alert">{t("notetypes.err.sample")}</p>
            {:else if sample}
              {#key info.key}
                <CardPreview note={sample} />
              {/key}
              <p class="note">{t("notetypes.sampleNote")}</p>
            {:else}
              <p class="note">{t("notetypes.sampleLoading")}</p>
            {/if}
          </section>

          <aside class="anatomy">
            <h3 class="label">{t("notetypes.templates", { n: info.templates.length })}</h3>
            <ul class="chips">
              {#each info.templates as template (template)}
                {@const added = status?.missing_templates.includes(template)}
                <li class:added>{templateName(template)}</li>
              {/each}
            </ul>
            <h3 class="label">{t("notetypes.fields", { n: info.fields.length })}</h3>
            <ul class="chips mono">
              {#each info.fields as field (field)}
                {@const added = status?.missing_fields.includes(field)}
                <li class:added title={added ? t("notetypes.addedField") : undefined}>{field}</li>
              {/each}
            </ul>
            <p class="note">{t("notetypes.ankiEdit")}</p>
          </aside>
        </div>
      {:else if !noteTypes.loadError}
        <p class="note">{t("notetypes.loading")}</p>
      {/if}
    </div>
  </Pane>
</div>

<style>
  .page {
    display: grid;
    gap: var(--gap);
    height: 100%;
    padding: 2px 10px 10px;
    grid-template-columns: 280px minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr);
    grid-template-areas: "list detail";
  }

  .mono {
    font-family: var(--mono);
    font-size: 13px;
  }

  .label {
    margin: 0 0 8px;
    font-size: 13px;
    font-weight: 400;
    color: var(--muted);
  }

  .note {
    margin: 0;
    font-size: 14px;
    color: var(--muted);
  }

  .error {
    margin: 0;
    font-size: 14px;
    color: var(--err);
  }

  .go {
    margin-left: 4px;
    white-space: nowrap;
  }

  .primary:disabled,
  .secondary:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  /* List */
  .types {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    margin: 0 -8px;
    padding: 0 8px;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  /* "Card theme" stays whole; the palette names give way. */
  @container app (min-width: 1001px) {
    .type.theme {
      grid-template-columns: 18px auto minmax(0, 1fr);
    }

    .type.theme .tstate {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      text-align: right;
    }
  }

  .divider {
    margin: 6px 8px;
    border-top: 1px solid var(--border);
  }

  .group {
    margin: 10px 8px 2px;
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
  }

  .type {
    display: grid;
    grid-template-columns: 18px minmax(0, 1fr) auto;
    align-items: center;
    gap: 8px;
    min-height: 40px;
    padding: 6px 8px;
    border-radius: 6px;
    color: inherit;
    text-decoration: none;
  }

  .type.sub .tname {
    padding-left: 10px;
  }

  .type:hover {
    background: var(--outer);
  }

  .type.on {
    background: var(--sel);
  }

  .glyph {
    display: grid;
    place-items: center;
    font-family: var(--mono);
    font-size: 12px;
  }

  .tname {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tstate {
    font-family: var(--mono);
    font-size: 12px;
  }

  .muted {
    color: var(--muted);
  }

  .ok {
    color: var(--ok);
  }

  .warn {
    color: var(--warn);
  }

  .new {
    color: var(--accent);
  }

  .tstate.ok {
    color: var(--muted);
  }

  .foot {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  /* Detail: the pane title overlaps the border, so scroll inside it. */
  .body {
    height: 100%;
    overflow-y: auto;
    margin: -4px -8px 0;
    padding: 4px 8px 0;
  }

  .ident {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 8px;
    margin: 0 0 14px;
    color: var(--muted);
  }

  .state {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 20px;
  }

  .state:empty {
    display: none;
  }

  .state-line {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0;
    font-weight: 600;
  }

  .state-line.ok {
    color: var(--fg);
  }

  .state-line.ok .glyph {
    color: var(--ok);
  }

  .changes {
    margin: 0;
    padding-left: 20px;
    font-size: 14px;
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 14px;
  }

  .cols {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 260px;
    gap: 24px;
    align-items: start;
    padding-bottom: 8px;
  }

  .sample {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }

  .sample .label {
    margin: 0;
  }

  .anatomy {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 0 0 18px;
    padding: 0;
    list-style: none;
  }

  .chips li {
    padding: 2px 8px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 13px;
    overflow-wrap: anywhere;
  }

  .chips li.added {
    border-color: var(--warn);
    color: var(--warn);
  }

  @container app (max-width: 1000px) {
    .page {
      grid-template-columns: 220px minmax(0, 1fr);
    }

    .tstate {
      display: none;
    }

    .cols {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  /* Phone: the types become a scrolling strip above the selected one. */
  @container app (max-width: 600px) {
    .page {
      padding: 0 8px 8px;
      gap: 8px;
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: auto minmax(0, 1fr);
      grid-template-areas:
        "list"
        "detail";
    }

    .types {
      flex-direction: row;
      overflow-x: auto;
      gap: 4px;
      margin: 0;
      padding: 0 0 2px;
    }

    .group,
    .divider {
      display: none;
    }

    .types li {
      flex: none;
    }

    .type {
      grid-template-columns: auto auto;
      min-height: 36px;
      padding: 6px 10px;
      border: 1px solid var(--border);
      white-space: nowrap;
    }

    .type.on {
      border-color: var(--accent);
    }

    .type.sub .tname {
      padding-left: 0;
    }

    .foot {
      flex-direction: row;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
      padding-top: 8px;
    }

    .foot .note {
      flex: 1 1 auto;
    }

    .actions .secondary,
    .actions .primary {
      min-height: 36px;
      padding-block: 4px;
    }
  }
</style>
