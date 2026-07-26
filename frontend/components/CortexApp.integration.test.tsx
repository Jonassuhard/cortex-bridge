import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { demoPipeline, demoRuntime, demoSettings, demoTransport } from "@/lib/demo";
import type { ChatRun, ChatRunEvent, MissionDetail } from "@/lib/types";

type ApiMock = (path: string, init?: RequestInit) => Promise<unknown>;
type JsonMock = (path: string, body?: unknown) => Promise<unknown>;

const network = vi.hoisted(() => ({
  api: vi.fn<ApiMock>(),
  postJson: vi.fn<JsonMock>(),
  putJson: vi.fn<JsonMock>(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: network.api, postJson: network.postJson, putJson: network.putJson };
});

import { CortexApp } from "./CortexApp";

const conversation = (key: string) => ({
  url: `https://chatgpt.com/c/${key}`,
  identity: key,
  title: `Conversation ${key.toUpperCase()}`,
  sync_state: "live" as const,
});

const run = (key: string, id = `run-${key}`): ChatRun => ({
  id,
  state: "QUEUED",
  conversation_url: `https://chatgpt.com/c/${key}`,
  text: `message ${key}`,
  created_at: "2026-07-26T12:00:00.000Z",
});

class AppEventSource {
  static instances: AppEventSource[] = [];
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close = vi.fn<() => void>();

  constructor(public readonly url: string) {
    AppEventSource.instances.push(this);
  }

  emit(event: ChatRunEvent) {
    this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>);
  }

  fail() {
    this.onerror?.(new Event("error"));
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((ok, fail) => {
    resolve = ok;
    reject = fail;
  });
  return { promise, resolve, reject };
}

function defaultApi(path: string) {
  if (path === "/api/conversations") return Promise.resolve([conversation("a"), conversation("b")]);
  if (path.startsWith("/api/conversations/snapshot") && path.includes("light=1")) {
    return Promise.resolve({ message_count: 0, last_id: null, streaming: false });
  }
  if (path.startsWith("/api/conversations/snapshot")) {
    const key = path.includes("%2Fb") ? "b" : "a";
    return Promise.resolve({
      url: `https://chatgpt.com/c/${key}`,
      conversation_id: key,
      title: `Conversation ${key.toUpperCase()}`,
      blocker: null,
      composer_present: true,
      send_button_present: true,
      stop_button_present: false,
      streaming: false,
      messages: [],
    });
  }
  if (path === "/api/status") return Promise.resolve(demoRuntime);
  if (path === "/api/transport/status") return Promise.resolve({ ...demoTransport, opt_in_accepted: true });
  if (path === "/api/pipeline/status") return Promise.resolve(demoPipeline);
  if (path === "/api/settings") return Promise.resolve(demoSettings);
  if (path === "/api/models/ollama") return Promise.resolve({ models: [] });
  if (path === "/api/models/chatgpt") return Promise.resolve({ models: [] });
  if (path === "/api/transport/capabilities") return Promise.resolve({ upload_file: true, take_screenshot: true });
  if (path === "/api/onboarding") return Promise.resolve({ completed: true, ready: true, checks: [] });
  return Promise.reject(new Error(`Unexpected GET ${path}`));
}

async function readyApp() {
  render(<CortexApp />);
  await screen.findByRole("heading", { name: "Conversation A" });
  await waitFor(() => expect(composer()).not.toBeDisabled());
}

function composer(): HTMLTextAreaElement {
  return screen.getByRole("textbox", { name: "" }) as HTMLTextAreaElement;
}

beforeEach(() => {
  AppEventSource.instances = [];
  vi.stubGlobal("EventSource", AppEventSource);
  network.api.mockReset().mockImplementation((path: string) => defaultApi(path));
  network.postJson.mockReset();
  network.putJson.mockReset().mockImplementation((_path: string, body: unknown) => Promise.resolve(body));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CortexApp conversation integration", () => {
  it("closes recovery synchronously and cancels the same run after a reconnect advanced its epoch", async () => {
    const cancel = deferred<unknown>();
    let recoverySignal: AbortSignal | null | undefined;
    network.postJson.mockImplementation((path: string) => {
      if (path === "/api/chat/send") return Promise.resolve(run("a"));
      if (path === "/api/chat/runs/run-a/cancel") return cancel.promise;
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    network.api.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/api/chat/runs/run-a") {
        recoverySignal = init?.signal;
        return Promise.resolve({ ...run("a"), state: "WAITING_FOR_CHATGPT" });
      }
      return defaultApi(path);
    });
    const user = userEvent.setup();
    await readyApp();
    await user.click(screen.getByRole("tab", { name: "Message simple" }));
    await user.type(composer(), "message exact");
    await user.click(screen.getByTitle("Envoyer"));
    await waitFor(() => expect(AppEventSource.instances).toHaveLength(1));

    act(() => AppEventSource.instances[0].fail());
    await waitFor(() => expect(AppEventSource.instances).toHaveLength(2));
    expect(recoverySignal).toBeInstanceOf(AbortSignal);
    const recoveredSource = AppEventSource.instances[1];
    await user.click(screen.getByTitle("Arrêter la réponse"));
    expect(recoveredSource.close).toHaveBeenCalledTimes(1);

    act(() => recoveredSource.fail());
    const recoveryCallsBeforeCancelResolution = network.api.mock.calls.filter(
      ([path]) => path === "/api/chat/runs/run-a",
    ).length;
    expect(recoveryCallsBeforeCancelResolution).toBe(1);
    await act(async () => cancel.resolve({}));

    await waitFor(() => expect(screen.queryByTitle("Arrêter la réponse")).not.toBeInTheDocument());
    expect(composer()).not.toBeDisabled();
    expect(AppEventSource.instances).toHaveLength(2);
  });

  it("rekeys a provisional mission from its canonical binding before the next chat send", async () => {
    const missionDetail: MissionDetail = {
      mission: {
        id: "mission-new",
        objective: "Mission canonique",
        workspace: "/tmp",
        state: "COMPLETED",
        created_at: 1,
        executor_kind: "deterministic",
        executor_model_used: null,
        runtime_mode: "live",
        release_eligible: true,
      },
      timeline: {
        conversation_bindings: [{
          conversation_url: "https://chatgpt.com/c/canonical-mission",
          conversation_target: "https://chatgpt.com/c/canonical-mission",
        }],
      },
      awaiting_approval: false,
      stopped: false,
    };
    network.api.mockImplementation((path: string) => {
      if (path === "/api/missions/mission-new") return Promise.resolve(missionDetail);
      return defaultApi(path);
    });
    network.postJson.mockImplementation((path: string) => {
      if (path === "/api/missions") return Promise.resolve({ id: "mission-new", state: "INITIALIZING_MISSION" });
      if (path === "/api/chat/send") return Promise.resolve(run("canonical-mission", "run-canonical"));
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    const user = userEvent.setup();
    await readyApp();
    await user.click(screen.getByRole("button", { name: "Nouvelle mission" }));
    await user.type(composer(), "Mission canonique");
    await user.click(screen.getByTitle("Envoyer"));
    await screen.findByText("Mission terminée");

    await user.click(screen.getByRole("tab", { name: "Message simple" }));
    await user.type(composer(), "suite");
    await user.click(screen.getByTitle("Envoyer"));
    await waitFor(() => {
      const call = network.postJson.mock.calls.find(([path]) => path === "/api/chat/send");
      expect(call?.[1]).toMatchObject({
        conversation_url: "https://chatgpt.com/c/canonical-mission",
        new_conversation: false,
      });
    });
  });

  it("ignores a stale manual A1 retry after A2 starts and leaves the A2 stream followed", async () => {
    const retryA1 = deferred<unknown>();
    let sendCount = 0;
    network.postJson.mockImplementation((path: string) => {
      if (path === "/api/chat/send") {
        sendCount += 1;
        return Promise.resolve(run("a", `run-a-${sendCount}`));
      }
      if (path === "/api/chat/runs/run-a-1/cancel") return Promise.reject(new Error("cancel indisponible"));
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    network.api.mockImplementation((path: string) => {
      if (path === "/api/chat/runs/run-a-1") return retryA1.promise;
      return defaultApi(path);
    });
    const user = userEvent.setup();
    await readyApp();
    await user.click(screen.getByRole("tab", { name: "Message simple" }));
    await user.type(composer(), "A1");
    await user.click(screen.getByTitle("Envoyer"));
    await user.click(await screen.findByTitle("Arrêter la réponse"));
    await screen.findByText("Livraison incertaine");
    await user.click(screen.getByRole("button", { name: "Réessayer la synchronisation" }));
    await waitFor(() => expect(network.api.mock.calls.some(([path]) => path === "/api/chat/runs/run-a-1")).toBe(true));

    await user.clear(composer());
    await user.type(composer(), "A2");
    await user.click(screen.getByTitle("Envoyer"));
    await waitFor(() => expect(AppEventSource.instances).toHaveLength(2));
    const sourceA2 = AppEventSource.instances[1];
    await act(async () => retryA1.resolve({ ...run("a", "run-a-1"), state: "WAITING_FOR_CHATGPT" }));

    expect(sourceA2.close).not.toHaveBeenCalled();
    expect(AppEventSource.instances).toHaveLength(2);
    act(() => sourceA2.emit({ seq: 2, ts: "now", type: "stream", payload: { text: "A2 reste suivi" } }));
    expect(await screen.findByText("A2 reste suivi")).toBeInTheDocument();
  });

  it("rekeys a provisional chat when manual terminal recovery proves its canonical URL", async () => {
    let sendCount = 0;
    network.postJson.mockImplementation((path: string) => {
      if (path === "/api/chat/send") {
        sendCount += 1;
        return Promise.resolve({
          ...run("provisional", `run-provisional-${sendCount}`),
          conversation_url: sendCount === 1 ? "https://chatgpt.com/" : "https://chatgpt.com/c/canonical-manual",
        });
      }
      if (path === "/api/chat/runs/run-provisional-1/cancel") return Promise.reject(new Error("cancel indisponible"));
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    network.api.mockImplementation((path: string) => {
      if (path === "/api/chat/runs/run-provisional-1") {
        return Promise.resolve({
          ...run("provisional", "run-provisional-1"),
          state: "COMPLETED",
          conversation_url: "https://chatgpt.com/",
          canonical_url: "https://chatgpt.com/c/canonical-manual",
          delivered_at: "now",
          completed_at: "now",
        });
      }
      return defaultApi(path);
    });
    const user = userEvent.setup();
    await readyApp();
    await user.click(screen.getByRole("button", { name: /Nouveau chat/ }));
    await user.click(screen.getByRole("tab", { name: "Message simple" }));
    await user.type(composer(), "premier");
    await user.click(screen.getByTitle("Envoyer"));
    await user.click(await screen.findByTitle("Arrêter la réponse"));
    await screen.findByText("Livraison incertaine");
    await user.click(screen.getByRole("button", { name: "Réessayer la synchronisation" }));
    await waitFor(() => expect(screen.queryByText("Livraison incertaine")).not.toBeInTheDocument());

    await user.type(composer(), "suite canonique");
    await user.click(screen.getByTitle("Envoyer"));
    await waitFor(() => {
      const sends = network.postJson.mock.calls.filter(([path]) => path === "/api/chat/send");
      expect(sends.at(-1)?.[1]).toMatchObject({
        conversation_url: "https://chatgpt.com/c/canonical-manual",
        new_conversation: false,
      });
    });
  });

  it("coalesces terminal refreshes and never polls the unused mission list", async () => {
    network.postJson.mockImplementation((path: string, body?: unknown) => {
      if (path === "/api/chat/send") {
        const text = (body as { text?: string } | undefined)?.text || "";
        const key = text === "A" ? "a" : "b";
        return Promise.resolve({ ...run(key), text });
      }
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    const user = userEvent.setup();
    await readyApp();
    await user.click(screen.getByRole("tab", { name: "Message simple" }));
    await user.type(composer(), "A");
    await user.click(screen.getByTitle("Envoyer"));
    await user.click(screen.getByRole("option", { name: /Conversation B/ }));
    await user.type(composer(), "B");
    await user.click(screen.getByTitle("Envoyer"));
    await waitFor(() => expect(AppEventSource.instances).toHaveLength(2));
    const conversationsBefore = network.api.mock.calls.filter(([path]) => path === "/api/conversations").length;

    act(() => {
      AppEventSource.instances[0].emit({ seq: 1, ts: "now", type: "complete", payload: { text: "A" } });
      AppEventSource.instances[1].emit({ seq: 1, ts: "now", type: "complete", payload: { text: "B" } });
    });
    await waitFor(() => {
      const count = network.api.mock.calls.filter(([path]) => path === "/api/conversations").length;
      expect(count).toBe(conversationsBefore + 1);
    }, { timeout: 1_500 });
    expect(network.api.mock.calls.some(([path]) => path === "/api/missions")).toBe(false);
  });

  it("cancels a pending terminal refresh on unmount", async () => {
    network.postJson.mockImplementation((path: string) => (
      path === "/api/chat/send" ? Promise.resolve(run("a")) : Promise.reject(new Error(path))
    ));
    const user = userEvent.setup();
    const rendered = render(<CortexApp />);
    await screen.findByRole("heading", { name: "Conversation A" });
    await user.click(screen.getByRole("tab", { name: "Message simple" }));
    await user.type(composer(), "A");
    await user.click(screen.getByTitle("Envoyer"));
    await waitFor(() => expect(AppEventSource.instances).toHaveLength(1));
    const conversationsBefore = network.api.mock.calls.filter(([path]) => path === "/api/conversations").length;
    act(() => AppEventSource.instances[0].emit({ seq: 1, ts: "now", type: "complete", payload: {} }));
    rendered.unmount();
    await new Promise((resolve) => setTimeout(resolve, 950));

    const conversationsAfter = network.api.mock.calls.filter(([path]) => path === "/api/conversations").length;
    expect(conversationsAfter).toBe(conversationsBefore);
  });
});
