export type HealthState =
  | "healthy"
  | "connected"
  | "available"
  | "unavailable"
  | "idle"
  | "running"
  | "waiting"
  | "manual_action"
  | "degraded"
  | "blocked"
  | "disconnected"
  | "failed"
  | "unknown";

export type MessageRole = "user" | "assistant" | "system" | "cortex";

export interface ConversationSummary {
  url: string;
  identity: string;
  title: string;
  preview?: string;
  timestamp?: string;
  unread?: number;
  pinned?: boolean;
  project?: boolean;
  project_id?: string | null;
  project_title?: string | null;
  archived?: boolean;
  /** Known only after the conversation has been synced once (P1d). */
  message_count?: number | null;
  status?: "idle" | "generating" | "mission" | "approval" | "blocked" | "error";
  sync_state?: "live" | "stale";
  sync_error?: string | null;
}

export type SyncHealth = "unknown" | "live" | "stale" | "unavailable";

export interface SyncStatus {
  state: SyncHealth;
  error: string | null;
  updated_at: string | null;
}

export interface CodeBlock {
  lang?: string;
  text: string;
}

export interface MessageImage {
  src: string;
  alt?: string;
}

export interface ConversationMessage {
  id: string;
  role: MessageRole;
  text: string;
  code_blocks?: CodeBlock[];
  images?: MessageImage[];
  created_at?: string;
  delivery?: "queued" | "sending" | "sent" | "visible" | "waiting" | "received" | "uncertain" | "failed";
  latency_ms?: number;
  streaming?: boolean;
}

export interface ConversationSnapshot {
  url: string;
  conversation_id: string | null;
  title: string;
  blocker: string | null;
  composer_present: boolean;
  send_button_present: boolean;
  stop_button_present: boolean;
  streaming: boolean;
  model_label?: string | null;
  messages: ConversationMessage[];
}

export type ConversationKey = string;
export type ConversationLoadPhase = "idle" | "loading" | "ready" | "error";
export type ConversationFreshness = "empty" | "cached" | "live" | "stale";

export interface SubmittedConversationPayload {
  runId: string;
  draft: string;
  attachment: File | null;
}

export interface ConversationEntry {
  key: ConversationKey;
  summary: ConversationSummary;
  snapshot: ConversationSnapshot | null;
  messages: ConversationMessage[];
  draft: string;
  attachment: File | null;
  submittedPayload: SubmittedConversationPayload | null;
  loadEpoch: number;
  loadPhase: ConversationLoadPhase;
  loadError: string | null;
  freshness: ConversationFreshness;
  run: ChatRun | null;
  streamEpoch: number;
  missionId: string | null;
  mission: MissionDetail | null;
  sendPending: boolean;
  cancelPending: boolean;
  recoveryPending: boolean;
  sendError: string | null;
}

export type ChatRunState =
  | "QUEUED"
  | "SELECTING_CONVERSATION"
  | "SENDING_TO_CHATGPT"
  | "VISIBLE_IN_CHATGPT"
  | "WAITING_FOR_CHATGPT"
  | "CHATGPT_STREAMING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED"
  | "DELIVERY_UNCERTAIN";

export interface ChatRun {
  id: string;
  state: ChatRunState;
  conversation_url: string;
  canonical_url?: string;
  text: string;
  response_text?: string;
  created_at: string;
  delivered_at?: string | null;
  first_response_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
  latency?: {
    delivery_ms?: number | null;
    first_response_ms?: number | null;
    total_ms?: number | null;
  };
}

export interface ChatRunEvent {
  seq: number;
  ts: string;
  type: "status" | "delivery" | "stream" | "complete" | "error" | "cancelled";
  payload: Record<string, unknown>;
}

export interface RuntimeModel {
  name: string;
  state: "missing" | "installed" | "loaded";
}

export type ExecutorKind = "deterministic" | "ollama" | "unavailable";
export type RuntimeMode = "live" | "development_fixture";

export interface RuntimeTruth {
  executor_kind: ExecutorKind;
  executor_model_used: string | null;
  runtime_mode: RuntimeMode;
  release_eligible: boolean;
}

export interface RuntimeExecution extends RuntimeTruth {
  task_id: string | null;
  state: string;
  active: boolean;
  observed_at: string | null;
}

