import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { demoMissionDetail, demoPipeline, demoRuntime, demoTransport } from "@/lib/demo";
import { PipelineInspector } from "./PipelineInspector";

function renderInspector({
  mission = null,
  globalStop = false,
  onStopAll = vi.fn<() => void>(),
  onResetStop = vi.fn<() => void>(),
}: {
  mission?: typeof demoMissionDetail | null;
  globalStop?: boolean;
  onStopAll?: () => void;
  onResetStop?: () => void;
} = {}) {
  const onPause = vi.fn<() => void>();
  const onResume = vi.fn<() => void>();
  const onCancel = vi.fn<() => void>();
  render(
    <PipelineInspector
      open
      pipeline={{
        ...demoPipeline,
        overall: mission ? "running" : "healthy",
        active_mission_id: mission?.mission.id ?? null,
        active_mission_state: mission?.mission.state ?? null,
        runtime_execution: mission
          ? demoPipeline.runtime_execution
          : {
              ...demoPipeline.runtime_execution,
              task_id: null,
              executor_kind: "unavailable",
              executor_model_used: null,
              state: "idle",
              active: false,
            },
        components: [
          { id: "transport", label: "Transport ChatGPT", state: "connected", detail: "chrome_extension · 1 onglet" },
          { id: "chrome", label: "Chrome Research", state: "idle", detail: "Désactivé" },
          { id: "ollama", label: "Ollama availability", state: "available", detail: "daemon healthy · candidat modèle installed" },
          { id: "executor", label: "Exécuteur réellement utilisé", state: "idle", detail: "unavailable" },
        ],
        events: [],
      }}
      runtime={demoRuntime}
      transport={{ ...demoTransport, global_stop: globalStop }}
      mission={mission}
      onClose={() => undefined}
      onPause={onPause}
      onResume={onResume}
      onCancel={onCancel}
      onStopAll={onStopAll}
      onResetStop={onResetStop}
    />,
  );
  return { onPause, onResume, onCancel };
}

describe("PipelineInspector", () => {
  it("shows a clear French ready state without inactive mission controls", async () => {
    const onStopAll = vi.fn<() => void>();
    const user = userEvent.setup();
    renderInspector({ onStopAll });

    const inspector = screen.getByRole("complementary", { name: "État du pipeline" });
    expect(within(inspector).getByText("Prêt", { exact: true })).toBeInTheDocument();
    expect(within(inspector).getByText("Recherche Chrome", { exact: true })).toBeInTheDocument();
    expect(within(inspector).getByText("service local opérationnel · candidat modèle installé", { exact: true })).toBeInTheDocument();
    expect(within(inspector).queryByText(/\binstalled\b/i)).not.toBeInTheDocument();
    expect(within(inspector).getAllByText("Inactif", { exact: true })).not.toHaveLength(0);
    expect(within(inspector).getByText("Aucune mission active.", { exact: true })).toBeInTheDocument();
    expect(within(inspector).getByText("Système local", { exact: true })).toBeInTheDocument();
    expect(within(inspector).getAllByText("Aucun exécuteur observé", { exact: true })).not.toHaveLength(0);
    expect(within(inspector).queryByText("unavailable", { exact: true })).not.toBeInTheDocument();
    expect(within(inspector).queryByText("Logs complets", { exact: true })).not.toBeInTheDocument();
    expect(within(inspector).queryByText("Runtime", { exact: true })).not.toBeInTheDocument();
    expect(within(inspector).queryByRole("button", { name: "Pause" })).not.toBeInTheDocument();
    expect(within(inspector).queryByRole("button", { name: "Reprendre" })).not.toBeInTheDocument();
    expect(within(inspector).queryByRole("button", { name: "Annuler" })).not.toBeInTheDocument();

    expect(within(inspector).getByText("Sécurité", { exact: true })).toBeInTheDocument();
    expect(within(inspector).getByRole("heading", { name: "Arrêt général" })).toBeInTheDocument();
    await user.click(within(inspector).getByRole("button", { name: "Tout arrêter" }));
    expect(onStopAll).toHaveBeenCalledOnce();
  });

  it("shows only the rearm action while the global stop is active", async () => {
    const onResetStop = vi.fn<() => void>();
    const user = userEvent.setup();
    renderInspector({ globalStop: true, onResetStop });

    expect(screen.getByText("Arrêt général actif", { exact: true })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tout arrêter" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Réarmer" }));
    expect(onResetStop).toHaveBeenCalledOnce();
  });

  it("shows mission controls only for the selected active mission without exposing its raw state", () => {
    renderInspector({ mission: demoMissionDetail });

    expect(screen.getByRole("button", { name: "Pause" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Reprendre" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled();
    expect(screen.queryByText("EXECUTING_LOCAL_ACTION", { exact: true })).not.toBeInTheDocument();
  });
});
