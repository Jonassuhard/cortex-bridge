import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import nextConfig from "../next.config";

test("static export uses the canonical deterministic version build id", async () => {
  assert.equal(typeof nextConfig.generateBuildId, "function");
  const version = readFileSync(new URL("../../VERSION", import.meta.url), "utf8").trim();
  assert.equal(await nextConfig.generateBuildId?.(), `cortex-bridge-v${version}`);
});

test("every CSS custom property used by the product is declared", () => {
  const source = ["globals.css", "atelier.css"].map((file) => readFileSync(new URL(`../app/${file}`, import.meta.url), "utf8")).join("\n");
  const declared = new Set([...source.matchAll(/(--[a-z0-9-]+)\s*:/giu)].map((match) => match[1]));
  const used = new Set([...source.matchAll(/var\((--[a-z0-9-]+)\)/giu)].map((match) => match[1]));
  const missing = [...used].filter((token) => !declared.has(token)).sort();
  assert.deepEqual(missing, []);
});

test("browser gates serve the audited static output without rewriting Next files", () => {
  const source = readFileSync(new URL("../playwright.config.ts", import.meta.url), "utf8");
  assert.match(source, /python3 -m http\.server 3420 --bind 127\.0\.0\.1 --directory out/u);
  assert.doesNotMatch(source, /next dev/u);
});
