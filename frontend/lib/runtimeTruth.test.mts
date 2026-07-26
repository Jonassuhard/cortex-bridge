import assert from "node:assert/strict";
import test from "node:test";

import {
  createUnavailableClientState,
  executorDisplay,
  executionStateLabel,
  isAvailableComponentState,
  usesOllamaStructuredTools,
} from "./runtimeTruth.ts";

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
