import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { demoPipeline, demoRuntime, demoSettings } from "@/lib/demo";
import { SettingsPanel } from "./SettingsPanel";

function renderPanel() {
  return render(
    <SettingsPanel
      open
      initialTab="diagnostics"
      settings={demoSettings}
      ollamaModels={[]}
      chatgptModels={[]}
      runtime={demoRuntime}
      runtimeExecution={demoPipeline.runtime_execution}
      saving={false}
      onClose={vi.fn<() => void>()}
      onSave={vi.fn<(settings: typeof demoSettings) => Promise<void>>().mockResolvedValue(undefined)}
      onSelectChatGPTModel={vi.fn<(label: string) => Promise<void>>().mockResolvedValue(undefined)}
    />,
  );
}

describe("SettingsPanel diagnostics export", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("requests one download while pending, reports the requested filename, and permits a failed retry", async () => {
    let resolveExport!: (value: { ok: boolean; status: number; json: () => Promise<unknown> }) => void;
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveExport = resolve;
      }))
      .mockResolvedValueOnce({ ok: false, status: 503, json: () => Promise.resolve({}) });
    const createObjectURL = vi.fn().mockReturnValue("blob:cortex-diagnostics");
    const revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function clickDownload(this: HTMLAnchorElement) {
      expect(this.isConnected).toBe(true);
      expect(this.download).toMatch(/^cortex-diagnostic-.+\.json$/);
      expect(this.href).toBe("blob:cortex-diagnostics");
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const user = userEvent.setup();

    renderPanel();
    const exportButton = screen.getByRole("button", { name: "Exporter le rapport" });
    await user.click(exportButton);
    await user.click(exportButton);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Exportation…" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Préparation du rapport de diagnostic…");

    resolveExport({ ok: true, status: 200, json: () => Promise.resolve({ version: "fixture" }) });

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(/^Téléchargement demandé : cortex-diagnostic-.+\.json$/);
    });
    expect(click).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:cortex-diagnostics"));

    await user.click(screen.getByRole("button", { name: "Exporter le rapport" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Impossible de demander le téléchargement du rapport de diagnostic (HTTP 503).",
      );
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("resets the export lock after an initial error so one successful retry can request one download", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 503, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ source: "fixture" }) });
    const createObjectURL = vi.fn().mockReturnValue("blob:cortex-retry");
    const revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const user = userEvent.setup();

    renderPanel();
    await user.click(screen.getByRole("button", { name: "Exporter le rapport" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "Impossible de demander le téléchargement du rapport de diagnostic (HTTP 503).",
      );
    });

    await user.click(screen.getByRole("button", { name: "Exporter le rapport" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(/^Téléchargement demandé : cortex-diagnostic-.+\.json$/);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(click).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
  });
});
