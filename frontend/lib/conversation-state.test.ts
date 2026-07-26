import { describe, expect, it } from "vitest";
import type { ChatRun, ConversationSnapshot, ConversationSummary, MissionDetail } from "./types";
import {
  conversationReducer,
  createConversationState,
  createProvisionalConversation,
  type ConversationEvent,
  type ConversationState,
} from "./conversation-state";

const summary = (key: string): ConversationSummary => ({
  url: `https://chatgpt.com/c/${key}`,
  identity: key,
  title: `Conversation ${key.toUpperCase()}`,
  sync_state: "live",
});

const snapshot = (key: string, text: string): ConversationSnapshot => ({
  url: `https://chatgpt.com/c/${key}`,
  conversation_id: key,
  title: `Conversation ${key.toUpperCase()}`,
  blocker: null,
  composer_present: true,
  send_button_present: true,
  stop_button_present: false,
  streaming: false,
  messages: [{ id: `${key}-message`, role: "assistant", text }],
});

const run = (key: string, id = `run-${key}`): ChatRun => ({
  id,
  state: "QUEUED",
  conversation_url: `https://chatgpt.com/c/${key}`,
  text: `draft ${key}`,
  created_at: "2026-07-26T12:00:00.000Z",
});

const mission = (id: string): MissionDetail => ({
  mission: {
    id,
    objective: id,
    workspace: `/tmp/${id}`,
    state: "EXECUTING_LOCAL_ACTION",
    created_at: 1,
    executor_kind: "deterministic",
    executor_model_used: null,
    runtime_mode: "live",
    release_eligible: true,
  },
  timeline: {},
  awaiting_approval: false,
  stopped: false,
});

function reduce(state: ConversationState, ...events: ConversationEvent[]): ConversationState {
  return events.reduce(conversationReducer, state);
}

