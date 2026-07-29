import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { StatusRail } from "./StatusRail";

// Regression: LIVE-LOGIN-002 — the real Chrome connection action must remain visible.
// Found during the v0.5 live acceptance run on 2026-07-29.
it("keeps the manual ChatGPT connection action visible beside its real status", () => {
  const openProfile = vi.fn<() => void>();

  render(
    <StatusRail
      transport="manual_action"
      executor="available"
      latencyMs={null}
      onOpenChatGPTProfile={openProfile}
    />,
  );

  expect(screen.getByTitle("Statut de la connexion ChatGPT")).toHaveTextContent("Action manuelle requise");
  fireEvent.click(screen.getByRole("button", { name: "Ouvrir et connecter ChatGPT" }));
  expect(openProfile).toHaveBeenCalledTimes(1);
});
