import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { demoPipeline, demoRuntime, demoTransport } from "@/lib/demo";
import { PipelineInspector } from "./PipelineInspector";

describe("PipelineInspector conversation scoping", () => {
  it("does not expose mission A controls or state after selecting conversation B without a mission", async () => {
    const onPause = vi.fn<() => void>();
    const onResume = vi.fn<() => void>();
    const onCancel = vi.fn<() => void>();
    const user = userEvent.setup();
    render(
      <PipelineInspector
        open
        pipeline={{
          ...demoPipeline,
          active_mission_id: "mission-a",
          active_mission_state: "EXECUTING_LOCAL_ACTION",
        }}
        runtime={demoRuntime}
        transport={demoTransport}
        mission={null}
        onClose={() => undefined}
        onPause={onPause}
        onResume={onResume}
        onCancel={onCancel}
        onStopAll={() => undefined}
        onResetStop={() => undefined}
      />,
    );

    expect(screen.getByRole("button", { name: "Pause" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reprendre" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();
    expect(screen.getByText("aucune")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Annuler" }));
    expect(onPause).not.toHaveBeenCalled();
    expect(onResume).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });
});
