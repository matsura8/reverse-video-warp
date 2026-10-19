import { copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const out = path.join(root, "dist");
await rm(out, { recursive: true, force: true });

for (const browser of ["chromium", "firefox"]) {
  const target = path.join(out, browser);
  await mkdir(target, { recursive: true });
  await copyFile(path.join(root, "build/background.js"), path.join(target, "background.js"));
  await copyFile(path.join(root, "build/content.js"), path.join(target, "content.js"));
  if (browser === "chromium") {
    await copyFile(path.join(root, "build/offscreen.js"), path.join(target, "offscreen.js"));
    await copyFile(path.join(root, "static/offscreen.html"), path.join(target, "offscreen.html"));
  }
  if (browser === "firefox") {
    await copyFile(path.join(root, "build/capture.js"), path.join(target, "capture.js"));
    await copyFile(path.join(root, "static/capture.html"), path.join(target, "capture.html"));
  }
  const manifest = JSON.parse(await readFile(path.join(root, "manifests", `${browser}.json`), "utf8"));
  await writeFile(path.join(target, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
}
await rm(path.join(root, "build"), { recursive: true, force: true });
