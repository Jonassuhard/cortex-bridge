import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

import * as runtimeTruthModule from "./runtimeTruth.ts";
const {
  createUnavailableClientState,
  executorDisplay,
  executionStateLabel,
  isAvailableComponentState,
  usesOllamaStructuredTools,
} = runtimeTruthModule;

const require = createRequire(import.meta.url);
const React = require("react") as typeof import("react");
const { renderToStaticMarkup } = require("react-dom/server") as typeof import("react-dom/server");
const ts = require("typescript") as typeof import("typescript");

function loadTsxExport(path: URL, exportName: string): React.ComponentType<Record<string, unknown>> {
  const source = readFileSync(path, "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      esModuleInterop: true,
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: path.pathname,
  }).outputText;
  const compiledModule = { exports: {} as Record<string, unknown> };
  const iconModules = new Proxy({}, {
    get: (_target, property) => {
      if (property === "__esModule") return true;
      return (props: Record<string, unknown>) => React.createElement("span", props);
    },
  });
  const localRequire = (specifier: string): unknown => {
    if (specifier === "react" || specifier === "react/jsx-runtime") return require(specifier);
    if (specifier === "@/lib/runtimeTruth") return runtimeTruthModule;
    if (specifier === "@/lib/api") {
      return {
        formatDuration: (value: number) => `${value} ms`,
        shortTime: () => "",
      };
    }
    if (specifier === "./Icons" || specifier === "./CortexLogo") return iconModules;
    if (specifier === "./ExecutionCard") {
      return { ExecutionCard: () => React.createElement("div", { "data-execution-card": true }) };
    }
    throw new Error(`unexpected TSX dependency: ${specifier}`);
  };
  const context = {
    console,
    exports: compiledModule.exports,
    module: compiledModule,
    process,
    require: localRequire,
    setTimeout,
  };
  vm.runInNewContext(output, context, { filename: path.pathname });
  return compiledModule.exports[exportName] as React.ComponentType<Record<string, unknown>>;
}

function pipelineWith(executorState: string) {
  return {
    overall: "connected",
    updated_at: "2026-07-26T12:00:00Z",
    components: [
      { id: "transport", label: "Transport", state: "connected", detail: "Playwright" },
      { id: "executor", label: "Exécuteur", state: executorState, detail: executorState },
    ],
    active_mission_id: "mission-paused",
    active_mission_state: "PAUSED",
    runtime_execution: {
      task_id: "mission-paused",
      executor_kind: "unavailable",
      executor_model_used: null,
      runtime_mode: "live",
      release_eligible: false,
      state: "PAUSED",
      active: false,
      observed_at: null,
    },
    queue_pending: 0,
    events: [],
    latency: {},
  };
}

const pausedMission = {
  mission: {
    id: "mission-paused",
    objective: "Pause indépendante",
    workspace: "/tmp",
    state: "PAUSED",
    created_at: 1,
    executor_kind: "deterministic",
    executor_model_used: null,
    runtime_mode: "live",
    release_eligible: false,
  },
  timeline: {},
  awaiting_approval: false,
  stopped: false,
};

const settings = {
  language: "fr",
  theme: "dark",
  planner_model: "ChatGPT",
  primary_executor: "local",
  fallback_executor: "none",
  approval_policy: "read-only-automatic",
  access_profile: "observe",
  default_workspace: "/tmp",
  max_iterations: 5,
  max_duration_minutes: 5,
  ollama_context: 4096,
  auto_continue: false,
  browser_research: false,
  network_access: false,
  never_delete_files: true,
  persist_conversation_history: true,
  response_stability_seconds: 1,
  chat_timeout_seconds: 30,
  browser_transport: "playwright",
  browser_profile_root: "/tmp/profile",
};

