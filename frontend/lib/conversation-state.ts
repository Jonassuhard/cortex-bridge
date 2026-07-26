import type {
  ChatRun,
  ChatRunEvent,
  ChatRunState,
  ConversationEntry,
  ConversationKey,
  ConversationSnapshot,
  ConversationSummary,
  MissionDetail,
  SyncStatus,
} from "./types";

export interface RekeyConflict {
  fromKey: ConversationKey;
  toKey: ConversationKey;
  error: string;
}

export interface ConversationState {
  selectedKey: ConversationKey | null;
  entries: Record<ConversationKey, ConversationEntry>;
  order: ConversationKey[];
  sync: SyncStatus;
  rekeyConflict: RekeyConflict | null;
}

export type ConversationEvent =
  | { type: "SELECT"; key: ConversationKey | null; summary?: ConversationSummary }
  | { type: "SUMMARIES_RECEIVED"; summaries: ConversationSummary[]; updatedAt: string }
  | { type: "CONVERSATIONS_FAILED"; error: string }
  | { type: "DRAFT_CHANGED"; key: ConversationKey; draft: string }
  | { type: "ATTACHMENT_STAGED"; key: ConversationKey; attachment: File | null }
  | { type: "REQUEST_STARTED"; request: "send"; key: ConversationKey }
  | { type: "SWITCH_STARTED"; key: ConversationKey; epoch: number; background?: boolean }
  | { type: "SNAPSHOT_RECEIVED"; key: ConversationKey; epoch: number; snapshot: ConversationSnapshot }
  | {
      type: "RUN_EVENT";
      key: ConversationKey;
      runId: string;
      streamEpoch: number;
      run?: ChatRun;
      event?: ChatRunEvent;
      accepted?: boolean;
      clearDraft?: boolean;
      clearAttachment?: boolean;
    }
  | {
      type: "MISSION_EVENT";
      key: ConversationKey;
      missionId: string;
      mission?: MissionDetail | null;
      accepted?: boolean;
    }
  | {
      type: "REKEY_CANONICAL";
      key: ConversationKey;
      canonicalKey: ConversationKey;
      canonicalUrl: string;
    }
  | {
      type: "REQUEST_FAILED";
      request: "load";
      key: ConversationKey;
      epoch: number;
      error: string;
      aborted?: boolean;
    }
  | {
      type: "REQUEST_FAILED";
      request: "send";
      key: ConversationKey;
      error: string;
      status?: number;
    };

const TERMINAL_RUN_STATES = new Set<ChatRunState>(["COMPLETED", "FAILED", "CANCELLED"]);

