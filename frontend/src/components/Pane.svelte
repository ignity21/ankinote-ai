<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    title,
    area,
    children,
  }: { title: string; area?: string; children: Snippet } = $props();
</script>

<!-- The focused pane (focus anywhere inside) gets the accent border. -->
<section class="pane" style:grid-area={area} aria-label={title}>
  <h2 class="pane-title">{title}</h2>
  {@render children()}
</section>

<style>
  .pane {
    position: relative;
    min-width: 0;
    min-height: 0;
    margin-top: 9px;
    padding: 22px 16px 16px;
    background: var(--tile);
    border: 2px solid var(--border);
    border-radius: 10px;
  }

  .pane:focus-within {
    border-color: var(--accent);
  }

  .pane-title {
    position: absolute;
    top: -11px;
    left: 12px;
    margin: 0;
    padding: 0 6px;
    background: var(--tile);
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 500;
    line-height: 18px;
    color: var(--muted);
  }

  .pane:focus-within > .pane-title {
    color: var(--accent);
  }
</style>
