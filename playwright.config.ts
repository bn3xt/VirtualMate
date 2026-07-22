import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const productRoot = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(productRoot, "../..");
const product = path.join(repo, "standalone", "virtual_mate");
const python = path.join(repo, ".venv", "Scripts", "python.exe");
const runtime = path.join(repo, ".tmp", "virtual_mate_ui");
const backend = path.join(product, "backend");
const web = path.join(product, "frontend", "dist");
const ps = [
  `$env:PYTHONPATH='${backend}'`,
  `$env:VSA_RUNTIME_ROOT='${runtime}'`,
  `$env:VSA_WEB_DIR='${web}'`,
  `& '${python}' -m uvicorn virtual_mate.app:app --host 127.0.0.1 --port 8135`,
].join("; ");

export default defineConfig({
  testDir: "./tests/ui",
  timeout: 45_000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8135",
    headless: true,
    trace: "retain-on-failure",
  },
  webServer: {
    command: `powershell -NoProfile -ExecutionPolicy Bypass -Command "${ps.replaceAll('"', '\\"')}"`,
    url: "http://127.0.0.1:8135/api/bootstrap",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});


