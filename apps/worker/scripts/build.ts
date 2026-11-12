/**
 * Production bundle. Workspace packages (@orrery/*) are source-only TypeScript and TSX, so they are
 * bundled; third-party packages stay external and are installed in the image.
 */
import { build } from "esbuild";

await build({
  entryPoints: { main: "src/main.ts", migrate: "src/migrate.ts" },
  outdir: "dist",
  bundle: true,
  platform: "node",
  target: "node26",
  format: "esm",
  sourcemap: true,
  jsx: "automatic",
  logLevel: "info",
  plugins: [
    {
      name: "externalize-third-party",
      setup(b) {
        b.onResolve({ filter: /^[^./]/ }, (args) =>
          args.path.startsWith("@orrery/") ? undefined : { path: args.path, external: true },
        );
      },
    },
  ],
});
