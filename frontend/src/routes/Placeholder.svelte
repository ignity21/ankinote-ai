<script lang="ts">
  import Pane from "../components/Pane.svelte";

  let { title, message }: { title: string; message: string } = $props();
</script>

<div class="single">
  <Pane {title}>
    <p class="empty">{message}</p>
  </Pane>
</div>

<style>
  .single {
    padding: 2px 10px 10px;
  }
</style>
