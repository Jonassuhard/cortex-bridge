import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { demoPipeline, demoRuntime, demoSettings, demoTransport } from "@/lib/demo";
import type { ChatRun, ChatRunEvent, MissionDetail } from "@/lib/types";

type ApiMock = (path: string, init?: RequestInit) => Promise<unknown>;
type JsonMock = (path: string, body?: unknown, init?: RequestInit) => Promise<unknown>;

const network = vi.hoisted(() => ({
  api: vi.fn<ApiMock>(),
  postJson: vi.fn<JsonMock>(),
  putJson: vi.fn<JsonMock>(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: network.api, postJson: network.postJson, putJson: network.putJson };
});

import { CortexApp, projectPipelineForConversation } from "./CortexApp";

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
  if (path.startsWith("/api/pipeline/status")) return Promise.resolve(demoPipeline);
  if (path === "/api/settings") return Promise.resolve(demoSettings);
  if (path === "/api/models/ollama") return Promise.resolve({ models: [] });
  if (path === "/api/models/chatgpt") return Promise.resolve({ models: [] });
  if (path === "/api/transport/capabilities") return Promise.resolve({ upload_file: true, take_screenshot: true });
  if (path === "/api/chrome-extension/status") {
    return Promise.resolve({ state: "paired", extension_connected: true, paired: true, pending_commands: 0 });
  }
  if (path === "/api/onboarding") return Promise.resolve({ completed: true, ready: true, checks: [] });
  return Promise.reject(new Error(`Unexpected GET ${path}`));
}

async function readyApp() {
  const rendered = render(<CortexApp />);
  await screen.findByRole("heading", { name: "Conversation A" });
  await waitFor(() => expect(composer()).not.toBeDisabled());
  return rendered;
}

function composer(): HTMLTextAreaElement {
  return screen.getByRole("textbox", { name: "Message à envoyer" }) as HTMLTextAreaElement;
}

