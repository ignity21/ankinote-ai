<script lang="ts">
  import { onDestroy } from "svelte";
  import StepNav from "../../components/StepNav.svelte";
  import type { AnkiBackend, Direction } from "../../lib/api";
  import { AnkiSetup, type Failure } from "../../lib/ankiSetup.svelte";
  import { t, type MessageKey } from "../../lib/i18n.svelte";
  import en from "../../lib/locales/en.json";

  let { onback, onnext }: { onback: () => void; onnext: () => void } = $props();

  const setup = new AnkiSetup();
  void setup.load();
  onDestroy(() => setup.dispose());

  let showPassword = $state(false);

  const status = $derived(setup.status);
  const sync = $derived(setup.sync);
  const builtin = $derived(setup.choice === "collection");
  const managed = $derived(builtin && !!status?.account_managed && setup.live);
  const directions = $derived(sync?.full_sync_required ? sync.directions : []);
  /** One direction means Anki found one side empty: nothing gets replaced. */
  const oneWay = $derived(directions.length === 1 ? directions[0]! : null);
  const choosing = $derived(
    setup.live && builtin && sync?.state === "needs_full_sync_choice" && !setup.syncing,
  );
  const showLogin = $derived(builtin && !managed && !setup.loggedIn && !setup.syncing);

  function failureText(failure: Failure | null): string {
    if (!failure) return "";
    const known = `anki.err.${failure.code}`;
    // An unknown server code falls back to the generic message.
    const key = (known in en ? known : "anki.err.error") as MessageKey;
    return t(key, {
      url: status?.connect_url ?? "",
      path: status?.collection_path ?? "",
      detail: failure.detail,
    });
  }

  const openError = $derived(
    builtin && status?.open_error && !setup.live
      ? failureText({ scope: "connect", ...status.open_error })
      : "",
  );

  const syncLine = $derived.by((): { glyph: string; tone: string; text: string } | null => {
    if (!setup.live || !builtin || !sync || sync.state === "not_logged_in") return null;
    if (status?.busy) {
      return { glyph: "…", tone: "warn", text: t("anki.sync.full") };
    }
    if (setup.syncing) return { glyph: "…", tone: "warn", text: t("anki.sync.syncing") };
    if (sync.error === "credentials") return { glyph: "✗", tone: "err", text: t("anki.sync.credentials") };
    if (sync.state === "needs_full_sync_choice") {
      return { glyph: "!", tone: "warn", text: t("anki.sync.choice") };
    }
    if (sync.error === "backup") return { glyph: "✗", tone: "err", text: t("anki.sync.backup") };
    if (sync.error === "media") {
      return { glyph: "!", tone: "warn", text: t("anki.sync.media") };
    }
    if (sync.state === "pending") {
      return {
        glyph: "!",
        tone: "warn",
        text: t(sync.initialized ? "anki.sync.offline" : "anki.sync.offlineFirst"),
      };
    }
    if (sync.state === "error") return { glyph: "✗", tone: "err", text: t("anki.sync.error") };
    return { glyph: "✓", tone: "ok", text: t("anki.sync.idle") };
  });

  const canRetry = $derived(
    setup.live && builtin && !setup.syncing && !!sync &&
      (sync.state === "pending" || (sync.state === "error" && sync.error !== "credentials")),
  );

  function pick(choice: AnkiBackend) {
    setup.select(choice);
  }

  function confirmFull(direction: Direction) {
    void setup.fullSync(direction);
  }

  const hint = $derived.by(() => {
    if (setup.ready) return "";
    if (setup.action === "types") return t("anki.types.working");
    if (!builtin) return t("anki.hint.desktop");
    return t(setup.loggedIn || managed ? "anki.hint.sync" : "anki.hint.builtin");
  });

  /** Several STEM note types share one deck; show the deck once. */
  const rows = $derived(
    (setup.noteTypes ?? []).map((n, i, all) => ({ ...n, sameDeck: i > 0 && all[i - 1]!.deck === n.deck })),
  );
</script>

<p class="intro">{t("anki.intro")}</p>

