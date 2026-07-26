"use client";

import { useCallback, useEffect, useRef } from "react";
import { apiUrl } from "@/lib/api";
import { conversationKeyFromUrl } from "@/lib/conversation-state";
import type { ChatRun, ChatRunEvent, ConversationKey } from "@/lib/types";
import type { ConversationDispatch } from "./useConversationController";

export interface ChatEventSource {
  onmessage: ((event: MessageEvent<string>) => void) | null;
  onerror: ((event: Event) => void) | null;
  close(): void;
}

interface StreamBinding {
  key: ConversationKey;
  runId: string;
  streamEpoch: number;
  source: ChatEventSource;
  closed: boolean;
  recoveryAttempt: number;
}

export interface ChatRunTerminalContext {
  key: ConversationKey;
  runId: string;
  event: ChatRunEvent;
}

export interface UseChatRunStreamOptions {
  dispatch: ConversationDispatch;
  createEventSource?: (url: string) => ChatEventSource;
  onTerminal?: (context: ChatRunTerminalContext) => void;
  onDisconnect?: (key: ConversationKey, runId: string) => void;
  recoverRun?: (key: ConversationKey, runId: string) => Promise<ChatRun>;
  recoveryBaseDelayMs?: number;
  maxRecoveryAttempts?: number;
}

export interface ChatRunSubscribeOptions {
  accepted?: boolean;
  clearDraft?: boolean;
  clearAttachment?: boolean;
  recoveryAttempt?: number;
}

export interface ChatRunStreamController {
  subscribe(key: ConversationKey, run: ChatRun, options?: ChatRunSubscribeOptions): number;
  close(key: ConversationKey): void;
}

const TERMINAL_EVENTS = new Set<ChatRunEvent["type"]>(["complete", "error", "cancelled"]);
const TERMINAL_STATES = new Set<ChatRun["state"]>(["COMPLETED", "FAILED", "CANCELLED"]);

function terminalEventFromRun(run: ChatRun): ChatRunEvent {
  if (run.state === "COMPLETED") {
    return {
      seq: 0,
      ts: run.completed_at || new Date().toISOString(),
      type: "complete",
      payload: { text: run.response_text || "", completed_at: run.completed_at, latency: run.latency },
    };
  }
  if (run.state === "CANCELLED") {
    return { seq: 0, ts: new Date().toISOString(), type: "cancelled", payload: {} };
  }
  return {
    seq: 0,
    ts: new Date().toISOString(),
    type: "error",
    payload: { error: run.error || "Erreur transport" },
  };
}

