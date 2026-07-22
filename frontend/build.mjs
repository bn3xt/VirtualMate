import { build } from "esbuild";
import { cp, mkdir, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(root, "dist");
await rm(dist, { recursive: true, force: true });
await mkdir(path.join(dist, "assets"), { recursive: true });
await build({
  entryPoints: [path.join(root, "src", "main.tsx")],
  bundle: true,
  minify: true,
  sourcemap: false,
  format: "esm",
  target: ["es2020"],
  outfile: path.join(dist, "assets", "app.js"),
  loader: { ".tsx": "tsx", ".ts": "ts", ".css": "css" },
});
await cp(path.join(root, "index.html"), path.join(dist, "index.html"));
await cp(path.join(root, "..", "avatar-default.svg"), path.join(dist, "assets", "avatar-default.svg"));
