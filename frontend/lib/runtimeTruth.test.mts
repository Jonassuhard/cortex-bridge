import assert from "node:assert/strict";
import test from "node:test";

import {
  createUnavailableClientState,
  executorDisplay,
  executionStateLabel,
  isAvailableComponentState,
  usesOllamaStructuredTools,
} from "./runtimeTruth.ts";

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