export function useChatRunStream({
  dispatch,
  createEventSource = (url) => new EventSource(url),
  onTerminal,
  onDisconnect,
  recoverRun,
  recoveryBaseDelayMs = 250,
  maxRecoveryAttempts = 3,
}: UseChatRunStreamOptions): ChatRunStreamController {
  const dispatchRef = useRef(dispatch);
  const factoryRef = useRef(createEventSource);
  const terminalRef = useRef(onTerminal);
  const disconnectRef = useRef(onDisconnect);
  const recoverRef = useRef(recoverRun);
  const recoveryBaseDelayRef = useRef(recoveryBaseDelayMs);
  const maxRecoveryAttemptsRef = useRef(maxRecoveryAttempts);
  dispatchRef.current = dispatch;
  factoryRef.current = createEventSource;
  terminalRef.current = onTerminal;
  disconnectRef.current = onDisconnect;
  recoverRef.current = recoverRun;
  recoveryBaseDelayRef.current = recoveryBaseDelayMs;
  maxRecoveryAttemptsRef.current = maxRecoveryAttempts;

  const streamsRef = useRef(new Map<ConversationKey, StreamBinding>());
  const epochsRef = useRef(new Map<ConversationKey, number>());
  const disposedRef = useRef(false);
  const subscribeRef = useRef<ChatRunStreamController["subscribe"]>(() => 0);
  const recoveryTimersRef = useRef(new Map<ConversationKey, ReturnType<typeof setTimeout>>());

  const closeBinding = useCallback((binding: StreamBinding) => {
    if (binding.closed) return;
    binding.closed = true;
    binding.source.close();
    if (streamsRef.current.get(binding.key) === binding) {
      streamsRef.current.delete(binding.key);
    }
  }, []);

  const close = useCallback((key: ConversationKey) => {
    const recoveryTimer = recoveryTimersRef.current.get(key);
    if (recoveryTimer) {
      clearTimeout(recoveryTimer);
      recoveryTimersRef.current.delete(key);
    }
    epochsRef.current.set(key, (epochsRef.current.get(key) || 0) + 1);
    const binding = streamsRef.current.get(key);
    if (binding) closeBinding(binding);
  }, [closeBinding]);

  const subscribe = useCallback((
    key: ConversationKey,
    run: ChatRun,
    options: ChatRunSubscribeOptions = {},
  ): number => {
    if (disposedRef.current) return 0;
    const pendingRecovery = recoveryTimersRef.current.get(key);
    if (pendingRecovery) {
      clearTimeout(pendingRecovery);
      recoveryTimersRef.current.delete(key);
    }
    const previous = streamsRef.current.get(key);
    if (previous) closeBinding(previous);
    const streamEpoch = (epochsRef.current.get(key) || 0) + 1;
    epochsRef.current.set(key, streamEpoch);
    const source = factoryRef.current(apiUrl(`/api/chat/runs/${run.id}/events`));
    const binding: StreamBinding = {
      key,
      runId: run.id,
      streamEpoch,
      source,
      closed: false,
      recoveryAttempt: options.recoveryAttempt || 0,
    };
    streamsRef.current.set(key, binding);
    dispatchRef.current({
      type: "RUN_EVENT",
      key,
      runId: run.id,
      streamEpoch,
      run,
      accepted: options.accepted !== false,
      clearDraft: options.clearDraft,
      clearAttachment: options.clearAttachment,
    });

    source.onmessage = (message) => {
      if (disposedRef.current || binding.closed || streamsRef.current.get(binding.key) !== binding) return;
      let event: ChatRunEvent;
      try {
        event = JSON.parse(message.data) as ChatRunEvent;
      } catch {
        return;
      }
      const previousKey = binding.key;
      const next = dispatchRef.current({
        type: "RUN_EVENT",
        key: previousKey,
        runId: binding.runId,
        streamEpoch: binding.streamEpoch,
        event,
      });

      if (event.type === "delivery" && event.payload.canonical_url) {
        const canonicalUrl = String(event.payload.canonical_url);
        const canonicalKey = conversationKeyFromUrl(canonicalUrl);
        if (canonicalKey && canonicalKey !== previousKey) {
          const rekeyed = dispatchRef.current({
            type: "REKEY_CANONICAL",
            key: previousKey,
            canonicalKey,
            canonicalUrl,
          });
          const moved = !rekeyed.entries[previousKey] && !!rekeyed.entries[canonicalKey];
          if (moved && !streamsRef.current.has(canonicalKey)) {
            streamsRef.current.delete(previousKey);
            binding.key = canonicalKey;
            streamsRef.current.set(canonicalKey, binding);
            epochsRef.current.set(
              canonicalKey,
              Math.max(epochsRef.current.get(canonicalKey) || 0, binding.streamEpoch),
            );
          }
        }
      }

      if (next.entries[previousKey] || next.entries[binding.key]) {
        if (TERMINAL_EVENTS.has(event.type)) {
          const terminalKey = binding.key;
          closeBinding(binding);
          terminalRef.current?.({ key: terminalKey, runId: binding.runId, event });
        }
      }
    };

    source.onerror = () => {
      if (disposedRef.current || binding.closed || streamsRef.current.get(binding.key) !== binding) return;
      const disconnectedKey = binding.key;
      const disconnectedEpoch = binding.streamEpoch;
      closeBinding(binding);
      disconnectRef.current?.(disconnectedKey, binding.runId);
      const recover = recoverRef.current;
      if (!recover) return;
      const scheduleRecovery = (attempt: number) => {
        if (attempt >= maxRecoveryAttemptsRef.current) return;
        const recoverAfterBackoff = () => {
          recoveryTimersRef.current.delete(disconnectedKey);
          if (
            disposedRef.current
            || epochsRef.current.get(disconnectedKey) !== disconnectedEpoch
            || streamsRef.current.has(disconnectedKey)
          ) return;
          void recover(disconnectedKey, binding.runId).then((recovered) => {
            if (
              disposedRef.current
              || recovered.id !== binding.runId
              || epochsRef.current.get(disconnectedKey) !== disconnectedEpoch
              || streamsRef.current.has(disconnectedKey)
            ) return;
            if (TERMINAL_STATES.has(recovered.state)) {
              const terminalEvent = terminalEventFromRun(recovered);
              const next = dispatchRef.current({
                type: "RUN_EVENT",
                key: disconnectedKey,
                runId: binding.runId,
                streamEpoch: disconnectedEpoch,
                run: recovered,
              });
              if (next.entries[disconnectedKey]?.run?.id === binding.runId) {
                terminalRef.current?.({ key: disconnectedKey, runId: binding.runId, event: terminalEvent });
              }
              return;
            }
            subscribeRef.current(disconnectedKey, recovered, {
              accepted: false,
              recoveryAttempt: attempt + 1,
            });
          }).catch(() => scheduleRecovery(attempt + 1));
        };
        const delay = recoveryBaseDelayRef.current * (2 ** attempt);
        if (delay <= 0) {
          recoverAfterBackoff();
        } else {
          const timer = setTimeout(recoverAfterBackoff, delay);
          recoveryTimersRef.current.set(disconnectedKey, timer);
        }
      };
      scheduleRecovery(binding.recoveryAttempt);
    };
    return streamEpoch;
  }, [closeBinding]);
  subscribeRef.current = subscribe;

  useEffect(() => {
    const streams = streamsRef.current;
    const recoveryTimers = recoveryTimersRef.current;
    disposedRef.current = false;
    return () => {
      disposedRef.current = true;
      for (const binding of streams.values()) closeBinding(binding);
      streams.clear();
      for (const timer of recoveryTimers.values()) clearTimeout(timer);
      recoveryTimers.clear();
    };
  }, [closeBinding]);

  return { subscribe, close };
}
