import type {
  ChatGPTModelInfo,
  CortexSettings,
  OllamaModelInfo,
  PipelineComponent,
  PipelineStatus,
  RuntimeStatus,
  RuntimeTruth,
  TransportStatus,
} from "./types";

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
