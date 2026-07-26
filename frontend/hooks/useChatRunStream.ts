"use client";

import { useCallback, useEffect, useRef } from "react";
import { apiUrl } from "@/lib/api";
import { conversationKeyFromUrl } from "@/lib/conversation-state";
import type { ChatRun, ChatRunEvent, ConversationKey } from "@/lib/types";
import type { ConversationDispatch } from "./useConversationController";

export const CHAT_RECOVERY_DEADLINE_MS = 10_000;
export const CHAT_CANCEL_DEADLINE_MS = 10_000;
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

interface CancelTask {
  key: ConversationKey;
  runId: string;
  streamEpoch: number;
  deadlineAt: number;
  controller: AbortController;
  timer: ReturnType<typeof setTimeout> | null;
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
  onCancelFailure?: (key: ConversationKey, runId: string, error: unknown) => void;
  recoverRun?: (
    key: ConversationKey,
    runId: string,
    context: ChatRunRecoveryContext,
  ) => Promise<ChatRun>;
  cancelRun?: (
    key: ConversationKey,
    runId: string,
    context: ChatRunRecoveryContext,
  ) => Promise<unknown>;
  recoveryBaseDelayMs?: number;
  maxRecoveryAttempts?: number;
  recoveryDeadlineMs?: number;
  cancelDeadlineMs?: number;
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
  cancel(key: ConversationKey, runId: string, streamEpoch: number): boolean;
  retry(key: ConversationKey, runId: string, streamEpoch: number): boolean;
  rekey(
    fromKey: ConversationKey,
    toKey: ConversationKey,
    choice: "source" | "target",
    streamEpoch: number,
  ): boolean;
}

