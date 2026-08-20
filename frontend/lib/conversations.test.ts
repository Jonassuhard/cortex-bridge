import { describe, expect, it } from "vitest";
import type { ConversationSummary } from "./types";
import { groupConversations } from "./conversations";

const item = (identity: string, extra: Partial<ConversationSummary> = {}): ConversationSummary => ({
  identity,
  url: `https://chatgpt.com/c/${identity}`,
  title: identity,
  ...extra,
});

describe("groupConversations", () => {
  it("deduplicates, caps at 50, and assigns every item to one group", () => {
    const source = Array.from({ length: 51 }, (_, index) => item(`recent-${index}`, { timestamp: `2026-07-26T12:${String(index).padStart(2, "0")}:00Z` }));
    source.unshift(item("pinned", { pinned: true }), item("project", { project_id: "atlas", project_title: "Atlas" }));
    source.push({ ...item("duplicate"), url: source[0].url });
    const groups = groupConversations(source);
    const all = [...groups.pinned, ...groups.projects.flatMap((group) => group.items), ...groups.recent];
    expect(all).toHaveLength(50);
    expect(new Set(all.map((entry) => entry.url)).size).toBe(50);
    expect(groups.pinned.every((entry) => entry.pinned)).toBe(true);
    expect(groups.projects[0]?.title).toBe("Atlas");
  });

  it("keeps stable input order when timestamps tie", () => {
    const groups = groupConversations([item("a"), item("b"), item("c")]);
    expect(groups.recent.map((entry) => entry.identity)).toEqual(["a", "b", "c"]);
  });
});
