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
  it("summarizes recorded validation outcomes, without equating missing proof with success", () => {
    render(<ExecutionCard mission={{ ...demoMissionDetail, mission: { ...demoMissionDetail.mission, state: "COMPLETED" }, timeline: {
      validation_results: [{ passed: 1 }, { passed: 0 }],
    } }} pipeline={demoPipeline} expanded={false} onToggle={() => undefined} onApprove={() => undefined} onReject={() => undefined} />);
    expect(screen.getByLabelText("Bilan de la mission")).toHaveTextContent("1 validation réussie · 1 en échec");
  });
  it("renders only recorded diffs as text, including hostile markup", () => {
    render(<ExecutionCard mission={{ ...demoMissionDetail, timeline: {
      tool_executions: [{ id: "diff", tool: "apply_patch", exit_code: 0, result_json: JSON.stringify({ path: "index.html", diff: "+<script>no()</script>", backup: "/tmp/backup" }) }],
    } }} pipeline={demoPipeline} expanded onToggle={() => undefined} onApprove={() => undefined} onReject={() => undefined} />);
    expect(screen.getByText("+<script>no()</script>")).toBeInTheDocument();
    expect(screen.getByText("Diff enregistré · index.html")).toBeInTheDocument();
  });

  it("identifies the pending action by the policy action id, never a different decision", () => {
    render(<ExecutionCard mission={{ ...demoMissionDetail, awaiting_approval: true, timeline: {
      policy_decisions: [{ action_id: "a1", tool: "write_file", requires_approval: 1 }],
      orchestrator_decisions: [
        { action_id: "a1", valid: 1, decision_json: JSON.stringify({ action: { tool: "write_file", arguments: { path: "approved.txt" } } }) },
        { action_id: "a2", valid: 1, decision_json: JSON.stringify({ action: { tool: "write_file", arguments: { path: "wrong.txt" } } }) },
      ],
    } }} pipeline={demoPipeline} expanded={false} onToggle={() => undefined} onApprove={() => undefined} onReject={() => undefined} />);
    expect(screen.getByText(/"path": "approved.txt"/)).toBeInTheDocument();
    expect(screen.getByLabelText("Cible de l’action")).toHaveTextContent("approved.txt");
    expect(screen.queryByText(/"path": "wrong.txt"/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Un point de restauration est conservé/)).not.toBeInTheDocument();
  });

  it("does not present failed tools as completed evidence or invent progress", () => {
    const { container } = render(<ExecutionCard mission={{ ...demoMissionDetail, timeline: {
      tool_executions: [{ id: "failed", tool: "run_tests", exit_code: 1 }],
    } }} pipeline={demoPipeline} expanded onToggle={() => undefined} onApprove={() => undefined} onReject={() => undefined} />);
    expect(screen.getByText("Action locale").closest(".execution-step")).not.toHaveClass("is-done");
    expect(container.querySelector(".execution-progress-track")).toBeNull();
  });

  it("shows recorded artifacts without pretending to open or download local files", () => {
    render(<ExecutionCard mission={{ ...demoMissionDetail, timeline: {
      artifacts: [{ id: "file", name: "Rapport", path: "/tmp/demo/report.md", sha256: "abc123" }],
    } }} pipeline={demoPipeline} expanded onToggle={() => undefined} onApprove={() => undefined} onReject={() => undefined} />);
    expect(screen.getByText("/tmp/demo/report.md")).toBeInTheDocument();
    expect(screen.getByText("abc123")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Rapport" })).not.toBeInTheDocument();
  });

  it("does not fabricate completed steps when a mission has no recorded evidence", () => {
    render(<ExecutionCard
      mission={{ ...demoMissionDetail, timeline: {}, mission: { ...demoMissionDetail.mission, state: "COMPLETED" } }}
      pipeline={demoPipeline} expanded={false} onToggle={() => undefined}
      onApprove={() => undefined} onReject={() => undefined}
    />);
    expect(screen.queryAllByText("Étape enregistrée")).toHaveLength(0);
    expect(screen.queryByText("Exécution en cours")).not.toBeInTheDocument();
    expect(screen.getByText("Aucune preuve détaillée disponible pour cette mission.")).toBeInTheDocument();
  });

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
