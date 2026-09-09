import { describe, expect, it } from "vitest";
import { runtimePanelState } from "./SettingsPanel";

describe("runtimePanelState", () => {
  it("does not turn contradictory Ollama fields into a verified state", () => {
    const state = runtimePanelState({
      ollama_up: true,
      ollama_status: "unavailable",
      volume_mounted: true,
      storage_status: "OK",
      storage_path: "/verified/storage",
    });

    expect(state.ollama).toEqual({ label: "Non vérifié", tone: "unknown" });
    expect(state.storage).toEqual({ label: "Vérifié : OK", tone: "good" });
  });

  it("treats absent runtime fields as unverified and an unmounted volume as unavailable", () => {
    expect(runtimePanelState({})).toEqual({
      ollama: { label: "Non vérifié", tone: "unknown" },
      storage: { label: "Non vérifié", tone: "unknown" },
      storagePath: "Chemin non vérifié",
    });
    expect(runtimePanelState({ volume_mounted: false, storage_status: "unknown" }).storage).toEqual({
      label: "Indisponible",
      tone: "bad",
    });
  });
});