function workspaceProps(executorState: string, conversation: Record<string, unknown> | null = null) {
  const noop = () => undefined;
  const asyncTrue = async () => true;
  return {
    capabilities: { upload_file: false, take_screenshot: false },
    chatRun: null,
    conversation,
    inspectorOpen: false,
    loadingMessages: false,
    messages: [],
    mission: pausedMission,
    onApprove: noop,
    onCancelChat: noop,
    onCancelMission: noop,
    onPauseMission: noop,
    onReject: noop,
    onResumeMission: noop,
    onSendAttachment: asyncTrue,
    onSendChat: asyncTrue,
    onSendScreenshot: asyncTrue,
    onStartMission: asyncTrue,
    onToggleInspector: noop,
    onToggleSidebar: noop,
    pipeline: pipelineWith(executorState),
    settings,
    sidebarCollapsed: false,
  };
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve(value: T): void;
  reject(error: Error): void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

const loadConversationA = {
  url: "https://chatgpt.com/c/load-a",
  identity: "load-a",
  title: "Conversation A",
  sync_state: "live",
  sync_error: null,
};
const loadConversationB = {
  url: "https://chatgpt.com/c/load-b",
  identity: "load-b",
  title: "Conversation B",
  sync_state: "live",
  sync_error: null,
};

function conversationSnapshot(url: string, texts: string[]) {
  return {
    url,
    conversation_id: url.split("/").at(-1) || null,
    title: "Snapshot",
    blocker: null,
    composer_present: true,
    send_button_present: true,
    stop_button_present: false,
    streaming: false,
    model_label: "ChatGPT",
    messages: texts.map((text, index) => ({ id: `${url}-${index}`, role: "assistant", text })),
  };
}

type ConversationLoadFactory = (effects: {
  onStart(conversation: Record<string, unknown>): void;
  onSuccess(conversation: Record<string, unknown>, snapshot: ReturnType<typeof conversationSnapshot>): void;
  onFailure(conversation: Record<string, unknown>, error: unknown): void;
  onFinish(conversation: Record<string, unknown>): void;
}) => {
  invalidate(): void;
  load(
    conversation: Record<string, unknown>,
    fetchSnapshot: (conversation: Record<string, unknown>) => Promise<ReturnType<typeof conversationSnapshot>>,
  ): Promise<void>;
};

function createConversationLoadHarness(factory: ConversationLoadFactory) {
  const view = {
    conversationState: {
      conversations: [loadConversationA, loadConversationB].map((conversation) => ({ ...conversation })),
      selectedConversation: null as Record<string, unknown> | null,
      sync: { state: "live", error: null as string | null, updated_at: "2026-07-26T13:00:00Z" },
    },
    loading: false,
    messages: [] as string[],
  };
  const controller = factory({
    onStart(conversation) {
      view.conversationState.selectedConversation = conversation;
      view.loading = true;
      view.messages = [];
    },
    onSuccess(conversation, snapshot) {
      view.messages = snapshot.messages.map((message) => message.text);
      view.conversationState.conversations = view.conversationState.conversations.map((item) => (
        item.url === conversation.url
          ? { ...item, sync_state: "live", sync_error: null, message_count: snapshot.messages.length }
          : item
      ));
      view.conversationState.selectedConversation = {
        ...conversation,
        sync_state: "live",
        sync_error: null,
        message_count: snapshot.messages.length,
      };
      view.conversationState.sync = {
        state: "live",
        error: null,
        updated_at: "2026-07-26T13:01:00Z",
      };
    },
    onFailure(conversation) {
      view.conversationState = runtimeTruthModule.reduceConversationRefreshFailure(
        view.conversationState as never,
        "Chargement de la conversation impossible",
        String(conversation.url),
      ) as typeof view.conversationState;
    },
    onFinish() {
      view.loading = false;
    },
  });
  return { controller, view };
}

function conversationView(view: ReturnType<typeof createConversationLoadHarness>["view"]) {
  const selectedUrl = String(view.conversationState.selectedConversation?.url || "");
  const selectedRow = view.conversationState.conversations.find((item) => item.url === selectedUrl);
  return {
    loading: view.loading,
    messages: [...view.messages],
    selectedUrl,
    staleError: selectedRow?.sync_error || null,
    staleState: selectedRow?.sync_state || null,
  };
}

test("successful conversation cache becomes visibly stale after refresh failure", async () => {
  const runtimeTruth = await import("./runtimeTruth.ts") as Record<string, unknown>;
  const reduceFailure = runtimeTruth.reduceConversationRefreshFailure as ((
    state: Record<string, unknown>,
    error: string,
  ) => {
    conversations: Array<Record<string, unknown>>;
    selectedConversation: Record<string, unknown>;
    sync: Record<string, unknown>;
  }) | undefined;
  assert.equal(typeof reduceFailure, "function");

  const conversation = {
    url: "https://chatgpt.com/c/cached",
    identity: "cached",
    title: "Conversation en cache",
    preview: "Dernier contenu synchronisé",
    sync_state: "live",
  };
  const result = reduceFailure!({
    conversations: [conversation],
    selectedConversation: conversation,
    sync: { state: "live", error: null, updated_at: "2026-07-26T10:00:00Z" },
  }, "Synchronisation impossible");

  assert.equal(result.conversations.length, 1);
  assert.equal(result.conversations[0].title, "Conversation en cache");
  assert.equal(result.conversations[0].sync_state, "stale");
  assert.equal(result.conversations[0].sync_error, "Synchronisation impossible");
  assert.equal(result.selectedConversation.identity, "cached");
  assert.equal(result.selectedConversation.sync_state, "stale");
  assert.deepEqual(result.sync, {
    state: "stale",
    error: "Synchronisation impossible",
    updated_at: "2026-07-26T10:00:00Z",
  });
});

test("selected-conversation poll failure marks only its cached row stale and no-cache unavailable", async () => {
  const runtimeTruth = await import("./runtimeTruth.ts") as Record<string, unknown>;
  const reduceFailure = runtimeTruth.reduceConversationRefreshFailure as ((
    state: Record<string, unknown>,
    error: string,
    targetUrl?: string,
  ) => {
    conversations: Array<Record<string, unknown>>;
    selectedConversation: Record<string, unknown> | null;
    sync: Record<string, unknown>;
  }) | undefined;
  assert.equal(typeof reduceFailure, "function");

  const selected = {
    url: "https://chatgpt.com/c/selected",
    identity: "selected",
    title: "Conversation sélectionnée",
    sync_state: "live",
  };
  const other = {
    url: "https://chatgpt.com/c/other",
    identity: "other",
    title: "Conversation indépendante",
    sync_state: "live",
  };
  const failed = reduceFailure!({
    conversations: [selected, other],
    selectedConversation: selected,
    sync: { state: "live", error: null, updated_at: "2026-07-26T12:00:00Z" },
  }, "Actualisation de la conversation impossible", selected.url);

  assert.equal(failed.conversations[0].sync_state, "stale");
  assert.equal(failed.conversations[0].sync_error, "Actualisation de la conversation impossible");
  assert.equal(failed.conversations[1].sync_state, "live");
  assert.equal(failed.selectedConversation?.sync_state, "stale");
  assert.equal(failed.sync.state, "stale");

  const empty = reduceFailure!({
    conversations: [],
    selectedConversation: null,
    sync: { state: "live", error: null, updated_at: null },
  }, "Actualisation impossible", selected.url);
  assert.deepEqual(empty, {
    conversations: [],
    selectedConversation: null,
    sync: { state: "unavailable", error: "Actualisation impossible", updated_at: null },
  });
});

test("sidebar and conversation header visibly expose stale cache and sync error", () => {
  const ChatWorkspace = loadTsxExport(
    new URL("../components/ChatWorkspace.tsx", import.meta.url),
    "ChatWorkspace",
  );
  const ConversationSidebar = loadTsxExport(
    new URL("../components/ConversationSidebar.tsx", import.meta.url),
    "ConversationSidebar",
  );
  const stale = {
    url: "https://chatgpt.com/c/stale",
    identity: "stale",
    title: "Conversation en cache",
    preview: "Contenu conservé",
    status: "idle",
    sync_state: "stale",
    sync_error: "Actualisation de la conversation impossible",
  };

  const workspaceHtml = renderToStaticMarkup(React.createElement(ChatWorkspace, workspaceProps("unknown", stale)));
  assert.match(workspaceHtml, /Cache obsolète/);
  assert.match(workspaceHtml, /synchronisation en échec/);
  assert.match(workspaceHtml, /Actualisation de la conversation impossible/);

  const sidebarHtml = renderToStaticMarkup(React.createElement(ConversationSidebar, {
    collapsed: false,
    conversations: [stale],
    loading: false,
    onCollapse() {},
    onNewConversation() {},
    onNewMission() {},
    onOpenSettings() {},
    onRefresh() {},
    onSelect() {},
    selectedUrl: stale.url,
  }));
  assert.match(sidebarHtml, /Cache obsolète/);
  assert.match(sidebarHtml, /Actualisation de la conversation impossible/);
});

test("paused mission never overrides unknown unavailable or error executor truth", () => {
  const ChatWorkspace = loadTsxExport(
    new URL("../components/ChatWorkspace.tsx", import.meta.url),
    "ChatWorkspace",
  );
  const cases = [
    { state: "unknown", tone: "unknown", label: "État inconnu" },
    { state: "unavailable", tone: "offline", label: "Indisponible" },
    { state: "error", tone: "offline", label: "Indisponible" },
  ];

  for (const entry of cases) {
    const html = renderToStaticMarkup(React.createElement(ChatWorkspace, workspaceProps(entry.state)));
    const expected = `title="Statut de l&#x27;agent exécutif local"><span class="presence-dot is-${entry.tone}"></span><span>Exécuteur</span><strong>${entry.label}</strong>`;
    assert.ok(html.includes(expected), `${entry.state} executor chip was: ${html.match(/Statut de l&#x27;agent exécutif local.{0,240}/)?.[0]}`);
  }
});

test("newer mission reset wins over an older deferred detail success", async () => {
  const runtimeTruth = await import("./runtimeTruth.ts") as Record<string, unknown>;
  const createEpoch = runtimeTruth.createRequestEpoch as (() => {
    begin(identity: string): unknown;
    isCurrent(ticket: unknown, currentIdentity: string | null): boolean;
  }) | undefined;
  assert.equal(typeof createEpoch, "function");
  const epoch = createEpoch!();
  let resolveOld!: (value: string) => void;
  const oldResponse = new Promise<string>((resolve) => { resolveOld = resolve; });
  let currentIdentity: string | null = "mission-a";
  let detail: string | null = "previous detail";
  const oldTicket = epoch.begin(currentIdentity);
  const oldCompletion = oldResponse.then((value) => {
    if (epoch.isCurrent(oldTicket, currentIdentity)) detail = value;
  });

  const failingTicket = epoch.begin(currentIdentity);
  if (epoch.isCurrent(failingTicket, currentIdentity)) {
    currentIdentity = null;
    detail = null;
  }
  resolveOld("stale mission detail");
  await oldCompletion;

  assert.equal(currentIdentity, null);
  assert.equal(detail, null);
});

test("newer conversation selection error wins over older deferred poll success", async () => {
  const runtimeTruth = await import("./runtimeTruth.ts") as Record<string, unknown>;
  const createEpoch = runtimeTruth.createRequestEpoch as (() => {
    begin(identity: string): unknown;
    isCurrent(ticket: unknown, currentIdentity: string | null): boolean;
  }) | undefined;
  assert.equal(typeof createEpoch, "function");
  const epoch = createEpoch!();
  let resolveOld!: (value: string[]) => void;
  const oldResponse = new Promise<string[]>((resolve) => { resolveOld = resolve; });
  let currentIdentity: string | null = "conversation-a";
  let messages = ["cache a"];
  const oldTicket = epoch.begin(currentIdentity);
  const oldCompletion = oldResponse.then((value) => {
    if (epoch.isCurrent(oldTicket, currentIdentity)) messages = value;
  });

  currentIdentity = "conversation-b";
  const failingTicket = epoch.begin(currentIdentity);
  if (epoch.isCurrent(failingTicket, currentIdentity)) messages = ["cache b obsolète"];
  resolveOld(["stale network response for a"]);
  await oldCompletion;

  assert.equal(currentIdentity, "conversation-b");
  assert.deepEqual(messages, ["cache b obsolète"]);
});

test("conversation loader ignores A success arriving after B success", async () => {
  const runtimeTruth = await import("./runtimeTruth.ts") as Record<string, unknown>;
  const factory = runtimeTruth.createConversationLoadController as ConversationLoadFactory | undefined;
  assert.equal(typeof factory, "function");
  const { controller, view } = createConversationLoadHarness(factory!);
  const requestA = deferred<ReturnType<typeof conversationSnapshot>>();
  const requestB = deferred<ReturnType<typeof conversationSnapshot>>();

  const loadingA = controller.load(loadConversationA, () => requestA.promise);
  const loadingB = controller.load(loadConversationB, () => requestB.promise);
  requestB.resolve(conversationSnapshot(loadConversationB.url, ["B récente"]));
  await loadingB;
  requestA.resolve(conversationSnapshot(loadConversationA.url, ["A tardive"]));
  await loadingA;

  assert.deepEqual(conversationView(view), {
    loading: false,
    messages: ["B récente"],
    selectedUrl: loadConversationB.url,
    staleError: null,
    staleState: "live",
  });
});

test("conversation loader ignores A failure and finally arriving after B success", async () => {
  const runtimeTruth = await import("./runtimeTruth.ts") as Record<string, unknown>;
  const factory = runtimeTruth.createConversationLoadController as ConversationLoadFactory | undefined;
  assert.equal(typeof factory, "function");
  const { controller, view } = createConversationLoadHarness(factory!);
  const requestA = deferred<ReturnType<typeof conversationSnapshot>>();
  const requestB = deferred<ReturnType<typeof conversationSnapshot>>();

  const loadingA = controller.load(loadConversationA, () => requestA.promise);
  const loadingB = controller.load(loadConversationB, () => requestB.promise);
  requestB.resolve(conversationSnapshot(loadConversationB.url, ["B confirmée"]));
  await loadingB;
  requestA.reject(new Error("A indisponible trop tard"));
  await loadingA;

  assert.deepEqual(conversationView(view), {
    loading: false,
    messages: ["B confirmée"],
    selectedUrl: loadConversationB.url,
    staleError: null,
    staleState: "live",
  });
});

test("conversation loader marks only current B stale when B fails", async () => {
  const runtimeTruth = await import("./runtimeTruth.ts") as Record<string, unknown>;
  const factory = runtimeTruth.createConversationLoadController as ConversationLoadFactory | undefined;
  assert.equal(typeof factory, "function");
  const { controller, view } = createConversationLoadHarness(factory!);
  const requestB = deferred<ReturnType<typeof conversationSnapshot>>();

  const loadingB = controller.load(loadConversationB, () => requestB.promise);
  requestB.reject(new Error("B indisponible"));
  await loadingB;

  assert.deepEqual(conversationView(view), {
    loading: false,
    messages: [],
    selectedUrl: loadConversationB.url,
    staleError: "Chargement de la conversation impossible",
    staleState: "stale",
  });
  assert.equal(view.conversationState.conversations[0].sync_state, "live");
  assert.equal(view.conversationState.conversations[0].sync_error, null);
});

test("conversation loader reset invalidates every late mutation", async () => {
  const runtimeTruth = await import("./runtimeTruth.ts") as Record<string, unknown>;
  const factory = runtimeTruth.createConversationLoadController as ConversationLoadFactory | undefined;
  assert.equal(typeof factory, "function");
  const { controller, view } = createConversationLoadHarness(factory!);
  const requestA = deferred<ReturnType<typeof conversationSnapshot>>();

  const loadingA = controller.load(loadConversationA, () => requestA.promise);
  controller.invalidate();
  view.conversationState.selectedConversation = {
    url: "https://chatgpt.com/",
    identity: "__new__",
    title: "Nouvelle conversation",
  };
  view.messages = ["Brouillon local"];
  view.loading = false;
  requestA.resolve(conversationSnapshot(loadConversationA.url, ["A après reset"]));
  await loadingA;

  assert.deepEqual(conversationView(view), {
    loading: false,
    messages: ["Brouillon local"],
    selectedUrl: "https://chatgpt.com/",
    staleError: null,
    staleState: null,
  });
});

test("mission refresh failure clears current execution while preserving independent transport", async () => {
  const runtimeTruth = await import("./runtimeTruth.ts") as Record<string, unknown>;
  const reduceFailure = runtimeTruth.reduceMissionRefreshFailure as ((
    state: Record<string, unknown>,
    updatedAt: string,
  ) => {
    selectedMissionId: string | null;
    missionDetail: Record<string, unknown> | null;
    pipeline: {
      overall: string;
      active_mission_id: string | null;
      active_mission_state: string | null;
      runtime_execution: Record<string, unknown>;
      events: unknown[];
      components: Array<Record<string, unknown>>;
    };
  }) | undefined;
  assert.equal(typeof reduceFailure, "function");

  const result = reduceFailure!({
    selectedMissionId: "mission-live",
    missionDetail: { mission: { id: "mission-live", state: "EXECUTING_LOCAL_ACTION" } },
    pipeline: {
      overall: "running",
      updated_at: "2026-07-26T10:00:00Z",
      active_mission_id: "mission-live",
      active_mission_state: "EXECUTING_LOCAL_ACTION",
      queue_pending: 0,
      runtime_execution: {
        task_id: "mission-live",
        executor_kind: "deterministic",
        executor_model_used: null,
        runtime_mode: "live",
        release_eligible: false,
        state: "EXECUTING_LOCAL_ACTION",
        active: true,
        observed_at: "2026-07-26T10:00:00Z",
      },
      components: [
        { id: "transport", label: "Transport ChatGPT", state: "connected", detail: "playwright" },
        { id: "task", label: "Tâche courante", state: "running", detail: "EXECUTING_LOCAL_ACTION" },
        { id: "executor", label: "Exécuteur", state: "running", detail: "deterministic" },
      ],
      events: [{ id: "current", ts: "2026-07-26T10:00:00Z", label: "Action active", state: "running" }],
      latency: { transport_ms: 50, local_model_ms: null, total_iteration_ms: 100 },
    },
  }, "2026-07-26T10:01:00Z");

  assert.equal(result.selectedMissionId, null);
  assert.equal(result.missionDetail, null);
  assert.equal(result.pipeline.overall, "unknown");
  assert.equal(result.pipeline.active_mission_id, null);
  assert.equal(result.pipeline.active_mission_state, null);
  assert.equal(result.pipeline.runtime_execution.executor_kind, "unavailable");
  assert.equal(result.pipeline.runtime_execution.active, false);
  assert.equal(result.pipeline.runtime_execution.state, "idle");
  assert.deepEqual(result.pipeline.events, []);
  assert.equal(result.pipeline.components[0].state, "connected");
  assert.equal(result.pipeline.components[1].state, "unknown");
  assert.equal(result.pipeline.components[2].state, "unknown");
});

test("unknown and unavailable states are never presented as connected or live", async () => {
  const runtimeTruth = await import("./runtimeTruth.ts") as Record<string, unknown>;
  const present = runtimeTruth.statusPresentation as ((state?: string) => Record<string, unknown>) | undefined;
  assert.equal(typeof present, "function");

  assert.deepEqual(present!("unknown"), {
    connected: false,
    label: "État inconnu",
    tone: "unknown",
  });
  assert.deepEqual(present!("unavailable"), {
    connected: false,
    label: "Indisponible",
    tone: "offline",
  });
  assert.deepEqual(present!("failed"), {
    connected: false,
    label: "Indisponible",
    tone: "offline",
  });
  assert.deepEqual(present!("error"), {
    connected: false,
    label: "Indisponible",
    tone: "offline",
  });
  assert.deepEqual(present!("connected"), {
    connected: true,
    label: "Connecté",
    tone: "online",
  });
});

test("API failure without fixture flag yields a neutral client state", () => {
  const state = createUnavailableClientState("2026-07-26T00:00:00.000Z");

  assert.equal(state.pipeline.overall, "unknown");
  assert.equal(state.pipeline.active_mission_id, null);
  assert.equal(state.pipeline.active_mission_state, null);
  assert.deepEqual(state.pipeline.components, []);
  assert.deepEqual(state.pipeline.events, []);
  assert.equal(state.pipeline.runtime_execution.executor_kind, "unavailable");
  assert.equal(state.pipeline.runtime_execution.state, "idle");
  assert.equal(state.pipeline.runtime_execution.active, false);
  assert.deepEqual(state.ollamaModels, []);
  assert.deepEqual(state.chatgptModels, []);
  assert.equal(state.settings.planner_model, "indisponible");
});

test("failed, blocked and cancelled states are never labelled done", () => {
  assert.equal(executionStateLabel("COMPLETED"), "Terminé");
  assert.equal(executionStateLabel("FAILED"), "Échec");
  assert.equal(executionStateLabel("BLOCKED"), "Bloquée");
  assert.equal(executionStateLabel("CANCELLED"), "Annulée");
});

test("idle truth never renders deterministic execution", () => {
  const state = createUnavailableClientState("2026-07-26T00:00:00.000Z");
  assert.equal(executorDisplay(state.pipeline.runtime_execution), "Aucun exécuteur observé");
  assert.equal(usesOllamaStructuredTools(state.pipeline.runtime_execution), false);
});

test("availability accepts available while Ollama claims require actual Ollama execution", () => {
  assert.equal(isAvailableComponentState("available"), true);
  assert.equal(isAvailableComponentState("healthy"), true);
  assert.equal(isAvailableComponentState("idle"), false);
  assert.equal(
    usesOllamaStructuredTools({
      executor_kind: "deterministic",
      executor_model_used: null,
      runtime_mode: "live",
      release_eligible: false,
    }),
    false,
  );
  assert.equal(
    usesOllamaStructuredTools({
      executor_kind: "ollama",
      executor_model_used: "orchestra-executor",
      runtime_mode: "live",
      release_eligible: true,
    }),
    true,
  );
});
