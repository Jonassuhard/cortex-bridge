import assert from "node:assert/strict";
import test from "node:test";

import nextConfig from "../next.config";

test("static export uses the canonical deterministic v0.5 build id", async () => {
  assert.equal(typeof nextConfig.generateBuildId, "function");
  assert.equal(await nextConfig.generateBuildId?.(), "cortex-bridge-v0.5.0");
});
