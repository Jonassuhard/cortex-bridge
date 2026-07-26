"use client";

import { useCallback, useEffect, useRef } from "react";
import { apiUrl } from "@/lib/api";
import { conversationKeyFromUrl } from "@/lib/conversation-state";
import type { ChatRun, ChatRunEvent, ConversationKey } from "@/lib/types";
import type { ConversationDispatch } from "./useConversationController";

export const CHAT_RECOVERY_DEADLINE_MS = 10_000;
export const CHAT_RECOVERY_EXHAUSTED_MESSAGE =
  "Livraison incertaine : impossible de confirmer le message dans ChatGPT.";

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
  recoveryDeadlineAt: number | null;
}

interface RecoveryTask {
  key: ConversationKey;
  runId: string;
  streamEpoch: number;
  deadlineAt: number;
  cancelled: boolean;
  timer: ReturnType<typeof setTimeout> | null;
  attemptTimer: ReturnType<typeof setTimeout> | null;
  controller: AbortController | null;
}

export interface ChatRunTerminalContext {
  key: ConversationKey;
  runId: string;
  event: ChatRunEvent;
}

export interface ChatRunRecoveryContext {
  signal: AbortSignal;
  deadlineAt: number;
  remainingMs: number;
}

export interface UseChatRunStreamOptions {
  dispatch: ConversationDispatch;
  createEventSource?: (url: string) => ChatEventSource;
  onTerminal?: (context: ChatRunTerminalContext) => void;
  onDisconnect?: (key: ConversationKey, runId: string) => void;
  recoverRun?: (
    key: ConversationKey,
    runId: string,
    context: ChatRunRecoveryContext,
  ) => Promise<ChatRun>;
  recoveryBaseDelayMs?: number;
  maxRecoveryAttempts?: number;
  recoveryDeadlineMs?: number;
}

export interface ChatRunSubscribeOptions {
  accepted?: boolean;
  submittedDraft?: string;
  submittedAttachment?: File | null;
  recoveryAttempt?: number;
  recoveryDeadlineAt?: number | null;
}

export interface ChatRunStreamController {
  subscribe(key: ConversationKey, run: ChatRun, options?: ChatRunSubscribeOptions): number;
  close(key: ConversationKey): void;
}

