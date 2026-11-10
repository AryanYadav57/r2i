import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // Big libraries in their own long-cached files; app code changes don't invalidate them.
        manualChunks: { maplibre: ["maplibre-gl"], deck: ["@deck.gl/core", "@deck.gl/layers", "@deck.gl/geo-layers", "@deck.gl/mapbox"], react: ["react", "react-dom"] },
      },
    },
  },
  resolve: { dedupe: ["react", "react-dom"] },
  server: { proxy: { "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") } } },
  preview: { port: 4173, proxy: { "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") } } },
});
