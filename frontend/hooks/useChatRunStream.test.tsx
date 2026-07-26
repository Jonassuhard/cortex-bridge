import { useRef } from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatRun, ChatRunEvent, ConversationSummary } from "@/lib/types";
import { createConversationState } from "@/lib/conversation-state";
import { useConversationController } from "./useConversationController";
import { useChatRunStream, type ChatEventSource } from "./useChatRunStream";

const summary = (key: string): ConversationSummary => ({
  url: `https://chatgpt.com/c/${key}`,
  identity: key,
  title: key.toUpperCase(),
});

const run = (key: string, id = `run-${key}`): ChatRun => ({
  id,
  state: "QUEUED",
  conversation_url: key.startsWith("provisional:") ? "https://chatgpt.com/" : `https://chatgpt.com/c/${key}`,
  text: `texte ${key}`,
  created_at: "2026-07-26T12:00:00.000Z",
});

class FakeEventSource implements ChatEventSource {
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close = vi.fn<() => void>();

  emit(event: ChatRunEvent) {
    this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>);
  }

  fail() {
    this.onerror?.(new Event("error"));
  }
}

function useStreamHarness(
  summaries: ConversationSummary[],
  selectedKey: string,
  recoverRun?: (
    key: string,
    runId: string,
    context: { signal: AbortSignal; deadlineAt: number; remainingMs: number },
  ) => Promise<ChatRun>,
  recovery?: { baseDelayMs?: number; maxAttempts?: number; deadlineMs?: number },
) {
  const controller = useConversationController({
    initialState: createConversationState(summaries, selectedKey),
    fetchSnapshot: () => new Promise(() => undefined),
  });
  const sources = useRef<FakeEventSource[]>([]);
  const streams = useChatRunStream({
    dispatch: controller.dispatch,
    createEventSource: () => {
      const source = new FakeEventSource();
      sources.current.push(source);
      return source;
    },
    recoverRun,
    recoveryBaseDelayMs: recovery?.baseDelayMs ?? 0,
    maxRecoveryAttempts: recovery?.maxAttempts,
    recoveryDeadlineMs: recovery?.deadlineMs,
  });
  return { controller, sources: sources.current, streams };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("useChatRunStream", () => {
  it("keeps A and B concurrent, ignores a stale A source, and terminal A leaves B open", () => {
    const { result } = renderHook(() => useStreamHarness([summary("a"), summary("b")], "b"));

    act(() => {
      result.current.streams.subscribe("a", run("a", "run-a-1"));
      result.current.streams.subscribe("b", run("b", "run-b"));
    });
    const [sourceA1, sourceB] = result.current.sources;
    expect(sourceA1.close).not.toHaveBeenCalled();
    expect(sourceB.close).not.toHaveBeenCalled();

    act(() => result.current.streams.subscribe("a", run("a", "run-a-2")));
    const sourceA2 = result.current.sources[2];
    expect(sourceA1.close).toHaveBeenCalledTimes(1);

    act(() => sourceA1.emit({
      seq: 1,
      ts: "2026-07-26T12:00:01.000Z",
      type: "stream",
      payload: { text: "A périmée" },
    }));
    expect(result.current.controller.state.entries.a.run?.id).toBe("run-a-2");
    expect(result.current.controller.state.entries.a.run?.response_text).toBeUndefined();

    act(() => sourceB.emit({
      seq: 2,
      ts: "2026-07-26T12:00:02.000Z",
      type: "stream",
      payload: { text: "B continue" },
    }));
    act(() => sourceA2.emit({
      seq: 3,
      ts: "2026-07-26T12:00:03.000Z",
      type: "complete",
      payload: { text: "A terminée" },
    }));

    expect(sourceA2.close).toHaveBeenCalledTimes(1);
    expect(sourceB.close).not.toHaveBeenCalled();
    expect(result.current.controller.state.entries.a.run?.state).toBe("COMPLETED");
    expect(result.current.controller.state.entries.b.run?.state).toBe("CHATGPT_STREAMING");
    expect(result.current.controller.state.entries.b.run?.response_text).toBe("B continue");
  });

  it("does not close a stream on state rerender and closes every remaining source once on unmount", () => {
    const { result, rerender, unmount } = renderHook(() => useStreamHarness([summary("a"), summary("b")], "a"));
    act(() => {
      result.current.streams.subscribe("a", run("a"));
      result.current.streams.subscribe("b", run("b"));
    });
    const [sourceA, sourceB] = result.current.sources;

    act(() => sourceA.emit({
      seq: 1,
      ts: "2026-07-26T12:00:01.000Z",
      type: "stream",
      payload: { text: "rerender" },
    }));
    rerender();
    expect(sourceA.close).not.toHaveBeenCalled();
    expect(sourceB.close).not.toHaveBeenCalled();

    unmount();
    expect(sourceA.close).toHaveBeenCalledTimes(1);
    expect(sourceB.close).toHaveBeenCalledTimes(1);
  });

  it("moves a provisional stream to its canonical key and keeps receiving events", () => {
    const provisionalKey = "provisional:d67ce32e-486e-45fd-9be2-cb4e812a9271";
    const provisional: ConversationSummary = {
      url: "https://chatgpt.com/",
      identity: provisionalKey,
      title: "Nouvelle conversation",
    };
    const { result } = renderHook(() => useStreamHarness([provisional], provisionalKey));

    act(() => result.current.streams.subscribe(provisionalKey, run(provisionalKey, "run-new")));
    const source = result.current.sources[0];
    act(() => source.emit({
      seq: 1,
      ts: "2026-07-26T12:00:01.000Z",
      type: "delivery",
      payload: {
        delivered_at: "2026-07-26T12:00:01.000Z",
        canonical_url: "https://chatgpt.com/c/canonical-new",
      },
    }));

    expect(result.current.controller.state.selectedKey).toBe("canonical-new");
    expect(result.current.controller.state.entries[provisionalKey]).toBeUndefined();
    expect(source.close).not.toHaveBeenCalled();

    act(() => source.emit({
      seq: 2,
      ts: "2026-07-26T12:00:02.000Z",
      type: "stream",
      payload: { text: "suite canonique" },
    }));
    expect(result.current.controller.state.entries["canonical-new"].run?.response_text).toBe("suite canonique");
  });

  it("recovers a non-terminal disconnect with a new source and reaches terminal", async () => {
    const recoverRun = vi.fn<(_key: string, _runId: string) => Promise<ChatRun>>(
      async () => ({ ...run("a"), state: "WAITING_FOR_CHATGPT" }),
    );
    const { result } = renderHook(() => useStreamHarness([summary("a")], "a", recoverRun));
    act(() => result.current.streams.subscribe("a", run("a")));
    const first = result.current.sources[0];

    await act(async () => first.fail());
    const recovered = result.current.sources[1];
    expect(first.close).toHaveBeenCalledTimes(1);
    expect(recoverRun).toHaveBeenCalledWith("a", "run-a", expect.objectContaining({
      signal: expect.any(AbortSignal),
      deadlineAt: expect.any(Number),
      remainingMs: expect.any(Number),
    }));
    expect(recovered).toBeDefined();
    expect(recovered.close).not.toHaveBeenCalled();

    act(() => recovered.emit({
      seq: 9,
      ts: "2026-07-26T12:00:09.000Z",
      type: "complete",
      payload: { text: "terminé après reconnexion" },
    }));
    expect(recovered.close).toHaveBeenCalledTimes(1);
    expect(result.current.controller.state.entries.a.run?.state).toBe("COMPLETED");
  });

  it("ignores a recovery GET for A1 after A2 subscribed", async () => {
    let resolveRecovery!: (value: ChatRun) => void;
    const recovery = new Promise<ChatRun>((resolve) => { resolveRecovery = resolve; });
    const { result } = renderHook(() => useStreamHarness(
      [summary("a")],
      "a",
      () => recovery,
    ));
    act(() => result.current.streams.subscribe("a", run("a", "run-a-1")));
    const first = result.current.sources[0];
    act(() => first.fail());
    act(() => result.current.streams.subscribe("a", run("a", "run-a-2")));

    await act(async () => resolveRecovery({
      ...run("a", "run-a-1"),
      state: "WAITING_FOR_CHATGPT",
    }));

    expect(result.current.sources).toHaveLength(2);
    expect(result.current.controller.state.entries.a.run?.id).toBe("run-a-2");
    expect(result.current.controller.state.entries.a.streamEpoch).toBe(2);
  });

  it("does not close a newer A2 stream when a stale manual A1 subscription resolves", () => {
    const { result } = renderHook(() => useStreamHarness([summary("a")], "a"));
    act(() => result.current.streams.subscribe("a", run("a", "run-a-1")));
    const sourceA1 = result.current.sources[0];
    act(() => result.current.streams.subscribe("a", run("a", "run-a-2")));
    const sourceA2 = result.current.sources[1];
    expect(sourceA1.close).toHaveBeenCalledTimes(1);

    act(() => result.current.streams.subscribe(
      "a",
      { ...run("a", "run-a-1"), state: "WAITING_FOR_CHATGPT" },
      { accepted: false },
    ));

    expect(sourceA2.close).not.toHaveBeenCalled();
    expect(result.current.controller.state.entries.a.run?.id).toBe("run-a-2");
    act(() => sourceA2.emit({
      seq: 2,
      ts: "now",
      type: "stream",
      payload: { text: "A2 reste suivi" },
    }));
    expect(result.current.controller.state.entries.a.run?.response_text).toBe("A2 reste suivi");
  });

  it("rekeys a provisional entry when terminal recovery returns a canonical URL", async () => {
    const provisionalKey = "provisional:terminal-recovery";
    const provisional: ConversationSummary = {
      url: "https://chatgpt.com/",
      identity: provisionalKey,
      title: "Nouvelle conversation",
    };
    const recoverRun = vi.fn<(
      key: string,
      runId: string,
      context: { signal: AbortSignal; deadlineAt: number; remainingMs: number },
    ) => Promise<ChatRun>>(async () => ({
      ...run(provisionalKey, "run-new"),
      state: "COMPLETED",
      canonical_url: "https://chatgpt.com/c/canonical-recovered",
      delivered_at: "now",
      completed_at: "now",
    }));
    const { result } = renderHook(() => useStreamHarness(
      [provisional],
      provisionalKey,
      recoverRun,
    ));
    act(() => result.current.streams.subscribe(provisionalKey, run(provisionalKey, "run-new")));
    await act(async () => result.current.sources[0].fail());

    expect(result.current.controller.state.selectedKey).toBe("canonical-recovered");
    expect(result.current.controller.state.entries[provisionalKey]).toBeUndefined();
    expect(result.current.controller.state.entries["canonical-recovered"].run?.state).toBe("COMPLETED");
  });

  it("aborts and does not resurrect a run when explicit close happens during recovery", async () => {
    let resolveRecovery!: (value: ChatRun) => void;
    let recoverySignal!: AbortSignal;
    const recovery = new Promise<ChatRun>((resolve) => { resolveRecovery = resolve; });
    const { result } = renderHook(() => useStreamHarness(
      [summary("a")],
      "a",
      (_key, _runId, context) => {
        recoverySignal = context.signal;
        return recovery;
      },
    ));
    act(() => result.current.streams.subscribe("a", run("a")));
    act(() => result.current.sources[0].fail());
    act(() => result.current.streams.close("a"));
    expect(recoverySignal.aborted).toBe(true);

    await act(async () => resolveRecovery({ ...run("a"), state: "WAITING_FOR_CHATGPT" }));

    expect(result.current.sources).toHaveLength(1);
    expect(result.current.sources[0].close).toHaveBeenCalledTimes(1);
  });

  it("aborts a suspended GET, lets a later bounded attempt proceed, and keeps one absolute deadline", async () => {
    vi.useFakeTimers();
    const signals: AbortSignal[] = [];
    const deadlines: number[] = [];
    const recoverRun = vi.fn<(
      key: string,
      runId: string,
      context: { signal: AbortSignal; deadlineAt: number; remainingMs: number },
    ) => Promise<ChatRun>>((
      _key: string,
      _runId: string,
      context: { signal: AbortSignal; deadlineAt: number; remainingMs: number },
    ) => {
      signals.push(context.signal);
      deadlines.push(context.deadlineAt);
      if (signals.length === 1) return new Promise<ChatRun>(() => undefined);
      return Promise.resolve({ ...run("a"), state: "WAITING_FOR_CHATGPT" as const });
    });
    const { result } = renderHook(() => useStreamHarness(
      [summary("a")],
      "a",
      recoverRun,
      { baseDelayMs: 0, maxAttempts: 2, deadlineMs: 300 },
    ));
    act(() => result.current.streams.subscribe("a", run("a")));
    act(() => result.current.sources[0].fail());
    expect(recoverRun).toHaveBeenCalledTimes(1);

    await act(async () => vi.advanceTimersByTime(150));

    expect(signals[0].aborted).toBe(true);
    expect(recoverRun).toHaveBeenCalledTimes(2);
    expect(deadlines[1]).toBe(deadlines[0]);
    expect(result.current.sources).toHaveLength(2);
  });

  it("marks delivery uncertain after a suspended final GET exhausts its deadline", async () => {
    vi.useFakeTimers();
    let recoverySignal!: AbortSignal;
    const file = new File(["exact"], "exact.txt");
    const { result } = renderHook(() => useStreamHarness(
      [summary("a")],
      "a",
      (_key, _runId, context) => {
        recoverySignal = context.signal;
        return new Promise<ChatRun>(() => undefined);
      },
      { baseDelayMs: 0, maxAttempts: 1, deadlineMs: 100 },
    ));
    act(() => {
      result.current.controller.dispatch({ type: "DRAFT_CHANGED", key: "a", draft: "exact  " });
      result.current.controller.dispatch({ type: "ATTACHMENT_STAGED", key: "a", attachment: file });
      result.current.streams.subscribe("a", run("a"), {
        submittedDraft: "exact  ",
        submittedAttachment: file,
      });
      result.current.sources[0].fail();
    });

    await act(async () => vi.advanceTimersByTime(100));

    const entry = result.current.controller.state.entries.a;
    expect(recoverySignal.aborted).toBe(true);
    expect(entry.run?.state).toBe("DELIVERY_UNCERTAIN");
    expect(entry.draft).toBe("exact  ");
    expect(entry.attachment).toBe(file);
    expect(result.current.sources).toHaveLength(1);
  });

  it("keeps the final attempt deadline armed when an earlier recovery rejects immediately", async () => {
    vi.useFakeTimers();
    const recoverRun = vi.fn<(
      key: string,
      runId: string,
      context: { signal: AbortSignal; deadlineAt: number; remainingMs: number },
    ) => Promise<ChatRun>>()
      .mockRejectedValueOnce(new Error("premier GET rejeté"))
      .mockImplementationOnce(() => new Promise<ChatRun>(() => undefined));
    const { result } = renderHook(() => useStreamHarness(
      [summary("a")],
      "a",
      recoverRun,
      { baseDelayMs: 0, maxAttempts: 2, deadlineMs: 300 },
    ));
    act(() => result.current.streams.subscribe("a", run("a")));
    act(() => result.current.sources[0].fail());
    await act(async () => Promise.resolve());
    expect(recoverRun).toHaveBeenCalledTimes(2);

    await act(async () => vi.advanceTimersByTime(300));

    expect(result.current.controller.state.entries.a.run?.state).toBe("DELIVERY_UNCERTAIN");
  });

  it("counts mismatched recovery run ids as failed attempts and exhausts truthfully", async () => {
    vi.useFakeTimers();
    const recoverRun = vi.fn<(
      key: string,
      runId: string,
      context: { signal: AbortSignal; deadlineAt: number; remainingMs: number },
    ) => Promise<ChatRun>>()
      .mockResolvedValueOnce({ ...run("a", "wrong-1"), state: "WAITING_FOR_CHATGPT" })
      .mockResolvedValueOnce({ ...run("a", "wrong-2"), state: "WAITING_FOR_CHATGPT" });
    const { result } = renderHook(() => useStreamHarness(
      [summary("a")],
      "a",
      recoverRun,
      { baseDelayMs: 0, maxAttempts: 2, deadlineMs: 300 },
    ));
    act(() => result.current.streams.subscribe("a", run("a")));
    act(() => result.current.sources[0].fail());
    await act(async () => Promise.resolve());

    expect(recoverRun).toHaveBeenCalledTimes(2);
    expect(result.current.sources).toHaveLength(1);
    expect(result.current.controller.state.entries.a.run?.state).toBe("DELIVERY_UNCERTAIN");
  });

  it("aborts recovery on unmount and ignores a late resolution", async () => {
    let resolveRecovery!: (value: ChatRun) => void;
    let recoverySignal!: AbortSignal;
    const recovery = new Promise<ChatRun>((resolve) => { resolveRecovery = resolve; });
    const rendered = renderHook(() => useStreamHarness(
      [summary("a")],
      "a",
      (_key, _runId, context) => {
        recoverySignal = context.signal;
        return recovery;
      },
    ));
    act(() => rendered.result.current.streams.subscribe("a", run("a")));
    act(() => rendered.result.current.sources[0].fail());
    const sourcesBefore = rendered.result.current.sources.length;
    rendered.unmount();

    expect(recoverySignal.aborted).toBe(true);
    await act(async () => resolveRecovery({ ...run("a"), state: "WAITING_FOR_CHATGPT" }));
    expect(rendered.result.current.sources).toHaveLength(sourcesBefore);
  });

  it("clears the exact submitted draft and File only after a delivery event", () => {
    const file = new File(["payload"], "payload.txt");
    const { result } = renderHook(() => useStreamHarness([summary("a")], "a"));
    act(() => {
      result.current.controller.dispatch({ type: "DRAFT_CHANGED", key: "a", draft: "à livrer" });
      result.current.controller.dispatch({ type: "ATTACHMENT_STAGED", key: "a", attachment: file });
      result.current.streams.subscribe("a", run("a"), {
        submittedDraft: "à livrer",
        submittedAttachment: file,
      });
    });
    expect(result.current.controller.state.entries.a.draft).toBe("à livrer");
    expect(result.current.controller.state.entries.a.attachment).toBe(file);

    act(() => result.current.sources[0].emit({
      seq: 1,
      ts: "2026-07-26T12:00:01.000Z",
      type: "delivery",
      payload: {},
    }));
    expect(result.current.controller.state.entries.a.draft).toBe("");
    expect(result.current.controller.state.entries.a.attachment).toBeNull();
  });

  it("backs off and stops after the configured recovery budget", async () => {
    vi.useFakeTimers();
    const recoverRun = vi.fn<(_key: string, _runId: string) => Promise<ChatRun>>(
      async () => ({ ...run("a"), state: "WAITING_FOR_CHATGPT" }),
    );
    const { result } = renderHook(() => useStreamHarness(
      [summary("a")],
      "a",
      recoverRun,
      { baseDelayMs: 100, maxAttempts: 2 },
    ));
    act(() => result.current.streams.subscribe("a", run("a")));
    act(() => result.current.sources[0].fail());
    await act(async () => vi.advanceTimersByTime(99));
    expect(recoverRun).not.toHaveBeenCalled();

    await act(async () => vi.advanceTimersByTime(1));
    expect(result.current.sources).toHaveLength(2);
    act(() => result.current.sources[1].fail());
    await act(async () => vi.advanceTimersByTime(199));
    expect(result.current.sources).toHaveLength(2);
    await act(async () => vi.advanceTimersByTime(1));
    expect(result.current.sources).toHaveLength(3);

    act(() => result.current.sources[2].fail());
    await act(async () => vi.advanceTimersByTime(1_000));
    expect(result.current.sources).toHaveLength(3);
    expect(recoverRun).toHaveBeenCalledTimes(2);
  });

  it("retries a rejected recovery GET within the same bounded backoff budget", async () => {
    vi.useFakeTimers();
    const recoverRun = vi.fn<(_key: string, _runId: string) => Promise<ChatRun>>()
      .mockRejectedValueOnce(new Error("GET temporairement indisponible"))
      .mockResolvedValueOnce({ ...run("a"), state: "WAITING_FOR_CHATGPT" });
    const { result } = renderHook(() => useStreamHarness(
      [summary("a")],
      "a",
      recoverRun,
      { baseDelayMs: 100, maxAttempts: 2 },
    ));
    act(() => result.current.streams.subscribe("a", run("a")));
    act(() => result.current.sources[0].fail());

    await act(async () => vi.advanceTimersByTime(100));
    expect(recoverRun).toHaveBeenCalledTimes(1);
    expect(result.current.sources).toHaveLength(1);
    await act(async () => vi.advanceTimersByTime(199));
    expect(recoverRun).toHaveBeenCalledTimes(1);

    await act(async () => vi.advanceTimersByTime(1));
    expect(recoverRun).toHaveBeenCalledTimes(2);
    expect(result.current.sources).toHaveLength(2);
  });

  it("keeps a provisional stream scoped when canonical rekey collides", () => {
    const provisionalKey = "provisional:collision";
    const provisional: ConversationSummary = {
      url: "https://chatgpt.com/",
      identity: provisionalKey,
      title: "Nouvelle conversation",
    };
    const { result } = renderHook(() => useStreamHarness(
      [provisional, summary("canonical-existing")],
      provisionalKey,
    ));
    act(() => result.current.streams.subscribe(provisionalKey, run(provisionalKey, "run-collision")));
    const source = result.current.sources[0];

    act(() => source.emit({
      seq: 1,
      ts: "2026-07-26T12:00:01.000Z",
      type: "delivery",
      payload: { canonical_url: "https://chatgpt.com/c/canonical-existing" },
    }));
    act(() => source.emit({
      seq: 2,
      ts: "2026-07-26T12:00:02.000Z",
      type: "stream",
      payload: { text: "reste provisoire" },
    }));

    expect(result.current.controller.state.rekeyConflict?.toKey).toBe("canonical-existing");
    expect(result.current.controller.state.entries[provisionalKey].run?.response_text).toBe("reste provisoire");
    expect(result.current.controller.state.entries["canonical-existing"].run).toBeNull();
  });
});
