import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { demoPipeline, demoSettings } from "@/lib/demo";
import {
  conversationReducer,
  createConversationState,
  type ConversationEvent,
  type ConversationState,
} from "@/lib/conversation-state";
import type { ChatRun, ConversationSummary } from "@/lib/types";
import { ChatWorkspace } from "./ChatWorkspace";

const summary = (key: string): ConversationSummary => ({
  url: `https://chatgpt.com/c/${key}`,
  identity: key,
  title: `Conversation ${key.toUpperCase()}`,
});

const acceptedRun = (key: string): ChatRun => ({
  id: `run-${key}`,
  state: "QUEUED",
  conversation_url: `https://chatgpt.com/c/${key}`,
  text: `texte ${key}`,
  created_at: "2026-07-26T12:00:00.000Z",
});

function ControlledWorkspace({
  initialState = createConversationState([summary("a"), summary("b")], "a"),
  refusedKeys = new Set<string>(),
  pendingKeys = new Map<string, Promise<void>>(),
  onRetryRecovery = () => undefined,
}: {
  initialState?: ConversationState;
  refusedKeys?: Set<string>;
  pendingKeys?: Map<string, Promise<void>>;
  onRetryRecovery?: (key: string) => void;
}) {
  const [state, setState] = useState(initialState);
  const dispatch = (event: ConversationEvent) => setState((current) => conversationReducer(current, event));
  const entry = state.selectedKey ? state.entries[state.selectedKey] : null;

  const send = async (key: string, clearAttachment = true) => {
    dispatch({ type: "REQUEST_STARTED", request: "send", key });
    await pendingKeys.get(key);
    if (refusedKeys.has(key)) {
      dispatch({
        type: "REQUEST_FAILED",
        request: "send",
        key,
        status: 409,
        error: "Votre brouillon est conservé.",
      });
      return false;
    }
    dispatch({
      type: "RUN_EVENT",
      key,
      runId: `run-${key}`,
      streamEpoch: 1,
      run: acceptedRun(key),
      accepted: true,
      submittedDraft: state.entries[key]?.draft || "",
      submittedAttachment: clearAttachment ? state.entries[key]?.attachment || null : null,
    });
    dispatch({
      type: "RUN_EVENT",
      key,
      runId: `run-${key}`,
      streamEpoch: 1,
      event: { seq: 1, ts: "2026-07-26T12:00:01.000Z", type: "delivery", payload: {} },
    });
    return true;
  };

  return (
    <>
      <nav aria-label="Sélection de test">
        <button onClick={() => dispatch({ type: "SELECT", key: "a" })}>Sélectionner A</button>
        <button onClick={() => dispatch({ type: "SELECT", key: "b" })}>Sélectionner B</button>
      </nav>
      <ChatWorkspace
        conversationKey={state.selectedKey}
        conversation={entry?.summary || null}
        messages={entry?.messages || []}
        loadingMessages={entry?.loadPhase === "loading"}
        sending={entry?.sendPending || false}
        draft={entry?.draft || ""}
        attachment={entry?.attachment || null}
        chatRun={entry?.run || null}
        mission={entry?.mission || null}
        pipeline={demoPipeline}
        settings={demoSettings}
        inspectorOpen={false}
        sidebarCollapsed={false}
        capabilities={{ upload_file: true, take_screenshot: true }}
        rekeyConflict={state.rekeyConflict}
        onDraftChange={(key, draft) => dispatch({ type: "DRAFT_CHANGED", key, draft })}
        onAttachmentStaged={(key, attachment) => dispatch({ type: "ATTACHMENT_STAGED", key, attachment })}
        onToggleSidebar={() => undefined}
        onToggleInspector={() => undefined}
        onSendChat={(key) => send(key)}
        onSendAttachment={(key) => send(key)}
        onSendScreenshot={(key) => send(key, false)}
        onStartMission={(key) => send(key)}
        onCancelChat={() => undefined}
        onRetryChatRecovery={onRetryRecovery}
        onResolveRekeyConflict={(fromKey, toKey) => dispatch({
          type: "RESOLVE_REKEY_CONFLICT",
          fromKey,
          toKey,
        })}
        onPauseMission={() => undefined}
        onResumeMission={() => undefined}
        onCancelMission={() => undefined}
        onApprove={() => undefined}
        onReject={() => undefined}
      />
    </>
  );
}

function fileInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("file input missing");
  return input;
}

describe("ChatWorkspace controlled composer", () => {
  it("allows B to submit while A's POST is still pending", async () => {
    let resolveA!: () => void;
    const pendingA = new Promise<void>((resolve) => { resolveA = resolve; });
    const user = userEvent.setup();
    render(<ControlledWorkspace pendingKeys={new Map([["a", pendingA]])} />);
    await user.click(screen.getByRole("tab", { name: "Message simple" }));
    await user.type(screen.getByRole("textbox"), "A en attente");
    await user.click(screen.getByTitle("Envoyer"));

    await user.click(screen.getByRole("button", { name: "Sélectionner B" }));
    expect(screen.getByRole("textbox")).not.toBeDisabled();
    await user.type(screen.getByRole("textbox"), "B concurrente");
    await user.click(screen.getByTitle("Envoyer"));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(""));

    resolveA();
    await user.click(screen.getByRole("button", { name: "Sélectionner A" }));
    await waitFor(() => expect(screen.getByTitle("Arrêter la réponse")).toBeInTheDocument());
  });

  it("shows independent A and B drafts and attachments across switches", async () => {
    const user = userEvent.setup();
    const { container } = render(<ControlledWorkspace />);
    const fileA = new File(["alpha"], "alpha.txt", { type: "text/plain" });
    const fileB = new File(["beta"], "beta.txt", { type: "text/plain" });

    await user.type(screen.getByRole("textbox"), "brouillon A");
    await user.upload(fileInput(container), fileA);
    expect(screen.getByText("alpha.txt")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Sélectionner B" }));
    expect(screen.getByRole("textbox")).toHaveValue("");
    expect(screen.queryByText("alpha.txt")).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox"), "brouillon B");
    await user.upload(fileInput(container), fileB);

    await user.click(screen.getByRole("button", { name: "Sélectionner A" }));
    expect(screen.getByRole("textbox")).toHaveValue("brouillon A");
    expect(screen.getByText("alpha.txt")).toBeInTheDocument();
    expect(screen.queryByText("beta.txt")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Sélectionner B" }));
    expect(screen.getByRole("textbox")).toHaveValue("brouillon B");
    expect(screen.getByText("beta.txt")).toBeInTheDocument();
  });

  it("preserves the controlled draft and File after a 409 refusal", async () => {
    const user = userEvent.setup();
    const { container } = render(<ControlledWorkspace refusedKeys={new Set(["a"])} />);
    const attachment = new File(["preuve"], "preuve.txt", { type: "text/plain" });
    await user.click(screen.getByRole("tab", { name: "Message simple" }));
    await user.type(screen.getByRole("textbox"), "message à conserver");
    await user.upload(fileInput(container), attachment);

    await user.click(screen.getByTitle("Envoyer"));
    await waitFor(() => expect(screen.getByTitle("Envoyer")).not.toBeDisabled());

    expect(screen.getByRole("textbox")).toHaveValue("message à conserver");
    expect(screen.getByText("preuve.txt")).toBeInTheDocument();
  });

  it("clears only A after acceptance and leaves B untouched", async () => {
    const fileA = new File(["a"], "a.txt");
    const fileB = new File(["b"], "b.txt");
    let initial = createConversationState([summary("a"), summary("b")], "a");
    initial = [
      { type: "DRAFT_CHANGED", key: "a", draft: "A à envoyer" },
      { type: "ATTACHMENT_STAGED", key: "a", attachment: fileA },
      { type: "DRAFT_CHANGED", key: "b", draft: "B à garder" },
      { type: "ATTACHMENT_STAGED", key: "b", attachment: fileB },
    ].reduce((state, event) => conversationReducer(state, event as ConversationEvent), initial);
    const user = userEvent.setup();
    render(<ControlledWorkspace initialState={initial} />);
    await user.click(screen.getByRole("tab", { name: "Message simple" }));

    await user.click(screen.getByTitle("Envoyer"));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(""));
    expect(screen.queryByText("a.txt")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Sélectionner B" }));
    expect(screen.getByRole("textbox")).toHaveValue("B à garder");
    expect(screen.getByText("b.txt")).toBeInTheDocument();
  });

  it("keeps a staged File when a screenshot send clears its draft", async () => {
    const file = new File(["later"], "later.txt");
    let initial = createConversationState([summary("a")], "a");
    initial = conversationReducer(initial, { type: "DRAFT_CHANGED", key: "a", draft: "capture" });
    initial = conversationReducer(initial, { type: "ATTACHMENT_STAGED", key: "a", attachment: file });
    const user = userEvent.setup();
    render(<ControlledWorkspace initialState={initial} />);

    await user.click(screen.getByTitle("Capturer l'onglet ChatGPT et l'envoyer"));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(""));

    expect(screen.getByText("later.txt")).toBeInTheDocument();
  });

  it("locks the submitted File controls until its POST settles", async () => {
    let resolveA!: () => void;
    const pendingA = new Promise<void>((resolve) => { resolveA = resolve; });
    const file = new File(["submitted"], "submitted.txt");
    let initial = createConversationState([summary("a")], "a");
    initial = conversationReducer(initial, { type: "DRAFT_CHANGED", key: "a", draft: "avec fichier" });
    initial = conversationReducer(initial, { type: "ATTACHMENT_STAGED", key: "a", attachment: file });
    const user = userEvent.setup();
    const { container } = render(
      <ControlledWorkspace initialState={initial} pendingKeys={new Map([["a", pendingA]])} />,
    );

    await user.click(screen.getByTitle("Envoyer"));

    expect(fileInput(container)).toBeDisabled();
    expect(screen.getByRole("button", { name: "Retirer la pièce jointe" })).toBeDisabled();
    resolveA();
    await waitFor(() => expect(screen.queryByText("submitted.txt")).not.toBeInTheDocument());
  });

  it("does not render another conversation's global pipeline mission", () => {
    render(<ControlledWorkspace />);

    expect(screen.queryByText("exécution locale")).not.toBeInTheDocument();
  });

  it("stops the spinner and offers a truthful recovery action when delivery is uncertain", async () => {
    const retry = vi.fn<(key: string) => void>();
    let initial = createConversationState([summary("a")], "a");
    initial = conversationReducer(initial, { type: "DRAFT_CHANGED", key: "a", draft: "à préserver" });
    initial = conversationReducer(initial, {
      type: "RUN_EVENT",
      key: "a",
      runId: "run-a",
      streamEpoch: 1,
      run: acceptedRun("a"),
      accepted: true,
      submittedDraft: "à préserver",
      submittedAttachment: null,
    });
    initial = conversationReducer(initial, {
      type: "RUN_RECOVERY_EXHAUSTED",
      key: "a",
      runId: "run-a",
      streamEpoch: 1,
      error: "Livraison incertaine : le bridge ne peut pas confirmer la réception.",
    });
    const user = userEvent.setup();
    render(<ControlledWorkspace initialState={initial} onRetryRecovery={retry} />);

    expect(screen.getByText("Livraison incertaine")).toBeInTheDocument();
    expect(screen.queryByTitle("Arrêter la réponse")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("à préserver");
    await user.click(screen.getByRole("button", { name: "Réessayer la synchronisation" }));
    expect(retry).toHaveBeenCalledWith("a");
  });

  it("blocks an ambiguous provisional composer and resolves toward the existing canonical entry", async () => {
    const provisional: ConversationSummary = {
      url: "https://chatgpt.com/",
      identity: "provisional:collision",
      title: "Nouvelle conversation",
    };
    let initial = createConversationState([provisional, summary("canonical-a")], provisional.identity);
    initial = conversationReducer(initial, {
      type: "DRAFT_CHANGED",
      key: provisional.identity,
      draft: "brouillon ambigu",
    });
    initial = conversationReducer(initial, {
      type: "REKEY_CANONICAL",
      key: provisional.identity,
      canonicalKey: "canonical-a",
      canonicalUrl: "https://chatgpt.com/c/canonical-a",
    });
    const user = userEvent.setup();
    render(<ControlledWorkspace initialState={initial} />);

    expect(screen.getByText("Identité de conversation ambiguë")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByTitle("Envoyer")).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Ouvrir la conversation existante" }));
    expect(screen.getByRole("heading", { name: "Conversation CANONICAL-A" })).toBeInTheDocument();
    expect(screen.getByRole("textbox")).not.toBeDisabled();
  });
});