beforeEach(() => {
  AppEventSource.instances = [];
  vi.stubGlobal("EventSource", AppEventSource);
  network.api.mockReset().mockImplementation((path: string) => defaultApi(path));
  network.postJson.mockReset();
  network.putJson.mockReset().mockImplementation((_path: string, body: unknown) => Promise.resolve(body));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("CortexApp conversation integration", () => {
  it("refreshes conversations after Chrome becomes connected", async () => {
    let conversationCalls = 0;
    network.api.mockImplementation((path: string) => {
      if (path === "/api/conversations") {
        conversationCalls += 1;
        return conversationCalls === 1
          ? Promise.reject(new Error("extension not paired yet"))
          : Promise.resolve([conversation("recovered")]);
      }
      return defaultApi(path);
    });
    network.postJson.mockImplementation((path: string) => {
      if (path === "/api/chrome-extension/pairing") {
        return Promise.resolve({ token: "a".repeat(43), expires_in_seconds: 60 });
      }
      if (path === "/api/chrome-extension/open") {
        return Promise.resolve({
          code: "CONNECTED",
          state: "connected",
          title: "ChatGPT connecté",
          message: "Cortex est lié à cet onglet Chrome.",
          recoverable: false,
          driver: "chrome_extension",
          url: "https://chatgpt.com/",
          tab_id: 42,
          window_id: 7,
        });
      }
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    const user = userEvent.setup();
    render(<CortexApp />);
    await waitFor(() => expect(conversationCalls).toBe(1));

    await user.click(screen.getByRole("button", { name: "Ouvrir et connecter ChatGPT" }));

    await waitFor(() => expect(conversationCalls).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(document.querySelectorAll(".conversation-row")).toHaveLength(1));
    expect(conversationCalls).toBe(2);
  });

  it("pairs Chrome, opens ChatGPT, explains login, and retries the existing tab", async () => {
    const token = "a".repeat(43);
    const postMessage = vi.spyOn(window, "postMessage").mockImplementation(() => undefined);
    network.postJson.mockImplementation((path: string) => {
      if (path === "/api/chrome-extension/pairing") {
        return Promise.resolve({ token, expires_in_seconds: 60 });
      }
      if (path === "/api/chrome-extension/open") {
        return Promise.resolve({
          code: "LOGIN_REQUIRED",
          state: "manual_action",
          title: "Connexion à ChatGPT requise",
          message: "ChatGPT est ouvert dans Chrome, mais tu n’es pas connecté. Connecte-toi dans l’onglet ChatGPT, puis réessaie.",
          recoverable: true,
          driver: "chrome_extension",
          url: "https://chatgpt.com/auth/login",
          tab_id: 42,
          window_id: 7,
        });
      }
      if (path === "/api/chrome-extension/retry") {
        return Promise.resolve({
          code: "CONNECTED",
          state: "connected",
          title: "ChatGPT connecté",
          message: "Cortex est lié à cet onglet Chrome.",
          recoverable: false,
          driver: "chrome_extension",
          url: "https://chatgpt.com/c/abc",
          tab_id: 42,
          window_id: 7,
        });
      }
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    const user = userEvent.setup();
    await readyApp();

    await user.click(screen.getByRole("button", { name: "Ouvrir et connecter ChatGPT" }));

    expect(await screen.findByRole("heading", { name: "Connexion à ChatGPT requise" })).toBeInTheDocument();
    expect(postMessage).toHaveBeenCalledWith(
      { source: "cortex-bridge-ui", type: "CORTEX_PAIR_EXTENSION", token },
      window.location.origin,
    );
    expect(network.postJson.mock.calls.map(([path]) => path)).toContain("/api/chrome-extension/open");

    await user.click(screen.getByRole("button", { name: "Réessayer" }));
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Connexion à ChatGPT requise" })).not.toBeInTheDocument();
    });
    expect(network.postJson.mock.calls.map(([path]) => path)).toContain("/api/chrome-extension/retry");
  });

  it("reloads Cortex and resumes pairing after the backend reports an outdated extension", async () => {
    const token = "b".repeat(43);
    let openCalls = 0;
    const reload = vi.spyOn(window.history, "go").mockImplementation(() => undefined);
    vi.spyOn(window, "postMessage").mockImplementation(() => undefined);
    network.postJson.mockImplementation((path: string) => {
      if (path === "/api/chrome-extension/pairing") {
        return Promise.resolve({ token, expires_in_seconds: 60 });
      }
      if (path === "/api/chrome-extension/open") {
        openCalls += 1;
        if (openCalls === 1) {
          return Promise.resolve({
            code: "EXTENSION_OUTDATED",
            state: "manual_action",
            title: "Extension Cortex à recharger",
            message: "Recharge l’extension Cortex Bridge, puis relance la connexion.",
            recoverable: true,
            driver: "chrome_extension",
            url: null,
            tab_id: null,
            window_id: null,
          });
        }
        return Promise.resolve({
          code: "CONNECTED",
          state: "connected",
          title: "ChatGPT connecté",
          message: "Cortex est lié à cet onglet Chrome.",
          recoverable: false,
          driver: "chrome_extension",
          url: "https://chatgpt.com/",
          tab_id: 42,
          window_id: 7,
        });
      }
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    const user = userEvent.setup();
    const rendered = await readyApp();

    await user.click(screen.getByRole("button", { name: "Ouvrir et connecter ChatGPT" }));
    expect(await screen.findByRole("heading", { name: "Extension Cortex à recharger" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(reload).toHaveBeenCalledWith(0);
    expect(window.sessionStorage.getItem("cortex:pair-after-extension-reload")).toBe("1");

    const pathsBeforeReload = network.postJson.mock.calls.map(([path]) => path);
    expect(pathsBeforeReload.filter((path) => path === "/api/chrome-extension/pairing")).toHaveLength(1);
    expect(pathsBeforeReload.filter((path) => path === "/api/chrome-extension/open")).toHaveLength(1);

    rendered.unmount();
    render(<CortexApp />);
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Extension Cortex à recharger" })).not.toBeInTheDocument();
    });

    const paths = network.postJson.mock.calls.map(([path]) => path);
    expect(paths.filter((path) => path === "/api/chrome-extension/pairing")).toHaveLength(2);
    expect(paths.filter((path) => path === "/api/chrome-extension/open")).toHaveLength(2);
    expect(paths).not.toContain("/api/chrome-extension/retry");
    expect(window.sessionStorage.getItem("cortex:pair-after-extension-reload")).toBeNull();
  });

  it("neutralizes every mission-specific pipeline field when no selected mission matches", () => {
    const projected = projectPipelineForConversation({
      ...demoPipeline,
      active_mission_id: "mission-a-secret",
      active_mission_state: "EXECUTING_LOCAL_ACTION_SECRET",
      components: [{ id: "secret-component", label: "A_SECRET_COMPONENT", state: "running", detail: "A" }],
      events: [{ id: "secret-event", ts: "now", label: "A_SECRET_EVENT" }],
      queue_pending: 73,
      runtime_execution: {
        task_id: "A_SECRET_TASK",
        state: "A_SECRET_RUNTIME_STATE",
        active: true,
        observed_at: "A_SECRET_TIME",
        executor_kind: "ollama",
        executor_model_used: "A_SECRET_MODEL",
        runtime_mode: "development_fixture",
        release_eligible: true,
      },
      latency: { transport_ms: 11, local_model_ms: 22, total_iteration_ms: 33 },
    }, null);

    expect(projected).toMatchObject({
      active_mission_id: null,
      active_mission_state: null,
      components: [],
      events: [],
      queue_pending: 0,
      runtime_execution: {
        task_id: null,
        state: "IDLE",
        active: false,
        observed_at: null,
        executor_kind: "unavailable",
        executor_model_used: null,
        runtime_mode: "live",
        release_eligible: false,
      },
      latency: { transport_ms: null, local_model_ms: null, total_iteration_ms: null },
    });
  });

  it("blocks Enter and screenshot while A1 is non-terminal without closing its source", async () => {
    let runIndex = 0;
    network.postJson.mockImplementation((path: string) => {
      if (path === "/api/chat/send" || path === "/api/chat/send-screenshot") {
        runIndex += 1;
        return Promise.resolve(run("a", `run-a-${runIndex}`));
      }
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    const user = userEvent.setup();
    await readyApp();

    await user.type(composer(), "A1");
    await user.click(screen.getByTitle("Envoyer"));
    await waitFor(() => expect(AppEventSource.instances).toHaveLength(1));
    const sourceA1 = AppEventSource.instances[0];

    await user.clear(composer());
    await user.type(composer(), "A2{enter}");
    await user.click(screen.getByTitle("Capturer l'onglet ChatGPT et l'envoyer"));

    const executionPosts = network.postJson.mock.calls.filter(([path]) => (
      path === "/api/chat/send" || path === "/api/chat/send-screenshot" || path === "/api/missions"
    ));
    expect(executionPosts).toHaveLength(1);
    expect(AppEventSource.instances).toHaveLength(1);
    expect(sourceA1.close).not.toHaveBeenCalled();
    expect(screen.getByText("Une réponse est déjà en cours pour cette conversation.")).toBeInTheDocument();
  });

  it("deduplicates cancel, keeps the healthy source until terminal truth, and ignores a late POST failure", async () => {
    const cancel = deferred<unknown>();
    let cancelSignal: AbortSignal | null | undefined;
    network.postJson.mockImplementation((path: string, _body?: unknown, init?: RequestInit) => {
      if (path === "/api/chat/send") return Promise.resolve(run("a"));
      if (path === "/api/chat/runs/run-a/cancel") {
        cancelSignal = init?.signal;
        return cancel.promise;
      }
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    const user = userEvent.setup();
    await readyApp();

    await user.type(composer(), "A active");
    await user.click(screen.getByTitle("Envoyer"));
    const source = AppEventSource.instances[0];
    const stop = await screen.findByTitle("Arrêter la réponse");

    await user.click(stop);
    await user.click(stop);
    expect(network.postJson.mock.calls.filter(([path]) => path === "/api/chat/runs/run-a/cancel")).toHaveLength(1);
    expect(source.close).not.toHaveBeenCalled();
    expect(stop).toBeDisabled();

    act(() => source.emit({ seq: 9, ts: "now", type: "cancelled", payload: {} }));
    await act(async () => cancel.reject(new Error("échec tardif")));
    await waitFor(() => expect(screen.queryByTitle("Arrêter la réponse")).not.toBeInTheDocument());
    expect(screen.queryByText("Livraison incertaine")).not.toBeInTheDocument();
    expect(cancelSignal?.aborted).toBe(true);
    expect(source.close).toHaveBeenCalledTimes(1);
  });

  it("aborts a hung cancel on unmount", async () => {
    let cancelSignal: AbortSignal | null | undefined;
    network.postJson.mockImplementation((path: string, _body?: unknown, init?: RequestInit) => {
      if (path === "/api/chat/send") return Promise.resolve(run("a"));
      if (path === "/api/chat/runs/run-a/cancel") {
        cancelSignal = init?.signal;
        return new Promise(() => undefined);
      }
      return Promise.reject(new Error(path));
    });
    const user = userEvent.setup();
    const rendered = await readyApp();

    await user.type(composer(), "A active");
    await user.click(screen.getByTitle("Envoyer"));
    await user.click(await screen.findByTitle("Arrêter la réponse"));
    rendered.unmount();

    expect(cancelSignal).toBeInstanceOf(AbortSignal);
    expect(cancelSignal?.aborted).toBe(true);
  });

  it("times out a hung cancel without closing its healthy source or stranding the action", async () => {
    let cancelSignal: AbortSignal | null | undefined;
    network.postJson.mockImplementation((path: string, _body?: unknown, init?: RequestInit) => {
      if (path === "/api/chat/send") return Promise.resolve(run("a"));
      if (path === "/api/chat/runs/run-a/cancel") {
        cancelSignal = init?.signal;
        return new Promise(() => undefined);
      }
      return Promise.reject(new Error(path));
    });
    const user = userEvent.setup();
    await readyApp();

    await user.type(composer(), "A active");
    await user.click(screen.getByTitle("Envoyer"));
    const source = AppEventSource.instances[0];
    const stop = await screen.findByTitle("Arrêter la réponse");

    vi.useFakeTimers();
    fireEvent.click(stop);
    await vi.advanceTimersByTimeAsync(10_000);

    expect(cancelSignal?.aborted).toBe(true);
    expect(source.close).not.toHaveBeenCalled();
    vi.useRealTimers();
    await waitFor(() => expect(screen.getByTitle("Arrêter la réponse")).toBeEnabled());
    expect(screen.queryByText("Livraison incertaine")).not.toBeInTheDocument();
  });

  it("deduplicates a manual retry, disables its action, and aborts it on unmount", async () => {
    let retrySignal: AbortSignal | null | undefined;
    let recoveryCount = 0;
    network.postJson.mockImplementation((path: string) => {
      if (path === "/api/chat/send") return Promise.resolve(run("a"));
      return Promise.reject(new Error(path));
    });
    network.api.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/api/chat/runs/run-a") {
        recoveryCount += 1;
        if (recoveryCount <= 3) return Promise.reject(new Error("recovery indisponible"));
        retrySignal = init?.signal;
        return new Promise(() => undefined);
      }
      return defaultApi(path);
    });
    const user = userEvent.setup();
    const rendered = await readyApp();

    await user.type(composer(), "A incertaine");
    await user.click(screen.getByTitle("Envoyer"));
    vi.useFakeTimers();
    act(() => AppEventSource.instances[0].fail());
    await act(async () => vi.advanceTimersByTimeAsync(2_000));
    vi.useRealTimers();
    const retry = await screen.findByRole("button", { name: "Réessayer la synchronisation" });
    const callsBeforeManualRetry = network.api.mock.calls.filter(
      ([path]) => path === "/api/chat/runs/run-a",
    ).length;

    await user.click(retry);
    await user.click(retry);
    expect(network.api.mock.calls.filter(([path]) => path === "/api/chat/runs/run-a"))
      .toHaveLength(callsBeforeManualRetry + 1);
    expect(retry).toBeDisabled();
    rendered.unmount();
    expect(retrySignal?.aborted).toBe(true);
  });

  it("times out a hung attachment POST, preserves the exact draft and File, and ignores its late result", async () => {
    const attachmentUpload = deferred<unknown>();
    let uploadSignal: AbortSignal | null | undefined;
    network.postJson.mockImplementation((path: string, _body?: unknown, init?: RequestInit) => {
      if (path === "/api/chat/attachments") {
        uploadSignal = init?.signal;
        return attachmentUpload.promise;
      }
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    const user = userEvent.setup();
    const rendered = await readyApp();

    await user.type(composer(), "preuve exacte");
    const file = new File(["preuve"], "preuve.txt", { type: "text/plain" });
    const input = rendered.container.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("file input missing");
    await user.upload(input, file);

    vi.stubGlobal("FileReader", class {
      result: string | ArrayBuffer | null = "data:text/plain;base64,cHJldXZl";
      error: DOMException | null = null;
      onload: ((event: ProgressEvent<FileReader>) => void) | null = null;
      onerror: ((event: ProgressEvent<FileReader>) => void) | null = null;
      readAsDataURL() {
        this.onload?.({} as ProgressEvent<FileReader>);
      }
    });
    vi.useFakeTimers();
    fireEvent.click(screen.getByTitle("Envoyer"));
    await act(async () => {
      await Promise.resolve();
      expect(uploadSignal).toBeInstanceOf(AbortSignal);
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(uploadSignal?.aborted).toBe(true);
    expect(composer()).toHaveValue("preuve exacte");
    expect(screen.getByText("preuve.txt")).toBeInTheDocument();
    expect(screen.getByText(/délai.*10 secondes/i)).toBeInTheDocument();
    expect(screen.getByTitle("Envoyer")).not.toBeDisabled();
    await act(async () => attachmentUpload.resolve({ path: "/tmp/late", name: "preuve.txt", kind: "file" }));
    expect(network.postJson.mock.calls.some(([path]) => path === "/api/chat/send-with-attachment")).toBe(false);
  });

  it("removes every mission-A inspector detail on B and restores it only when A is selected again", async () => {
    const missionA: MissionDetail = {
      mission: {
        id: "mission-a",
        objective: "Mission A isolée",
        workspace: "/tmp/a",
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
    };
    network.api.mockImplementation((path: string) => {
      if (path.startsWith("/api/pipeline/status")) {
        return Promise.resolve({
          ...demoPipeline,
          active_mission_id: "mission-a",
          active_mission_state: "EXECUTING_LOCAL_ACTION",
          components: [
            ...demoPipeline.components,
            { id: "mission-a-only", label: "Composant mission A", state: "running", detail: "A seulement" },
          ],
          events: [
            {
              id: "mission-a-event",
              ts: "2026-07-26T12:00:00.000Z",
              label: "Événement mission A",
              detail: "MISSION_A_EVENT_SECRET",
            },
          ],
          latency: { transport_ms: 654_321, local_model_ms: 765_432, total_iteration_ms: 876_543 },
          runtime_execution: {
            task_id: "MISSION_A_TASK_SECRET",
            state: "MISSION_A_RUNTIME_SECRET",
            active: true,
            observed_at: "2026-07-26T12:34:56.000Z",
            executor_kind: "ollama",
            executor_model_used: "MISSION_A_MODEL_SECRET",
            runtime_mode: "development_fixture",
            release_eligible: false,
          },
        });
      }
      if (path === "/api/missions/mission-a") return Promise.resolve(missionA);
      return defaultApi(path);
    });
    network.postJson.mockImplementation((path: string) => {
      if (path === "/api/missions") return Promise.resolve({ id: "mission-a", state: "EXECUTING_LOCAL_ACTION" });
      return Promise.reject(new Error(path));
    });
    const user = userEvent.setup();
    await readyApp();
    await user.type(composer(), "Mission A isolée");
    await user.click(screen.getByRole("button", { name: "Exécuter…" }));
    await user.click(screen.getByRole("button", { name: "Démarrer en lecture seule" }));
    await screen.findByText("Mission A isolée");
    await user.click(screen.getByTitle("Détails du bridge (pipeline, logs, transport)"));
    const inspector = within(screen.getByLabelText("État de la pipeline"));
    expect(inspector.getByText("Composant mission A")).toBeInTheDocument();
    expect(inspector.getByText("Événement mission A")).toBeInTheDocument();
    expect(inspector.getByText("MISSION_A_MODEL_SECRET")).toBeInTheDocument();
    expect(screen.getAllByText(/14m 37s/).length).toBeGreaterThan(0);
    expect(inspector.getByRole("button", { name: "Pause" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /Conversation B/ }));
    expect(inspector.queryByText("Composant mission A")).not.toBeInTheDocument();
    expect(inspector.queryByText("Événement mission A")).not.toBeInTheDocument();
    expect(screen.queryAllByText("MISSION_A_MODEL_SECRET")).toHaveLength(0);
    expect(screen.queryByText("MISSION_A_EVENT_SECRET")).not.toBeInTheDocument();
    expect(screen.queryByText("MISSION_A_RUNTIME_SECRET")).not.toBeInTheDocument();
    expect(screen.queryByText("MISSION_A_TASK_SECRET")).not.toBeInTheDocument();
    expect(screen.queryAllByText(/14m 37s/)).toHaveLength(0);
    expect(inspector.getByRole("button", { name: "Pause" })).toBeDisabled();
    expect(inspector.getByRole("button", { name: "Annuler" })).toBeDisabled();
    expect(screen.getAllByText("ChatGPT").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Exécuteur").length).toBeGreaterThan(0);
    expect(screen.getByTitle("Statut de la connexion ChatGPT")).toHaveTextContent("Connecté");
    expect(screen.getByTitle("Statut de l'agent exécutif local")).toHaveTextContent("Disponible");

    await user.click(screen.getByRole("button", { name: /Conversation A/ }));
    expect(inspector.getByText("Composant mission A")).toBeInTheDocument();
    expect(inspector.getByText("Événement mission A")).toBeInTheDocument();
    expect(inspector.getByText("MISSION_A_MODEL_SECRET")).toBeInTheDocument();
    expect(screen.getAllByText(/14m 37s/).length).toBeGreaterThan(0);
    expect(inspector.getByRole("button", { name: "Pause" })).toBeEnabled();
  });

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

    await user.type(composer(), "message exact");
    await user.click(screen.getByTitle("Envoyer"));
    await waitFor(() => expect(AppEventSource.instances).toHaveLength(1));

    act(() => AppEventSource.instances[0].fail());
    await waitFor(() => expect(AppEventSource.instances).toHaveLength(2));
    expect(recoverySignal).toBeInstanceOf(AbortSignal);
    const recoveredSource = AppEventSource.instances[1];
    await user.click(screen.getByTitle("Arrêter la réponse"));
    expect(recoveredSource.close).not.toHaveBeenCalled();

    act(() => recoveredSource.fail());
    const recoveryCallsBeforeCancelResolution = network.api.mock.calls.filter(
      ([path]) => path === "/api/chat/runs/run-a",
    ).length;
    expect(recoveryCallsBeforeCancelResolution).toBe(1);
    await act(async () => cancel.resolve({
      ...run("a"),
      state: "CANCELLED",
      completed_at: "now",
    }));

    await waitFor(() => expect(screen.queryByTitle("Arrêter la réponse")).not.toBeInTheDocument());
    expect(recoveredSource.close).toHaveBeenCalledTimes(1);
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
    await user.click(screen.getByRole("button", { name: /Nouvelle conversation/ }));
    await user.type(composer(), "Mission canonique");
    await user.click(screen.getByRole("button", { name: "Exécuter…" }));
    await user.click(screen.getByRole("button", { name: "Démarrer en lecture seule" }));
    await screen.findByText("Mission terminée");

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

  it("keeps A1 recovery owned and blocks A2 Enter without closing or posting", async () => {
    const retryA1 = deferred<unknown>();
    let retryA1Signal: AbortSignal | null | undefined;
    let sendCount = 0;
    let recoveryCount = 0;
    network.postJson.mockImplementation((path: string) => {
      if (path === "/api/chat/send") {
        sendCount += 1;
        return Promise.resolve(run("a", `run-a-${sendCount}`));
      }
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    network.api.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/api/chat/runs/run-a-1") {
        recoveryCount += 1;
        if (recoveryCount <= 3) return Promise.reject(new Error("recovery indisponible"));
        retryA1Signal = init?.signal;
        return retryA1.promise;
      }
      return defaultApi(path);
    });
    const user = userEvent.setup();
    await readyApp();

    await user.type(composer(), "A1");
    await user.click(screen.getByTitle("Envoyer"));
    vi.useFakeTimers();
    act(() => AppEventSource.instances[0].fail());
    await act(async () => vi.advanceTimersByTimeAsync(2_000));
    vi.useRealTimers();
    await screen.findAllByText("Livraison incertaine");
    await user.click(screen.getByRole("button", { name: "Réessayer la synchronisation" }));
    await waitFor(() => expect(network.api.mock.calls.some(([path]) => path === "/api/chat/runs/run-a-1")).toBe(true));

    await user.clear(composer());
    await user.type(composer(), "A2");
    expect(composer()).not.toBeDisabled();
    expect(screen.getByTitle("Envoyer")).toBeDisabled();
    fireEvent.keyDown(composer(), { key: "Enter" });
    expect(network.postJson.mock.calls.filter(([path]) => path === "/api/chat/send")).toHaveLength(1);
    expect(AppEventSource.instances).toHaveLength(1);
    expect(retryA1Signal?.aborted).toBe(false);
    await act(async () => retryA1.resolve({ ...run("a", "run-a-1"), state: "WAITING_FOR_CHATGPT" }));

    expect(AppEventSource.instances).toHaveLength(2);
    const recoveredA1 = AppEventSource.instances[1];
    expect(recoveredA1.close).not.toHaveBeenCalled();
    act(() => recoveredA1.emit({ seq: 2, ts: "now", type: "stream", payload: { text: "A1 reste suivi" } }));
    expect(await screen.findByText("A1 reste suivi")).toBeInTheDocument();
    expect(composer()).toHaveValue("A2");
  });

  it("rekeys a provisional chat when manual terminal recovery proves its canonical URL", async () => {
    let sendCount = 0;
    let recoveryCount = 0;
    network.postJson.mockImplementation((path: string) => {
      if (path === "/api/chat/send") {
        sendCount += 1;
        return Promise.resolve({
          ...run("provisional", `run-provisional-${sendCount}`),
          conversation_url: sendCount === 1 ? "https://chatgpt.com/" : "https://chatgpt.com/c/canonical-manual",
        });
      }
      return Promise.reject(new Error(`Unexpected POST ${path}`));
    });
    network.api.mockImplementation((path: string) => {
      if (path === "/api/chat/runs/run-provisional-1") {
        recoveryCount += 1;
        if (recoveryCount <= 3) return Promise.reject(new Error("recovery indisponible"));
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
    await user.click(screen.getByRole("button", { name: /Nouvelle conversation/ }));

    await user.type(composer(), "premier");
    await user.click(screen.getByTitle("Envoyer"));
    vi.useFakeTimers();
    act(() => AppEventSource.instances.at(-1)?.fail());
    await act(async () => vi.advanceTimersByTimeAsync(2_000));
    vi.useRealTimers();
    await screen.findAllByText("Livraison incertaine");
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

    await user.type(composer(), "A");
    await user.click(screen.getByTitle("Envoyer"));
    await user.click(screen.getByRole("button", { name: /Conversation B/ }));
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
