"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, postJson, putJson } from "@/lib/api";
import {
  demoConversations,
  demoMessages,
  demoMissionDetail,
  demoPipeline,
  demoRuntime,
  demoSettings,
  demoTransport,
} from "@/lib/demo";
import type {
  ChatGPTModelInfo,
  ChromeConnectionResult,
  ChromeExtensionPairing,
  ChromeExtensionStatus,
  ChatRun,
  ConversationKey,
  ConversationSnapshot,
  ConversationSummary,
  CortexSettings,
  ExecutionPreflight,
  HealthState,
  MissionDetail,
  OllamaModelInfo,
  PipelineStatus,
  RuntimeStatus,
  TransportStatus,
  TransportProbeStatus,
} from "@/lib/types";
import { useInterval } from "@/hooks/useInterval";
import { useChatRunStream } from "@/hooks/useChatRunStream";
import { useConversationController } from "@/hooks/useConversationController";
import { canResolveRekeyConflict } from "@/lib/conversation-state";
import {
  createRequestEpoch,
  createUnavailableClientState,
  transportHealthFromProbe,
} from "@/lib/runtimeTruth";
import { ConversationSidebar } from "./ConversationSidebar";
import { ChatWorkspace, type WorkspaceAvailability } from "./ChatWorkspace";
import { PipelineInspector } from "./PipelineInspector";
import { SettingsPanel } from "./SettingsPanel";
import { HistoryPanel } from "./HistoryPanel";
import { OnboardingPanel } from "./OnboardingPanel";
import { ChatGPTConnectionDialog } from "./ChatGPTConnectionDialog";

const DEVELOPMENT_FIXTURES_ENABLED =
  process.env.NEXT_PUBLIC_CORTEX_DEVELOPMENT_FIXTURES === "1";
const INITIAL_UNAVAILABLE_STATE = createUnavailableClientState(
  new Date(0).toISOString(),
);
const INITIAL_POST_DEADLINE_MS = 10_000;
const INITIAL_POST_TIMEOUT_MESSAGE =
  "Envoi incertain : le délai de 10 secondes a expiré. Le brouillon et la pièce jointe sont conservés.";
const PAIR_AFTER_EXTENSION_RELOAD_KEY = "cortex:pair-after-extension-reload";
const INITIAL_CHROME_CONNECTION: ChromeConnectionResult = {
  code: "CHECKING_CONNECTION",
  state: "checking",
  title: "Vérification de la connexion…",
  message: "Cortex cherche l’extension puis vérifie l’onglet ChatGPT dans cette fenêtre Chrome.",
  recoverable: false,
  driver: "chrome_extension",
  url: null,
  tab_id: null,
  window_id: null,
};

interface InitialRequestTask {
  token: symbol;
  controller: AbortController;
  timer: ReturnType<typeof setTimeout>;
  rejectInterrupted: (error: Error) => void;
}

class InitialRequestInterruptedError extends Error {}

