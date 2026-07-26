import type {
  ConversationMessage,
  ConversationSummary,
  CortexSettings,
  MissionDetail,
  MissionSummary,
  PipelineStatus,
  RuntimeStatus,
  TransportStatus,
} from "./types";

export const demoConversations: ConversationSummary[] = [
  {
    url: "https://chatgpt.com/c/demo-cool-bank",
    identity: "demo-cool-bank",
    title: "COOL BANK V3",
    preview: "Audit du parcours d'inscription et correction des tests…",
    timestamp: "10:24",
    pinned: true,
    status: "mission",
  },
  {
    url: "https://chatgpt.com/c/demo-cortex",
    identity: "demo-cortex",
    title: "Cortex Bridge Mission",
    preview: "Connexion WebBridge et validation de la boucle autonome…",
    timestamp: "09:42",
    unread: 2,
    status: "generating",
  },
  {
    url: "https://chatgpt.com/c/demo-preuvia",
    identity: "demo-preuvia",
    title: "Analyse et évaluation",
    preview: "Revoir l'interface locale et le design Preuvia…",
    timestamp: "Hier",
    pinned: true,
  },
  {
    url: "https://chatgpt.com/c/demo-claude",
    identity: "demo-claude",
    title: "Claude certification",
    preview: "Préparer la grille de tests et les preuves…",
    timestamp: "Hier",
  },
  {
    url: "https://chatgpt.com/c/demo-local-ai",
    identity: "demo-local-ai",
    title: "OpenCodex et IA locales",
    preview: "Comparer Granite, Qwen et les profils Ollama…",
    timestamp: "22 juil.",
  },
];

export const demoMessages: ConversationMessage[] = [
  {
    id: "demo-u1",
    role: "user",
    text: "Inspecte le checkout, lance les tests, vérifie les commits récents et utilise le navigateur pour valider le parcours de bout en bout.",
    created_at: new Date(Date.now() - 85_000).toISOString(),
    delivery: "received",
    latency_ms: 128,
  },
  {
    id: "demo-a1",
    role: "assistant",
    text: "Je vais analyser le dépôt, exécuter la suite de tests, examiner les changements récents puis valider le comportement dans Chrome. La mission continuera automatiquement et chaque résultat sera vérifié avant la prochaine étape.",
    created_at: new Date(Date.now() - 72_000).toISOString(),
    latency_ms: 2130,
  },
  {
    id: "demo-c1",
    role: "cortex",
    text: "Exécution locale en cours",
    created_at: new Date(Date.now() - 62_000).toISOString(),
    streaming: true,
  },
];

export const demoRuntime: RuntimeStatus = {
  ollama_up: true,
  ollama_status: "healthy",
  endpoint: "http://127.0.0.1:11434",
  storage_path: "/Volumes/DJO/AI/Ollama/models",
  volume_mounted: true,
  storage_status: "OK",
  primary: { name: "orchestra-executor", state: "loaded" },
  executor_available: true,
  executor_kind: "unavailable",
  executor_model_used: null,
  runtime_mode: "development_fixture",
};

export const demoTransport: TransportStatus = {
  experimental_warning:
    "Ce mode automatise l'interface Web de ChatGPT. Il est expérimental et peut casser lorsque l'interface change.",
  opt_in_accepted: true,
  global_stop: false,
};

