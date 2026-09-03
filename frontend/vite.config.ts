import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend is fully isolated in /frontend. It never imports Python or the
// statistics engine — it consumes JSON produced by that engine.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: false, open: false },
  build: { outDir: "dist", sourcemap: true },
});
