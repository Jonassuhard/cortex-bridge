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
      submittedDraft?: string;
      submittedAttachment?: File | null;
    }
  | {
      type: "RUN_RECOVERY_EXHAUSTED";
      key: ConversationKey;
      runId: string;
      streamEpoch: number;
      error: string;
    }
  | {
      type: "RUN_CANCELLED";
      key: ConversationKey;
      runId: string;
      cancelledAt: string;
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
      type: "RESOLVE_REKEY_CONFLICT";
      fromKey: ConversationKey;
      toKey: ConversationKey;
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

const TERMINAL_RUN_STATES = new Set<ChatRunState>([
  "COMPLETED",
  "FAILED",
  "CANCELLED",
  "DELIVERY_UNCERTAIN",
]);
const TERMINAL_MISSION_STATES = new Set(["COMPLETED", "BLOCKED", "FAILED", "CANCELLED"]);

export function conversationKeyFromUrl(url: string): ConversationKey {
  const normalized = url.trim().replace(/\/$/, "");
  const match = normalized.match(/\/c\/([^/?#]+)/);
  return match?.[1] || normalized;
}

export function conversationKeyOf(summary: ConversationSummary): ConversationKey {
  return summary.identity || conversationKeyFromUrl(summary.url);
}

export function canonicalConversationUrlFromMission(mission: MissionDetail): string | null {
  const bindings = mission.timeline.conversation_bindings || [];
  for (let index = bindings.length - 1; index >= 0; index -= 1) {
    const binding = bindings[index];
    for (const candidate of [binding.conversation_url, binding.conversation_target]) {
      if (typeof candidate !== "string") continue;
      const normalized = candidate.trim().replace(/\/$/, "");
      if (/^https?:\/\//i.test(normalized) && /\/c\/[^/?#]+/.test(normalized)) return normalized;
    }
  }
  return null;
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
    submittedPayload: null,
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

function isMissionActive(entry: ConversationEntry): boolean {
  if (!entry.missionId) return false;
  return !entry.mission || !TERMINAL_MISSION_STATES.has(entry.mission.mission.state);
}

function shouldRetainOmittedEntry(entry: ConversationEntry, selected: boolean): boolean {
  if (entry.sendPending || isRunActive(entry.run) || isMissionActive(entry)) return true;
  if (entry.draft || entry.attachment || entry.submittedPayload) return true;
  if (entry.key.startsWith("provisional:")) return selected;
  return false;
}

function reduceSummaries(
  state: ConversationState,
  summaries: ConversationSummary[],
  updatedAt: string,
): ConversationState {
  const entries: Record<ConversationKey, ConversationEntry> = {};
  const incomingOrder: ConversationKey[] = [];
  const incoming = new Set<ConversationKey>();
  for (const summary of summaries) {
    const key = conversationKeyOf(summary);
    if (incoming.has(key)) continue;
    incoming.add(key);
    incomingOrder.push(key);
    const current = state.entries[key];
    entries[key] = current ? { ...current, summary: { ...current.summary, ...summary } } : createEntry(summary);
  }

  const retainedLocal = state.order.filter((key) => {
    if (incoming.has(key)) return false;
    const entry = state.entries[key];
    if (!entry || !shouldRetainOmittedEntry(entry, state.selectedKey === key)) return false;
    entries[key] = entry;
    return true;
  });
  const selectedKey = state.selectedKey && (incoming.has(state.selectedKey) || retainedLocal.includes(state.selectedKey))
    ? state.selectedKey
    : incomingOrder[0] || retainedLocal[0] || null;

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
    return updateEntry(state, event.key, (entry) => {
      if (entry.draft === event.draft) return entry;
      const abandonUncertainPayload = entry.run?.state === "DELIVERY_UNCERTAIN"
        && !!entry.submittedPayload
        && event.draft !== entry.submittedPayload.draft;
      return {
        ...entry,
        draft: event.draft,
        submittedPayload: abandonUncertainPayload ? null : entry.submittedPayload,
      };
    });
  }

  if (event.type === "ATTACHMENT_STAGED") {
    return updateEntry(state, event.key, (entry) => {
      if (entry.attachment === event.attachment) return entry;
      const abandonUncertainPayload = entry.run?.state === "DELIVERY_UNCERTAIN"
        && !!entry.submittedPayload
        && event.attachment !== entry.submittedPayload.attachment;
      return {
        ...entry,
        attachment: event.attachment,
        submittedPayload: abandonUncertainPayload ? null : entry.submittedPayload,
      };
    });
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
      return updateEntry(state, event.key, (current) => {
        const submittedPayload = event.accepted
          ? {
              runId: event.runId,
              draft: event.submittedDraft ?? current.draft,
              attachment: event.submittedAttachment === undefined
                ? current.attachment
                : event.submittedAttachment,
            }
          : current.submittedPayload;
        const delivered = !!event.run && (
          !!event.run.delivered_at
          || ["VISIBLE_IN_CHATGPT", "WAITING_FOR_CHATGPT", "CHATGPT_STREAMING", "COMPLETED"].includes(event.run.state)
        );
        const endedWithoutDelivery = !!event.run
          && ["FAILED", "CANCELLED"].includes(event.run.state);
        return {
          ...current,
          run: event.run || null,
          streamEpoch: event.streamEpoch,
          draft: delivered && submittedPayload && current.draft === submittedPayload.draft ? "" : current.draft,
          attachment: delivered && submittedPayload && current.attachment === submittedPayload.attachment
            ? null
            : current.attachment,
          submittedPayload: delivered || endedWithoutDelivery ? null : submittedPayload,
          sendPending: event.accepted ? false : current.sendPending,
          sendError: null,
        };
      });
    }
    if (!event.event || !entry.run || entry.run.id !== event.runId || entry.streamEpoch !== event.streamEpoch) {
      return state;
    }
    return updateEntry(state, event.key, (current) => {
      const delivery = event.event?.type === "delivery";
      const endedWithoutDelivery = event.event?.type === "error" || event.event?.type === "cancelled";
      const submitted = current.submittedPayload?.runId === event.runId ? current.submittedPayload : null;
      return {
        ...current,
        run: current.run ? applyRunEvent(current.run, event.event!) : null,
        draft: delivery && submitted && current.draft === submitted.draft ? "" : current.draft,
        attachment: delivery && submitted && current.attachment === submitted.attachment
          ? null
          : current.attachment,
        submittedPayload: delivery || endedWithoutDelivery ? null : current.submittedPayload,
      };
    });
  }

  if (event.type === "RUN_RECOVERY_EXHAUSTED") {
    const entry = state.entries[event.key];
    if (
      !entry?.run
      || entry.run.id !== event.runId
      || entry.streamEpoch !== event.streamEpoch
    ) return state;
    return updateEntry(state, event.key, (current) => ({
      ...current,
      run: current.run ? { ...current.run, state: "DELIVERY_UNCERTAIN", error: event.error } : null,
      sendPending: false,
      sendError: event.error,
    }));
  }

  if (event.type === "RUN_CANCELLED") {
    const entry = state.entries[event.key];
    if (!entry?.run || entry.run.id !== event.runId) return state;
    return updateEntry(state, event.key, (current) => ({
      ...current,
      run: current.run ? { ...current.run, state: "CANCELLED", completed_at: event.cancelledAt } : null,
      submittedPayload: null,
      sendPending: false,
    }));
  }

  if (event.type === "MISSION_EVENT") {
    const current = state.entries[event.key];
    if (!current) return state;
    if (!event.accepted && current.missionId && current.missionId !== event.missionId) return state;
    const next = updateEntry(state, event.key, (entry) => ({
      ...entry,
      missionId: event.missionId,
      mission: event.mission === undefined ? (event.accepted ? null : entry.mission) : event.mission,
      draft: event.accepted ? "" : entry.draft,
      attachment: event.accepted ? null : entry.attachment,
      sendPending: event.accepted ? false : entry.sendPending,
      sendError: null,
    }));
    const canonicalUrl = event.mission && event.key.startsWith("provisional:")
      ? canonicalConversationUrlFromMission(event.mission)
      : null;
    if (!canonicalUrl || next.entries[event.key]?.missionId !== event.missionId) return next;
    return conversationReducer(next, {
      type: "REKEY_CANONICAL",
      key: event.key,
      canonicalKey: conversationKeyFromUrl(canonicalUrl),
      canonicalUrl,
    });
  }

  if (event.type === "RESOLVE_REKEY_CONFLICT") {
    const conflict = state.rekeyConflict;
    if (
      !conflict
      || conflict.fromKey !== event.fromKey
      || conflict.toKey !== event.toKey
      || !state.entries[event.toKey]
    ) return state;
    const source = state.entries[event.fromKey];
    if (!source) return { ...state, selectedKey: event.toKey, rekeyConflict: null };
    const safeToDiscard = !source.sendPending
      && !source.draft
      && !source.attachment
      && !source.submittedPayload
      && !source.snapshot
      && source.messages.length === 0
      && !source.run
      && !source.missionId;
    if (!safeToDiscard) return { ...state, selectedKey: event.toKey };
    const entries = { ...state.entries };
    delete entries[event.fromKey];
    return {
      ...state,
      entries,
      order: state.order.filter((key) => key !== event.fromKey),
      selectedKey: event.toKey,
      rekeyConflict: null,
    };
  }

  if (event.type !== "REKEY_CANONICAL") return state;
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