export const demoPipeline: PipelineStatus = {
  overall: "running",
  updated_at: new Date().toISOString(),
  active_mission_id: "demo-mission",
  active_mission_state: "EXECUTING_LOCAL_ACTION",
  queue_pending: 0,
  runtime_execution: {
    executor_kind: "deterministic",
    executor_model_used: null,
    runtime_mode: "development_fixture",
  },
  latency: { transport_ms: 128, local_model_ms: 3700, total_iteration_ms: 12800 },
  components: [
    { id: "transport", label: "Transport ChatGPT", state: "connected", detail: "Conversation verrouillée", latency_ms: 128 },
    { id: "validator", label: "Validateur Cortex", state: "healthy", detail: "cortex.v1 valide", latency_ms: 96 },
    { id: "task", label: "Tâche courante", state: "running", detail: "Tests Vitest · étape 2/4" },
    { id: "chrome", label: "Chrome Research", state: "running", detail: "Page locale chargée" },
    { id: "screenshots", label: "Captures", state: "healthy", detail: "3 preuves enregistrées" },
    { id: "filesystem", label: "Fichiers", state: "healthy", detail: "Lecture / écriture workspace" },
    { id: "ollama", label: "Disponibilité Ollama", state: "available", detail: "daemon fixture · candidat installé" },
    { id: "executor", label: "Exécuteur réellement utilisé", state: "running", detail: "deterministic · fixture de développement" },
    { id: "approvals", label: "Approbations", state: "idle", detail: "Aucune en attente" },
    { id: "queue", label: "File d'attente", state: "idle", detail: "0 action" },
    { id: "database", label: "Persistance", state: "healthy", detail: "SQLite synchronisé" },
  ],
  events: [
    { id: "e1", ts: new Date(Date.now() - 2_000).toISOString(), label: "Suite de tests lancée", detail: "vitest", duration_ms: 12_000, state: "running" },
    { id: "e2", ts: new Date(Date.now() - 4_000).toISOString(), label: "Dépôt inspecté", duration_ms: 1_200, state: "healthy" },
    { id: "e3", ts: new Date(Date.now() - 5_000).toISOString(), label: "Décision reçue de ChatGPT", duration_ms: 600, state: "healthy" },
    { id: "e4", ts: new Date(Date.now() - 6_000).toISOString(), label: "Conversation verrouillée", duration_ms: 400, state: "connected" },
  ],
};

export const demoMissions: MissionSummary[] = [
  {
    id: "demo-mission",
    objective: "Auditer le checkout et valider le parcours de bout en bout",
    workspace: "/Users/asterion/Projects/checkout",
    state: "EXECUTING_LOCAL_ACTION",
    created_at: Date.now() / 1000 - 140,
    max_iterations: 25,
    executor_kind: "deterministic",
    executor_model_used: null,
    runtime_mode: "development_fixture",
  },
];

export const demoMissionDetail: MissionDetail = {
  mission: demoMissions[0],
  awaiting_approval: false,
  stopped: false,
  timeline: {
    conversation_bindings: [{ rowid: 1, selected_at: Date.now() / 1000 - 140, conversation_title: "Audit checkout" }],
    orchestrator_decisions: [{ rowid: 2, created_at: Date.now() / 1000 - 80, valid: 1, decision_json: JSON.stringify({ state: "EXECUTE", summary: "Run the repository test suite", action: { tool: "run_tests", arguments: { command: "npm test" } } }) }],
    policy_decisions: [{ rowid: 3, created_at: Date.now() / 1000 - 78, tool: "run_tests", allowed: 1, requires_approval: 0, reason: "Configured project test command" }],
    tool_executions: [{ rowid: 4, started_at: Date.now() / 1000 - 60, tool: "run_tests", arguments_json: JSON.stringify({ argv: ["npm", "test"] }), exit_code: null }],
    validation_results: [],
    transport_events: [],
    iterations: [],
    approvals: [],
    artifacts: [],
  },
};

export const demoSettings: CortexSettings = {
  language: "fr",
  theme: "dark",
  planner_model: "ChatGPT — modèle visible actuel",
  primary_executor: "orchestra-executor",
  fallback_executor: "orchestra-executor-fallback",
  approval_policy: "workspace-write-with-approvals",
  access_profile: "workspace",
  default_workspace: "/Users/asterion/Documents/kimi/workspace/e2e-sandbox",
  max_iterations: 25,
  max_duration_minutes: 60,
  ollama_context: 8192,
  auto_continue: true,
  browser_research: false,
  network_access: false,
  never_delete_files: true,
  persist_conversation_history: false,
  response_stability_seconds: 2,
  chat_timeout_seconds: 300,
  browser_transport: "playwright",
  browser_profile_root: "console/data/browser-profiles",
};
