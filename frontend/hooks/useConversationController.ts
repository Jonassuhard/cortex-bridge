"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import {
  conversationKeyOf,
  conversationReducer,
  createConversationState,
  createProvisionalConversation,
  type ConversationEvent,
  type ConversationState,
} from "@/lib/conversation-state";
import type {
  ConversationEntry,
  ConversationKey,
  ConversationSnapshot,
  ConversationSummary,
} from "@/lib/types";

export const CONVERSATION_LOAD_DEADLINE_MS = 10_000;
export const CONVERSATION_LOAD_DEADLINE_MESSAGE =
  "Le chargement a dépassé la limite de 10 secondes.";

export type ConversationDispatch = (event: ConversationEvent) => ConversationState;
export type ConversationSnapshotFetcher = (
  conversation: ConversationSummary,
  signal: AbortSignal,
) => Promise<ConversationSnapshot>;
export type ConversationBackgroundFetcher = (
  conversation: ConversationSummary,
  entry: ConversationEntry,
  signal: AbortSignal,
) => Promise<ConversationSnapshot>;

interface LoadOptions {
  force?: boolean;
  background?: boolean;
}

interface ActiveLoad {
  key: ConversationKey;
  epoch: number;
  controller: AbortController;
  timer: ReturnType<typeof setTimeout>;
  rejectInterrupted(error: Error): void;
  obsolete: boolean;
  promise: Promise<void>;
}

export interface ConversationRequestController {
  load(conversation: ConversationSummary, options?: LoadOptions): Promise<void>;
  cancelSelected(): void;
  activate(): void;
  dispose(): void;
}

class ObsoleteConversationLoadError extends Error {
  constructor() {
    super("Conversation load superseded");
    this.name = "ObsoleteConversationLoadError";
  }
}

