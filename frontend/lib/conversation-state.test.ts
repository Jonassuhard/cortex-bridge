import { describe, expect, it } from "vitest";
import type { ChatRun, ConversationSnapshot, ConversationSummary, MissionDetail } from "./types";
import {
  canResolveRekeyConflict,
  canonicalConversationUrlFromMission,
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

  it("keeps the immutable submitted payload until delivery, then clears only the matching composer", () => {
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
      submittedDraft: "A",
      submittedAttachment: fileA,
    });

    expect(accepted.selectedKey).toBe("b");
    expect(accepted.entries.a.draft).toBe("A");
    expect(accepted.entries.a.attachment).toBe(fileA);
    expect(accepted.entries.a.submittedPayload).toEqual({
      runId: "run-a",
      draft: "A",
      attachment: fileA,
    });
    expect(accepted.entries.b.draft).toBe("B");
    expect(accepted.entries.b.attachment).toBe(fileB);

    const delivered = conversationReducer(accepted, {
      type: "RUN_EVENT",
      key: "a",
      runId: "run-a",
      streamEpoch: 1,
      event: {
        seq: 1,
        ts: "2026-07-26T12:00:01.000Z",
        type: "delivery",
        payload: { delivered_at: "2026-07-26T12:00:01.000Z" },
      },
    });

    expect(delivered.entries.a.draft).toBe("");
    expect(delivered.entries.a.attachment).toBeNull();
    expect(delivered.entries.a.submittedPayload).toBeNull();
    expect(delivered.entries.b.draft).toBe("B");
    expect(delivered.entries.b.attachment).toBe(fileB);
  });

  it("does not erase newer composer edits when delivery proves an older submitted payload", () => {
    const submittedFile = new File(["one"], "one.txt");
    const newerFile = new File(["two"], "two.txt");
    const accepted = reduce(
      createConversationState([summary("a")], "a"),
      { type: "DRAFT_CHANGED", key: "a", draft: "premier" },
      { type: "ATTACHMENT_STAGED", key: "a", attachment: submittedFile },
      {
        type: "RUN_EVENT",
        key: "a",
        runId: "run-a",
        streamEpoch: 1,
        run: run("a"),
        accepted: true,
        submittedDraft: "premier",
        submittedAttachment: submittedFile,
      },
      { type: "DRAFT_CHANGED", key: "a", draft: "nouveau" },
      { type: "ATTACHMENT_STAGED", key: "a", attachment: newerFile },
    );
    const delivered = conversationReducer(accepted, {
      type: "RUN_EVENT",
      key: "a",
      runId: "run-a",
      streamEpoch: 1,
      event: { seq: 1, ts: "2026-07-26T12:00:01.000Z", type: "delivery", payload: {} },
    });

    expect(delivered.entries.a.draft).toBe("nouveau");
    expect(delivered.entries.a.attachment).toBe(newerFile);
    expect(delivered.entries.a.submittedPayload).toBeNull();
  });

  it("marks recovery exhaustion as delivery uncertain without losing exact draft or File", () => {
    const file = new File(["preuve"], "preuve.txt");
    const seeded = reduce(
      createConversationState([summary("a")], "a"),
      { type: "DRAFT_CHANGED", key: "a", draft: "contenu exact  " },
      { type: "ATTACHMENT_STAGED", key: "a", attachment: file },
      {
        type: "RUN_EVENT",
        key: "a",
        runId: "run-a",
        streamEpoch: 2,
        run: run("a"),
        accepted: true,
        submittedDraft: "contenu exact  ",
        submittedAttachment: file,
      },
    );
    const exhausted = conversationReducer(seeded, {
      type: "RUN_RECOVERY_EXHAUSTED",
      key: "a",
      runId: "run-a",
      streamEpoch: 2,
      error: "Livraison incertaine : impossible de confirmer le message.",
    });

    expect(exhausted.entries.a.run?.state).toBe("DELIVERY_UNCERTAIN");
    expect(exhausted.entries.a.run?.error).toMatch(/Livraison incertaine/);
    expect(exhausted.entries.a.draft).toBe("contenu exact  ");
    expect(exhausted.entries.a.attachment).toBe(file);
    expect(exhausted.entries.a.submittedPayload).toEqual({
      runId: "run-a",
      draft: "contenu exact  ",
      attachment: file,
    });

    const proven = conversationReducer(exhausted, {
      type: "RUN_EVENT",
      key: "a",
      runId: "run-a",
      streamEpoch: 3,
      run: { ...run("a"), state: "WAITING_FOR_CHATGPT", delivered_at: "now" },
    });
    expect(proven.entries.a.draft).toBe("");
    expect(proven.entries.a.attachment).toBeNull();
    expect(proven.entries.a.submittedPayload).toBeNull();
  });

  it("abandons an uncertain submitted payload only when the composer is explicitly changed", () => {
    const seeded = reduce(
      createConversationState([summary("a")], "a"),
      { type: "DRAFT_CHANGED", key: "a", draft: "original" },
      {
        type: "RUN_EVENT",
        key: "a",
        runId: "run-a",
        streamEpoch: 1,
        run: run("a"),
        accepted: true,
        submittedDraft: "original",
        submittedAttachment: null,
      },
      {
        type: "RUN_RECOVERY_EXHAUSTED",
        key: "a",
        runId: "run-a",
        streamEpoch: 1,
        error: "incertain",
      },
    );
    expect(seeded.entries.a.submittedPayload?.draft).toBe("original");
    const edited = conversationReducer(seeded, {
      type: "DRAFT_CHANGED",
      key: "a",
      draft: "nouveau choix",
    });
    expect(edited.entries.a.submittedPayload).toBeNull();
  });

  it("cancels the current run by identity even after its stream epoch advanced", () => {
    const seeded = reduce(
      createConversationState([summary("a")], "a"),
      { type: "RUN_EVENT", key: "a", runId: "run-a", streamEpoch: 1, run: run("a"), accepted: true },
      { type: "RUN_EVENT", key: "a", runId: "run-a", streamEpoch: 3, run: { ...run("a"), state: "WAITING_FOR_CHATGPT" } },
    );
    const cancelled = conversationReducer(seeded, {
      type: "RUN_CANCELLED",
      key: "a",
      runId: "run-a",
      cancelledAt: "2026-07-26T12:00:05.000Z",
    });

    expect(cancelled.entries.a.run?.state).toBe("CANCELLED");
    expect(cancelled.entries.a.streamEpoch).toBe(3);
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

  it("keeps a screenshot draft and staged File until delivery proof", () => {
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
      submittedDraft: "capture",
      submittedAttachment: null,
    });

    expect(accepted.entries.a.draft).toBe("capture");
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

  it("selects the existing canonical entry and discards only a safe provisional collision", () => {
    const provisional = createProvisionalConversation(() => "safe-collision");
    const collided = conversationReducer(
      createConversationState([provisional, summary("canonical-a")], provisional.identity),
      {
        type: "REKEY_CANONICAL",
        key: provisional.identity,
        canonicalKey: "canonical-a",
        canonicalUrl: "https://chatgpt.com/c/canonical-a",
      },
    );
    const resolved = conversationReducer(collided, {
      type: "RESOLVE_REKEY_CONFLICT",
      fromKey: provisional.identity,
      toKey: "canonical-a",
      choice: "target",
    });

    expect(resolved.selectedKey).toBe("canonical-a");
    expect(resolved.entries[provisional.identity]).toBeUndefined();
    expect(resolved.entries["canonical-a"]).toStrictEqual(collided.entries["canonical-a"]);
    expect(resolved.rekeyConflict).toBeNull();
  });

  it("never discards an active provisional entry while resolving a canonical collision", () => {
    const provisional = createProvisionalConversation(() => "active-collision");
    const active = reduce(
      createConversationState([provisional, summary("canonical-a")], provisional.identity),
      { type: "DRAFT_CHANGED", key: provisional.identity, draft: "à préserver" },
      {
        type: "RUN_EVENT",
        key: provisional.identity,
        runId: "run-active",
        streamEpoch: 1,
        run: run("active", "run-active"),
        accepted: true,
      },
      {
        type: "REKEY_CANONICAL",
        key: provisional.identity,
        canonicalKey: "canonical-a",
        canonicalUrl: "https://chatgpt.com/c/canonical-a",
      },
    );
    const resolved = conversationReducer(active, {
      type: "RESOLVE_REKEY_CONFLICT",
      fromKey: provisional.identity,
      toKey: "canonical-a",
      choice: "target",
    });

    expect(resolved).toBe(active);
    expect(resolved.selectedKey).toBe(provisional.identity);
    expect(resolved.entries[provisional.identity].draft).toBe("à préserver");
    expect(resolved.rekeyConflict).toEqual(active.rekeyConflict);
  });

  it.each([
    ["source" as const, "brouillon provisoire", "source.txt"],
    ["target" as const, "brouillon canonique", "target.txt"],
  ])("resolves a safe collision with the chosen exact %s composer and one canonical entry", (choice, expectedDraft, expectedFile) => {
    const provisional = createProvisionalConversation(() => `choice-${choice}`);
    const sourceFile = new File(["source"], "source.txt");
    const targetFile = new File(["target"], "target.txt");
    const sourceSnapshot = {
      ...snapshot("source", "source message"),
      messages: [
        { id: "shared", role: "assistant" as const, text: "partagé" },
        { id: "source-only", role: "user" as const, text: "source" },
      ],
    };
    const targetSnapshot = {
      ...snapshot("canonical-a", "target message"),
      messages: [
        { id: "shared", role: "assistant" as const, text: "partagé" },
        { id: "target-only", role: "assistant" as const, text: "target" },
      ],
    };
    const collided = reduce(
      createConversationState([provisional, summary("canonical-a")], provisional.identity),
      { type: "DRAFT_CHANGED", key: provisional.identity, draft: "brouillon provisoire" },
      { type: "ATTACHMENT_STAGED", key: provisional.identity, attachment: sourceFile },
      { type: "SWITCH_STARTED", key: provisional.identity, epoch: 1 },
      { type: "SNAPSHOT_RECEIVED", key: provisional.identity, epoch: 1, snapshot: sourceSnapshot },
      { type: "DRAFT_CHANGED", key: "canonical-a", draft: "brouillon canonique" },
      { type: "ATTACHMENT_STAGED", key: "canonical-a", attachment: targetFile },
      { type: "SWITCH_STARTED", key: "canonical-a", epoch: 1 },
      { type: "SNAPSHOT_RECEIVED", key: "canonical-a", epoch: 1, snapshot: targetSnapshot },
      {
        type: "REKEY_CANONICAL",
        key: provisional.identity,
        canonicalKey: "canonical-a",
        canonicalUrl: "https://chatgpt.com/c/canonical-a",
      },
    );
    expect(canResolveRekeyConflict(collided)).toBe(true);

    const resolved = conversationReducer(collided, {
      type: "RESOLVE_REKEY_CONFLICT",
      fromKey: provisional.identity,
      toKey: "canonical-a",
      choice,
    });

    expect(resolved.order).toEqual(["canonical-a"]);
    expect(resolved.selectedKey).toBe("canonical-a");
    expect(resolved.entries[provisional.identity]).toBeUndefined();
    expect(resolved.rekeyConflict).toBeNull();
    expect(resolved.entries["canonical-a"].draft).toBe(expectedDraft);
    expect(resolved.entries["canonical-a"].attachment?.name).toBe(expectedFile);
    expect(resolved.entries["canonical-a"].messages.map((message) => message.id)).toEqual([
      "shared",
      "target-only",
      "source-only",
    ]);
  });

  it("refuses collision resolution while either entry owns active work", () => {
    const provisional = createProvisionalConversation(() => "unsafe-choice");
    const collided = reduce(
      createConversationState([provisional, summary("canonical-a")], provisional.identity),
      {
        type: "RUN_EVENT",
        key: provisional.identity,
        runId: "run-active",
        streamEpoch: 1,
        run: run("active", "run-active"),
        accepted: true,
      },
      {
        type: "REKEY_CANONICAL",
        key: provisional.identity,
        canonicalKey: "canonical-a",
        canonicalUrl: "https://chatgpt.com/c/canonical-a",
      },
    );
    expect(canResolveRekeyConflict(collided)).toBe(false);
    const refused = conversationReducer(collided, {
      type: "RESOLVE_REKEY_CONFLICT",
      fromKey: provisional.identity,
      toKey: "canonical-a",
      choice: "source",
    });

    expect(refused).toBe(collided);
    expect(refused.rekeyConflict).not.toBeNull();
    expect(refused.entries[provisional.identity]).toBeDefined();
    expect(refused.entries["canonical-a"]).toBeDefined();
  });

  it("extracts a canonical mission binding URL and atomically rekeys on accepted mission detail", () => {
    const provisional = createProvisionalConversation(() => "mission-new");
    const detail = mission("mission-a");
    detail.timeline.conversation_bindings = [{
      conversation_url: "https://chatgpt.com/c/canonical-mission",
      conversation_target: "https://chatgpt.com/c/canonical-mission",
    }];
    const canonicalUrl = canonicalConversationUrlFromMission(detail);
    expect(canonicalUrl).toBe("https://chatgpt.com/c/canonical-mission");

    const rekeyed = conversationReducer(
      createConversationState([provisional], provisional.identity),
      { type: "MISSION_EVENT", key: provisional.identity, missionId: "mission-a", mission: detail },
    );
    expect(rekeyed.selectedKey).toBe("canonical-mission");
    expect(rekeyed.entries["canonical-mission"].mission).toBe(detail);
  });

  it("does not rekey from a stale canonical mission detail after a newer mission was accepted", () => {
    const provisional = createProvisionalConversation(() => "mission-stale");
    const oldDetail = mission("mission-old");
    oldDetail.timeline.conversation_bindings = [{
      conversation_url: "https://chatgpt.com/c/wrong-old",
    }];
    const seeded = reduce(
      createConversationState([provisional], provisional.identity),
      { type: "MISSION_EVENT", key: provisional.identity, missionId: "mission-new", accepted: true },
    );
    const stale = conversationReducer(seeded, {
      type: "MISSION_EVENT",
      key: provisional.identity,
      missionId: "mission-old",
      mission: oldDetail,
    });

    expect(stale).toBe(seeded);
    expect(stale.selectedKey).toBe(provisional.identity);
    expect(stale.entries["wrong-old"]).toBeUndefined();
  });

  it("retains omitted pending/non-terminal entries but purges absent terminal and idle entries", () => {
    const activeMission = mission("mission-active");
    const terminalMission = mission("mission-terminal");
    terminalMission.mission.state = "COMPLETED";
    let seeded = reduce(
      createConversationState([summary("pending"), summary("run"), summary("mission"), summary("terminal"), summary("idle")], "run"),
      { type: "REQUEST_STARTED", request: "send", key: "pending" },
      { type: "RUN_EVENT", key: "run", runId: "run-active", streamEpoch: 1, run: run("run", "run-active"), accepted: true },
      { type: "MISSION_EVENT", key: "mission", missionId: "mission-active", mission: activeMission },
      { type: "MISSION_EVENT", key: "terminal", missionId: "mission-terminal", mission: terminalMission },
    );
    seeded = conversationReducer(seeded, {
      type: "SUMMARIES_RECEIVED",
      summaries: [summary("fresh")],
      updatedAt: "2026-07-26T13:00:00.000Z",
    });

    expect(seeded.entries.pending).toBeDefined();
    expect(seeded.entries.run).toBeDefined();
    expect(seeded.entries.mission).toBeDefined();
    expect(seeded.entries.terminal).toBeUndefined();
    expect(seeded.entries.idle).toBeUndefined();
    expect(seeded.selectedKey).toBe("run");
    expect(seeded.order).toEqual(["pending", "run", "mission", "fresh"]);
  });

  it("purges an omitted selected idle entry and selects a fresh canonical summary", () => {
    const reconciled = conversationReducer(
      createConversationState([summary("old")], "old"),
      { type: "SUMMARIES_RECEIVED", summaries: [summary("fresh")], updatedAt: "now" },
    );

    expect(reconciled.entries.old).toBeUndefined();
    expect(reconciled.selectedKey).toBe("fresh");
  });

  it("releases terminal submitted payload references so a cleared omitted entry can be purged", () => {
    const file = new File(["large"], "large.bin");
    const failed = reduce(
      createConversationState([summary("a")], "a"),
      { type: "DRAFT_CHANGED", key: "a", draft: "échec" },
      { type: "ATTACHMENT_STAGED", key: "a", attachment: file },
      {
        type: "RUN_EVENT",
        key: "a",
        runId: "run-a",
        streamEpoch: 1,
        run: run("a"),
        accepted: true,
        submittedDraft: "échec",
        submittedAttachment: file,
      },
      {
        type: "RUN_EVENT",
        key: "a",
        runId: "run-a",
        streamEpoch: 1,
        event: { seq: 2, ts: "now", type: "error", payload: { error: "transport" } },
      },
    );
    expect(failed.entries.a.draft).toBe("échec");
    expect(failed.entries.a.attachment).toBe(file);
    expect(failed.entries.a.submittedPayload).toBeNull();
    const cleared = reduce(
      failed,
      { type: "DRAFT_CHANGED", key: "a", draft: "" },
      { type: "ATTACHMENT_STAGED", key: "a", attachment: null },
      { type: "SUMMARIES_RECEIVED", summaries: [], updatedAt: "later" },
    );
    expect(cleared.entries.a).toBeUndefined();
  });

  it("purges an omitted non-selected provisional entry whose run is terminal", () => {
    const provisional = createProvisionalConversation(() => "terminal-provisional");
    const seeded = reduce(
      createConversationState([provisional, summary("b")], "b"),
      {
        type: "RUN_EVENT",
        key: provisional.identity,
        runId: "run-p",
        streamEpoch: 1,
        run: { ...run("p", "run-p"), state: "COMPLETED", delivered_at: "now" },
        accepted: true,
      },
    );
    const reconciled = conversationReducer(seeded, {
      type: "SUMMARIES_RECEIVED",
      summaries: [summary("b")],
      updatedAt: "later",
    });

    expect(reconciled.entries[provisional.identity]).toBeUndefined();
    expect(reconciled.order).toEqual(["b"]);
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
