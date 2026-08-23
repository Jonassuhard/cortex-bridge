import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { demoMissionDetail, demoPipeline } from "@/lib/demo";
import { ExecutionCard } from "./ExecutionCard";

function renderPausedMission(state: "PAUSED" | "PAUSED_RECOVERY_REQUIRED", pauseReason: string) {
  render(
    <ExecutionCard
      mission={{
        ...demoMissionDetail,
        mission: {
          ...demoMissionDetail.mission,
          state,
          pause_reason: pauseReason,
        },
      }}
      pipeline={{ ...demoPipeline, active_mission_state: state }}
      expanded={false}
      onToggle={() => undefined}
      onApprove={() => undefined}
      onReject={() => undefined}
    />,
  );
}

describe("ExecutionCard pause explanations", () => {
  it("explains a ChatGPT rate limit in French and tells the user how to resume", () => {
    renderPausedMission("PAUSED", "RATE_LIMIT");

    expect(screen.getByText("Pause expliquée")).toBeInTheDocument();
    expect(screen.getByText(/ChatGPT a atteint sa limite d'utilisation/)).toBeInTheDocument();
    expect(screen.getByText(/appuie sur Reprendre/)).toBeInTheDocument();
  });

  it("refuses the Work surface and directs the user to a classic chat", () => {
    renderPausedMission("PAUSED_RECOVERY_REQUIRED", "WORK_SURFACE_REJECTED");

    expect(screen.getByText("Action requise")).toBeInTheDocument();
    expect(screen.getByText(/jamais sur une surface Work/)).toBeInTheDocument();
    expect(screen.getByText(/Ouvre un chat classique/)).toBeInTheDocument();
  });
});
