import { describe, expect, it } from "vitest";
import { createBridgeDiagramModel } from "./bridge-diagram-model";

describe("createBridgeDiagramModel", () => {
  it("keeps deterministic order and makes Ollama optional", () => {
    const base = createBridgeDiagramModel({ locale: "fr", includeOllama: false, reducedMotion: true });
    expect(base.nodes.map((node) => node.id)).toEqual(["user", "profile", "chatgpt", "preflight", "executor", "workspace", "evidence"]);
    expect(base.nodes.some((node) => node.id === "ollama")).toBe(false);
    expect(base.animated).toBe(false);
    expect(base.description).toContain("profil Playwright dédié");

    const optional = createBridgeDiagramModel({ locale: "en", includeOllama: true, reducedMotion: false });
    expect(optional.nodes.map((node) => node.id)).toContain("ollama");
    expect(optional.description).toContain("optional Ollama");
  });
});
