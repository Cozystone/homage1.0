import { spawn } from "node:child_process";
import { cp, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const webDir = path.join(root, "apps", "web");
const desktopSrc = path.join(root, "build", "desktop-web-src");
const desktopOut = path.join(desktopSrc, "out");
const finalOut = path.join(webDir, "out");

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: root,
      env: { ...process.env, HOMAGE_TAURI_EXPORT: "1" },
      shell: false,
      stdio: "inherit",
      ...options,
    });
    child.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} ${args.join(" ")} exited with ${code}`));
    });
  });
}

async function main() {
  await rm(desktopSrc, { recursive: true, force: true });
  await rm(finalOut, { recursive: true, force: true });
  await cp(webDir, desktopSrc, {
    recursive: true,
    filter(source) {
      const relative = path.relative(webDir, source).replaceAll("\\", "/");
      if (!relative) return true;
      if (relative === "app/api" || relative.startsWith("app/api/")) return false;
      if (relative === "app/updater" || relative.startsWith("app/updater/")) return false;
      // instrumentation.ts is a server-only process guard (unhandledRejection). The static
      // export has no Node server, so it only emits Edge-runtime warnings here — drop it.
      if (relative === "instrumentation.ts") return false;
      if (relative === ".next" || relative.startsWith(".next/")) return false;
      if (relative === "out" || relative.startsWith("out/")) return false;
      if (relative === ".vercel" || relative.startsWith(".vercel/")) return false;
      if (relative.endsWith(".log")) return false;
      return true;
    },
  });
  const nextBin = path.join(root, "node_modules", "next", "dist", "bin", "next");
  await run(process.execPath, [nextBin, "build", desktopSrc]);
  await cp(desktopOut, finalOut, { recursive: true });
}

main().catch(async (error) => {
  console.error(error);
  process.exit(1);
});
