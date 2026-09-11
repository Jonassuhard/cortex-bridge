import { describe, expect, it } from "vitest";
import type { ConversationMessage } from "./types";
import { parseContextRequest, stripContextRequestMarkup } from "./contextRequest";

const payload = {
  protocol: "cortex-context-request.v1",
  requestId: "ctx-1",
  summary: "Vérifier le rendu local",
  items: [
    { id: "file-1", kind: "file", reason: "Lire le manifeste", path: "docs/README.md" },
    { id: "shot-1", kind: "screenshot", reason: "Comparer la vue", target: "current_chatgpt" },
    { id: "link-1", kind: "link", reason: "Consulter la documentation", url: "https://example.com/docs" },
  ],
};

function message(overrides: Partial<ConversationMessage> = {}): ConversationMessage {
  return { id: "m1", role: "assistant", text: "", ...overrides };
}

describe("context request marker", () => {
  it("parses one valid fenced proposal and marks every item as approval-required", () => {
    const result = parseContextRequest(message({
      text: `Voici ce dont j'ai besoin.\n\n\`\`\`cortex-context-request\n${JSON.stringify(payload)}\n\`\`\``,
    }));
    expect(result?.requestId).toBe("ctx-1");
    expect(result?.items.map((item) => item.transmission)).toEqual([
      "proposal_required", "proposal_required", "proposal_required",
    ]);
  });

  it("parses a structured code block returned by the transport", () => {
    const result = parseContextRequest(message({
      code_blocks: [{ lang: "cortex-context-request", text: JSON.stringify(payload) }],
    }));
    expect(result?.items[0].path).toBe("docs/README.md");
  });

  it("does not interpret user text or malformed JSON", () => {
    expect(parseContextRequest(message({ role: "user", text: "```cortex-context-request\n{}\n```" }))).toBeNull();
    expect(parseContextRequest(message({ text: "```cortex-context-request\nnot json\n```" }))).toBeNull();
  });

  it("rejects traversal, absolute paths, invalid links and duplicate ids", () => {
    const invalidPayloads = [
      { ...payload, items: [{ ...payload.items[0], path: "../secret.txt" }] },
      { ...payload, items: [{ ...payload.items[0], path: "/tmp/secret.txt" }] },
      { ...payload, items: [{ ...payload.items[2], url: "file:///tmp/secret.txt" }] },
      { ...payload, items: [payload.items[0], { ...payload.items[1], id: "file-1" }] },
    ];
    for (const invalidPayload of invalidPayloads) {
      const result = parseContextRequest(message({
        text: `\`\`\`cortex-context-request\n${JSON.stringify(invalidPayload)}\n\`\`\``,
      }));
      expect(result).toBeNull();
    }
  });

  it("strips only a valid marker from visible prose", () => {
    const text = `Avant\n\`\`\`cortex-context-request\n${JSON.stringify(payload)}\n\`\`\`\nAprès`;
    expect(stripContextRequestMarkup(text)).toBe("Avant\n\nAprès");
    expect(stripContextRequestMarkup("```cortex-context-request\nnot json\n```")).toContain("not json");
  });
});