class ConversationDeadlineError extends Error {
  constructor() {
    super(CONVERSATION_LOAD_DEADLINE_MESSAGE);
    this.name = "ConversationDeadlineError";
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "Chargement de la conversation impossible";
}

export function createConversationRequestController({
  dispatch,
  getState,
  fetchSnapshot,
  fetchBackgroundSnapshot,
  deadlineMs = CONVERSATION_LOAD_DEADLINE_MS,
}: {
  dispatch: ConversationDispatch;
  getState: () => ConversationState;
  fetchSnapshot: ConversationSnapshotFetcher;
  fetchBackgroundSnapshot?: ConversationBackgroundFetcher;
  deadlineMs?: number;
}): ConversationRequestController {
  let active: ActiveLoad | null = null;
  let disposed = false;
  const epochs = new Map<ConversationKey, number>();

  function cancelActive(notifyReducer: boolean) {
    const request = active;
    if (!request) return;
    active = null;
    request.obsolete = true;
    clearTimeout(request.timer);
    request.controller.abort(new ObsoleteConversationLoadError());
    if (notifyReducer) {
      dispatch({
        type: "REQUEST_FAILED",
        request: "load",
        key: request.key,
        epoch: request.epoch,
        error: "",
        aborted: true,
      });
    }
    request.rejectInterrupted(new ObsoleteConversationLoadError());
  }

  return {
    load(conversation, options = {}) {
      if (disposed) return Promise.resolve();
      const key = conversationKeyOf(conversation);
      if (active?.key === key && !options.force) return active.promise;
      cancelActive(true);

      const entryEpoch = getState().entries[key]?.loadEpoch || 0;
      const epoch = Math.max(epochs.get(key) || 0, entryEpoch) + 1;
      epochs.set(key, epoch);
      const controller = new AbortController();
      let rejectInterrupted!: (error: Error) => void;
      const interrupted = new Promise<never>((_resolve, reject) => {
        rejectInterrupted = reject;
      });
      const request = {
        key,
        epoch,
        controller,
        timer: 0 as unknown as ReturnType<typeof setTimeout>,
        rejectInterrupted,
        obsolete: false,
        promise: Promise.resolve(),
      } satisfies ActiveLoad;
      active = request;
      dispatch({
        type: "SWITCH_STARTED",
        key,
        epoch,
        background: options.background,
      });

      request.timer = setTimeout(() => {
        if (active !== request || request.obsolete) return;
        active = null;
        request.controller.abort(new ConversationDeadlineError());
        request.rejectInterrupted(new ConversationDeadlineError());
      }, deadlineMs);

      let fetched: Promise<ConversationSnapshot>;
      try {
        const currentEntry = getState().entries[key];
        fetched = options.background && currentEntry && fetchBackgroundSnapshot
          ? fetchBackgroundSnapshot(conversation, currentEntry, controller.signal)
          : fetchSnapshot(conversation, controller.signal);
      } catch (error) {
        fetched = Promise.reject(error);
      }

      request.promise = Promise.race([fetched, interrupted])
        .then((snapshot) => {
          if (disposed || request.obsolete) return;
          dispatch({ type: "SNAPSHOT_RECEIVED", key, epoch, snapshot });
        })
        .catch((error: unknown) => {
          if (disposed || request.obsolete || error instanceof ObsoleteConversationLoadError) return;
          dispatch({
            type: "REQUEST_FAILED",
            request: "load",
            key,
            epoch,
            error: error instanceof ConversationDeadlineError
              ? CONVERSATION_LOAD_DEADLINE_MESSAGE
              : errorMessage(error),
          });
        })
        .finally(() => {
          clearTimeout(request.timer);
          if (active === request) active = null;
        });
      return request.promise;
    },
    cancelSelected() {
      cancelActive(true);
    },
    activate() {
      disposed = false;
    },
    dispose() {
      disposed = true;
      cancelActive(true);
    },
  };
}

export interface UseConversationControllerOptions {
  fetchSnapshot?: ConversationSnapshotFetcher;
  fetchBackgroundSnapshot?: ConversationBackgroundFetcher;
  initialState?: ConversationState;
  deadlineMs?: number;
}

export interface ConversationControllerResult {
  state: ConversationState;
  selectedEntry: ConversationEntry | null;
  dispatch: ConversationDispatch;
  replaceSummaries(summaries: ConversationSummary[]): void;
  selectConversation(conversation: ConversationSummary, options?: LoadOptions): void;
  selectNone(): void;
  reloadSelected(options?: Omit<LoadOptions, "force">): void;
  newConversation(randomUUID?: () => string): ConversationSummary;
}

export function useConversationController({
  fetchSnapshot = (conversation, signal) => api<ConversationSnapshot>(
    `/api/conversations/snapshot?url=${encodeURIComponent(conversation.url)}`,
    { signal },
  ),
  fetchBackgroundSnapshot,
  initialState = createConversationState(),
  deadlineMs = CONVERSATION_LOAD_DEADLINE_MS,
}: UseConversationControllerOptions = {}): ConversationControllerResult {
  const stateRef = useRef(initialState);
  const mountedRef = useRef(true);
  const fetchSnapshotRef = useRef(fetchSnapshot);
  const fetchBackgroundSnapshotRef = useRef(fetchBackgroundSnapshot);
  fetchSnapshotRef.current = fetchSnapshot;
  fetchBackgroundSnapshotRef.current = fetchBackgroundSnapshot;
  const [state, setState] = useState(initialState);

  const dispatch = useCallback<ConversationDispatch>((event) => {
    const next = conversationReducer(stateRef.current, event);
    stateRef.current = next;
    if (mountedRef.current) setState(next);
    return next;
  }, []);

  const requestControllerRef = useRef<ConversationRequestController | null>(null);
  if (!requestControllerRef.current) {
    requestControllerRef.current = createConversationRequestController({
      dispatch,
      getState: () => stateRef.current,
      fetchSnapshot: (conversation, signal) => fetchSnapshotRef.current(conversation, signal),
      fetchBackgroundSnapshot: (conversation, entry, signal) => {
        const backgroundFetcher = fetchBackgroundSnapshotRef.current;
        return backgroundFetcher
          ? backgroundFetcher(conversation, entry, signal)
          : fetchSnapshotRef.current(conversation, signal);
      },
      deadlineMs,
    });
  }

  useEffect(() => {
    mountedRef.current = true;
    requestControllerRef.current?.activate();
    return () => {
      mountedRef.current = false;
      requestControllerRef.current?.dispose();
    };
  }, []);

  const selectConversation = useCallback((conversation: ConversationSummary, options?: LoadOptions) => {
    const key = conversationKeyOf(conversation);
    const previousKey = stateRef.current.selectedKey;
    dispatch({ type: "SELECT", key, summary: conversation });
    if (previousKey !== key || options?.force) {
      void requestControllerRef.current?.load(conversation, options);
    }
  }, [dispatch]);

  const replaceSummaries = useCallback((summaries: ConversationSummary[]) => {
    const previousKey = stateRef.current.selectedKey;
    const next = dispatch({
      type: "SUMMARIES_RECEIVED",
      summaries,
      updatedAt: new Date().toISOString(),
    });
    if (next.selectedKey === previousKey) {
      const selected = next.selectedKey ? next.entries[next.selectedKey] : null;
      if (
        selected
        && !selected.key.startsWith("provisional:")
        && selected.loadPhase === "idle"
        && selected.freshness === "empty"
      ) {
        void requestControllerRef.current?.load(selected.summary);
      }
      return;
    }
    if (!next.selectedKey) {
      requestControllerRef.current?.cancelSelected();
      return;
    }
    const entry = next.entries[next.selectedKey];
    if (entry) void requestControllerRef.current?.load(entry.summary);
  }, [dispatch]);

  const selectNone = useCallback(() => {
    requestControllerRef.current?.cancelSelected();
    dispatch({ type: "SELECT", key: null });
  }, [dispatch]);

  const reloadSelected = useCallback((options?: Omit<LoadOptions, "force">) => {
    const selectedKey = stateRef.current.selectedKey;
    const entry = selectedKey ? stateRef.current.entries[selectedKey] : null;
    if (!entry || entry.key.startsWith("provisional:")) return;
    void requestControllerRef.current?.load(entry.summary, options);
  }, []);

  const newConversation = useCallback((randomUUID?: () => string) => {
    requestControllerRef.current?.cancelSelected();
    const conversation = createProvisionalConversation(randomUUID);
    dispatch({ type: "SELECT", key: conversation.identity, summary: conversation });
    return conversation;
  }, [dispatch]);

  const selectedEntry = useMemo(() => (
    state.selectedKey ? state.entries[state.selectedKey] || null : null
  ), [state]);

  return {
    state,
    selectedEntry,
    dispatch,
    replaceSummaries,
    selectConversation,
    selectNone,
    reloadSelected,
    newConversation,
  };
}