export interface RuntimeStatus extends RuntimeTruth {
  ollama_up: boolean;
  ollama_status: string;
  endpoint: string;
  storage_path: string;
  volume_mounted: boolean;
  storage_status: string;
  primary: RuntimeModel;
  executor_available: boolean;
}

export interface TransportStatus {
  experimental_warning: string;
  opt_in_accepted: boolean;
  global_stop: boolean;
}

export interface TransportProbeStatus {
  ok: boolean;
  title?: string | null;
  failures?: string[];
}

export interface ChromeExtensionPairing {
  token: string;
  expires_in_seconds: number;
}

export interface ChromeExtensionStatus {
  state: "disconnected" | "awaiting_extension" | "extension_detected" | "paired";
  extension_connected: boolean;
  paired: boolean;
  pending_commands: number;
}

export interface ChromeConnectionResult {
  code: string;
  state: "disconnected" | "checking" | "manual_action" | "connected";
  title: string;
  message: string;
  recoverable: boolean;
  driver: string;
  url: string | null;
  tab_id: number | null;
  window_id: number | null;
}

export interface PipelineComponent {
  id: string;
  label: string;
  state: HealthState;
  detail: string;
  latency_ms?: number | null;
  heartbeat_at?: string | null;
}

export interface PipelineEvent {
  id: string;
  ts: string;
  label: string;
  detail?: string;
  duration_ms?: number | null;
  state?: HealthState;
}

export interface PipelineStatus {
  conversation_identity?: string | null;
  overall: HealthState;
  updated_at: string;
  components: PipelineComponent[];
  active_mission_id?: string | null;
  active_mission_state?: string | null;
  runtime_execution: RuntimeExecution;
  queue_pending: number;
  events: PipelineEvent[];
  latency?: {
    transport_ms?: number | null;
    local_model_ms?: number | null;
    total_iteration_ms?: number | null;
  };
}

export interface MissionSummary extends RuntimeTruth {
  id: string;
  objective: string;
  workspace: string;
  state: string;
  created_at: number;
  updated_at?: number;
  max_iterations?: number;
  max_duration_seconds?: number;
  pause_reason?: string | null;
}

export interface TimelineRow extends Record<string, unknown> {
  rowid?: number;
  created_at?: number;
  started_at?: number;
  updated_at?: number;
  finished_at?: number;
  selected_at?: number;
}

export interface MissionDetail {
  mission: MissionSummary;
  timeline: Record<string, TimelineRow[]>;
  awaiting_approval: boolean;
  stopped: boolean;
}

export interface ExecutionPreflight {
  conversationKey: string;
  workspace: string;
  executorKind: "deterministic" | "ollama";
  capabilities: {
    read: true;
    write: boolean;
    processes: boolean;
    network: boolean;
    delete: false;
  };
  approvalPolicy: "read-only" | "write-with-approvals" | "reviewed-processes";
  maxIterations: number;
  maxDurationMinutes: number;
  attachmentTokens: string[];
}

export type ApprovalPolicy =
  | "read-only-automatic"
  | "workspace-write-with-approvals"
  | "workspace-write-automatic";

export type AccessProfile = "observe" | "workspace" | "extended" | "browser-research" | "lab";

export interface CortexSettings {
  language: "fr" | "en";
  theme: "dark" | "light" | "system";
  planner_model: string;
  primary_executor: string;
  fallback_executor: string;
  approval_policy: ApprovalPolicy;
  access_profile: AccessProfile;
  default_workspace: string;
  max_iterations: number;
  max_duration_minutes: number;
  ollama_context: number;
  auto_continue: boolean;
  browser_research: boolean;
  network_access: boolean;
  never_delete_files: boolean;
  persist_conversation_history: boolean;
  response_stability_seconds: number;
  chat_timeout_seconds: number;
  browser_transport: "chrome_extension" | "playwright" | "webbridge";
  browser_profile_root: string;
}

export interface OllamaModelInfo {
  name: string;
  size: number;
  modified_at?: string;
  digest?: string;
  loaded?: boolean;
}

export interface ChatGPTModelInfo {
  label: string;
  selected?: boolean;
  available?: boolean;
}
