import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import nextConfig from "../next.config";

test("static export uses the canonical deterministic v0.5 build id", async () => {
  assert.equal(typeof nextConfig.generateBuildId, "function");
  assert.equal(await nextConfig.generateBuildId?.(), "cortex-bridge-v0.5.0");
});

test("every CSS custom property used by the product is declared", () => {
  const source = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
  const declared = new Set([...source.matchAll(/(--[a-z0-9-]+)\s*:/giu)].map((match) => match[1]));
  const used = new Set([...source.matchAll(/var\((--[a-z0-9-]+)\)/giu)].map((match) => match[1]));
  const missing = [...used].filter((token) => !declared.has(token)).sort();
  assert.deepEqual(missing, []);
});
