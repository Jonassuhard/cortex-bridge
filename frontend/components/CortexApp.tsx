"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { ConversationSidebar } from "./ConversationSidebar";
import { ChatWorkspace } from "./ChatWorkspace";
import { PipelineInspector } from "./PipelineInspector";
import { SettingsPanel } from "./SettingsPanel";

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
  };
}

function nonTerminal(state?: string) {
  return !!state && !["COMPLETED", "BLOCKED", "FAILED", "CANCELLED"].includes(state);
}

export function CortexApp() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<ConversationSummary | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [runtime, setRuntime] = useState<RuntimeStatus>(demoRuntime);
  const [transport, setTransport] = useState<TransportStatus>(demoTransport);
  const [pipeline, setPipeline] = useState<PipelineStatus>(demoPipeline);
  const [, setMissions] = useState<MissionSummary[]>([]);
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null);
  const [missionDetail, setMissionDetail] = useState<MissionDetail | null>(null);
  const [chatRun, setChatRun] = useState<ChatRun | null>(null);
  const [settings, setSettings] = useState<CortexSettings>(demoSettings);
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
      setRuntime(demoRuntime);
      setTransport(demoTransport);
      setDemoMode(true);
    }
  }, []);

  const refreshPipeline = useCallback(async () => {
    try {
      const data = await api<PipelineStatus>("/api/pipeline/status");
      setPipeline(data);
    } catch {
      setPipeline(() => demoMode ? demoPipeline : {
        ...demoPipeline,
        updated_at: new Date().toISOString(),
        components: demoPipeline.components.map((component) =>
          component.id === "ollama"
            ? { ...component, state: runtime.ollama_up ? "healthy" : "failed", detail: runtime.ollama_status }
            : component,
        ),
      });
    }
  }, [demoMode, runtime.ollama_status, runtime.ollama_up]);

  const refreshConversations = useCallback(async () => {
    setLoadingConversations(true);
    try {
      const data = await api<ConversationSummary[]>("/api/conversations");
      // 50 most recent max (Jonas spec P1d); the backend already caps, this
      // is a second belt for demo/fallback data.
      const normalized = data.map(normalizeConversation).slice(0, 50);
      setConversations(normalized);
      setDemoMode(false);
      setSelectedConversation((current) => {
        if (current) {
          const stillThere = normalized.find((item) => item.url === current.url);
          if (stillThere) return stillThere;
          // Deletion sync: the conversation vanished from ChatGPT — drop it
          // from Cortex too, unless a chat run is actively writing into it.
          const runActive = chatRun && !["COMPLETED", "FAILED", "CANCELLED"].includes(chatRun.state);
          if (current.identity === "__new__" || runActive) return current;
          return normalized[0] || null;
        }
        return normalized[0] || null;
      });
    } catch {
      setConversations(demoConversations);
      setSelectedConversation((current) => current || demoConversations[0]);
      setDemoMode(true);
    } finally {
      setLoadingConversations(false);
    }
  }, [chatRun]);

  const refreshMissions = useCallback(async () => {
    try {
      const data = await api<MissionSummary[]>("/api/missions");
      setMissions(data);
      const currentId = selectedMissionId || data.find((mission) => nonTerminal(mission.state))?.id || data[0]?.id || null;
      if (currentId && currentId !== selectedMissionId) setSelectedMissionId(currentId);
    } catch {
      setMissions(demoMissions);
      setSelectedMissionId((current) => current || demoMissions[0].id);
    }
  }, [selectedMissionId]);

  const refreshMissionDetail = useCallback(async () => {
    if (!selectedMissionId) {
      setMissionDetail(null);
      return;
    }
    try {
      const data = await api<MissionDetail>(`/api/missions/${selectedMissionId}`);
      setMissionDetail(data);
    } catch {
      if (selectedMissionId === demoMissionDetail.mission.id) setMissionDetail(demoMissionDetail);
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
      setSettings(demoSettings);
      setOllamaModels([
        { name: "orchestra-executor", size: 5_300_000_000, loaded: true },
        { name: "orchestra-executor-fallback", size: 6_600_000_000, loaded: false },
      ]);
      setChatGPTModels([{ label: demoSettings.planner_model, selected: true, available: true }]);
    }
  }, []);

  const loadConversation = useCallback(async (conversation: ConversationSummary) => {
    setSelectedConversation(conversation);
    setLoadingMessages(true);
    setMessages([]);
    setLastLightSig(null);
    try {
      if (conversation.identity.startsWith("demo-")) throw new Error("demo");
      const snapshot = await api<ConversationSnapshot>(`/api/conversations/snapshot?url=${encodeURIComponent(conversation.url)}`);
      setMessages(snapshot.messages || []);
      // P1d: remember the synced message count for the sidebar sub-line.
      const count = (snapshot.messages || []).length;
      setConversations((current) =>
        current.map((item) => (item.url === conversation.url ? { ...item, message_count: count } : item)),
      );
      if (snapshot.model_label) {
        setSettings((current) => ({ ...current, planner_model: snapshot.model_label || current.planner_model }));
      }
    } catch {
      setMessages(conversation.identity.startsWith("demo-") ? demoMessages : []);
    } finally {
      setLoadingMessages(false);
    }
  }, []);

  const refreshSelectedConversation = useCallback(async () => {
    if (!selectedConversation || selectedConversation.identity === "__new__" || selectedConversation.identity.startsWith("demo-")) return;
    try {
      // P0c: cheap light poll first; only fetch the full snapshot (which
      // serializes every message) when the conversation actually changed.
      const light = await api<{ message_count: number; last_id: string | null; streaming: boolean }>(
        `/api/conversations/snapshot?url=${encodeURIComponent(selectedConversation.url)}&light=1`,
      );
      const sig = `${light.message_count}|${light.last_id}|${light.streaming}`;
      setConversations((current) =>
        current.map((item) => (item.url === selectedConversation.url ? { ...item, message_count: light.message_count } : item)),
      );
      if (sig === lastLightSig) return;
      setLastLightSig(sig);
      if (!chatRun || ["COMPLETED", "FAILED", "CANCELLED"].includes(chatRun.state)) {
        const snapshot = await api<ConversationSnapshot>(`/api/conversations/snapshot?url=${encodeURIComponent(selectedConversation.url)}`);
        setMessages(snapshot.messages || []);
      }
    } catch {
      // Keep the last readable snapshot. Transport errors surface in pipeline status.
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
    return () => chatEventSource.current?.close();
  }, [refreshConversations, refreshMissions, refreshPipeline, refreshRuntime, refreshSettings]);

  useEffect(() => {
    if (selectedConversation && messages.length === 0 && !loadingMessages) void loadConversation(selectedConversation);
  }, [loadConversation, loadingMessages, messages.length, selectedConversation]);

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
        primary_executor: settings.primary_executor,
        fallback_executor: settings.fallback_executor,
      });
      setSelectedMissionId(response.id);
      setMissionDetail(null);
      notify("Mission autonome lancée.");
      void refreshMissions();
      return true;
    } catch (error) {
      if (demoMode) {
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
      setSettings(next);
      setSettingsOpen(false);
      notify("Paramètres appliqués localement dans l'aperçu.");
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
    <main className={`cortex-app theme-${settings.theme} ${inspectorOpen ? "inspector-visible" : ""}`}>
      <div className="app-grid-background" aria-hidden="true" />
      <div className="app-signal-sweep" aria-hidden="true" />
      <ConversationSidebar
        conversations={conversations}
        selectedUrl={selectedUrl}
        loading={loadingConversations}
        collapsed={sidebarCollapsed}
        onCollapse={() => setSidebarCollapsed((value) => !value)}
        onSelect={(conversation) => void loadConversation(conversation)}
        onRefresh={() => void refreshConversations()}
        onNewConversation={() => {
          const fresh: ConversationSummary = { url: "https://chatgpt.com/", identity: "__new__", title: "Nouvelle conversation", preview: "Le chat sera créé au premier envoi", status: "idle" };
          setSelectedConversation(fresh);
          setMessages([]);
        }}
        onNewMission={() => {
          const fresh: ConversationSummary = { url: "https://chatgpt.com/", identity: "__new__", title: "Nouvelle mission", preview: "ChatGPT orchestrera la mission", status: "mission" };
          setSelectedConversation(fresh);
          setMessages([]);
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
        saving={settingsSaving}
        onClose={() => setSettingsOpen(false)}
        onSave={saveSettings}
        onSelectChatGPTModel={selectChatGPTModel}
      />

      {demoMode && <div className="demo-mode-badge">Aperçu hors ligne · connecte FastAPI pour les données réelles</div>}
      {toast && <div className="app-toast" role="status">{toast}</div>}
    </main>
  );
}
