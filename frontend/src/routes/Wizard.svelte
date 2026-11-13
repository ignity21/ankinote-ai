<script lang="ts">
  import Pane from "../components/Pane.svelte";
  import StepNav from "../components/StepNav.svelte";
  import AnkiStep from "./wizard/AnkiStep.svelte";
  import ModelStep from "./wizard/ModelStep.svelte";
  import { t, type MessageKey } from "../lib/i18n.svelte";

  const steps: { key: MessageKey; skippable?: boolean }[] = [
    { key: "wizard.step.model" },
    { key: "wizard.step.anki" },
    { key: "wizard.step.languages" },
    { key: "wizard.step.appearance", skippable: true },
    { key: "wizard.step.first" },
  ];

  let current = $state(0);
  let done = $state(0);
  const step = $derived(steps[current]!);
  const last = $derived(current === steps.length - 1);

  function next() {
    done = Math.max(done, current + 1);
    if (!last) current += 1;
  }

  function back() {
    current -= 1;
  }
</script>

<div class="wizard">
  <Pane title={t("wizard.steps")} area="steps">
    <ol class="steps">
      {#each steps as s, i (s.key)}
        <li>
          <button
            class:on={i === current}
            disabled={i > done}
            aria-current={i === current ? "step" : undefined}
            onclick={() => (current = i)}
          >
            <span class="n">{i < done ? "✓" : i + 1}</span>
            {t(s.key)}
          </button>
        </li>
      {/each}
    </ol>
  </Pane>

  <Pane title={t("wizard.title")} area="body">
    <div class="body">
      <p class="progress">{t("wizard.stepOf", { n: current + 1, total: steps.length })}</p>
      <div class="bars" aria-hidden="true">
        {#each steps as s, i (s.key)}<span class:filled={i <= current}></span>{/each}
      </div>
      <h1>{t(step.key)}</h1>
      {#if current === 0}
        <ModelStep onnext={next} />
      {:else if current === 1}
        <AnkiStep onback={back} onnext={next} />
      {:else}
        <p class="empty">{t("page.soon")}</p>
        <StepNav
          onback={back}
          onskip={step.skippable ? next : undefined}
          onnext={next}
          {last}
        />
      {/if}
    </div>
  </Pane>
</div>

<style>
  .wizard {
    display: grid;
    gap: var(--gap);
    height: 100%;
    padding: 2px 10px 10px;
    grid-template-columns: 280px minmax(0, 1fr);
    grid-template-areas: "steps body";
  }

  .steps {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .steps button {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    min-height: 40px;
    padding: 8px 10px;
    border: 0;
    border-radius: 6px;
    background: none;
    text-align: left;
    cursor: pointer;
  }

  .steps button:disabled {
    color: var(--muted);
    cursor: default;
  }

  .steps button.on {
    background: var(--sel);
  }

  .n {
    font-family: var(--mono);
    color: var(--accent);
    min-width: 1.2em;
  }

  .progress {
    display: none;
    margin: 0 0 8px;
    font-family: var(--mono);
    font-size: 13px;
    color: var(--muted);
  }

  .bars {
    display: none;
    gap: 4px;
    margin-bottom: 16px;
  }

  .bars span {
    flex: 1;
    height: 4px;
    border-radius: 2px;
    background: var(--border);
  }

  .bars span.filled {
    background: var(--accent);
  }

  h1 {
    margin: 0 0 12px;
    font-size: 24px;
    font-weight: 600;
    line-height: 1.3;
  }

  /* The pane title overlaps the border, so scroll inside, not on the pane. */
  .body {
    height: 100%;
    overflow-y: auto;
    margin: -4px -8px 0;
    padding: 4px 8px 0;
  }

  @container app (max-width: 1000px) {
    .wizard {
      grid-template-columns: 220px minmax(0, 1fr);
    }
  }

  @container app (max-width: 600px) {
    .wizard {
      padding: 0 8px 8px;
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas: "body";
    }

    .wizard > :global(.pane:first-child) {
      display: none;
    }

    .progress,
    .bars {
      display: flex;
    }
  }
</style>
