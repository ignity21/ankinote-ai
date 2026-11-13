<script lang="ts">
  import StepNav from "../../components/StepNav.svelte";
  import { t, type MessageKey } from "../../lib/i18n.svelte";
  import { LanguageSetup } from "../../lib/languageSetup.svelte";
  import { ENDONYM, LANG_TAG, SAMPLE_MEANING, SAMPLE_WORD, sameLanguage } from "../../lib/languages";
  import en from "../../lib/locales/en.json";

  let { onback, onnext }: { onback: () => void; onnext: () => void } = $props();

  const setup = new LanguageSetup();
  void setup.load();

  const options = $derived(setup.options);
  const beta = $derived(options?.targets.find((o) => o.id === setup.target)?.beta ?? false);
  const sample = $derived(setup.ready ? SAMPLE_WORD[setup.target!] : undefined);
  const meaning = $derived(setup.ready ? SAMPLE_MEANING[setup.native!] : undefined);

  /** The language's name in the interface language, unless the endonym already says it. */
  function localName(id: string): string {
    const name = t(`lang.${id}` as MessageKey);
    return name.toLowerCase() === (ENDONYM[id] ?? id).toLowerCase() ? "" : name;
  }

  const hint = $derived.by(() => {
    if (setup.native === null) return t("languages.hint.native");
    if (setup.target === null) return t("languages.hint.target");
    return "";
  });

  const errorText = $derived.by(() => {
    if (!setup.failure) return "";
    const known = `languages.err.${setup.failure}`;
    return t((known in en ? known : "languages.err.server") as MessageKey);
  });

  async function next() {
    if (await setup.save()) onnext();
  }
</script>

<p class="intro">{t("languages.intro")}</p>

{#if setup.loadError}
  <p class="error" role="alert">{t("languages.err.load")}</p>
{:else if options}
  <div class="wrap">
    <div class="layout">
      <div class="pickers">
        <fieldset>
          <legend>{t("languages.native")}</legend>
          <p class="note">{t("languages.nativeNote")}</p>
          <div class="grid">
            {#each options.natives as id (id)}
              <label class="opt">
                <input
                  type="radio"
                  name="native"
                  value={id}
                  checked={setup.native === id}
                  onchange={() => setup.pickNative(id)}
                />
                <span class="name" lang={LANG_TAG[id]}>{ENDONYM[id] ?? id}</span>
                <span class="sub">{localName(id)}</span>
              </label>
            {/each}
          </div>
        </fieldset>

        <fieldset>
          <legend>{t("languages.target")}</legend>
          <p class="note">{t("languages.targetNote")}</p>
          <div class="grid">
            {#each options.targets as option (option.id)}
              {@const own = setup.native !== null && sameLanguage(setup.native, option.id)}
              <label class="opt">
                <input
                  type="radio"
                  name="target"
                  value={option.id}
                  checked={setup.target === option.id}
                  disabled={own}
                  onchange={() => setup.pickTarget(option.id)}
                />
                <span class="name" lang={LANG_TAG[option.id]}>{ENDONYM[option.id] ?? option.id}</span>
                <span class="sub">{own ? t("languages.yours") : localName(option.id)}</span>
                {#if option.beta}<span class="tag">{t("languages.beta")}</span>{/if}
              </label>
            {/each}
          </div>
          {#if beta}
            <p class="note beta-note">{t("languages.betaNote", { lang: ENDONYM[setup.target!] ?? "" })}</p>
          {/if}
        </fieldset>
      </div>

      <figure class="preview" aria-live="polite">
        <figcaption>{t("languages.preview")}</figcaption>
        {#if sample && meaning}
          <div class="card">
            <p class="word" lang={LANG_TAG[setup.target!]}>{sample.word}</p>
            <p class="sound" lang={LANG_TAG[setup.target!]}>{sample.sound}</p>
            <hr />
            <p class="meaning" lang={LANG_TAG[setup.native!]}>{meaning}</p>
            <p class="where">
              <span>{ENDONYM[setup.target!]}</span> → <span>{ENDONYM[setup.native!]}</span>
            </p>
          </div>
        {:else}
          <p class="note">{t("languages.previewEmpty")}</p>
        {/if}
      </figure>
    </div>
  </div>

  {#if errorText}<p class="error" role="alert">{errorText}</p>{/if}
{/if}

<StepNav {onback} {hint} onnext={next} nextDisabled={!setup.ready} busy={setup.saving} />

<style>
  .intro {
    max-width: 62ch;
    margin: 0 0 20px;
  }

  /* Pickers and the example card side by side when the step is wide. */
  .wrap {
    container: step / inline-size;
  }

  .layout {
    display: grid;
    gap: 20px;
    max-width: 980px;
  }

  @container step (min-width: 820px) {
    .layout {
      grid-template-columns: minmax(0, 1fr) 260px;
      align-items: start;
    }
  }

  .pickers {
    display: flex;
    flex-direction: column;
    gap: 20px;
    min-width: 0;
  }

  fieldset {
    margin: 0;
    padding: 0;
    border: 0;
    min-width: 0;
  }

  legend {
    padding: 0;
    font-weight: 600;
  }

  fieldset > .note {
    margin: 2px 0 10px;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 8px;
  }

  /* Name over its translation, so every tile in a row is the same height. */
  .opt {
    position: relative;
    display: flex;
    flex-direction: column;
    justify-content: center;
    min-height: 60px;
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--outer);
    cursor: pointer;
  }

  /* The radio stays focusable and announced; the tile is what shows. */
  .opt input {
    position: absolute;
    opacity: 0;
    width: 1px;
    height: 1px;
    margin: 0;
  }

  .opt:hover:not(:has(input:disabled)) {
    border-color: var(--muted);
  }

  .opt:has(input:checked) {
    border-color: var(--accent);
    background: var(--sel);
  }

  .opt:has(input:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .opt:has(input:disabled) {
    cursor: not-allowed;
    opacity: 0.55;
  }

  .name {
    font-weight: 600;
  }

  .sub {
    font-size: 13px;
    color: var(--muted);
  }

  .tag {
    position: absolute;
    top: 8px;
    right: 8px;
    padding: 0 6px;
    border: 1px solid var(--warn);
    border-radius: 4px;
    font-family: var(--mono);
    font-size: 12px;
    color: var(--warn);
  }

  .beta-note {
    margin-top: 8px;
  }

  .preview {
    margin: 0;
  }

  figcaption {
    margin-bottom: 6px;
    font-size: 13px;
    color: var(--muted);
  }

  .card {
    padding: 18px 18px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--outer);
    text-align: center;
  }

  .card p {
    margin: 0;
  }

  .word {
    font-size: 32px;
    font-weight: 600;
    line-height: 1.25;
  }

  .sound {
    margin-top: 2px;
    font-family: var(--mono);
    font-size: 14px;
    color: var(--muted);
  }

  .card hr {
    margin: 14px 0;
    border: 0;
    border-top: 1px solid var(--border);
  }

  .meaning {
    font-size: 18px;
  }

  .where {
    margin-top: 14px;
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
  }

  .error {
    margin: 16px 0 0;
    color: var(--err);
  }
</style>
