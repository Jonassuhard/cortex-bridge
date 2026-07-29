import { expect, it } from "vitest";

import { transportHealthFromProbe } from "./runtimeTruth";

// Regression: LIVE-LOGIN-001 — the ChatGPT verification page was shown as "État inconnu".
// Found during the v0.5 live acceptance run on 2026-07-29.
it("requires an explicit manual action for a ChatGPT verification page", () => {
  expect(transportHealthFromProbe({
    ok: false,
    title: "Un instant…",
    failures: ["composer", "messages"],
  })).toBe("manual_action");

  expect(transportHealthFromProbe({
    ok: true,
    title: "Conversation de validation",
    failures: [],
  })).toBe("connected");
});
