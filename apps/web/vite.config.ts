import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  // Only PUBLIC_ variables reach the browser bundle (requirement 2.4).
  envPrefix: "PUBLIC_",
  server: { port: 3000, strictPort: true },
  plugins: [tailwindcss(), tanstackStart(), viteReact()],
});