const TERMINAL_EVENTS = new Set<ChatRunEvent["type"]>(["complete", "error", "cancelled"]);
const TERMINAL_STATES = new Set<ChatRun["state"]>([
  "COMPLETED",
  "FAILED",
  "CANCELLED",
  "DELIVERY_UNCERTAIN",
]);
const API_RUN_STATES = new Set<ChatRun["state"]>([
  "QUEUED",
  "SELECTING_CONVERSATION",
  "SENDING_TO_CHATGPT",
  "VISIBLE_IN_CHATGPT",
  "WAITING_FOR_CHATGPT",
  "CHATGPT_STREAMING",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isChatGptUrl(value: unknown, canonical = false): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || !["chatgpt.com", "www.chatgpt.com"].includes(url.hostname)) {
      return false;
    }
    if (canonical) return /^\/c\/[^/?#]+\/?$/.test(url.pathname);
    return url.pathname === "/" || /^\/c\/[^/?#]+\/?$/.test(url.pathname);
  } catch {
    return false;
  }
}

function isOptionalString(value: unknown): boolean {
  return value === undefined || value === null || typeof value === "string";
}

function isValidLatency(value: unknown): boolean {
  if (value === undefined || value === null) return true;
  if (!isRecord(value)) return false;
  return ["delivery_ms", "first_response_ms", "total_ms"].every((field) => {
    const measurement = value[field];
    return measurement === undefined
      || measurement === null
      || (typeof measurement === "number" && Number.isFinite(measurement) && measurement >= 0);
  });
}

export function validatedChatRun(value: unknown, expectedRunId: string): ChatRun | null {
  if (!isRecord(value)) return null;
  if (value.id !== expectedRunId || typeof value.id !== "string") return null;
  if (typeof value.state !== "string" || !API_RUN_STATES.has(value.state as ChatRun["state"])) return null;
  if (!isChatGptUrl(value.conversation_url)) return null;
  if (typeof value.text !== "string" || typeof value.created_at !== "string") return null;
  if (value.canonical_url !== undefined
    && value.canonical_url !== null
    && !isChatGptUrl(value.canonical_url, true)) return null;
  if (!["response_text", "delivered_at", "first_response_at", "completed_at", "error"]
    .every((field) => isOptionalString(value[field]))) return null;
  if (!isValidLatency(value.latency)) return null;
  return {
    ...(value as unknown as ChatRun),
    canonical_url: typeof value.canonical_url === "string" ? value.canonical_url : undefined,
  };
}

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
  onCancelFailure,
  recoverRun,
  cancelRun,
  recoveryBaseDelayMs = 250,
  maxRecoveryAttempts = 3,
  recoveryDeadlineMs = CHAT_RECOVERY_DEADLINE_MS,
  cancelDeadlineMs = CHAT_CANCEL_DEADLINE_MS,
}: UseChatRunStreamOptions): ChatRunStreamController {
  const dispatchRef = useRef(dispatch);
  const factoryRef = useRef(createEventSource);
  const terminalRef = useRef(onTerminal);
  const disconnectRef = useRef(onDisconnect);
  const cancelFailureRef = useRef(onCancelFailure);
  const recoverRef = useRef(recoverRun);
  const cancelRunRef = useRef(cancelRun);
  const recoveryBaseDelayRef = useRef(recoveryBaseDelayMs);
  const maxRecoveryAttemptsRef = useRef(maxRecoveryAttempts);
  const recoveryDeadlineRef = useRef(recoveryDeadlineMs);
  const cancelDeadlineRef = useRef(cancelDeadlineMs);
  dispatchRef.current = dispatch;
  factoryRef.current = createEventSource;
  terminalRef.current = onTerminal;
  disconnectRef.current = onDisconnect;
  cancelFailureRef.current = onCancelFailure;
  recoverRef.current = recoverRun;
  cancelRunRef.current = cancelRun;
  recoveryBaseDelayRef.current = recoveryBaseDelayMs;
  maxRecoveryAttemptsRef.current = maxRecoveryAttempts;
  recoveryDeadlineRef.current = recoveryDeadlineMs;
  cancelDeadlineRef.current = cancelDeadlineMs;

  const streamsRef = useRef(new Map<ConversationKey, StreamBinding>());
  const epochsRef = useRef(new Map<ConversationKey, number>());
  const recoveriesRef = useRef(new Map<ConversationKey, RecoveryTask>());
  const cancellationsRef = useRef(new Map<ConversationKey, CancelTask>());
  const disposedRef = useRef(false);
  const subscribeRef = useRef<ChatRunStreamController["subscribe"]>(() => 0);

  const closeBinding = useCallback((binding: StreamBinding) => {
    if (binding.closed) return;
    binding.closed = true;
    binding.source.close();
    if (streamsRef.current.get(binding.key) === binding) streamsRef.current.delete(binding.key);
  }, []);

  const finishRecovery = useCallback((task: RecoveryTask, abort = true) => {
    if (recoveriesRef.current.get(task.key) !== task) return;
    task.cancelled = true;
    if (task.timer) clearTimeout(task.timer);
    if (task.attemptTimer) clearTimeout(task.attemptTimer);
    if (abort) task.controller?.abort();
    recoveriesRef.current.delete(task.key);
    if (!disposedRef.current) {
      dispatchRef.current({
        type: "RUN_OPERATION_PENDING",
        operation: "recovery",
        pending: false,
        key: task.key,
        runId: task.runId,
        streamEpoch: task.streamEpoch,
      });
    }
  }, []);

  const cancelRecovery = useCallback((key: ConversationKey) => {
    const task = recoveriesRef.current.get(key);
    if (task) finishRecovery(task);
  }, [finishRecovery]);

  const finishCancellation = useCallback((task: CancelTask, abort = true) => {
    if (cancellationsRef.current.get(task.key) !== task) return;
    if (task.timer) clearTimeout(task.timer);
    if (abort) task.controller.abort();
    cancellationsRef.current.delete(task.key);
    if (!disposedRef.current) {
      dispatchRef.current({
        type: "RUN_OPERATION_PENDING",
        operation: "cancel",
        pending: false,
        key: task.key,
        runId: task.runId,
        streamEpoch: task.streamEpoch,
      });
    }
  }, []);

  const cancelCancellation = useCallback((key: ConversationKey) => {
    const task = cancellationsRef.current.get(key);
    if (task) finishCancellation(task);
  }, [finishCancellation]);

  const startRecovery = useCallback((
    key: ConversationKey,
    runId: string,
    streamEpoch: number,
    initialAttempt = 0,
    deadlineAt = Date.now() + recoveryDeadlineRef.current,
    immediate = false,
  ): boolean => {
    if (
      disposedRef.current
      || !recoverRef.current
      || recoveriesRef.current.has(key)
      || epochsRef.current.get(key) !== streamEpoch
      || streamsRef.current.has(key)
    ) return false;
    const task: RecoveryTask = {
      key,
      runId,
      streamEpoch,
      deadlineAt,
      cancelled: false,
      timer: null,
      attemptTimer: null,
      controller: null,
    };
    recoveriesRef.current.set(key, task);
    dispatchRef.current({
      type: "RUN_OPERATION_PENDING",
      operation: "recovery",
      pending: true,
      key,
      runId,
      streamEpoch,
    });

    const isCurrent = () => (
      !disposedRef.current
      && !task.cancelled
      && recoveriesRef.current.get(task.key) === task
      && epochsRef.current.get(task.key) === task.streamEpoch
      && !streamsRef.current.has(task.key)
    );
    const exhaust = () => {
      if (!isCurrent()) return;
      finishRecovery(task);
      dispatchRef.current({
        type: "RUN_RECOVERY_EXHAUSTED",
        key: task.key,
        runId: task.runId,
        streamEpoch: task.streamEpoch,
        error: CHAT_RECOVERY_EXHAUSTED_MESSAGE,
      });
    };
    const schedule = (attempt: number, skipDelay = false) => {
      if (!isCurrent()) return;
      const remainingBeforeDelay = task.deadlineAt - Date.now();
      if (attempt >= maxRecoveryAttemptsRef.current || remainingBeforeDelay <= 0) {
        exhaust();
        return;
      }
      const configuredDelay = skipDelay ? 0 : recoveryBaseDelayRef.current * (2 ** attempt);
      const delay = Math.min(configuredDelay, remainingBeforeDelay);
      const recoverAfterBackoff = () => {
        task.timer = null;
        if (!isCurrent()) return;
        const remainingMs = task.deadlineAt - Date.now();
        const recover = recoverRef.current;
        if (remainingMs <= 0 || !recover) {
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
        void Promise.race([recovered, timedOut]).then((payload) => {
          if (!isCurrent()) return;
          const nextRun = validatedChatRun(payload, task.runId);
          if (!nextRun) {
            schedule(attempt + 1);
            return;
          }
          if (TERMINAL_STATES.has(nextRun.state)) {
            const terminalEvent = terminalEventFromRun(nextRun);
            finishRecovery(task);
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
          finishRecovery(task);
          subscribeRef.current(task.key, nextRun, {
            accepted: false,
            recoveryAttempt: attempt + 1,
            recoveryDeadlineAt: task.deadlineAt,
          });
        }).catch(() => {
          if (isCurrent()) schedule(attempt + 1);
        }).finally(() => {
          if (attemptTimer) clearTimeout(attemptTimer);
          if (task.attemptTimer === attemptTimer) task.attemptTimer = null;
          if (task.controller === controller) task.controller = null;
        });
      };
      if (delay <= 0) recoverAfterBackoff();
      else task.timer = setTimeout(recoverAfterBackoff, delay);
    };
    schedule(initialAttempt, immediate);
    return true;
  }, [finishRecovery]);

  const close = useCallback((key: ConversationKey) => {
    cancelRecovery(key);
    cancelCancellation(key);
    epochsRef.current.set(key, (epochsRef.current.get(key) || 0) + 1);
    const binding = streamsRef.current.get(key);
    if (binding) closeBinding(binding);
  }, [cancelCancellation, cancelRecovery, closeBinding]);

  const rekey = useCallback((
    fromKey: ConversationKey,
    toKey: ConversationKey,
    choice: "source" | "target",
    streamEpoch: number,
  ): boolean => {
    if (disposedRef.current || !Number.isInteger(streamEpoch) || streamEpoch < 0) return false;
    if (fromKey === toKey) {
      epochsRef.current.set(toKey, streamEpoch);
      return true;
    }
    const sourceBinding = streamsRef.current.get(fromKey);
    const targetBinding = streamsRef.current.get(toKey);
    if (choice === "source" && targetBinding && targetBinding !== sourceBinding) return false;
    cancelRecovery(fromKey);
    cancelCancellation(fromKey);
    cancelRecovery(toKey);
    cancelCancellation(toKey);
    if (sourceBinding) {
      if (choice === "source") {
        streamsRef.current.delete(fromKey);
        sourceBinding.key = toKey;
        streamsRef.current.set(toKey, sourceBinding);
      } else {
        closeBinding(sourceBinding);
      }
    }
    epochsRef.current.delete(fromKey);
    epochsRef.current.set(toKey, streamEpoch);
    return true;
  }, [cancelCancellation, cancelRecovery, closeBinding]);

  const subscribe = useCallback((
    key: ConversationKey,
    run: ChatRun,
    options: ChatRunSubscribeOptions = {},
  ): number => {
    if (disposedRef.current) return 0;
    const previous = streamsRef.current.get(key);
    if ((previous && !previous.closed)
      || recoveriesRef.current.has(key)
      || cancellationsRef.current.has(key)) return 0;
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
    cancelCancellation(key);
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
      const nextState = dispatchRef.current({
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
            epochsRef.current.delete(previousKey);
            epochsRef.current.set(
              canonicalKey,
              Math.max(epochsRef.current.get(canonicalKey) || 0, binding.streamEpoch),
            );
          }
        }
      }

      if ((nextState.entries[previousKey] || nextState.entries[binding.key]) && TERMINAL_EVENTS.has(event.type)) {
        const terminalKey = binding.key;
        cancelCancellation(terminalKey);
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
      const cancellation = cancellationsRef.current.get(disconnectedKey);
      if (cancellation?.runId === binding.runId
        && cancellation.streamEpoch === disconnectedEpoch) return;
      startRecovery(
        disconnectedKey,
        binding.runId,
        disconnectedEpoch,
        binding.recoveryAttempt,
        binding.recoveryDeadlineAt ?? (Date.now() + recoveryDeadlineRef.current),
      );
    };
    return streamEpoch;
  }, [cancelCancellation, cancelRecovery, closeBinding, startRecovery]);
  subscribeRef.current = subscribe;

  const cancel = useCallback((
    key: ConversationKey,
    runId: string,
    streamEpoch: number,
  ): boolean => {
    if (disposedRef.current || !cancelRunRef.current || cancellationsRef.current.has(key)) return false;
    cancelRecovery(key);
    const controller = new AbortController();
    const deadlineAt = Date.now() + cancelDeadlineRef.current;
    const task: CancelTask = { key, runId, streamEpoch, deadlineAt, controller, timer: null };
    cancellationsRef.current.set(key, task);
    dispatchRef.current({
      type: "RUN_OPERATION_PENDING",
      operation: "cancel",
      pending: true,
      key,
      runId,
      streamEpoch,
    });
    const cancelRequest = cancelRunRef.current;
    const fail = (error: unknown) => {
      if (disposedRef.current || cancellationsRef.current.get(key) !== task) return;
      finishCancellation(task);
      cancelFailureRef.current?.(key, runId, error);
      const binding = streamsRef.current.get(key);
      if (!binding || binding.runId !== runId || binding.streamEpoch !== streamEpoch) {
        if (!startRecovery(key, runId, streamEpoch, 0, Date.now() + recoveryDeadlineRef.current, true)) {
          dispatchRef.current({
            type: "RUN_RECOVERY_EXHAUSTED",
            key,
            runId,
            streamEpoch,
            error: "Annulation incertaine : impossible de confirmer l'état de la réponse.",
          });
        }
      }
    };
    task.timer = setTimeout(() => {
      controller.abort();
      fail(new Error("Le délai d'annulation de 10 secondes a expiré."));
    }, cancelDeadlineRef.current);
    let request: Promise<unknown>;
    try {
      request = cancelRequest(key, runId, {
        signal: controller.signal,
        deadlineAt,
        remainingMs: cancelDeadlineRef.current,
      });
    } catch (error) {
      request = Promise.reject(error);
    }
    void request.then((payload) => {
      if (disposedRef.current || cancellationsRef.current.get(key) !== task) return;
      const terminalRun = validatedChatRun(payload, runId);
      if (!terminalRun || !["COMPLETED", "FAILED", "CANCELLED"].includes(terminalRun.state)) {
        fail(new Error("Réponse d'annulation invalide : état terminal non confirmé."));
        return;
      }
      finishCancellation(task);
      cancelRecovery(key);
      let terminalKey = key;
      let next = dispatchRef.current({
        type: "RUN_EVENT",
        key,
        runId,
        streamEpoch,
        run: terminalRun,
      });
      const canonicalUrl = terminalRun.canonical_url;
      if (canonicalUrl && next.entries[key]?.run?.id === runId) {
        const canonicalKey = conversationKeyFromUrl(canonicalUrl);
        const rekeyed = dispatchRef.current({
          type: "REKEY_CANONICAL",
          key,
          canonicalKey,
          canonicalUrl,
        });
        if (!rekeyed.entries[key] && rekeyed.entries[canonicalKey]) {
          rekey(key, canonicalKey, "source", streamEpoch);
          terminalKey = canonicalKey;
          next = rekeyed;
        }
      }
      const binding = streamsRef.current.get(terminalKey) || streamsRef.current.get(key);
      if (next.entries[terminalKey]?.run?.id === runId
        && binding?.runId === runId
        && binding.streamEpoch === streamEpoch) {
        closeBinding(binding);
      }
      if (next.entries[terminalKey]?.run?.id === runId) {
        terminalRef.current?.({
          key: terminalKey,
          runId,
          event: terminalEventFromRun(terminalRun),
        });
      }
    }).catch(fail).finally(() => {
      if (task.timer) clearTimeout(task.timer);
      task.timer = null;
    });
    return true;
  }, [cancelRecovery, closeBinding, finishCancellation, rekey, startRecovery]);

  const retry = useCallback((
    key: ConversationKey,
    runId: string,
    streamEpoch: number,
  ): boolean => startRecovery(
    key,
    runId,
    streamEpoch,
    0,
    Date.now() + recoveryDeadlineRef.current,
    true,
  ), [startRecovery]);

  useEffect(() => {
    const streams = streamsRef.current;
    const recoveries = recoveriesRef.current;
    const cancellations = cancellationsRef.current;
    disposedRef.current = false;
    return () => {
      disposedRef.current = true;
      for (const binding of streams.values()) closeBinding(binding);
      streams.clear();
      for (const task of recoveries.values()) {
        task.cancelled = true;
        if (task.timer) clearTimeout(task.timer);
        if (task.attemptTimer) clearTimeout(task.attemptTimer);
        task.controller?.abort();
      }
      recoveries.clear();
      for (const task of cancellations.values()) {
        if (task.timer) clearTimeout(task.timer);
        task.controller.abort();
      }
      cancellations.clear();
    };
  }, [closeBinding]);

  return { subscribe, close, cancel, retry, rekey };
}
