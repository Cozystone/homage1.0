import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const args = process.argv.slice(2);
const command = args[0] ?? "build";
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const npxCommand = process.platform === "win32" ? "npx.cmd" : "npx";

function run(cmd, cmdArgs) {
  const result = spawnSync(cmd, cmdArgs, {
    cwd: root,
    env: process.env,
    shell: process.platform === "win32",
    stdio: "inherit",
  });
  if (result.error) {
    console.error(`[ATANOR Tauri] Failed to launch ${cmd}: ${result.error.message}`);
  }
  process.exit(result.status ?? 1);
}

if (command === "build") {
  if (args.includes("--prod")) {
    console.log("[ATANOR Tauri] --prod is implied by `tauri build`; continuing with production desktop build.");
  }
  run(npmCommand, ["run", "desktop:build"]);
}

run(npxCommand, ["tauri", ...args]);
