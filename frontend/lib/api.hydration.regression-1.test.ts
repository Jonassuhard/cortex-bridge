import { expect, it } from "vitest";

import { shortTime } from "./api";

// Regression: LIVE-HYDRATION-001 — static HTML rendered "Jan 1" while the browser rendered "1 janv.".
// Found during the v0.5 live acceptance run on 2026-07-29.
it("formats non-current dates with the same explicit French locale on server and client", () => {
  expect(shortTime("1970-01-01T12:00:00.000Z")).toBe("1 janv.");
});