const TERMINAL_EVENTS = new Set<ChatRunEvent["type"]>(["complete", "error", "cancelled"]);
const TERMINAL_STATES = new Set<ChatRun["state"]>([
  "COMPLETED",
  "FAILED",
  "CANCELLED",
  "DELIVERY_UNCERTAIN",
]);

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
  recoveryDeadlineMs = CHAT_RECOVERY_DEADLINE_MS,
}: UseChatRunStreamOptions): ChatRunStreamController {
  const dispatchRef = useRef(dispatch);
  const factoryRef = useRef(createEventSource);
  const terminalRef = useRef(onTerminal);
  const disconnectRef = useRef(onDisconnect);
  const recoverRef = useRef(recoverRun);
  const recoveryBaseDelayRef = useRef(recoveryBaseDelayMs);
  const maxRecoveryAttemptsRef = useRef(maxRecoveryAttempts);
  const recoveryDeadlineRef = useRef(recoveryDeadlineMs);
  dispatchRef.current = dispatch;
  factoryRef.current = createEventSource;
  terminalRef.current = onTerminal;
  disconnectRef.current = onDisconnect;
  recoverRef.current = recoverRun;
  recoveryBaseDelayRef.current = recoveryBaseDelayMs;
  maxRecoveryAttemptsRef.current = maxRecoveryAttempts;
  recoveryDeadlineRef.current = recoveryDeadlineMs;

  const streamsRef = useRef(new Map<ConversationKey, StreamBinding>());
  const epochsRef = useRef(new Map<ConversationKey, number>());
  const recoveriesRef = useRef(new Map<ConversationKey, RecoveryTask>());
  const disposedRef = useRef(false);
  const subscribeRef = useRef<ChatRunStreamController["subscribe"]>(() => 0);

  const closeBinding = useCallback((binding: StreamBinding) => {
    if (binding.closed) return;
    binding.closed = true;
    binding.source.close();
    if (streamsRef.current.get(binding.key) === binding) streamsRef.current.delete(binding.key);
  }, []);

  const cancelRecovery = useCallback((key: ConversationKey) => {
    const task = recoveriesRef.current.get(key);
    if (!task) return;
    task.cancelled = true;
    if (task.timer) clearTimeout(task.timer);
    if (task.attemptTimer) clearTimeout(task.attemptTimer);
    task.controller?.abort();
    recoveriesRef.current.delete(key);
  }, []);

  const close = useCallback((key: ConversationKey) => {
    cancelRecovery(key);
    epochsRef.current.set(key, (epochsRef.current.get(key) || 0) + 1);
    const binding = streamsRef.current.get(key);
    if (binding) closeBinding(binding);
  }, [cancelRecovery, closeBinding]);

  const subscribe = useCallback((
    key: ConversationKey,
    run: ChatRun,
    options: ChatRunSubscribeOptions = {},
  ): number => {
    if (disposedRef.current) return 0;
    const previous = streamsRef.current.get(key);
    const streamEpoch = (epochsRef.current.get(key) || 0) + 1;
    const source = factoryRef.current(apiUrl(`/api/chat/runs/${run.id}/events`));
    const binding: StreamBinding = {
      key,
      runId: run.id,
      streamEpoch,
      source,
      closed: false,
      recoveryAttempt: options.recoveryAttempt || 0,
      recoveryDeadlineAt: options.recoveryDeadlineAt ?? null,
    };
    const next = dispatchRef.current({
      type: "RUN_EVENT",
      key,
      runId: run.id,
      streamEpoch,
      run,
      accepted: options.accepted !== false,
      submittedDraft: options.submittedDraft,
      submittedAttachment: options.submittedAttachment,
    });
    const acceptedBinding = next.entries[key]?.run?.id === run.id
      && next.entries[key]?.streamEpoch === streamEpoch;
    if (!acceptedBinding) {
      binding.closed = true;
      source.close();
      return 0;
    }
    cancelRecovery(key);
    if (previous) closeBinding(previous);
    epochsRef.current.set(key, streamEpoch);
    streamsRef.current.set(key, binding);

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

      if ((next.entries[previousKey] || next.entries[binding.key]) && TERMINAL_EVENTS.has(event.type)) {
        const terminalKey = binding.key;
        closeBinding(binding);
        terminalRef.current?.({ key: terminalKey, runId: binding.runId, event });
      }
    };

    source.onerror = () => {
      if (disposedRef.current || binding.closed || streamsRef.current.get(binding.key) !== binding) return;
      const disconnectedKey = binding.key;
      const disconnectedEpoch = binding.streamEpoch;
      closeBinding(binding);
      disconnectRef.current?.(disconnectedKey, binding.runId);
      if (!recoverRef.current) return;

      const task: RecoveryTask = {
        key: disconnectedKey,
        runId: binding.runId,
        streamEpoch: disconnectedEpoch,
        deadlineAt: binding.recoveryDeadlineAt ?? (Date.now() + recoveryDeadlineRef.current),
        cancelled: false,
        timer: null,
        attemptTimer: null,
        controller: null,
      };
      cancelRecovery(disconnectedKey);
      recoveriesRef.current.set(disconnectedKey, task);

      const isCurrent = () => (
        !disposedRef.current
        && !task.cancelled
        && recoveriesRef.current.get(task.key) === task
        && epochsRef.current.get(task.key) === task.streamEpoch
        && !streamsRef.current.has(task.key)
      );
      const exhaust = () => {
        if (!isCurrent()) return;
        cancelRecovery(task.key);
        dispatchRef.current({
          type: "RUN_RECOVERY_EXHAUSTED",
          key: task.key,
          runId: task.runId,
          streamEpoch: task.streamEpoch,
          error: CHAT_RECOVERY_EXHAUSTED_MESSAGE,
        });
      };
      const scheduleRecovery = (attempt: number) => {
        if (!isCurrent()) return;
        const remainingBeforeDelay = task.deadlineAt - Date.now();
        if (attempt >= maxRecoveryAttemptsRef.current || remainingBeforeDelay <= 0) {
          exhaust();
          return;
        }
        const configuredDelay = recoveryBaseDelayRef.current * (2 ** attempt);
        const delay = Math.min(configuredDelay, remainingBeforeDelay);
        const recoverAfterBackoff = () => {
          task.timer = null;
          if (!isCurrent()) return;
          const remainingMs = task.deadlineAt - Date.now();
          if (remainingMs <= 0) {
            exhaust();
            return;
          }
          const recover = recoverRef.current;
          if (!recover) {
            exhaust();
            return;
          }
          const controller = new AbortController();
          task.controller = controller;
          const attemptsRemaining = Math.max(1, maxRecoveryAttemptsRef.current - attempt);
          const attemptBudgetMs = Math.max(1, Math.floor(remainingMs / attemptsRemaining));
          let attemptTimer: ReturnType<typeof setTimeout> | null = null;
          const timedOut = new Promise<never>((_resolve, reject) => {
            attemptTimer = setTimeout(() => {
              controller.abort();
              reject(new Error("Recovery attempt deadline exceeded"));
            }, attemptBudgetMs);
            task.attemptTimer = attemptTimer;
          });
          let recovered: Promise<ChatRun>;
          try {
            recovered = recover(task.key, task.runId, {
              signal: controller.signal,
              deadlineAt: task.deadlineAt,
              remainingMs,
            });
          } catch (error) {
            recovered = Promise.reject(error);
          }
          void Promise.race([recovered, timedOut]).then((nextRun) => {
            if (!isCurrent() || nextRun.id !== task.runId) return;
            if (TERMINAL_STATES.has(nextRun.state)) {
              const terminalEvent = terminalEventFromRun(nextRun);
              cancelRecovery(task.key);
              let terminalKey = task.key;
              const next = dispatchRef.current({
                type: "RUN_EVENT",
                key: task.key,
                runId: task.runId,
                streamEpoch: task.streamEpoch,
                run: nextRun,
              });
              if (next.entries[task.key]?.run?.id === task.runId) {
                const canonicalUrl = nextRun.canonical_url;
                if (canonicalUrl) {
                  const canonicalKey = conversationKeyFromUrl(canonicalUrl);
                  const rekeyed = dispatchRef.current({
                    type: "REKEY_CANONICAL",
                    key: task.key,
                    canonicalKey,
                    canonicalUrl,
                  });
                  if (!rekeyed.entries[task.key] && rekeyed.entries[canonicalKey]) terminalKey = canonicalKey;
                }
                terminalRef.current?.({ key: terminalKey, runId: task.runId, event: terminalEvent });
              }
              return;
            }
            cancelRecovery(task.key);
            subscribeRef.current(task.key, nextRun, {
              accepted: false,
              recoveryAttempt: attempt + 1,
              recoveryDeadlineAt: task.deadlineAt,
            });
          }).catch(() => {
            if (!isCurrent()) return;
            scheduleRecovery(attempt + 1);
          }).finally(() => {
            if (attemptTimer) clearTimeout(attemptTimer);
            if (task.attemptTimer === attemptTimer) task.attemptTimer = null;
            if (task.controller === controller) task.controller = null;
          });
        };
        if (delay <= 0) recoverAfterBackoff();
        else {
          task.timer = setTimeout(recoverAfterBackoff, delay);
        }
      };
      scheduleRecovery(binding.recoveryAttempt);
    };
    return streamEpoch;
  }, [cancelRecovery, closeBinding]);
  subscribeRef.current = subscribe;

  useEffect(() => {
    const streams = streamsRef.current;
    const recoveries = recoveriesRef.current;
    disposedRef.current = false;
    return () => {
      disposedRef.current = true;
      for (const binding of streams.values()) closeBinding(binding);
      streams.clear();
      for (const key of recoveries.keys()) cancelRecovery(key);
    };
  }, [cancelRecovery, closeBinding]);

  return { subscribe, close };
}
