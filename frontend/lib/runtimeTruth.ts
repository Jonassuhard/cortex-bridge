import type {
  ChatGPTModelInfo,
  ConversationSummary,
  CortexSettings,
  MissionDetail,
  OllamaModelInfo,
  PipelineComponent,
  PipelineStatus,
  RuntimeStatus,
  RuntimeTruth,
  SyncStatus,
  TransportStatus,
} from "./types";

export interface ConversationRefreshState {
  conversations: ConversationSummary[];
  selectedConversation: ConversationSummary | null;
  sync: SyncStatus;
}

export interface MissionRefreshState {
  selectedMissionId: string | null;
  missionDetail: MissionDetail | null;
  pipeline: PipelineStatus;
}

export interface StatusPresentation {
  connected: boolean;
  label: string;
  tone: "online" | "offline" | "unknown" | "active";
}

export function createUnavailableClientState(updatedAt: string): {
  runtime: RuntimeStatus;
  transport: TransportStatus;
  pipeline: PipelineStatus;
  settings: CortexSettings;
  ollamaModels: OllamaModelInfo[];
  chatgptModels: ChatGPTModelInfo[];
} {
  return {
    runtime: {
      ollama_up: false,
      ollama_status: "unavailable",
      endpoint: "http://127.0.0.1:11434",
      storage_path: "",
      volume_mounted: false,
      storage_status: "unknown",
      primary: { name: "", state: "missing" },
      executor_available: false,
      executor_kind: "unavailable",
      executor_model_used: null,
      runtime_mode: "live",
      release_eligible: false,
    },
    transport: {
      experimental_warning: "Transport indisponible",
      opt_in_accepted: false,
      global_stop: false,
    },
    pipeline: {
      overall: "unknown",
      updated_at: updatedAt,
      components: [],
      active_mission_id: null,
      active_mission_state: null,
      runtime_execution: {
        task_id: null,
        executor_kind: "unavailable",
        executor_model_used: null,
        runtime_mode: "live",
        release_eligible: false,
        state: "idle",
        active: false,
        observed_at: null,
      },
      queue_pending: 0,
      events: [],
      latency: {
        transport_ms: null,
        local_model_ms: null,
        total_iteration_ms: null,
      },
    },
    settings: {
      language: "fr",
      theme: "dark",
      planner_model: "indisponible",
      primary_executor: "",
      fallback_executor: "",
      approval_policy: "workspace-write-with-approvals",
      access_profile: "workspace",
      default_workspace: "~/",
      max_iterations: 25,
      max_duration_minutes: 60,
      ollama_context: 8192,
      auto_continue: false,
      browser_research: false,
      network_access: false,
      never_delete_files: true,
      persist_conversation_history: false,
      response_stability_seconds: 2,
      chat_timeout_seconds: 300,
      browser_transport: "playwright",
      browser_profile_root: "console/data/browser-profiles",
    },
    ollamaModels: [],
    chatgptModels: [],
  };
}

export function isAvailableComponentState(
  state: PipelineComponent["state"] | undefined,
): boolean {
  return state === "available" || state === "healthy" || state === "connected";
}

export function executorDisplay(truth?: RuntimeTruth | null): string {
  if (truth?.executor_kind === "deterministic") return "Mode A · déterministe";
  if (truth?.executor_kind === "ollama" && truth.executor_model_used) {
    return truth.executor_model_used;
  }
  return "Aucun exécuteur observé";
}

export function usesOllamaStructuredTools(truth?: RuntimeTruth | null): boolean {
  return truth?.executor_kind === "ollama" && !!truth.executor_model_used;
}

export function executorDiagnosticsLabel(truth?: RuntimeTruth | null): string {
  if (usesOllamaStructuredTools(truth)) {
    return `Ollama structured tools · ${truth?.executor_model_used}`;
  }
  if (truth?.executor_kind === "deterministic") {
    return "Mode A · outils déterministes";
  }
  return "Aucun exécuteur observé";
}

export function executionStateLabel(state?: string): string | null {
  if (state === "COMPLETED") return "Terminé";
  if (state === "FAILED") return "Échec";
  if (state === "BLOCKED") return "Bloquée";
  if (state === "CANCELLED") return "Annulée";
  return null;
}

export function reduceConversationRefreshFailure(
  current: ConversationRefreshState,
  error: string,
): ConversationRefreshState {
  const markStale = (conversation: ConversationSummary): ConversationSummary => ({
    ...conversation,
    sync_state: "stale",
    sync_error: error,
  });
  const hasCache = current.conversations.length > 0 || current.selectedConversation !== null;
  if (!hasCache) {
    return {
      conversations: [],
      selectedConversation: null,
      sync: { state: "unavailable", error, updated_at: current.sync.updated_at },
    };
  }
  return {
    conversations: current.conversations.map(markStale),
    selectedConversation: current.selectedConversation
      ? markStale(current.selectedConversation)
      : null,
    sync: { state: "stale", error, updated_at: current.sync.updated_at },
  };
}

export function reduceMissionRefreshFailure(
  current: MissionRefreshState,
  updatedAt: string,
): MissionRefreshState {
  return {
    selectedMissionId: null,
    missionDetail: null,
    pipeline: {
      ...current.pipeline,
      overall: "unknown",
      updated_at: updatedAt,
      active_mission_id: null,
      active_mission_state: null,
      queue_pending: 0,
      runtime_execution: {
        task_id: null,
        executor_kind: "unavailable",
        executor_model_used: null,
        runtime_mode: "live",
        release_eligible: false,
        state: "idle",
        active: false,
        observed_at: null,
      },
      components: current.pipeline.components.map((component) =>
        component.id === "task" || component.id === "executor"
          ? { ...component, state: "unknown", detail: "État inconnu", heartbeat_at: null }
          : component,
      ),
      events: [],
      latency: {
        ...current.pipeline.latency,
        local_model_ms: null,
        total_iteration_ms: null,
      },
    },
  };
}

export function statusPresentation(state?: string): StatusPresentation {
  if (state === "connected" || state === "healthy") {
    return { connected: true, label: "Connecté", tone: "online" };
  }
  if (state === "available") {
    return { connected: true, label: "Disponible", tone: "online" };
  }
  if (state === "running") {
    return { connected: false, label: "En cours", tone: "active" };
  }
  if (state === "waiting") {
    return { connected: false, label: "En attente", tone: "active" };
  }
  if (state === "idle") {
    return { connected: false, label: "Inactif", tone: "unknown" };
  }
  if (state === "degraded") {
    return { connected: false, label: "Dégradé", tone: "unknown" };
  }
  if (state === "unavailable" || state === "failed" || state === "error" || state === "disconnected" || state === "blocked") {
    return { connected: false, label: "Indisponible", tone: "offline" };
  }
  return { connected: false, label: "État inconnu", tone: "unknown" };
}
