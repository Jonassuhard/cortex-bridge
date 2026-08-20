import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ExecutionPreflight } from "@/lib/types";
import { ExecutionPreflightDialog } from "./ExecutionPreflightDialog";

const preflight: ExecutionPreflight = {
  conversationKey: "atlas-release",
  workspace: "/tmp/cortex-demo-workspace",
  executorKind: "deterministic",
  capabilities: { read: true, write: false, processes: false, network: false, delete: false },
  approvalPolicy: "read-only",
  maxIterations: 12,
  maxDurationMinutes: 20,
  attachmentTokens: [],
};

describe("ExecutionPreflightDialog", () => {
  it("shows exact boundaries and mutates nothing before confirmation", async () => {
    const onChange = vi.fn<(value: ExecutionPreflight) => void>();
    const onConfirm = vi.fn<() => void>();
    render(<ExecutionPreflightDialog open value={preflight} attachmentName="preuve.txt" confirming={false} onChange={onChange} onClose={vi.fn<() => void>()} onConfirm={onConfirm} />);

    expect(screen.getByText("/tmp/cortex-demo-workspace")).toBeInTheDocument();
    expect(screen.getByText("12 itérations · 20 min")).toBeInTheDocument();
    expect(screen.getByText("preuve.txt")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Écriture avec approbations" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Commandes revues" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Réseau" })).not.toBeChecked();
    expect(onChange).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();

    await userEvent.setup().click(screen.getByRole("button", { name: "Démarrer en lecture seule" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
