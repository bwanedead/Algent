import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Keep the config minimal; adjust aliases/plugins as the stack evolves.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