describe("conversationReducer", () => {
  it("keeps A and B drafts and exact File attachments independent", () => {
    const fileA = new File(["alpha"], "alpha.txt", { type: "text/plain" });
    const fileB = new File(["beta"], "beta.txt", { type: "text/plain" });
    const state = reduce(
      createConversationState([summary("a"), summary("b")], "a"),
      { type: "DRAFT_CHANGED", key: "a", draft: "texte A" },
      { type: "ATTACHMENT_STAGED", key: "a", attachment: fileA },
      { type: "SELECT", key: "b" },
      { type: "DRAFT_CHANGED", key: "b", draft: "texte B" },
      { type: "ATTACHMENT_STAGED", key: "b", attachment: fileB },
    );

    expect(state.selectedKey).toBe("b");
    expect(state.entries.a.draft).toBe("texte A");
    expect(state.entries.a.attachment).toBe(fileA);
    expect(state.entries.b.draft).toBe("texte B");
    expect(state.entries.b.attachment).toBe(fileB);
  });

  it("lets a valid A load update only A while B stays selected and unchanged", () => {
    const before = reduce(
      createConversationState([summary("a"), summary("b")], "b"),
      { type: "SWITCH_STARTED", key: "a", epoch: 4 },
    );
    const selectedBBefore = before.entries.b;
    const after = conversationReducer(before, {
      type: "SNAPSHOT_RECEIVED",
      key: "a",
      epoch: 4,
      snapshot: snapshot("a", "réponse A"),
    });

    expect(after.selectedKey).toBe("b");
    expect(after.entries.b).toBe(selectedBBefore);
    expect(after.entries.a.messages[0].text).toBe("réponse A");
  });

  it("ignores stale success and failure epochs", () => {
    const current = reduce(
      createConversationState([summary("a")], "a"),
      { type: "SWITCH_STARTED", key: "a", epoch: 7 },
    );
    const staleSuccess = conversationReducer(current, {
      type: "SNAPSHOT_RECEIVED",
      key: "a",
      epoch: 6,
      snapshot: snapshot("a", "trop tard"),
    });
    const staleFailure = conversationReducer(staleSuccess, {
      type: "REQUEST_FAILED",
      request: "load",
      key: "a",
      epoch: 6,
      error: "échec trop tardif",
    });

    expect(staleFailure).toBe(current);
    expect(staleFailure.entries.a.loadPhase).toBe("loading");
    expect(staleFailure.entries.a.messages).toEqual([]);
    expect(staleFailure.entries.a.loadError).toBeNull();
  });

  it("keeps a refused third conversation exact without disturbing A or B", () => {
    const attachment = new File(["payload"], "preuve.txt", { type: "text/plain" });
    const refusal = "Deux conversations écrivent déjà. Votre brouillon est conservé.";
    const seeded = reduce(
      createConversationState([summary("a"), summary("b"), summary("c")], "c"),
      { type: "DRAFT_CHANGED", key: "a", draft: "A active" },
      { type: "DRAFT_CHANGED", key: "b", draft: "B active" },
      { type: "DRAFT_CHANGED", key: "c", draft: "contenu exact  " },
      { type: "ATTACHMENT_STAGED", key: "c", attachment },
    );
    const entryA = seeded.entries.a;
    const entryB = seeded.entries.b;
    const refused = conversationReducer(seeded, {
      type: "REQUEST_FAILED",
      request: "send",
      key: "c",
      status: 409,
      error: refusal,
    });
    const transportFailed = conversationReducer(refused, {
      type: "REQUEST_FAILED",
      request: "send",
      key: "c",
      error: "transport interrompu",
    });

    expect(transportFailed.entries.a).toBe(entryA);
    expect(transportFailed.entries.b).toBe(entryB);
    expect(transportFailed.entries.c.draft).toBe("contenu exact  ");
    expect(transportFailed.entries.c.attachment).toBe(attachment);
    expect(transportFailed.entries.c.sendError).toBe("transport interrompu");
  });

  it("clears only the accepted conversation after send success", () => {
    const fileA = new File(["a"], "a.txt");
    const fileB = new File(["b"], "b.txt");
    const seeded = reduce(
      createConversationState([summary("a"), summary("b")], "b"),
      { type: "DRAFT_CHANGED", key: "a", draft: "A" },
      { type: "ATTACHMENT_STAGED", key: "a", attachment: fileA },
      { type: "DRAFT_CHANGED", key: "b", draft: "B" },
      { type: "ATTACHMENT_STAGED", key: "b", attachment: fileB },
    );
    const accepted = conversationReducer(seeded, {
      type: "RUN_EVENT",
      key: "a",
      runId: "run-a",
      streamEpoch: 1,
      run: run("a"),
      accepted: true,
    });

    expect(accepted.selectedKey).toBe("b");
    expect(accepted.entries.a.draft).toBe("");
    expect(accepted.entries.a.attachment).toBeNull();
    expect(accepted.entries.b.draft).toBe("B");
    expect(accepted.entries.b.attachment).toBe(fileB);
  });

  it("terminates A without changing B's concurrent run", () => {
    const seeded = reduce(
      createConversationState([summary("a"), summary("b")], "b"),
      { type: "RUN_EVENT", key: "a", runId: "run-a", streamEpoch: 2, run: run("a"), accepted: true },
      { type: "RUN_EVENT", key: "b", runId: "run-b", streamEpoch: 3, run: run("b"), accepted: true },
    );
    const runBBefore = seeded.entries.b.run;
    const completed = conversationReducer(seeded, {
      type: "RUN_EVENT",
      key: "a",
      runId: "run-a",
      streamEpoch: 2,
      event: {
        seq: 9,
        ts: "2026-07-26T12:00:09.000Z",
        type: "complete",
        payload: { text: "A terminée", completed_at: "2026-07-26T12:00:09.000Z" },
      },
    });

    expect(completed.entries.a.run?.state).toBe("COMPLETED");
    expect(completed.entries.b.run).toBe(runBBefore);
    expect(completed.entries.b.run?.state).toBe("QUEUED");
  });

  it("ignores events from a stale run id or stream epoch", () => {
    const seeded = reduce(
      createConversationState([summary("a")], "a"),
      { type: "RUN_EVENT", key: "a", runId: "run-current", streamEpoch: 5, run: run("a", "run-current"), accepted: true },
    );
    const event = {
      seq: 1,
      ts: "2026-07-26T12:00:01.000Z",
      type: "stream" as const,
      payload: { text: "réponse périmée" },
    };

    expect(conversationReducer(seeded, {
      type: "RUN_EVENT", key: "a", runId: "old", streamEpoch: 5, event,
    })).toBe(seeded);
    expect(conversationReducer(seeded, {
      type: "RUN_EVENT", key: "a", runId: "run-current", streamEpoch: 4, event,
    })).toBe(seeded);
  });

  it("ignores a stale recovery GET after a newer run has been accepted", () => {
    const seeded = reduce(
      createConversationState([summary("a")], "a"),
      {
        type: "RUN_EVENT",
        key: "a",
        runId: "run-a-2",
        streamEpoch: 2,
        run: run("a", "run-a-2"),
        accepted: true,
      },
    );
    const staleRecovery = conversationReducer(seeded, {
      type: "RUN_EVENT",
      key: "a",
      runId: "run-a-1",
      streamEpoch: 1,
      run: { ...run("a", "run-a-1"), state: "WAITING_FOR_CHATGPT" },
    });

    expect(staleRecovery).toBe(seeded);
    expect(staleRecovery.entries.a.run?.id).toBe("run-a-2");
    expect(staleRecovery.entries.a.streamEpoch).toBe(2);
  });

  it("can clear a screenshot draft without discarding its staged File", () => {
    const attachment = new File(["later"], "later.txt");
    const seeded = reduce(
      createConversationState([summary("a")], "a"),
      { type: "DRAFT_CHANGED", key: "a", draft: "capture" },
      { type: "ATTACHMENT_STAGED", key: "a", attachment },
    );
    const accepted = conversationReducer(seeded, {
      type: "RUN_EVENT",
      key: "a",
      runId: "run-shot",
      streamEpoch: 1,
      run: run("a", "run-shot"),
      accepted: true,
      clearAttachment: false,
    });

    expect(accepted.entries.a.draft).toBe("");
    expect(accepted.entries.a.attachment).toBe(attachment);
  });

  it("atomically rekeys a provisional UUID while preserving its whole entry", () => {
    const provisional = createProvisionalConversation(() => "d67ce32e-486e-45fd-9be2-cb4e812a9271");
    const file = new File(["jointe"], "jointe.txt");
    let state = reduce(
      createConversationState([provisional], provisional.identity),
      { type: "SWITCH_STARTED", key: provisional.identity, epoch: 3 },
      { type: "SNAPSHOT_RECEIVED", key: provisional.identity, epoch: 3, snapshot: snapshot("provisional", "cache") },
      {
        type: "RUN_EVENT",
        key: provisional.identity,
        runId: "run-new",
        streamEpoch: 8,
        run: run("new", "run-new"),
        accepted: true,
      },
      { type: "DRAFT_CHANGED", key: provisional.identity, draft: "suite conservée" },
      { type: "ATTACHMENT_STAGED", key: provisional.identity, attachment: file },
    );
    const before = state.entries[provisional.identity];
    state = conversationReducer(state, {
      type: "REKEY_CANONICAL",
      key: provisional.identity,
      canonicalKey: "canonical-a",
      canonicalUrl: "https://chatgpt.com/c/canonical-a",
    });

    expect(state.selectedKey).toBe("canonical-a");
    expect(state.entries[provisional.identity]).toBeUndefined();
    expect(state.entries["canonical-a"]).toMatchObject({
      key: "canonical-a",
      draft: "suite conservée",
      attachment: file,
      messages: before.messages,
      run: before.run,
      loadEpoch: 3,
    });
    expect(state.entries["canonical-a"].summary.url).toBe("https://chatgpt.com/c/canonical-a");
    expect(state.rekeyConflict).toBeNull();
  });

  it("reports a canonical collision without overwriting either entry", () => {
    const provisional = createProvisionalConversation(() => "fda19eeb-bc37-40ed-a647-f06c42641a42");
    const seeded = createConversationState([provisional, summary("canonical-a")], provisional.identity);
    const sourceBefore = seeded.entries[provisional.identity];
    const targetBefore = seeded.entries["canonical-a"];
    const refused = conversationReducer(seeded, {
      type: "REKEY_CANONICAL",
      key: provisional.identity,
      canonicalKey: "canonical-a",
      canonicalUrl: "https://chatgpt.com/c/canonical-a",
    });

    expect(refused.selectedKey).toBe(provisional.identity);
    expect(refused.entries[provisional.identity]).toBe(sourceBefore);
    expect(refused.entries["canonical-a"]).toBe(targetBefore);
    expect(refused.rekeyConflict).toEqual({
      fromKey: provisional.identity,
      toKey: "canonical-a",
      error: "La conversation canonique existe déjà dans le cache.",
    });
  });

  it("attaches mission state to its conversation entry", () => {
    const missionA = mission("mission-a");
    const seeded = createConversationState([summary("a"), summary("b")], "b");
    const updated = conversationReducer(seeded, {
      type: "MISSION_EVENT",
      key: "a",
      missionId: "mission-a",
      mission: missionA,
    });

    expect(updated.selectedKey).toBe("b");
    expect(updated.entries.a.mission).toBe(missionA);
    expect(updated.entries.b.mission).toBeNull();
  });

  it("ignores a stale mission detail after a newer mission was accepted", () => {
    const seeded = reduce(
      createConversationState([summary("a")], "a"),
      { type: "MISSION_EVENT", key: "a", missionId: "mission-old", mission: mission("mission-old") },
      { type: "MISSION_EVENT", key: "a", missionId: "mission-new", accepted: true },
    );
    const lateOld = conversationReducer(seeded, {
      type: "MISSION_EVENT",
      key: "a",
      missionId: "mission-old",
      mission: mission("mission-old"),
    });

    expect(lateOld).toBe(seeded);
    expect(lateOld.entries.a.missionId).toBe("mission-new");
    expect(lateOld.entries.a.mission).toBeNull();
  });
});
