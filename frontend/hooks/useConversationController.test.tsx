import { StrictMode, type PropsWithChildren } from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConversationSnapshot, ConversationSummary } from "@/lib/types";
import { conversationReducer, createConversationState } from "@/lib/conversation-state";
import {
  createConversationRequestController,
  useConversationController,
} from "./useConversationController";

const summary = (key: string): ConversationSummary => ({
  url: `https://chatgpt.com/c/${key}`,
  identity: key,
  title: key.toUpperCase(),
  sync_state: "live",
});

const snapshot = (key: string, text: string): ConversationSnapshot => ({
  url: `https://chatgpt.com/c/${key}`,
  conversation_id: key,
  title: key.toUpperCase(),
  blocker: null,
  composer_present: true,
  send_button_present: true,
  stop_button_present: false,
  streaming: false,
  messages: [{ id: `${key}-1`, role: "assistant", text }],
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("useConversationController", () => {
  it("reactivates its request manager after an effect cleanup/setup cycle", async () => {
    let state = createConversationState([summary("a")], "a");
    const pending = deferred<ConversationSnapshot>();
    const dispatch = (event: Parameters<typeof conversationReducer>[1]) => {
      state = conversationReducer(state, event);
      return state;
    };
    const manager = createConversationRequestController({
      dispatch,
      getState: () => state,
      fetchSnapshot: () => pending.promise,
    });

    manager.dispose();
    manager.activate();
    const loading = manager.load(summary("a"));
    expect(state.entries.a.loadPhase).toBe("loading");
    pending.resolve(snapshot("a", "après réactivation"));
    await loading;

    expect(state.entries.a.loadPhase).toBe("ready");
    expect(state.entries.a.messages[0].text).toBe("après réactivation");
  });

  it("survives the React StrictMode setup-cleanup cycle and completes the first load", async () => {
    const pending = deferred<ConversationSnapshot>();
    const wrapper = ({ children }: PropsWithChildren) => <StrictMode>{children}</StrictMode>;
    const { result } = renderHook(() => useConversationController({
      fetchSnapshot: () => pending.promise,
    }), { wrapper });

    act(() => result.current.replaceSummaries([summary("a")]));
    expect(result.current.selectedEntry?.loadPhase).toBe("loading");
    await act(async () => pending.resolve(snapshot("a", "chargée après cleanup")));

    expect(result.current.selectedEntry?.loadPhase).toBe("ready");
    expect(result.current.selectedEntry?.messages[0].text).toBe("chargée après cleanup");
  });

  it("reconciles external A to B once, aborts A, and cannot leave B spinning", async () => {
    const requests = new Map([
      ["a", deferred<ConversationSnapshot>()],
      ["b", deferred<ConversationSnapshot>()],
    ]);
    const signals = new Map<string, AbortSignal>();
    const counts = new Map<string, number>();
    const fetchSnapshot = vi.fn<(
      conversation: ConversationSummary,
      signal: AbortSignal,
    ) => Promise<ConversationSnapshot>>((conversation, signal) => {
      counts.set(conversation.identity, (counts.get(conversation.identity) || 0) + 1);
      signals.set(conversation.identity, signal);
      return requests.get(conversation.identity)!.promise;
    });
    const { result } = renderHook(() => useConversationController({ fetchSnapshot }));

    act(() => result.current.replaceSummaries([summary("a")]));
    expect(result.current.state.selectedKey).toBe("a");
    expect(result.current.selectedEntry?.loadPhase).toBe("loading");

    act(() => result.current.replaceSummaries([summary("b")]));
    expect(signals.get("a")?.aborted).toBe(true);
    expect(result.current.state.selectedKey).toBe("b");
    expect(result.current.state.entries.a).toBeUndefined();
    expect(result.current.selectedEntry?.loadPhase).toBe("loading");

    act(() => result.current.replaceSummaries([summary("b")]));
    expect(Object.fromEntries(counts)).toEqual({ a: 1, b: 1 });

    await act(async () => requests.get("b")!.resolve(snapshot("b", "B fraîche")));
    expect(result.current.selectedEntry?.loadPhase).toBe("ready");
    expect(result.current.selectedEntry?.messages[0].text).toBe("B fraîche");

    await act(async () => requests.get("a")!.resolve(snapshot("a", "A tardive")));
    expect(result.current.state.selectedKey).toBe("b");
    expect(result.current.selectedEntry?.messages[0].text).toBe("B fraîche");
    expect(result.current.state.entries.a).toBeUndefined();
  });

  it("aborts at the hard 10 second deadline and ignores a late success", async () => {
    vi.useFakeTimers();
    const pending = deferred<ConversationSnapshot>();
    let signal: AbortSignal | undefined;
    const { result } = renderHook(() => useConversationController({
      fetchSnapshot: (_conversation, requestSignal) => {
        signal = requestSignal;
        return pending.promise;
      },
    }));

    act(() => result.current.replaceSummaries([summary("a")]));
    await act(async () => vi.advanceTimersByTime(9_999));
    expect(result.current.selectedEntry?.loadPhase).toBe("loading");
    expect(signal?.aborted).toBe(false);

    await act(async () => vi.advanceTimersByTime(1));
    expect(signal?.aborted).toBe(true);
    expect(result.current.selectedEntry?.loadPhase).toBe("error");
    expect(result.current.selectedEntry?.loadError).toBe("Le chargement a dépassé la limite de 10 secondes.");

    await act(async () => pending.resolve(snapshot("a", "trop tard")));
    expect(result.current.selectedEntry?.messages).toEqual([]);
    expect(result.current.selectedEntry?.loadPhase).toBe("error");
  });

  it("does not let background polling restart a hung load before its 10 second deadline", async () => {
    vi.useFakeTimers();
    const pending = deferred<ConversationSnapshot>();
    const signals: AbortSignal[] = [];
    const fetchSnapshot = vi.fn<(
      conversation: ConversationSummary,
      signal: AbortSignal,
    ) => Promise<ConversationSnapshot>>((_conversation, signal) => {
      signals.push(signal);
      return pending.promise;
    });
    const { result } = renderHook(() => useConversationController({ fetchSnapshot }));

    act(() => result.current.replaceSummaries([summary("a")]));
    await act(async () => vi.advanceTimersByTime(2_200));
    act(() => result.current.reloadSelected({ background: true }));
    await act(async () => vi.advanceTimersByTime(2_200));
    act(() => result.current.reloadSelected({ background: true }));

    expect(fetchSnapshot).toHaveBeenCalledTimes(1);
    expect(signals[0].aborted).toBe(false);

    await act(async () => vi.advanceTimersByTime(5_600));
    expect(signals[0].aborted).toBe(true);
    expect(result.current.selectedEntry?.loadPhase).toBe("error");
    expect(result.current.selectedEntry?.loadError).toBe("Le chargement a dépassé la limite de 10 secondes.");
  });

  it("renders B's cache immediately while its live refresh is pending", () => {
    let initial = createConversationState([summary("a"), summary("b")], "a");
    initial = conversationReducer(initial, { type: "SWITCH_STARTED", key: "b", epoch: 1 });
    initial = conversationReducer(initial, {
      type: "SNAPSHOT_RECEIVED",
      key: "b",
      epoch: 1,
      snapshot: snapshot("b", "B en cache"),
    });
    const pending = deferred<ConversationSnapshot>();
    const { result } = renderHook(() => useConversationController({
      initialState: initial,
      fetchSnapshot: () => pending.promise,
    }));

    act(() => result.current.selectConversation(summary("b")));

    expect(result.current.state.selectedKey).toBe("b");
    expect(result.current.selectedEntry?.messages[0].text).toBe("B en cache");
    expect(result.current.selectedEntry?.freshness).toBe("cached");
    expect(result.current.selectedEntry?.loadPhase).toBe("loading");
  });

  it("uses the delta-aware background fetcher with the current cache", async () => {
    let initial = createConversationState([summary("b")], "b");
    initial = conversationReducer(initial, { type: "SWITCH_STARTED", key: "b", epoch: 1 });
    initial = conversationReducer(initial, {
      type: "SNAPSHOT_RECEIVED",
      key: "b",
      epoch: 1,
      snapshot: snapshot("b", "cache stable"),
    });
    const fullFetch = vi.fn<() => Promise<ConversationSnapshot>>(() => (
      Promise.reject(new Error("full fetch must not run"))
    ));
    const backgroundFetch = vi.fn<(
      conversation: ConversationSummary,
      entry: typeof initial.entries.b,
      signal: AbortSignal,
    ) => Promise<ConversationSnapshot>>((_conversation, entry) => Promise.resolve(entry.snapshot!));
    const { result } = renderHook(() => useConversationController({
      initialState: initial,
      fetchSnapshot: fullFetch,
      fetchBackgroundSnapshot: backgroundFetch,
    }));

    act(() => result.current.reloadSelected({ background: true }));
    await act(async () => undefined);

    expect(backgroundFetch).toHaveBeenCalledTimes(1);
    expect(backgroundFetch.mock.calls[0][1].messages[0].text).toBe("cache stable");
    expect(fullFetch).not.toHaveBeenCalled();
    expect(result.current.selectedEntry?.freshness).toBe("live");
  });
});