function normalizeConversation(raw: Partial<ConversationSummary> & { url: string }): ConversationSummary {
  const identity = raw.identity || raw.url.match(/\/c\/([^/?#]+)/)?.[1] || raw.url;
  return {
    url: raw.url,
    identity,
    title: raw.title?.replace(/\s*[-–—]\s*ChatGPT\s*$/i, "").trim() || "Conversation sans titre",
    preview: raw.preview || "Ouvrir la conversation ChatGPT",
    timestamp: raw.timestamp || "",
    unread: raw.unread || 0,
    pinned: !!raw.pinned,
    project: !!raw.project,
    project_id: raw.project_id || null,
    project_title: raw.project_title || null,
    archived: !!raw.archived,
    message_count: typeof raw.message_count === "number" ? raw.message_count : null,
    status: raw.status || "idle",
    sync_state: raw.sync_state || "live",
    sync_error: raw.sync_error || null,
  };
}

function nonTerminal(state?: string) {
  return !!state && !["COMPLETED", "BLOCKED", "FAILED", "CANCELLED"].includes(state);
}

export function projectPipelineForConversation(
  pipeline: PipelineStatus,
  mission: MissionDetail | null,
): PipelineStatus {
  if (mission && pipeline.active_mission_id === mission.mission.id) {
    return {
      ...pipeline,
      active_mission_id: mission.mission.id,
      active_mission_state: mission.mission.state,
    };
  }
  return {
    ...pipeline,
    overall: "unknown",
    active_mission_id: null,
    active_mission_state: null,
    components: [],
    events: [],
    queue_pending: 0,
    runtime_execution: {
      ...pipeline.runtime_execution,
      task_id: null,
      state: "IDLE",
      active: false,
      observed_at: null,
      executor_kind: "unavailable",
      executor_model_used: null,
      runtime_mode: "live",
      release_eligible: false,
    },
    latency: {
      transport_ms: null,
      local_model_ms: null,
      total_iteration_ms: null,
    },
  };
}

export function CortexApp() {
  const {
    state: conversationState,
    selectedEntry,
    dispatch: dispatchConversation,
    replaceSummaries,
    selectConversation,
    reloadSelected,
    newConversation,
  } = useConversationController({
    fetchSnapshot: async (requested, signal) => {
      if (DEVELOPMENT_FIXTURES_ENABLED && requested.identity.startsWith("demo-")) {
        return {
          url: requested.url,
          conversation_id: requested.identity,
          title: requested.title,
          blocker: null,
          composer_present: true,
          send_button_present: true,
          stop_button_present: false,
          streaming: false,
          model_label: demoSettings.planner_model,
          messages: demoMessages,
        } satisfies ConversationSnapshot;
      }
      return api<ConversationSnapshot>(
        `/api/conversations/snapshot?url=${encodeURIComponent(requested.url)}`,
        { signal },
      );
    },
    fetchBackgroundSnapshot: async (requested, entry, signal) => {
      if (DEVELOPMENT_FIXTURES_ENABLED && requested.identity.startsWith("demo-")) {
        return {
          url: requested.url,
          conversation_id: requested.identity,
          title: requested.title,
          blocker: null,
          composer_present: true,
          send_button_present: true,
          stop_button_present: false,
          streaming: false,
          model_label: demoSettings.planner_model,
          messages: demoMessages,
        } satisfies ConversationSnapshot;
      }
      const light = await api<{
        message_count: number;
        last_id: string | null;
        streaming: boolean;
      }>(
        `/api/conversations/snapshot?url=${encodeURIComponent(requested.url)}&light=1`,
        { signal },
      );
      const lastId = entry.messages.at(-1)?.id || null;
      if (
        entry.snapshot
        && light.message_count === entry.messages.length
        && light.last_id === lastId
        && light.streaming === entry.snapshot.streaming
      ) {
        return entry.snapshot;
      }
      return api<ConversationSnapshot>(
        `/api/conversations/snapshot?url=${encodeURIComponent(requested.url)}`,
        { signal },
      );
    },
  });
  const conversationStateRef = useRef(conversationState);
  conversationStateRef.current = conversationState;
  const conversations = conversationState.order
    .map((key) => conversationState.entries[key]?.summary)
    .filter((conversation): conversation is ConversationSummary => !!conversation);
  const selectedConversation = selectedEntry?.summary || null;
  const messages = selectedEntry?.messages || [];
  const loadingMessages = selectedEntry?.loadPhase === "loading";
  const chatRun = selectedEntry?.run || null;
  const selectedMissionId = selectedEntry?.missionId || null;
  const missionDetail = selectedEntry?.mission || null;
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [runtime, setRuntime] = useState<RuntimeStatus>(
    DEVELOPMENT_FIXTURES_ENABLED ? demoRuntime : INITIAL_UNAVAILABLE_STATE.runtime,
  );
  const [transport, setTransport] = useState<TransportStatus>(
    DEVELOPMENT_FIXTURES_ENABLED ? demoTransport : INITIAL_UNAVAILABLE_STATE.transport,
  );
  const [transportHealth, setTransportHealth] = useState<HealthState>("unknown");
  const [pipeline, setPipeline] = useState<PipelineStatus>(
    DEVELOPMENT_FIXTURES_ENABLED ? demoPipeline : INITIAL_UNAVAILABLE_STATE.pipeline,
  );
  const [settings, setSettings] = useState<CortexSettings>(
    DEVELOPMENT_FIXTURES_ENABLED ? demoSettings : INITIAL_UNAVAILABLE_STATE.settings,
  );
  const [ollamaModels, setOllamaModels] = useState<OllamaModelInfo[]>([]);
  const [chatgptModels, setChatGPTModels] = useState<ChatGPTModelInfo[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [capabilities, setCapabilities] = useState<{ upload_file: boolean; take_screenshot: boolean }>({ upload_file: false, take_screenshot: false });
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [chatGPTConnection, setChatGPTConnection] = useState<ChromeConnectionResult | null>(null);
  const [connectionDialogOpen, setConnectionDialogOpen] = useState(false);
  const [connectionBusy, setConnectionBusy] = useState(false);
  const missionDetailRequestEpoch = useRef(createRequestEpoch());
  const pipelineRequestRef = useRef<{ controller: AbortController; key: ConversationKey } | null>(null);
  const terminalRefreshTimer = useRef<number | null>(null);
  const initialRequestsRef = useRef(new Map<ConversationKey, InitialRequestTask>());

  useEffect(() => {
    if (window.matchMedia?.("(max-width: 760px)").matches) setSidebarCollapsed(true);
  }, []);

  const activeMission = useMemo(() => {
    if (missionDetail && nonTerminal(missionDetail.mission.state)) return missionDetail;
    return null;
  }, [missionDetail]);
  const selectedPipeline = useMemo(
    () => projectPipelineForConversation(pipeline, missionDetail),
    [missionDetail, pipeline],
  );
  const workspaceAvailability = useMemo<WorkspaceAvailability>(() => {
    const transportComponent = pipeline.components.find((component) => component.id === "transport");
    const pipelineState = transportComponent?.state || pipeline.overall;
    return {
      chatState: chatGPTConnection
        ? chatGPTConnection.state === "connected"
          ? "connected"
          : chatGPTConnection.state === "manual_action"
            ? "manual_action"
            : chatGPTConnection.state === "checking"
              ? "waiting"
              : "disconnected"
        : pipelineState === "unknown" ? transportHealth : pipelineState,
      agentState: runtime.executor_available ? "available" : "unavailable",
      transportLatencyMs: transportComponent?.latency_ms ?? null,
    };
  }, [chatGPTConnection, pipeline, runtime.executor_available, transportHealth]);

  const notify = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast((current) => (current === message ? null : current)), 2600);
  }, []);

  const refreshRuntime = useCallback(async () => {
    try {
      const [runtimeData, transportData, probeData] = await Promise.all([
        api<RuntimeStatus>("/api/status"),
        api<TransportStatus>("/api/transport/status"),
        api<TransportProbeStatus>("/api/transport/probe").catch(() => null),
      ]);
      setRuntime(runtimeData);
      setTransport(transportData);
      setTransportHealth(transportHealthFromProbe(probeData));
      setDemoMode(false);
    } catch {
      if (DEVELOPMENT_FIXTURES_ENABLED) {
        setRuntime(demoRuntime);
        setTransport(demoTransport);
        setDemoMode(true);
      } else {
        const unavailable = createUnavailableClientState(new Date().toISOString());
        setRuntime(unavailable.runtime);
        setTransport(unavailable.transport);
        setTransportHealth("unknown");
        setDemoMode(false);
      }
    }
  }, []);

  const applyConnectionResult = useCallback((result: ChromeConnectionResult) => {
    setChatGPTConnection(result);
    if (result.code === "CONNECTED") {
      setConnectionDialogOpen(false);
      notify("ChatGPT connecté dans cette fenêtre Chrome.");
    } else {
      setConnectionDialogOpen(true);
    }
  }, [notify]);

  const waitForExtensionPairing = useCallback(async () => {
    const deadline = Date.now() + 2_000;
    while (Date.now() < deadline) {
      const status = await api<ChromeExtensionStatus>("/api/chrome-extension/status");
      if (status.paired) return true;
      await new Promise((resolve) => window.setTimeout(resolve, 120));
    }
    return false;
  }, []);

  const openChatGPTProfile = useCallback(async () => {
    setConnectionBusy(true);
    setChatGPTConnection(INITIAL_CHROME_CONNECTION);
    setConnectionDialogOpen(true);
    try {
      const pairing = await postJson<ChromeExtensionPairing>(
        "/api/chrome-extension/pairing",
        {},
      );
      window.postMessage(
        {
          source: "cortex-bridge-ui",
          type: "CORTEX_PAIR_EXTENSION",
          token: pairing.token,
        },
        window.location.origin,
      );
      await waitForExtensionPairing();
      const result = await postJson<ChromeConnectionResult>(
        "/api/chrome-extension/open",
        {},
      );
      applyConnectionResult(result);
      await refreshRuntime();
    } catch (error) {
      applyConnectionResult({
        ...INITIAL_CHROME_CONNECTION,
        code: "CONNECTION_FAILED",
        state: "disconnected",
        title: "Connexion Chrome impossible",
        message: error instanceof Error ? error.message : "Cortex ne peut pas joindre l’extension Chrome.",
        recoverable: true,
      });
    } finally {
      setConnectionBusy(false);
    }
  }, [applyConnectionResult, refreshRuntime, waitForExtensionPairing]);

  const retryChatGPTConnection = useCallback(async () => {
    if (chatGPTConnection?.code === "EXTENSION_OUTDATED") {
      window.sessionStorage.setItem(PAIR_AFTER_EXTENSION_RELOAD_KEY, "1");
      window.history.go(0);
      return;
    }
    if (["EXTENSION_MISSING", "EXTENSION_UNPAIRED", "CONNECTION_FAILED"].includes(chatGPTConnection?.code || "")) {
      await openChatGPTProfile();
      return;
    }
    setConnectionBusy(true);
    try {
      const result = await postJson<ChromeConnectionResult>(
        "/api/chrome-extension/retry",
        {},
      );
      applyConnectionResult(result);
      await refreshRuntime();
    } catch (error) {
      applyConnectionResult({
        ...INITIAL_CHROME_CONNECTION,
        code: "CONNECTION_FAILED",
        state: "disconnected",
        title: "Vérification Chrome impossible",
        message: error instanceof Error ? error.message : "La vérification de ChatGPT a échoué.",
        recoverable: true,
      });
    } finally {
      setConnectionBusy(false);
    }
  }, [applyConnectionResult, chatGPTConnection?.code, openChatGPTProfile, refreshRuntime]);

  useEffect(() => {
    if (window.sessionStorage.getItem(PAIR_AFTER_EXTENSION_RELOAD_KEY) !== "1") return;
    window.sessionStorage.removeItem(PAIR_AFTER_EXTENSION_RELOAD_KEY);
    void openChatGPTProfile();
  }, [openChatGPTProfile]);

  const refreshPipeline = useCallback(async () => {
    const key = conversationStateRef.current.selectedKey;
    const entry = key ? conversationStateRef.current.entries[key] : null;
    if (!key || !entry) return;
    pipelineRequestRef.current?.controller.abort();
    const controller = new AbortController();
    pipelineRequestRef.current = { controller, key };
    const params = new URLSearchParams({ conversation_identity: entry.summary.identity });
    if (entry.missionId) params.set("mission_id", entry.missionId);
    try {
      const data = await api<PipelineStatus>(`/api/pipeline/status?${params}`, { signal: controller.signal });
      if (controller.signal.aborted || conversationStateRef.current.selectedKey !== key) return;
      if (data.conversation_identity && data.conversation_identity !== entry.summary.identity) return;
      setPipeline(data);
    } catch {
      if (controller.signal.aborted || conversationStateRef.current.selectedKey !== key) return;
      setPipeline(
        DEVELOPMENT_FIXTURES_ENABLED
          ? demoPipeline
          : createUnavailableClientState(new Date().toISOString()).pipeline,
      );
    }
  }, []);

  const refreshConversations = useCallback(async () => {
    setLoadingConversations(true);
    try {
      const data = await api<ConversationSummary[]>("/api/conversations");
      const normalized = data.map(normalizeConversation).slice(0, 50);
      setDemoMode(false);
      replaceSummaries(normalized);
    } catch {
      if (DEVELOPMENT_FIXTURES_ENABLED) {
        replaceSummaries(demoConversations.map(normalizeConversation));
        setDemoMode(true);
      } else {
        dispatchConversation({
          type: "CONVERSATIONS_FAILED",
          error: "Synchronisation ChatGPT impossible",
        });
        setDemoMode(false);
      }
    } finally {
      setLoadingConversations(false);
    }
  }, [dispatchConversation, replaceSummaries]);

  const applyMissionDetail = useCallback((key: ConversationKey, missionId: string, data: MissionDetail) => {
    dispatchConversation({ type: "MISSION_EVENT", key, missionId, mission: data });
  }, [dispatchConversation]);

  const refreshMissionDetail = useCallback(async () => {
    const key = conversationState.selectedKey;
    if (!key || !selectedMissionId) {
      missionDetailRequestEpoch.current.invalidate();
      return;
    }
    const requestedMissionId = selectedMissionId;
    const identity = `${key}:${requestedMissionId}`;
    const ticket = missionDetailRequestEpoch.current.begin(identity);
    try {
      const data = await api<MissionDetail>(`/api/missions/${requestedMissionId}`);
      if (!missionDetailRequestEpoch.current.isCurrent(ticket, identity)) return;
      applyMissionDetail(key, requestedMissionId, data);
    } catch {
      if (!missionDetailRequestEpoch.current.isCurrent(ticket, identity)) return;
      if (DEVELOPMENT_FIXTURES_ENABLED && requestedMissionId === demoMissionDetail.mission.id) {
        applyMissionDetail(key, requestedMissionId, demoMissionDetail);
      }
    }
  }, [applyMissionDetail, conversationState.selectedKey, selectedMissionId]);

  const refreshSettings = useCallback(async () => {
    try {
      const [settingsData, ollamaData, chatgptData] = await Promise.all([
        api<CortexSettings>("/api/settings"),
        api<{ models: OllamaModelInfo[] }>("/api/models/ollama"),
        api<{ models: ChatGPTModelInfo[] }>("/api/models/chatgpt").catch(() => ({ models: [] })),
      ]);
      setSettings(settingsData);
      setOllamaModels(ollamaData.models);
      setChatGPTModels(chatgptData.models);
    } catch {
      if (DEVELOPMENT_FIXTURES_ENABLED) {
        setSettings(demoSettings);
        setOllamaModels([
          { name: "orchestra-executor", size: 5_300_000_000, loaded: true },
          { name: "orchestra-executor-fallback", size: 6_600_000_000, loaded: false },
        ]);
        setChatGPTModels([{ label: demoSettings.planner_model, selected: true, available: true }]);
      } else {
        const unavailable = createUnavailableClientState(new Date().toISOString());
        setSettings(unavailable.settings);
        setOllamaModels(unavailable.ollamaModels);
        setChatGPTModels(unavailable.chatgptModels);
      }
    }
  }, []);

  const refreshSelectedConversation = useCallback(() => {
    reloadSelected({ background: true });
  }, [reloadSelected]);

  const runInitialRequest = useCallback(async function runInitialRequest<T>(
    key: ConversationKey,
    operation: (signal: AbortSignal) => Promise<T>,
  ): Promise<T> {
    if (initialRequestsRef.current.has(key)) {
      throw new Error("Un envoi est déjà en cours pour cette conversation.");
    }
    const controller = new AbortController();
    const token = Symbol(key);
    let rejectInterrupted!: (error: Error) => void;
    const interrupted = new Promise<never>((_resolve, reject) => {
      rejectInterrupted = reject;
    });
    const timedOut = new Promise<never>((_resolve, reject) => {
      const task: InitialRequestTask = {
        token,
        controller,
        timer: setTimeout(() => {
          if (initialRequestsRef.current.get(key)?.token !== token) return;
          controller.abort();
          reject(new Error(INITIAL_POST_TIMEOUT_MESSAGE));
        }, INITIAL_POST_DEADLINE_MS),
        rejectInterrupted,
      };
      initialRequestsRef.current.set(key, task);
    });
    const task = initialRequestsRef.current.get(key)!;
    let request: Promise<T>;
    try {
      request = operation(controller.signal);
    } catch (error) {
      request = Promise.reject(error);
    }
    try {
      const result = await Promise.race([request, timedOut, interrupted]);
      if (initialRequestsRef.current.get(key) !== task || controller.signal.aborted) {
        throw new InitialRequestInterruptedError();
      }
      return result;
    } finally {
      clearTimeout(task.timer);
      if (initialRequestsRef.current.get(key) === task) initialRequestsRef.current.delete(key);
    }
  }, []);

  const chatStreams = useChatRunStream({
    dispatch: dispatchConversation,
    onTerminal: () => {
      if (terminalRefreshTimer.current) window.clearTimeout(terminalRefreshTimer.current);
      terminalRefreshTimer.current = window.setTimeout(() => {
        terminalRefreshTimer.current = null;
        void refreshConversations();
      }, 900);
    },
    recoverRun: (_key, runId, context) => api<ChatRun>(`/api/chat/runs/${runId}`, {
      signal: context.signal,
    }),
    cancelRun: (_key, runId, context) => postJson(`/api/chat/runs/${runId}/cancel`, {}, {
      signal: context.signal,
    }),
    onCancelFailure: (_key, _runId, error) => {
      if (error instanceof InitialRequestInterruptedError) return;
      notify(error instanceof Error ? error.message : "Impossible d'arrêter la réponse.");
    },
  });

  useEffect(() => {
    void Promise.all([
      refreshRuntime(),
      refreshConversations(),
      refreshSettings(),
      refreshPipeline(),
    ]);
    api<{ upload_file?: boolean; take_screenshot?: boolean }>("/api/transport/capabilities")
      .then((caps) => setCapabilities({ upload_file: !!caps.upload_file, take_screenshot: !!caps.take_screenshot }))
      .catch(() => undefined);
  }, [refreshConversations, refreshPipeline, refreshRuntime, refreshSettings]);

  useEffect(() => {
    if (chatGPTConnection?.code === "CONNECTED") {
      void refreshConversations();
    }
  }, [chatGPTConnection?.code, refreshConversations]);

  useEffect(() => () => {
    if (terminalRefreshTimer.current) window.clearTimeout(terminalRefreshTimer.current);
    terminalRefreshTimer.current = null;
    for (const [key, task] of initialRequestsRef.current) {
      initialRequestsRef.current.delete(key);
      clearTimeout(task.timer);
      task.controller.abort();
      task.rejectInterrupted(new InitialRequestInterruptedError());
    }
  }, []);

  useEffect(() => {
    void refreshMissionDetail();
  }, [refreshMissionDetail]);

  useEffect(() => {
    const modelLabel = selectedEntry?.snapshot?.model_label;
    if (!modelLabel) return;
    setSettings((current) => (
      current.planner_model === modelLabel ? current : { ...current, planner_model: modelLabel }
    ));
  }, [selectedEntry?.snapshot?.model_label]);

  useInterval(() => void refreshRuntime(), 5000);
  useInterval(() => void refreshPipeline(), 2500);
  useInterval(() => void refreshMissionDetail(), selectedMissionId ? 1600 : null);
  useInterval(() => refreshSelectedConversation(), selectedConversation ? 2200 : null);

  function requestFailed(key: ConversationKey, error: unknown, fallback: string) {
    const message = error instanceof Error ? error.message : fallback;
    dispatchConversation({
      type: "REQUEST_FAILED",
      request: "send",
      key,
      status: error instanceof ApiError ? error.status : undefined,
      error: message,
    });
    notify(message);
  }

  function conversationForKey(key: ConversationKey): ConversationSummary | null {
    return conversationState.entries[key]?.summary || null;
  }

  function isProvisional(key: ConversationKey, conversation: ConversationSummary): boolean {
    return key.startsWith("provisional:") || conversation.url.replace(/\/$/, "") === "https://chatgpt.com";
  }

  function beginExecution(key: ConversationKey): boolean {
    const current = conversationStateRef.current;
    const entry = current.entries[key];
    const runActive = !!entry?.run
      && !["COMPLETED", "FAILED", "CANCELLED", "DELIVERY_UNCERTAIN"].includes(entry.run.state);
    const missionActive = !!entry?.missionId
      && (!entry.mission || nonTerminal(entry.mission.mission.state));
    const conflicted = current.rekeyConflict?.fromKey === key;
    if (!entry || conflicted) {
      notify("L'identité de cette conversation doit être résolue avant tout nouvel envoi.");
      return false;
    }
    if (
      entry.sendPending
      || entry.cancelPending
      || entry.recoveryPending
      || runActive
      || missionActive
      || initialRequestsRef.current.has(key)
    ) {
      notify("Une réponse est déjà en cours pour cette conversation.");
      return false;
    }
    if (!chatStreams.close(key)) {
      notify("Une opération est encore en cours pour cette conversation.");
      return false;
    }
    dispatchConversation({ type: "REQUEST_STARTED", request: "send", key });
    return true;
  }

  async function sendChat(key: ConversationKey, text: string): Promise<boolean> {
    const conversation = conversationForKey(key);
    if (!conversation) return false;
    if (!transport.opt_in_accepted && !demoMode) {
      notify("Active d'abord le transport expérimental dans les paramètres.");
      setSettingsOpen(true);
      return false;
    }
    if (!beginExecution(key)) return false;
    try {
      const run = await runInitialRequest(key, (signal) => postJson<ChatRun>("/api/chat/send", {
          conversation_url: conversation.url,
          text,
          new_conversation: isProvisional(key, conversation),
        }, { signal }));
      chatStreams.subscribe(key, run, { submittedDraft: text, submittedAttachment: null });
      return true;
    } catch (error) {
      if (error instanceof InitialRequestInterruptedError) return false;
      requestFailed(key, error, "Impossible d'envoyer le message.");
      return false;
    }
  }

  async function sendAttachment(key: ConversationKey, text: string, file: File): Promise<boolean> {
    const conversation = conversationForKey(key);
    if (!conversation) return false;
    if (!transport.opt_in_accepted && !demoMode) {
      notify("Active d'abord le transport expérimental dans les paramètres.");
      setSettingsOpen(true);
      return false;
    }
    if (!beginExecution(key)) return false;
    try {
      const { descriptor, run } = await runInitialRequest(key, async (signal) => {
        const dataB64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(file);
        });
        if (signal.aborted) throw new InitialRequestInterruptedError();
        const descriptor = await postJson<{ path: string; name: string; kind: string }>("/api/chat/attachments", {
          name: file.name,
          data_b64: dataB64,
        }, { signal });
        if (signal.aborted) throw new InitialRequestInterruptedError();
        const run = await postJson<ChatRun>("/api/chat/send-with-attachment", {
          conversation_url: conversation.url,
          text,
          path: descriptor.path,
          name: descriptor.name,
          image: descriptor.kind === "image",
          new_conversation: isProvisional(key, conversation),
        }, { signal });
        return { descriptor, run };
      });
      chatStreams.subscribe(key, run, { submittedDraft: text, submittedAttachment: file });
      notify(`Pièce jointe prise en charge : ${descriptor.name}. Confirmation en cours.`);
      return true;
    } catch (error) {
      if (error instanceof InitialRequestInterruptedError) return false;
      requestFailed(key, error, "Impossible d'envoyer la pièce jointe.");
      return false;
    }
  }

  async function sendScreenshot(key: ConversationKey, text: string): Promise<boolean> {
    const conversation = conversationForKey(key);
    if (!conversation) return false;
    if (!transport.opt_in_accepted && !demoMode) {
      notify("Active d'abord le transport expérimental dans les paramètres.");
      setSettingsOpen(true);
      return false;
    }
    if (!beginExecution(key)) return false;
    try {
      const run = await runInitialRequest(key, (signal) => postJson<ChatRun>("/api/chat/send-screenshot", {
        conversation_url: conversation.url,
        text,
        new_conversation: isProvisional(key, conversation),
      }, { signal }));
      chatStreams.subscribe(key, run, { submittedDraft: text, submittedAttachment: null });
      notify("Capture prise en charge. Confirmation ChatGPT en cours.");
      return true;
    } catch (error) {
      if (error instanceof InitialRequestInterruptedError) return false;
      requestFailed(key, error, "Capture impossible.");
      return false;
    }
  }

  async function startMission(
    key: ConversationKey,
    text: string,
    preflight: ExecutionPreflight,
  ): Promise<boolean> {
    const conversation = conversationForKey(key);
    if (!conversation) return false;
    if (!beginExecution(key)) return false;
    try {
      const response = await runInitialRequest(key, (signal) => postJson<{ id: string; state: string }>("/api/missions", {
        objective: text,
        workspace: preflight.workspace,
        constraints: ["Ne jamais supprimer définitivement un fichier", "Rester dans les racines autorisées"],
        conversation_url: conversation.url,
        new_conversation: isProvisional(key, conversation),
        max_iterations: preflight.maxIterations,
        max_duration_minutes: preflight.maxDurationMinutes,
        approval_policy: preflight.approvalPolicy === "read-only"
          ? "read-only-automatic"
          : "workspace-write-with-approvals",
        allow_processes: preflight.capabilities.processes,
        allow_network: preflight.capabilities.network,
        allow_write: preflight.capabilities.write,
        attachment_tokens: preflight.attachmentTokens,
        executor_kind: preflight.executorKind,
      }, { signal }));
      missionDetailRequestEpoch.current.invalidate();
      dispatchConversation({
        type: "MISSION_EVENT",
        key,
        missionId: response.id,
        accepted: true,
      });
      void api<MissionDetail>(`/api/missions/${response.id}`).then((mission) => {
        applyMissionDetail(key, response.id, mission);
        void refreshPipeline();
      }).catch(() => undefined);
      notify("Mission autonome lancée.");
      return true;
    } catch (error) {
      if (error instanceof InitialRequestInterruptedError) return false;
      if (DEVELOPMENT_FIXTURES_ENABLED && demoMode) {
        missionDetailRequestEpoch.current.invalidate();
        dispatchConversation({
          type: "MISSION_EVENT",
          key,
          missionId: demoMissionDetail.mission.id,
          mission: demoMissionDetail,
          accepted: true,
        });
        notify("Aperçu local : mission simulée.");
        return true;
      } else {
        requestFailed(key, error, "Impossible de lancer la mission.");
        return false;
      }
    }
  }

  function cancelChat(key: ConversationKey) {
    const entry = conversationStateRef.current.entries[key];
    const run = entry?.run;
    if (!run) return;
    chatStreams.cancel(key, run.id, entry.streamEpoch);
  }

  function retryChatRecovery(key: ConversationKey) {
    const entry = conversationStateRef.current.entries[key];
    const runId = entry?.run?.id;
    if (!entry || !runId) return;
    if (!chatStreams.retry(key, runId, entry.streamEpoch)) {
      notify("Une synchronisation est déjà en cours pour cette conversation.");
    }
  }

  function resolveRekeyConflict(
    fromKey: ConversationKey,
    toKey: ConversationKey,
    choice: "source" | "target",
  ) {
    const next = dispatchConversation({
      type: "RESOLVE_REKEY_CONFLICT",
      fromKey,
      toKey,
      choice,
    });
    const target = next.entries[toKey];
    if (!next.entries[fromKey] && target) {
      chatStreams.rekey(fromKey, toKey, choice, target.streamEpoch);
    }
  }

  async function refreshMissionFor(key: ConversationKey, missionId: string) {
    const mission = await api<MissionDetail>(`/api/missions/${missionId}`);
    applyMissionDetail(key, missionId, mission);
  }

  async function missionAction(key: ConversationKey, action: "pause" | "resume" | "cancel") {
    const missionId = conversationState.entries[key]?.missionId;
    if (!missionId) return;
    try {
      await postJson(`/api/missions/${missionId}/${action}`, {});
      await refreshMissionFor(key, missionId);
    } catch (error) {
      notify(error instanceof Error ? error.message : `Impossible de ${action} la mission.`);
    }
  }

  async function approve(key: ConversationKey, scope: "once" | "tool" | "all-writes") {
    const missionId = conversationState.entries[key]?.missionId;
    if (!missionId) return;
    try {
      await postJson(`/api/missions/${missionId}/approve`, { scope, approve: true });
      notify("Action approuvée.");
      await refreshMissionFor(key, missionId);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Approbation impossible.");
    }
  }

  async function reject(key: ConversationKey) {
    const missionId = conversationState.entries[key]?.missionId;
    if (!missionId) return;
    try {
      await postJson(`/api/missions/${missionId}/approve`, { scope: "once", approve: false });
      notify("Action refusée et rapportée à ChatGPT.");
      await refreshMissionFor(key, missionId);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Refus impossible.");
    }
  }

  async function stopEverything() {
    try {
      await postJson("/api/transport/stop-everything", {});
      setTransport((current) => ({ ...current, global_stop: true }));
      notify("STOP EVERYTHING actif.");
      void refreshPipeline();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Arrêt global impossible.");
    }
  }

  async function resetStop() {
    try {
      await postJson("/api/transport/stop-reset", {});
      setTransport((current) => ({ ...current, global_stop: false }));
      notify("Pipeline réarmée.");
    } catch (error) {
      notify(error instanceof Error ? error.message : "Réarmement impossible.");
    }
  }

  async function saveSettings(next: CortexSettings) {
    setSettingsSaving(true);
    try {
      const saved = await putJson<CortexSettings>("/api/settings", next);
      setSettings(saved);
      setSettingsOpen(false);
      notify("Paramètres enregistrés.");
    } catch {
      if (DEVELOPMENT_FIXTURES_ENABLED) {
        setSettings(next);
        setSettingsOpen(false);
        notify("Paramètres appliqués à la fixture de développement.");
      } else {
        notify("Échec de l'enregistrement : paramètres inchangés.");
      }
    } finally {
      setSettingsSaving(false);
    }
  }

  async function selectChatGPTModel(label: string) {
    try {
      const response = await putJson<{ selected: string }>("/api/models/chatgpt", {
        conversation_url: selectedConversation?.url || "https://chatgpt.com/",
        label,
      });
      setSettings((current) => ({ ...current, planner_model: response.selected }));
      notify(`Modèle ChatGPT confirmé : ${response.selected}`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Le modèle ChatGPT n'a pas pu être confirmé.");
    }
  }

  return (
    <main
      aria-label="Conversation principale"
      className={`cortex-app theme-${settings.theme} ${inspectorOpen ? "inspector-visible" : ""}`}
    >
      <div className="app-grid-background" aria-hidden="true" />
      <div className="app-signal-sweep" aria-hidden="true" />
      <ConversationSidebar
        conversations={conversations}
        selectedKey={conversationState.selectedKey}
        loading={loadingConversations}
        collapsed={sidebarCollapsed}
        onCollapse={() => setSidebarCollapsed((value) => !value)}
        onSelect={(conversation) => {
          selectConversation(conversation, {
            force: selectedConversation?.identity === conversation.identity,
          });
        }}
        onRefresh={() => void refreshConversations()}
        onNewConversation={() => newConversation()}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenHistory={() => setHistoryOpen(true)}
      />

      <ChatWorkspace
        conversationKey={conversationState.selectedKey}
        conversation={selectedConversation}
        messages={messages}
        loadingMessages={loadingMessages}
        sending={selectedEntry?.sendPending || false}
        cancelPending={selectedEntry?.cancelPending || false}
        recoveryPending={selectedEntry?.recoveryPending || false}
        draft={selectedEntry?.draft || ""}
        attachment={selectedEntry?.attachment || null}
        chatRun={chatRun}
        mission={activeMission || missionDetail}
        pipeline={selectedPipeline}
        availability={workspaceAvailability}
        settings={settings}
        inspectorOpen={inspectorOpen}
        sidebarCollapsed={sidebarCollapsed}
        capabilities={capabilities}
        rekeyConflict={conversationState.rekeyConflict}
        rekeyResolutionAllowed={canResolveRekeyConflict(conversationState)}
        onDraftChange={(key, draft) => dispatchConversation({ type: "DRAFT_CHANGED", key, draft })}
        onAttachmentStaged={(key, attachment) => dispatchConversation({
          type: "ATTACHMENT_STAGED",
          key,
          attachment,
        })}
        onToggleSidebar={() => setSidebarCollapsed((value) => !value)}
        onToggleInspector={() => setInspectorOpen((value) => !value)}
        onOpenChatGPTProfile={() => void openChatGPTProfile()}
        chatGPTConnecting={connectionBusy}
        onSendChat={sendChat}
        onSendAttachment={sendAttachment}
        onSendScreenshot={sendScreenshot}
        onStartMission={startMission}
        onCancelChat={(key) => void cancelChat(key)}
        onRetryChatRecovery={(key) => void retryChatRecovery(key)}
        onReloadConversation={() => reloadSelected()}
        onResolveRekeyConflict={resolveRekeyConflict}
        onPauseMission={(key) => void missionAction(key, "pause")}
        onResumeMission={(key) => void missionAction(key, "resume")}
        onCancelMission={(key) => void missionAction(key, "cancel")}
        onApprove={(key, scope) => void approve(key, scope)}
        onReject={(key) => void reject(key)}
      />

      <PipelineInspector
        open={inspectorOpen}
        pipeline={selectedPipeline}
        runtime={runtime}
        transport={transport}
        mission={activeMission || missionDetail}
        onClose={() => setInspectorOpen(false)}
        onPause={() => {
          if (conversationState.selectedKey) void missionAction(conversationState.selectedKey, "pause");
        }}
        onResume={() => {
          if (conversationState.selectedKey) void missionAction(conversationState.selectedKey, "resume");
        }}
        onCancel={() => {
          if (conversationState.selectedKey) void missionAction(conversationState.selectedKey, "cancel");
        }}
        onStopAll={() => void stopEverything()}
        onResetStop={() => void resetStop()}
      />

      <SettingsPanel
        open={settingsOpen}
        settings={settings}
        ollamaModels={ollamaModels}
        chatgptModels={chatgptModels}
        runtimeExecution={pipeline.runtime_execution}
        saving={settingsSaving}
        onClose={() => setSettingsOpen(false)}
        onSave={saveSettings}
        onSelectChatGPTModel={selectChatGPTModel}
      />

      <HistoryPanel open={historyOpen} onClose={() => setHistoryOpen(false)} />

      {!settingsOpen && <OnboardingPanel onOpenSettings={() => setSettingsOpen(true)} />}

      {chatGPTConnection && (
        <ChatGPTConnectionDialog
          open={connectionDialogOpen}
          result={chatGPTConnection}
          busy={connectionBusy}
          onRetry={() => void retryChatGPTConnection()}
          onClose={() => setConnectionDialogOpen(false)}
        />
      )}

      {demoMode && <div className="demo-mode-badge">development_fixture · aucune preuve de release</div>}
      {toast && <output className="app-toast">{toast}</output>}
    </main>
  );
}