export function conversationKeyFromUrl(url: string): ConversationKey {
  const normalized = url.trim().replace(/\/$/, "");
  const match = normalized.match(/\/c\/([^/?#]+)/);
  return match?.[1] || normalized;
}

export function conversationKeyOf(summary: ConversationSummary): ConversationKey {
  return summary.identity || conversationKeyFromUrl(summary.url);
}

export function createProvisionalConversation(
  randomUUID: () => string = () => globalThis.crypto.randomUUID(),
): ConversationSummary {
  const key = `provisional:${randomUUID()}`;
  return {
    url: "https://chatgpt.com/",
    identity: key,
    title: "Nouvelle conversation",
    preview: "Le chat sera créé au premier envoi",
    status: "idle",
    sync_state: "live",
    sync_error: null,
  };
}

function createEntry(summary: ConversationSummary): ConversationEntry {
  const key = conversationKeyOf(summary);
  return {
    key,
    summary,
    snapshot: null,
    messages: [],
    draft: "",
    attachment: null,
    loadEpoch: 0,
    loadPhase: "idle",
    loadError: null,
    freshness: "empty",
    run: null,
    streamEpoch: 0,
    missionId: null,
    mission: null,
    sendPending: false,
    sendError: null,
  };
}

export function createConversationState(
  summaries: ConversationSummary[] = [],
  selectedKey: ConversationKey | null = null,
): ConversationState {
  const entries: Record<ConversationKey, ConversationEntry> = {};
  const order: ConversationKey[] = [];
  for (const summary of summaries) {
    const entry = createEntry(summary);
    if (entries[entry.key]) continue;
    entries[entry.key] = entry;
    order.push(entry.key);
  }
  return {
    selectedKey: selectedKey && entries[selectedKey] ? selectedKey : null,
    entries,
    order,
    sync: { state: "unknown", error: null, updated_at: null },
    rekeyConflict: null,
  };
}

function updateEntry(
  state: ConversationState,
  key: ConversationKey,
  update: (entry: ConversationEntry) => ConversationEntry,
): ConversationState {
  const entry = state.entries[key];
  if (!entry) return state;
  const nextEntry = update(entry);
  if (nextEntry === entry) return state;
  return { ...state, entries: { ...state.entries, [key]: nextEntry } };
}

function isRunActive(run: ChatRun | null): boolean {
  return !!run && !TERMINAL_RUN_STATES.has(run.state);
}

function reduceSummaries(
  state: ConversationState,
  summaries: ConversationSummary[],
  updatedAt: string,
): ConversationState {
  const entries = { ...state.entries };
  const incomingOrder: ConversationKey[] = [];
  const incoming = new Set<ConversationKey>();
  for (const summary of summaries) {
    const key = conversationKeyOf(summary);
    if (incoming.has(key)) continue;
    incoming.add(key);
    incomingOrder.push(key);
    const current = entries[key];
    entries[key] = current ? { ...current, summary: { ...current.summary, ...summary } } : createEntry(summary);
  }

  const currentSelected = state.selectedKey ? entries[state.selectedKey] : null;
  const preserveSelected = !!currentSelected && (
    incoming.has(currentSelected.key)
    || currentSelected.key.startsWith("provisional:")
    || isRunActive(currentSelected.run)
    || !!currentSelected.missionId
  );
  const selectedKey = preserveSelected ? currentSelected.key : incomingOrder[0] || null;
  const retainedLocal = state.order.filter((key) => {
    if (incoming.has(key)) return false;
    const entry = entries[key];
    return !!entry && (key.startsWith("provisional:") || isRunActive(entry.run) || !!entry.missionId);
  });

  return {
    ...state,
    entries,
    order: [...retainedLocal, ...incomingOrder],
    selectedKey,
    sync: { state: "live", error: null, updated_at: updatedAt },
  };
}

function applyRunEvent(run: ChatRun, event: ChatRunEvent): ChatRun {
  if (event.type === "status") {
    return { ...run, state: String(event.payload.state) as ChatRunState };
  }
  if (event.type === "delivery") {
    return {
      ...run,
      state: "VISIBLE_IN_CHATGPT",
      delivered_at: String(event.payload.delivered_at || event.ts),
      canonical_url: String(event.payload.canonical_url || run.canonical_url || run.conversation_url),
    };
  }
  if (event.type === "stream") {
    return {
      ...run,
      state: "CHATGPT_STREAMING",
      response_text: String(event.payload.text || ""),
      first_response_at: run.first_response_at || String(event.payload.first_response_at || event.ts),
    };
  }
  if (event.type === "complete") {
    return {
      ...run,
      state: "COMPLETED",
      response_text: String(event.payload.text || run.response_text || ""),
      completed_at: String(event.payload.completed_at || event.ts),
      latency: event.payload.latency as ChatRun["latency"],
    };
  }
  if (event.type === "error") {
    return { ...run, state: "FAILED", error: String(event.payload.error || "Erreur transport") };
  }
  if (event.type === "cancelled") return { ...run, state: "CANCELLED" };
  return run;
}

export function conversationReducer(
  state: ConversationState,
  event: ConversationEvent,
): ConversationState {
  if (event.type === "SELECT") {
    if (event.key === null) {
      return state.selectedKey === null ? state : { ...state, selectedKey: null };
    }
    let next = state;
    if (!state.entries[event.key] && event.summary) {
      const entry = createEntry(event.summary);
      next = {
        ...state,
        entries: { ...state.entries, [event.key]: { ...entry, key: event.key } },
        order: state.order.includes(event.key) ? state.order : [event.key, ...state.order],
      };
    } else if (event.summary && state.entries[event.key]) {
      next = updateEntry(state, event.key, (entry) => ({
        ...entry,
        summary: { ...entry.summary, ...event.summary },
      }));
    }
    return next.selectedKey === event.key ? next : { ...next, selectedKey: event.key };
  }

  if (event.type === "SUMMARIES_RECEIVED") {
    return reduceSummaries(state, event.summaries, event.updatedAt);
  }

  if (event.type === "CONVERSATIONS_FAILED") {
    return {
      ...state,
      sync: { state: state.order.length ? "stale" : "unavailable", error: event.error, updated_at: state.sync.updated_at },
    };
  }

  if (event.type === "DRAFT_CHANGED") {
    return updateEntry(state, event.key, (entry) => (
      entry.draft === event.draft ? entry : { ...entry, draft: event.draft }
    ));
  }

  if (event.type === "ATTACHMENT_STAGED") {
    return updateEntry(state, event.key, (entry) => (
      entry.attachment === event.attachment ? entry : { ...entry, attachment: event.attachment }
    ));
  }

  if (event.type === "REQUEST_STARTED") {
    return updateEntry(state, event.key, (entry) => ({
      ...entry,
      sendPending: true,
      sendError: null,
    }));
  }

  if (event.type === "SWITCH_STARTED") {
    return updateEntry(state, event.key, (entry) => ({
      ...entry,
      loadEpoch: event.epoch,
      loadPhase: event.background && entry.freshness !== "empty" ? entry.loadPhase : "loading",
      loadError: null,
      freshness: entry.freshness === "empty" ? "empty" : "cached",
    }));
  }

  if (event.type === "SNAPSHOT_RECEIVED") {
    const entry = state.entries[event.key];
    if (!entry || entry.loadEpoch !== event.epoch) return state;
    const messageCount = event.snapshot.messages.length;
    return updateEntry(state, event.key, (current) => ({
      ...current,
      snapshot: event.snapshot,
      messages: event.snapshot.messages,
      loadPhase: "ready",
      loadError: null,
      freshness: "live",
      summary: {
        ...current.summary,
        title: event.snapshot.title || current.summary.title,
        message_count: messageCount,
        sync_state: "live",
        sync_error: null,
      },
    }));
  }

  if (event.type === "REQUEST_FAILED") {
    if (event.request === "send") {
      return updateEntry(state, event.key, (entry) => ({
        ...entry,
        sendPending: false,
        sendError: event.error,
      }));
    }
    const entry = state.entries[event.key];
    if (!entry || entry.loadEpoch !== event.epoch) return state;
    return updateEntry(state, event.key, (current) => ({
      ...current,
      loadPhase: event.aborted ? (current.snapshot ? "ready" : "idle") : "error",
      loadError: event.aborted ? null : event.error,
      freshness: current.snapshot ? (event.aborted ? "cached" : "stale") : "empty",
      summary: event.aborted ? current.summary : {
        ...current.summary,
        sync_state: "stale",
        sync_error: event.error,
      },
    }));
  }

  if (event.type === "RUN_EVENT") {
    const entry = state.entries[event.key];
    if (!entry) return state;
    if (event.run) {
      if (event.run.id !== event.runId) return state;
      if (!event.accepted && (
        !entry.run
        || entry.run.id !== event.runId
        || event.streamEpoch < entry.streamEpoch
      )) return state;
      return updateEntry(state, event.key, (current) => ({
        ...current,
        run: event.run || null,
        streamEpoch: event.streamEpoch,
        draft: event.accepted && event.clearDraft !== false ? "" : current.draft,
        attachment: event.accepted && event.clearAttachment !== false ? null : current.attachment,
        sendPending: event.accepted ? false : current.sendPending,
        sendError: null,
      }));
    }
    if (!event.event || !entry.run || entry.run.id !== event.runId || entry.streamEpoch !== event.streamEpoch) {
      return state;
    }
    return updateEntry(state, event.key, (current) => ({
      ...current,
      run: current.run ? applyRunEvent(current.run, event.event!) : null,
    }));
  }

  if (event.type === "MISSION_EVENT") {
    const current = state.entries[event.key];
    if (!current) return state;
    if (!event.accepted && current.missionId && current.missionId !== event.missionId) return state;
    return updateEntry(state, event.key, (entry) => ({
      ...entry,
      missionId: event.missionId,
      mission: event.mission === undefined ? (event.accepted ? null : entry.mission) : event.mission,
      draft: event.accepted ? "" : entry.draft,
      attachment: event.accepted ? null : entry.attachment,
      sendPending: event.accepted ? false : entry.sendPending,
      sendError: null,
    }));
  }

  const source = state.entries[event.key];
  if (!source) return state;
  if (event.key !== event.canonicalKey && state.entries[event.canonicalKey]) {
    return {
      ...state,
      rekeyConflict: {
        fromKey: event.key,
        toKey: event.canonicalKey,
        error: "La conversation canonique existe déjà dans le cache.",
      },
    };
  }
  const canonicalEntry: ConversationEntry = {
    ...source,
    key: event.canonicalKey,
    summary: {
      ...source.summary,
      url: event.canonicalUrl,
      identity: event.canonicalKey,
    },
  };
  const entries = { ...state.entries };
  delete entries[event.key];
  entries[event.canonicalKey] = canonicalEntry;
  return {
    ...state,
    entries,
    order: [...new Set(state.order.map((key) => key === event.key ? event.canonicalKey : key))],
    selectedKey: state.selectedKey === event.key ? event.canonicalKey : state.selectedKey,
    rekeyConflict: null,
  };
}
