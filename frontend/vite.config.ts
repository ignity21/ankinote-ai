import { fileURLToPath, URL } from "node:url";

import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

const pkg = (p: string) => fileURLToPath(new URL(p, import.meta.url));

export default defineConfig({
  plugins: [svelte()],
  resolve: {
    alias: {
      // Design tokens live in the Python package so card CSS can use them too.
      $themes: pkg("../src/ankinote/themes"),
    },
  },
  server: {
    port: 5173,
    fs: { allow: [pkg(".."), pkg("../src/ankinote/themes")] },
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: {
    outDir: pkg("../src/ankinote/web/dist"),
    emptyOutDir: true,
  },
});
