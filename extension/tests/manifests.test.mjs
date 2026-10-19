import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function manifest(name) {
  return JSON.parse(await readFile(new URL(`../manifests/${name}.json`, import.meta.url)));
}

test("Chromium requests only the scoped localhost host", async () => {
  const value = await manifest("chromium");
  assert.deepEqual(value.host_permissions, ["http://127.0.0.1:17842/*"]);
  assert.ok(value.permissions.includes("nativeMessaging"));
  assert.ok(value.permissions.includes("tabCapture"));
});

test("Firefox has an explicit stable extension id and no Chromium capture permissions", async () => {
  const value = await manifest("firefox");
  assert.equal(value.browser_specific_settings.gecko.id, "reversewarp@maxpowerit.local");
  assert.ok(!value.permissions.includes("tabCapture"));
  assert.ok(!value.permissions.includes("offscreen"));
});
