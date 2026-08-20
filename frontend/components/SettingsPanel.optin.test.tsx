import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { demoPipeline, demoSettings } from "@/lib/demo";
import { SettingsPanel } from "./SettingsPanel";

function renderPanel() {
  return render(
    <SettingsPanel
      open
      settings={demoSettings}
      ollamaModels={[]}
      chatgptModels={[]}
      runtimeExecution={demoPipeline.runtime_execution}
      saving={false}
      onClose={vi.fn<() => void>()}
      onSave={vi.fn<(settings: typeof demoSettings) => Promise<void>>().mockResolvedValue(undefined)}
      onSelectChatGPTModel={vi.fn<(label: string) => Promise<void>>().mockResolvedValue(undefined)}
    />,
  );
}

describe("SettingsPanel transport opt-in", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the explicit OpenAI risk notice and the opt-in toggle", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ opt_in_accepted: false }),
    }));
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /Transport/i }));

    expect(screen.getByText(/non autorisé par OpenAI/i)).toBeInTheDocument();
    expect(screen.getByText(/restriction ou la suspension de ton compte/i)).toBeInTheDocument();
    const toggle = await screen.findByRole("checkbox", {
      name: /activer le bridge ChatGPT/i,
    });
    await waitFor(() => expect(toggle).not.toBeDisabled());
    expect(toggle).not.toBeChecked();
  });

  it("posts the explicit acceptance to the transport opt-in endpoint", async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<{ ok: boolean; json: () => Promise<unknown> }>>().mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/transport/status") {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ opt_in_accepted: false }) });
      }
      if (url === "/api/transport/opt-in") {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ opt_in_accepted: true }) });
      }
      return Promise.reject(new Error(`unexpected fetch ${url} ${init?.method ?? "GET"}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /Transport/i }));

    const toggle = await screen.findByRole("checkbox", { name: /activer le bridge ChatGPT/i });
    await waitFor(() => expect(toggle).not.toBeDisabled());
    await user.click(toggle);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/transport/opt-in", expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ accepted: true }),
      }));
    });
    expect(toggle).toBeChecked();
  });
});
