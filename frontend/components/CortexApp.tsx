"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api, apiUrl, postJson, putJson } from "@/lib/api";
import {
  demoConversations,
  demoMessages,
  demoMissionDetail,
  demoMissions,
  demoPipeline,
  demoRuntime,
  demoSettings,
  demoTransport,
} from "@/lib/demo";
import type {
  ChatGPTModelInfo,
  ChatRun,
  ChatRunEvent,
  ConversationMessage,
  ConversationSnapshot,
  ConversationSummary,
  CortexSettings,
  MissionDetail,
  MissionSummary,
  OllamaModelInfo,
  PipelineStatus,
  RuntimeStatus,
  TransportStatus,
} from "@/lib/types";
import { useInterval } from "@/hooks/useInterval";
import {
  createConversationLoadController,
  createConversationSelectionCoordinator,
  createRequestEpoch,
  createUnavailableClientState,
  reduceConversationRefreshFailure,
  reduceMissionRefreshFailure,
  type ConversationRefreshState,
} from "@/lib/runtimeTruth";
import { ConversationSidebar } from "./ConversationSidebar";
import { ChatWorkspace } from "./ChatWorkspace";
import { PipelineInspector } from "./PipelineInspector";
import { SettingsPanel } from "./SettingsPanel";
import { OnboardingPanel } from "./OnboardingPanel";

const DEVELOPMENT_FIXTURES_ENABLED =
  process.env.NEXT_PUBLIC_CORTEX_DEVELOPMENT_FIXTURES === "1";
const INITIAL_UNAVAILABLE_STATE = createUnavailableClientState(
  new Date(0).toISOString(),
);

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

