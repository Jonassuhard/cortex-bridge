import type { ConversationMessage } from "./types";

export const CONTEXT_REQUEST_PROTOCOL = "cortex-context-request.v1" as const;

export type ContextRequestKind = "file" | "screenshot" | "link";

export interface ContextRequestItem {
  id: string;
  kind: ContextRequestKind;
  reason: string;
  path?: string;
  target?: string;
  url?: string;
  transmission: "proposal_required";
}

export interface ContextRequest {
  protocol: typeof CONTEXT_REQUEST_PROTOCOL;
  requestId: string;
  summary: string;
  items: ContextRequestItem[];
}

interface ContextRequestCandidate {
  raw: string;
  start: number;
  end: number;
}

const FENCED_REQUEST_RE = /```cortex-context-request[ \t]*\r?\n([\s\S]*?)```/gi;
const MAX_ITEMS = 10;
const MAX_ID_CHARS = 120;
const MAX_REASON_CHARS = 500;
const MAX_SUMMARY_CHARS = 600;

function candidatesFromText(text: string): ContextRequestCandidate[] {
  const candidates: ContextRequestCandidate[] = [];
  for (const match of text.matchAll(FENCED_REQUEST_RE)) {
    const raw = match[1]?.trim();
    if (!raw || match.index == null) continue;
    candidates.push({
      raw,
      start: match.index,
      end: match.index + match[0].length,
    });
  }
  return candidates;
}

function isPlainString(value: unknown, maxLength: number): value is string {
  return typeof value === "string" && value.trim().length > 0 && value.length <= maxLength;
}

function safeRelativePath(value: unknown): value is string {
  if (!isPlainString(value, 1000)) return false;
  const path = value.trim();
  return !path.includes("\0")
    && !path.startsWith("/")
    && !path.startsWith("\\")
    && !/^[A-Za-z]:[\\/]/.test(path)
    && !path.split(/[\\/]+/).some((part) => part === ".." || part === "");
}

function normalizeItem(value: unknown): ContextRequestItem | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const item = value as Record<string, unknown>;
  const kind = item.kind;
  const id = typeof item.id === "string" ? item.id.trim() : "";
  const reason = typeof item.reason === "string" ? item.reason.trim() : "";
  if (!isPlainString(id, MAX_ID_CHARS) || !isPlainString(reason, MAX_REASON_CHARS)) return null;
  if (kind === "file") {
    if (!safeRelativePath(item.path)) return null;
    return { id, kind, reason, path: item.path.trim(), transmission: "proposal_required" };
  }
  if (kind === "screenshot") {
    if (!isPlainString(item.target, 120)) return null;
    return { id, kind, reason, target: item.target.trim(), transmission: "proposal_required" };
  }
  if (kind === "link") {
    const url = typeof item.url === "string" ? item.url.trim() : "";
    if (!/^https?:\/\/[^\s]+$/i.test(url)) return null;
    return { id, kind, reason, url, transmission: "proposal_required" };
  }
  return null;
}

function normalizePayload(value: unknown): ContextRequest | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const payload = value as Record<string, unknown>;
  if (payload.protocol !== CONTEXT_REQUEST_PROTOCOL) return null;
  const requestId = typeof payload.requestId === "string" ? payload.requestId.trim() : "";
  const summary = typeof payload.summary === "string" ? payload.summary.trim() : "";
  if (!isPlainString(requestId, MAX_ID_CHARS) || !isPlainString(summary, MAX_SUMMARY_CHARS)) return null;
  if (!Array.isArray(payload.items) || payload.items.length === 0 || payload.items.length > MAX_ITEMS) return null;
  const items = payload.items.map(normalizeItem);
  if (items.some((item) => item === null)) return null;
  const normalizedItems = items as ContextRequestItem[];
  if (new Set(normalizedItems.map((item) => item.id)).size !== normalizedItems.length) return null;
  return { protocol: CONTEXT_REQUEST_PROTOCOL, requestId, summary, items: normalizedItems };
}

function parseCandidate(raw: string): ContextRequest | null {
  try {
    return normalizePayload(JSON.parse(raw));
  } catch {
    return null;
  }
}

function contextCodeBlocks(message: ConversationMessage) {
  return (message.code_blocks || []).filter(
    (block) => block.lang?.trim().toLowerCase() === CONTEXT_REQUEST_PROTOCOL.replace(".v1", ""),
  );
}

function codeBlockRequest(message: ConversationMessage): ContextRequest | null {
  const blocks = contextCodeBlocks(message);
  if (blocks.length !== 1) return null;
  return parseCandidate(blocks[0].text);
}

/** Parse only assistant-authored, explicitly fenced context proposals. */
export function parseContextRequest(message: ConversationMessage): ContextRequest | null {
  if (message.role !== "assistant") return null;
  const candidates = candidatesFromText(message.text || "");
  const structuredBlocks = contextCodeBlocks(message);
  if (candidates.length > 0 && structuredBlocks.length > 0) return null;
  if (candidates.length > 1) return null;
  if (candidates.length === 1) return parseCandidate(candidates[0].raw);
  return codeBlockRequest(message);
}

/** Remove a valid proposal marker from the visible assistant prose. */
export function stripContextRequestMarkup(text: string): string {
  const candidates = candidatesFromText(text);
  if (candidates.length !== 1 || !parseCandidate(candidates[0].raw)) return text;
  return `${text.slice(0, candidates[0].start)}${text.slice(candidates[0].end)}`.trim();
}
