import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { demoPipeline, demoSettings } from "@/lib/demo";
import { SettingsPanel } from "./SettingsPanel";

describe("SettingsPanel settings refresh", () => {
  it("uses settings loaded after the panel opened without restoring stale fallback fields", async () => {
    // Regression: ISSUE-SETTINGS-001 — a late settings response left an invalid
    // fallback browser_profile_root in the draft and PUT /api/settings returned 422.
    // Found by /qa on 2026-07-30.
    const onSave = vi.fn<(settings: typeof demoSettings) => Promise<void>>().mockResolvedValue(undefined);
    const common = {
      open: true,
      ollamaModels: [],
      chatgptModels: [],
      runtimeExecution: demoPipeline.runtime_execution,
      saving: false,
      onClose: vi.fn<() => void>(),
      onSave,
      onSelectChatGPTModel: vi.fn<(label: string) => Promise<void>>().mockResolvedValue(undefined),
    };
    const stale = {
      ...demoSettings,
      default_workspace: "~/",
      browser_profile_root: "console/data/browser-profiles",
    };
    const fresh = {
      ...demoSettings,
      default_workspace: "/tmp/cortex-bridge-qa/user-data/workspaces",
      browser_profile_root: "/tmp/cortex-bridge-qa/user-data/browser-profiles",
    };
    const { rerender } = render(<SettingsPanel {...common} settings={stale} />);

    rerender(<SettingsPanel {...common} settings={fresh} />);

    const user = userEvent.setup();
    const workspace = screen.getByRole("textbox", { name: /Workspace par défaut/i });
    await user.clear(workspace);
    await user.type(workspace, "/tmp/cortex-bridge-qa/workspaces/site-1");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(onSave).toHaveBeenCalledWith({
      ...fresh,
      default_workspace: "/tmp/cortex-bridge-qa/workspaces/site-1",
    });
  });
});