{#if setup.loadError}
  <p class="error" role="alert">{t("anki.err.load")}</p>
{:else if status}
  <div class="choices" role="radiogroup" aria-label={t("anki.choose")}>
    <button
      class="choice"
      role="radio"
      aria-checked={builtin}
      disabled={!status.builtin_available || !!setup.action}
      onclick={() => pick("collection")}
    >
      <span class="choice-title">
        <span class="dot" aria-hidden="true"></span>{t("anki.builtin")}
        <span class="tag">{t("anki.recommended")}</span>
      </span>
      <span class="choice-text">
        {status.builtin_available ? t("anki.builtin.text") : t("anki.builtin.unavailable")}
      </span>
    </button>
    <button
      class="choice"
      role="radio"
      aria-checked={!builtin}
      disabled={!!setup.action}
      onclick={() => pick("connect")}
    >
      <span class="choice-title"><span class="dot" aria-hidden="true"></span>{t("anki.desktop")}</span>
      <span class="choice-text">{t("anki.desktop.text")}</span>
    </button>
  </div>

  {#if builtin}
    <section class="panel" aria-label={t("anki.builtin")}>
      {#if openError}<p class="error" role="alert">{openError}</p>{/if}

      {#if managed}
        <p>{t("anki.managed", { account: status.account ?? "" })}</p>
      {:else if setup.loggedIn}
        <p class="account">
          <span class="key">AnkiWeb</span>
          <span class="mono">{status.account}</span>
          <button class="link" onclick={() => setup.logout()} disabled={!!setup.action}>
            {t("anki.logout")}
          </button>
        </p>
      {/if}

      {#if showLogin}
        {#if setup.live && sync?.error === "credentials"}
          <p class="note">{t("anki.relogin")}</p>
        {/if}
        <form
          class="login"
          onsubmit={(event) => {
            event.preventDefault();
            void setup.login();
          }}
        >
          <label class="field">
            <span class="label">{t("anki.email")}</span>
            <input
              class="input"
              type="email"
              autocomplete="username"
              autocapitalize="off"
              spellcheck="false"
              bind:value={setup.email}
            />
          </label>
          <div class="field">
            <label class="label" for="ankiweb-password">{t("anki.password")}</label>
            <div class="pw-row">
              <input
                id="ankiweb-password"
                class="input"
                type={showPassword ? "text" : "password"}
                autocomplete="current-password"
                bind:value={setup.password}
              />
              <button
                class="secondary"
                type="button"
                aria-pressed={showPassword}
                onclick={() => (showPassword = !showPassword)}
              >
                {showPassword ? t("model.hide") : t("model.show")}
              </button>
            </div>
          </div>
          <p class="note">{t("anki.passwordNote")}</p>
          <p class="note">
            {t("anki.noAccount")}
            <a href="https://ankiweb.net/account/signup" target="_blank" rel="noreferrer">
              {t("anki.signup")} ↗
            </a>
          </p>
          <div class="actions">
            <button class="primary" type="submit" disabled={!!setup.action}>
              {setup.action === "login" || setup.action === "connect"
                ? t("anki.loggingIn")
                : t("anki.login")}
            </button>
          </div>
          {#if setup.failure?.scope === "login" || setup.failure?.scope === "connect"}
            <p class="error" role="alert">{failureText(setup.failure)}</p>
          {/if}
        </form>
      {:else if builtin && status.account_managed && !setup.live}
        <p>{t("anki.managed", { account: status.account ?? "" })}</p>
        <div class="actions">
          <button class="primary" onclick={() => setup.connectBuiltin()} disabled={!!setup.action}>
            {setup.action === "connect" ? t("anki.connecting") : t("anki.connect")}
          </button>
        </div>
        {#if setup.failure?.scope === "connect"}
          <p class="error" role="alert">{failureText(setup.failure)}</p>
        {/if}
      {/if}

      {#if syncLine}
        <p class={`sync ${syncLine.tone}`} role="status" aria-live="polite">
          <span class="glyph" aria-hidden="true">{syncLine.glyph}</span>{syncLine.text}
        </p>
      {/if}

      {#if canRetry}
        <div class="actions">
          <button class="secondary" onclick={() => setup.retrySync()} disabled={!!setup.action}>
            {setup.action === "sync" ? t("anki.syncing") : t("anki.retry")}
          </button>
        </div>
      {/if}
      {#if setup.failure?.scope === "sync"}
        <p class="error" role="alert">{failureText(setup.failure)}</p>
      {/if}

      {#if choosing}
        <div class="full" role="group" aria-labelledby="full-title">
          <h2 id="full-title" class="label">{t("anki.full.title")}</h2>
          {#if oneWay}
            <p>{t(`anki.full.only.${oneWay}` as MessageKey)}</p>
            <div class="actions">
              <button class="primary" onclick={() => confirmFull(oneWay)} disabled={!!setup.action}>
                {t(`anki.full.go.${oneWay}` as MessageKey)}
              </button>
            </div>
          {:else}
            <p>{t("anki.full.both")}</p>
            <div class="options">
              {#each directions as d (d)}
                <label class="option">
                  <input type="radio" name="direction" value={d} bind:group={setup.direction} />
                  <span>
                    <strong>{t(`anki.full.keep.${d}` as MessageKey)}</strong>
                    <span class="note">{t(`anki.full.keepText.${d}` as MessageKey)}</span>
                  </span>
                </label>
              {/each}
            </div>
            <p class="note">{t("anki.full.backup")}</p>
            {#if setup.direction}
              <div class="actions">
                <button
                  class="primary danger"
                  onclick={() => confirmFull(setup.direction as Direction)}
                  disabled={!!setup.action}
                >
                  {t(`anki.full.replace.${setup.direction}` as MessageKey)}
                </button>
              </div>
            {/if}
          {/if}
        </div>
      {/if}
    </section>
  {:else}
    <section class="panel" aria-label={t("anki.desktop")}>
      <ol class="howto">
        <li>
          {t("anki.desktop.install")}
          <a href="https://apps.ankiweb.net" target="_blank" rel="noreferrer">apps.ankiweb.net ↗</a>
        </li>
        <li>{t("anki.desktop.addon")} <code class="mono">2055492159</code></li>
        <li>{t("anki.desktop.open")}</li>
      </ol>
      <p class="note">{t("anki.desktop.url")} <span class="mono">{status.connect_url}</span></p>
      <div class="actions">
        <button
          class={setup.live && setup.noteTypes ? "secondary" : "primary"}
          onclick={() => setup.connectDesktop()}
          disabled={!!setup.action}
        >
          {setup.action === "connect" ? t("anki.connecting") : setup.live && setup.noteTypes ? t("anki.reconnect") : t("anki.connect")}
        </button>
      </div>
      {#if setup.failure?.scope === "connect"}
        <p class="error" role="alert">{failureText(setup.failure)}</p>
      {/if}
    </section>
  {/if}

  {#if setup.live && (setup.noteTypes || setup.action === "types" || setup.failure?.scope === "types")}
    <section class="types" aria-labelledby="types-title" aria-busy={setup.action === "types"}>
      <h2 id="types-title" class="label">{t("anki.types.title")}</h2>
      {#if setup.noteTypes}
        <ul>
          {#each rows as n (n.key)}
            <li>
              <span class="mono name">{n.name}</span>
              <span class="mono deck">{n.sameDeck ? "" : n.deck}</span>
              <span class={`mono state ${n.state}`}>
                {n.state === "synced" ? "✓" : "!"}
                {t(`anki.types.${n.result ?? n.state}` as MessageKey)}
              </span>
            </li>
          {/each}
        </ul>
        <p class="note">{t("anki.types.safe")}</p>
      {:else if setup.action === "types"}
        <p class="note">{t("anki.types.working")}</p>
      {/if}
      {#if setup.failure?.scope === "types"}
        <p class="error" role="alert">{failureText(setup.failure)}</p>
        <div class="actions">
          <button class="secondary" onclick={() => setup.prepare()} disabled={!!setup.action}>
            {t("anki.types.retry")}
          </button>
        </div>
      {/if}
    </section>
  {/if}
{/if}

<StepNav {hint} {onback} {onnext} nextDisabled={!setup.ready} />

<style>
  .intro {
    max-width: 62ch;
    margin: 0 0 20px;
  }

  .label {
    margin: 0 0 6px;
    font-size: 13px;
    font-weight: 400;
    color: var(--muted);
  }

  .mono {
    font-family: var(--mono);
    font-size: 13px;
  }

  .choices {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    max-width: 760px;
  }

  .choice {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--outer);
    text-align: left;
    cursor: pointer;
  }

  .choice:hover:not(:disabled) {
    border-color: var(--muted);
  }

  .choice[aria-checked="true"] {
    border-color: var(--accent);
    background: var(--sel);
  }

  .choice:disabled {
    cursor: not-allowed;
  }

  .choice:disabled[aria-checked="false"] {
    opacity: 0.6;
  }

  .choice-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
  }

  .dot {
    width: 14px;
    height: 14px;
    flex: none;
    border: 2px solid var(--muted);
    border-radius: 50%;
  }

  [aria-checked="true"] .dot {
    border-color: var(--accent);
    background: radial-gradient(var(--accent) 0 3px, transparent 3.5px);
  }

  .tag {
    margin-left: auto;
    padding: 0 6px;
    border-radius: 4px;
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 400;
    color: var(--accent);
    border: 1px solid currentColor;
  }

  .choice-text {
    color: var(--muted);
    font-size: 14px;
  }

  .panel {
    max-width: 620px;
    margin-top: 20px;
  }

  .panel > p {
    margin: 0 0 12px;
  }

  .login {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .pw-row {
    display: flex;
    gap: 8px;
  }

  .pw-row .input {
    flex: 1;
    min-width: 0;
  }

  .actions {
    margin: 4px 0 12px;
  }

  .login .actions {
    margin: 0;
  }

  .actions button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .account {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 6px 12px;
  }

  .account .key {
    color: var(--muted);
    font-size: 13px;
    font-family: var(--mono);
  }

  .account .link {
    margin-left: auto;
  }

  .sync {
    display: flex;
    gap: 8px;
  }

  .glyph {
    font-family: var(--mono);
    min-width: 1em;
  }

  .sync.ok .glyph {
    color: var(--ok);
  }

  .sync.warn .glyph {
    color: var(--warn);
  }

  .sync.err .glyph {
    color: var(--err);
  }

  .full {
    margin: 8px 0 12px;
    padding: 12px 16px;
    border: 1px solid var(--warn);
    border-radius: 8px;
    background: var(--outer);
  }

  .full p {
    margin: 0 0 10px;
  }

  .options {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 10px;
  }

  .option {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    min-height: 36px;
    cursor: pointer;
  }

  .option input {
    margin-top: 5px;
    accent-color: var(--accent);
  }

  .option > span {
    display: flex;
    flex-direction: column;
  }

  .danger {
    background: var(--err);
  }

  .howto {
    margin: 0 0 12px;
    padding-left: 1.4em;
  }

  .howto li + li {
    margin-top: 6px;
  }

  .howto a {
    white-space: nowrap;
  }

  .howto code {
    padding: 1px 6px;
    border-radius: 4px;
    background: var(--sel);
  }

  .panel > .note {
    margin-bottom: 12px;
  }

  .types {
    max-width: 760px;
    margin-top: 20px;
  }

  .types ul {
    list-style: none;
    margin: 0 0 8px;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--outer);
  }

  .types li {
    display: grid;
    grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr) 9em;
    column-gap: 12px;
    padding: 8px 12px;
  }

  .types li + li {
    border-top: 1px solid var(--border);
  }

  .name,
  .deck {
    overflow-wrap: anywhere;
  }

  .deck {
    color: var(--muted);
  }

  .state.synced {
    color: var(--ok);
  }

  .state.update,
  .state.missing {
    color: var(--warn);
  }

  .error {
    margin: 0 0 12px;
    color: var(--err);
  }

  @container app (max-width: 600px) {
    .choices {
      grid-template-columns: minmax(0, 1fr);
    }

    .types li {
      grid-template-columns: minmax(0, 1fr) auto;
    }

    .deck {
      grid-column: 1;
      grid-row: 2;
    }

    .deck:empty {
      display: none;
    }

    .state {
      grid-row: 1;
      grid-column: 2;
    }
  }
</style>