export function CortexApp() {
  const [conversationState, setConversationState] = useState<ConversationRefreshState>({
    conversations: [],
    selectedConversation: null,
    sync: { state: "unknown", error: null, updated_at: null },
  });
  const { conversations, selectedConversation } = conversationState;
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [runtime, setRuntime] = useState<RuntimeStatus>(
    DEVELOPMENT_FIXTURES_ENABLED ? demoRuntime : INITIAL_UNAVAILABLE_STATE.runtime,
  );
  const [transport, setTransport] = useState<TransportStatus>(
    DEVELOPMENT_FIXTURES_ENABLED ? demoTransport : INITIAL_UNAVAILABLE_STATE.transport,
  );
  const [pipeline, setPipeline] = useState<PipelineStatus>(
    DEVELOPMENT_FIXTURES_ENABLED ? demoPipeline : INITIAL_UNAVAILABLE_STATE.pipeline,
  );
  const [, setMissions] = useState<MissionSummary[]>([]);
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null);
  const [missionDetail, setMissionDetail] = useState<MissionDetail | null>(null);
  const [chatRun, setChatRun] = useState<ChatRun | null>(null);
  const [settings, setSettings] = useState<CortexSettings>(
    DEVELOPMENT_FIXTURES_ENABLED ? demoSettings : INITIAL_UNAVAILABLE_STATE.settings,
  );
  const [ollamaModels, setOllamaModels] = useState<OllamaModelInfo[]>([]);
  const [chatgptModels, setChatGPTModels] = useState<ChatGPTModelInfo[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [capabilities, setCapabilities] = useState<{ upload_file: boolean; take_screenshot: boolean }>({ upload_file: false, take_screenshot: false });
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [lastLightSig, setLastLightSig] = useState<string | null>(null);
  const [demoMode, setDemoMode] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const chatEventSource = useRef<EventSource | null>(null);
  const selectedConversationRef = useRef<ConversationSummary | null>(selectedConversation);
  const missionDetailRequestEpoch = useRef(createRequestEpoch());
  const conversationPollRequestEpoch = useRef(createRequestEpoch());
  const [conversationLoadController] = useState(() => createConversationLoadController({
    onStart(conversation) {
      setConversationState((current) => ({ ...current, selectedConversation: conversation }));
      setLoadingMessages(true);
      setMessages([]);
      setLastLightSig(null);
    },
    onSuccess(conversation, snapshot) {
      const count = snapshot.messages.length;
      setMessages(snapshot.messages);
      setConversationState((current) => ({
        conversations: current.conversations.map((item) => (
          item.url === conversation.url
            ? { ...item, message_count: count, sync_state: "live", sync_error: null }
            : item
        )),
        selectedConversation: current.selectedConversation?.url === conversation.url
          ? { ...current.selectedConversation, message_count: count, sync_state: "live", sync_error: null }
          : current.selectedConversation,
        sync: { state: "live", error: null, updated_at: new Date().toISOString() },
      }));
      if (snapshot.model_label) {
        setSettings((current) => ({ ...current, planner_model: snapshot.model_label || current.planner_model }));
      }
    },
    onFailure(conversation) {
      setConversationState((current) => reduceConversationRefreshFailure(
        current,
        "Chargement de la conversation impossible",
        conversation.url,
      ));
    },
    onFinish() {
      setLoadingMessages(false);
    },
  }));
  const [conversationSelectionCoordinator] = useState(() => (
    createConversationSelectionCoordinator(conversationLoadController)
  ));

  const activeMission = useMemo(() => {
    if (missionDetail && nonTerminal(missionDetail.mission.state)) return missionDetail;
    return null;
  }, [missionDetail]);

  const notify = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast((current) => (current === message ? null : current)), 2600);
  }, []);

  const refreshRuntime = useCallback(async () => {
    try {
      const [runtimeData, transportData] = await Promise.all([
        api<RuntimeStatus>("/api/status"),
        api<TransportStatus>("/api/transport/status"),
      ]);
      setRuntime(runtimeData);
      setTransport(transportData);
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
        setDemoMode(false);
      }
    }
  }, []);

  const refreshPipeline = useCallback(async () => {
    try {
      const data = await api<PipelineStatus>("/api/pipeline/status");
      setPipeline(data);
    } catch {
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
      // 50 most recent max (Jonas spec P1d); the backend already caps, this
      // is a second belt for demo/fallback data.
      const normalized = data.map(normalizeConversation).slice(0, 50);
      setDemoMode(false);
      setConversationState((current) => {
        let selected: ConversationSummary | null;
        const currentSelection = current.selectedConversation;
        if (currentSelection) {
          const stillThere = normalized.find((item) => item.url === currentSelection.url);
          if (stillThere) selected = stillThere;
          // Deletion sync: the conversation vanished from ChatGPT — drop it
          // from Cortex too, unless a chat run is actively writing into it.
          else {
            const runActive = chatRun && !["COMPLETED", "FAILED", "CANCELLED"].includes(chatRun.state);
            selected = currentSelection.identity === "__new__" || runActive
              ? { ...currentSelection, sync_state: "live", sync_error: null }
              : normalized[0] || null;
          }
        } else {
          selected = normalized[0] || null;
        }
        selectedConversationRef.current = selected;
        return {
          conversations: normalized,
          selectedConversation: selected,
          sync: { state: "live", error: null, updated_at: new Date().toISOString() },
        };
      });
    } catch {
      if (DEVELOPMENT_FIXTURES_ENABLED) {
        setConversationState((current) => {
          const selected = current.selectedConversation || normalizeConversation(demoConversations[0]);
          selectedConversationRef.current = selected;
          return {
            conversations: demoConversations.map(normalizeConversation),
            selectedConversation: selected,
            sync: { state: "live", error: null, updated_at: new Date().toISOString() },
          };
        });
        setDemoMode(true);
      } else {
        setConversationState((current) => reduceConversationRefreshFailure(
          current,
          "Synchronisation ChatGPT impossible",
        ));
        setDemoMode(false);
      }
    } finally {
      setLoadingConversations(false);
    }
  }, [chatRun]);

  const refreshMissions = useCallback(async () => {
    try {
      const data = await api<MissionSummary[]>("/api/missions");
      setMissions(data);
      const currentId = selectedMissionId || data.find((mission) => nonTerminal(mission.state))?.id || data[0]?.id || null;
      if (currentId && currentId !== selectedMissionId) {
        missionDetailRequestEpoch.current.invalidate();
        setSelectedMissionId(currentId);
      }
    } catch {
      if (DEVELOPMENT_FIXTURES_ENABLED) {
        setMissions(demoMissions);
        setSelectedMissionId((current) => {
          const selected = current || demoMissions[0].id;
          missionDetailRequestEpoch.current.invalidate();
          return selected;
        });
      } else {
        missionDetailRequestEpoch.current.invalidate();
        setMissions([]);
        setSelectedMissionId(null);
        setMissionDetail(null);
        setPipeline((current) => reduceMissionRefreshFailure({
          selectedMissionId: null,
          missionDetail: null,
          pipeline: current,
        }, new Date().toISOString()).pipeline);
      }
    }
  }, [selectedMissionId]);

  const refreshMissionDetail = useCallback(async () => {
    if (!selectedMissionId) {
      missionDetailRequestEpoch.current.invalidate();
      setMissionDetail(null);
      return;
    }
    const requestedMissionId = selectedMissionId;
    const ticket = missionDetailRequestEpoch.current.begin(requestedMissionId);
    try {
      const data = await api<MissionDetail>(`/api/missions/${requestedMissionId}`);
      if (!missionDetailRequestEpoch.current.isCurrent(ticket, requestedMissionId)) return;
      setMissionDetail(data);
    } catch {
      if (!missionDetailRequestEpoch.current.isCurrent(ticket, requestedMissionId)) return;
      if (DEVELOPMENT_FIXTURES_ENABLED && requestedMissionId === demoMissionDetail.mission.id) {
        setMissionDetail(demoMissionDetail);
      } else if (!DEVELOPMENT_FIXTURES_ENABLED) {
        missionDetailRequestEpoch.current.invalidate();
        setSelectedMissionId(null);
        setMissionDetail(null);
        setPipeline((current) => reduceMissionRefreshFailure({
          selectedMissionId: null,
          missionDetail: null,
          pipeline: current,
        }, new Date().toISOString()).pipeline);
      }
    }
  }, [selectedMissionId]);

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

  const loadConversation = useCallback((conversation: ConversationSummary) => {
    conversationPollRequestEpoch.current.invalidate();
    return conversationLoadController.load(conversation, async (requested) => {
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
        };
      }
      return api<ConversationSnapshot>(`/api/conversations/snapshot?url=${encodeURIComponent(requested.url)}`);
    });
  }, [conversationLoadController]);

  const refreshSelectedConversation = useCallback(async () => {
    if (!selectedConversation || selectedConversation.identity === "__new__" || selectedConversation.identity.startsWith("demo-")) {
      conversationPollRequestEpoch.current.invalidate();
      return;
    }
    const requestedUrl = selectedConversation.url;
    const ticket = conversationPollRequestEpoch.current.begin(requestedUrl);
    try {
      // P0c: cheap light poll first; only fetch the full snapshot (which
      // serializes every message) when the conversation actually changed.
      const light = await api<{ message_count: number; last_id: string | null; streaming: boolean }>(
        `/api/conversations/snapshot?url=${encodeURIComponent(requestedUrl)}&light=1`,
      );
      if (!conversationPollRequestEpoch.current.isCurrent(ticket, requestedUrl)) return;
      const sig = `${light.message_count}|${light.last_id}|${light.streaming}`;
      setConversationState((current) => ({
        conversations: current.conversations.map((item) => (
          item.url === requestedUrl
            ? { ...item, message_count: light.message_count, sync_state: "live", sync_error: null }
            : item
        )),
        selectedConversation: current.selectedConversation?.url === requestedUrl
          ? { ...current.selectedConversation, message_count: light.message_count, sync_state: "live", sync_error: null }
          : current.selectedConversation,
        sync: { state: "live", error: null, updated_at: new Date().toISOString() },
      }));
      if (sig === lastLightSig) return;
      setLastLightSig(sig);
      if (!chatRun || ["COMPLETED", "FAILED", "CANCELLED"].includes(chatRun.state)) {
        const snapshot = await api<ConversationSnapshot>(`/api/conversations/snapshot?url=${encodeURIComponent(requestedUrl)}`);
        if (!conversationPollRequestEpoch.current.isCurrent(ticket, requestedUrl)) return;
        setMessages(snapshot.messages || []);
      }
    } catch {
      if (!conversationPollRequestEpoch.current.isCurrent(ticket, requestedUrl)) return;
      setConversationState((current) => reduceConversationRefreshFailure(
        current,
        "Actualisation de la conversation impossible",
        requestedUrl,
      ));
    }
  }, [chatRun, lastLightSig, selectedConversation]);

  useEffect(() => {
    void Promise.all([
      refreshRuntime(),
      refreshConversations(),
      refreshMissions(),
      refreshSettings(),
      refreshPipeline(),
    ]);
    api<{ upload_file?: boolean; take_screenshot?: boolean }>("/api/transport/capabilities")
      .then((caps) => setCapabilities({ upload_file: !!caps.upload_file, take_screenshot: !!caps.take_screenshot }))
      .catch(() => undefined);
    return () => {
      conversationLoadController.invalidate();
      chatEventSource.current?.close();
    };
  }, [conversationLoadController, refreshConversations, refreshMissions, refreshPipeline, refreshRuntime, refreshSettings]);

  const selectedConversationIdentity = selectedConversation?.identity || null;
  useLayoutEffect(() => {
    const selected = selectedConversationRef.current;
    const loadable = selected && selected.identity !== "__new__" && selected.sync_state !== "stale"
      ? selected
      : null;
    conversationSelectionCoordinator.reconcile(loadable, {
      reset() {
        conversationPollRequestEpoch.current.invalidate();
        setMessages([]);
        setLoadingMessages(false);
        setLastLightSig(null);
      },
      load(conversation) {
        return loadConversation(conversation);
      },
    });
  }, [conversationSelectionCoordinator, loadConversation, selectedConversationIdentity]);

  useEffect(() => {
    void refreshMissionDetail();
  }, [refreshMissionDetail]);

  useInterval(() => void refreshRuntime(), 5000);
  useInterval(() => void refreshPipeline(), 2500);
  useInterval(() => void refreshMissions(), 3500);
  useInterval(() => void refreshMissionDetail(), selectedMissionId ? 1600 : null);
  useInterval(() => void refreshSelectedConversation(), selectedConversation ? 2200 : null);

  function subscribeRun(run: ChatRun) {
    setChatRun(run);
    chatEventSource.current?.close();
    const events = new EventSource(apiUrl(`/api/chat/runs/${run.id}/events`));
    chatEventSource.current = events;
    events.onmessage = (event) => {
      const payload = JSON.parse(event.data) as ChatRunEvent;
      setChatRun((current) => {
        if (!current || current.id !== run.id) return current;
        if (payload.type === "status") return { ...current, state: String(payload.payload.state) as ChatRun["state"] };
        if (payload.type === "delivery") return { ...current, state: "VISIBLE_IN_CHATGPT", delivered_at: String(payload.payload.delivered_at || new Date().toISOString()), canonical_url: String(payload.payload.canonical_url || current.canonical_url || current.conversation_url) };
        if (payload.type === "stream") return { ...current, state: "CHATGPT_STREAMING", response_text: String(payload.payload.text || ""), first_response_at: current.first_response_at || String(payload.payload.first_response_at || new Date().toISOString()) };
        if (payload.type === "complete") return { ...current, state: "COMPLETED", response_text: String(payload.payload.text || current.response_text || ""), completed_at: String(payload.payload.completed_at || new Date().toISOString()), latency: payload.payload.latency as ChatRun["latency"] };
        if (payload.type === "error") return { ...current, state: "FAILED", error: String(payload.payload.error || "Erreur transport") };
        if (payload.type === "cancelled") return { ...current, state: "CANCELLED" };
        return current;
      });
      if (payload.type === "complete" || payload.type === "error" || payload.type === "cancelled") {
        events.close();
        window.setTimeout(() => {
          void refreshConversations();
          void refreshSelectedConversation();
        }, 900);
      }
    };
    events.onerror = () => {
      events.close();
      void api<ChatRun>(`/api/chat/runs/${run.id}`).then(setChatRun).catch(() => undefined);
    };
  }

  async function sendChat(text: string): Promise<boolean> {
    const conversation = selectedConversation || {
      url: "https://chatgpt.com/",
      identity: "__new__",
      title: "Nouvelle conversation",
    };
    if (!transport.opt_in_accepted && !demoMode) {
      notify("Active d'abord le transport expérimental dans les paramètres.");
      setSettingsOpen(true);
      return false;
    }
    try {
      const run = await postJson<ChatRun>("/api/chat/send", {
        conversation_url: conversation.url,
        text,
        new_conversation: conversation.identity === "__new__" || conversation.url === "https://chatgpt.com/",
      });
      subscribeRun(run);
      return true;
    } catch (error) {
      notify(error instanceof Error ? error.message : "Impossible d'envoyer le message.");
      return false;
    }
  }

  async function sendAttachment(text: string, file: File): Promise<boolean> {
    const conversation = selectedConversation || {
      url: "https://chatgpt.com/",
      identity: "__new__",
      title: "Nouvelle conversation",
    };
    if (!transport.opt_in_accepted && !demoMode) {
      notify("Active d'abord le transport expérimental dans les paramètres.");
      setSettingsOpen(true);
      return false;
    }
    try {
      const dataB64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
      const descriptor = await postJson<{ path: string; name: string; kind: string }>("/api/chat/attachments", {
        name: file.name,
        data_b64: dataB64,
      });
      const run = await postJson<ChatRun>("/api/chat/send-with-attachment", {
        conversation_url: conversation.url,
        text,
        path: descriptor.path,
        name: descriptor.name,
        image: descriptor.kind === "image",
        new_conversation: conversation.identity === "__new__" || conversation.url === "https://chatgpt.com/",
      });
      subscribeRun(run);
      notify(`Pièce jointe envoyée : ${descriptor.name}`);
      return true;
    } catch (error) {
      notify(error instanceof Error ? error.message : "Impossible d'envoyer la pièce jointe.");
      return false;
    }
  }

  async function sendScreenshot(text: string): Promise<boolean> {
    const conversation = selectedConversation || {
      url: "https://chatgpt.com/",
      identity: "__new__",
      title: "Nouvelle conversation",
    };
    try {
      const run = await postJson<ChatRun>("/api/chat/send-screenshot", {
        conversation_url: conversation.url,
        text,
        new_conversation: conversation.identity === "__new__" || conversation.url === "https://chatgpt.com/",
      });
      subscribeRun(run);
      notify("Capture d'écran envoyée dans ChatGPT.");
      return true;
    } catch (error) {
      notify(error instanceof Error ? error.message : "Capture impossible.");
      return false;
    }
  }

  async function startMission(text: string): Promise<boolean> {
    const conversation = selectedConversation || {
      url: "https://chatgpt.com/",
      identity: "__new__",
      title: "Nouvelle conversation",
    };
    try {
      const response = await postJson<{ id: string; state: string }>("/api/missions", {
        objective: text,
        workspace: settings.default_workspace,
        constraints: ["Ne jamais supprimer définitivement un fichier", "Rester dans les racines autorisées"],
        conversation_url: conversation.url,
        new_conversation: conversation.identity === "__new__" || conversation.url === "https://chatgpt.com/",
        max_iterations: settings.max_iterations,
        max_duration_minutes: settings.max_duration_minutes,
        approval_policy: settings.approval_policy,
      });
      missionDetailRequestEpoch.current.invalidate();
      setSelectedMissionId(response.id);
      setMissionDetail(null);
      notify("Mission autonome lancée.");
      void refreshMissions();
      return true;
    } catch (error) {
      if (DEVELOPMENT_FIXTURES_ENABLED && demoMode) {
        missionDetailRequestEpoch.current.invalidate();
        setSelectedMissionId(demoMissionDetail.mission.id);
        setMissionDetail(demoMissionDetail);
        notify("Aperçu local : mission simulée.");
        return true;
      } else {
        notify(error instanceof Error ? error.message : "Impossible de lancer la mission.");
        return false;
      }
    }
  }

  async function cancelChat() {
    if (!chatRun) return;
    try {
      await postJson(`/api/chat/runs/${chatRun.id}/cancel`, {});
      setChatRun((current) => current ? { ...current, state: "CANCELLED" } : current);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Impossible d'arrêter la réponse.");
    }
  }

  async function missionAction(action: "pause" | "resume" | "cancel") {
    if (!selectedMissionId) return;
    try {
      await postJson(`/api/missions/${selectedMissionId}/${action}`, {});
      await refreshMissionDetail();
    } catch (error) {
      notify(error instanceof Error ? error.message : `Impossible de ${action} la mission.`);
    }
  }

  async function approve(scope: "once" | "tool" | "all-writes") {
    if (!selectedMissionId) return;
    try {
      await postJson(`/api/missions/${selectedMissionId}/approve`, { scope, approve: true });
      notify("Action approuvée.");
      await refreshMissionDetail();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Approbation impossible.");
    }
  }

  async function reject() {
    if (!selectedMissionId) return;
    try {
      await postJson(`/api/missions/${selectedMissionId}/approve`, { scope: "once", approve: false });
      notify("Action refusée et rapportée à ChatGPT.");
      await refreshMissionDetail();
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

  const selectedUrl = selectedConversation?.url || null;

  return (
    <main
      aria-label="Conversation principale"
      className={`cortex-app theme-${settings.theme} ${inspectorOpen ? "inspector-visible" : ""}`}
    >
      <div className="app-grid-background" aria-hidden="true" />
      <div className="app-signal-sweep" aria-hidden="true" />
      <ConversationSidebar
        conversations={conversations}
        selectedUrl={selectedUrl}
        loading={loadingConversations}
        collapsed={sidebarCollapsed}
        onCollapse={() => setSidebarCollapsed((value) => !value)}
        onSelect={(conversation) => {
          if (selectedConversation?.identity === conversation.identity) {
            void loadConversation(conversation);
            return;
          }
          selectedConversationRef.current = conversation;
          setConversationState((current) => ({ ...current, selectedConversation: conversation }));
        }}
        onRefresh={() => void refreshConversations()}
        onNewConversation={() => {
          const fresh: ConversationSummary = { url: "https://chatgpt.com/", identity: "__new__", title: "Nouvelle conversation", preview: "Le chat sera créé au premier envoi", status: "idle" };
          conversationPollRequestEpoch.current.invalidate();
          conversationLoadController.invalidate();
          selectedConversationRef.current = fresh;
          setConversationState((current) => ({ ...current, selectedConversation: fresh }));
          setMessages([]);
          setLoadingMessages(false);
        }}
        onNewMission={() => {
          const fresh: ConversationSummary = { url: "https://chatgpt.com/", identity: "__new__", title: "Nouvelle mission", preview: "ChatGPT orchestrera la mission", status: "mission" };
          conversationPollRequestEpoch.current.invalidate();
          conversationLoadController.invalidate();
          selectedConversationRef.current = fresh;
          setConversationState((current) => ({ ...current, selectedConversation: fresh }));
          setMessages([]);
          setLoadingMessages(false);
          notify("Décris la mission dans le composer central.");
        }}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <ChatWorkspace
        conversation={selectedConversation}
        messages={messages}
        loadingMessages={loadingMessages}
        chatRun={chatRun}
        mission={activeMission || missionDetail}
        pipeline={pipeline}
        settings={settings}
        inspectorOpen={inspectorOpen}
        sidebarCollapsed={sidebarCollapsed}
        capabilities={capabilities}
        onToggleSidebar={() => setSidebarCollapsed((value) => !value)}
        onToggleInspector={() => setInspectorOpen((value) => !value)}
        onSendChat={sendChat}
        onSendAttachment={sendAttachment}
        onSendScreenshot={sendScreenshot}
        onStartMission={startMission}
        onCancelChat={() => void cancelChat()}
        onPauseMission={() => void missionAction("pause")}
        onResumeMission={() => void missionAction("resume")}
        onCancelMission={() => void missionAction("cancel")}
        onApprove={(scope) => void approve(scope)}
        onReject={() => void reject()}
      />

      <PipelineInspector
        open={inspectorOpen}
        pipeline={pipeline}
        runtime={runtime}
        transport={transport}
        mission={activeMission || missionDetail}
        onClose={() => setInspectorOpen(false)}
        onPause={() => void missionAction("pause")}
        onResume={() => void missionAction("resume")}
        onCancel={() => void missionAction("cancel")}
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

      {!settingsOpen && <OnboardingPanel onOpenSettings={() => setSettingsOpen(true)} />}

      {demoMode && <div className="demo-mode-badge">development_fixture · aucune preuve de release</div>}
      {toast && <div className="app-toast" role="status">{toast}</div>}
    </main>
  );
}
