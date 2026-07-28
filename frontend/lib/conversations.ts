import type { ConversationSummary } from "./types";

export interface ConversationProjectGroup {
  id: string;
  title: string;
  items: ConversationSummary[];
}

export interface ConversationGroups {
  pinned: ConversationSummary[];
  projects: ConversationProjectGroup[];
  recent: ConversationSummary[];
}

function canonicalKey(item: ConversationSummary): string {
  if (item.identity.startsWith("provisional:")) return item.identity;
  const normalizedUrl = item.url.trim().replace(/[?#].*$/, "").replace(/\/+$/, "");
  return normalizedUrl || item.identity;
}

export function groupConversations(items: ConversationSummary[], limit = 50): ConversationGroups {
  const seen = new Set<string>();
  const unique = items
    .map((item, index) => ({ item, index, time: Date.parse(item.timestamp || "") || 0 }))
    .filter(({ item }) => {
      const key = canonicalKey(item);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => {
      const priority = (entry: ConversationSummary) => entry.pinned ? 0 : entry.project_id && entry.project_title ? 1 : 2;
      return priority(a.item) - priority(b.item) || b.time - a.time || a.index - b.index;
    })
    .slice(0, Math.max(0, limit))
    .map(({ item }) => item);

  const pinned: ConversationSummary[] = [];
  const recent: ConversationSummary[] = [];
  const projects = new Map<string, ConversationProjectGroup>();
  for (const item of unique) {
    if (item.pinned) {
      pinned.push(item);
      continue;
    }
    if (item.project_id && item.project_title) {
      const group = projects.get(item.project_id) || {
        id: item.project_id,
        title: item.project_title,
        items: [],
      };
      group.items.push(item);
      projects.set(item.project_id, group);
      continue;
    }
    recent.push(item);
  }
  return { pinned, projects: [...projects.values()], recent };
}
