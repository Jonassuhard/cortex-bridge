"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ChatRun,
  ConversationKey,
  ConversationMessage,
  ConversationSummary,
  CortexSettings,
  ExecutionPreflight,
  HealthState,
  MissionDetail,
  PipelineStatus,
} from "@/lib/types";
import { formatDuration, shortTime } from "@/lib/api";
import { executorDisplay } from "@/lib/runtimeTruth";
import {
  ActivityIcon,
  BrowserIcon,
  CheckIcon,
  ClockIcon,
  CopyIcon,
  DoubleCheckIcon,
  FolderIcon,
  MenuIcon,
  MoreIcon,
  PanelIcon,
  PlayIcon,
  ShieldIcon,
  SparkIcon,
  StopIcon,
  TerminalIcon,
} from "./Icons";
import { ExecutionCard } from "./ExecutionCard";
import { Composer } from "./Composer";
import { ExecutionPreflightDialog } from "./ExecutionPreflightDialog";
import { StatusRail } from "./StatusRail";
import type { RekeyConflict } from "@/lib/conversation-state";

export interface WorkspaceAvailability {
  chatState: HealthState;
  agentState: HealthState;
  transportLatencyMs: number | null;
}

interface ChatWorkspaceProps {
  conversationKey: ConversationKey | null;
  conversation: ConversationSummary | null;
  messages: ConversationMessage[];
  loadingMessages: boolean;
  sending: boolean;
  cancelPending: boolean;
  recoveryPending: boolean;
  draft: string;
  attachment: File | null;
  chatRun: ChatRun | null;
  mission: MissionDetail | null;
  pipeline: PipelineStatus;
  availability: WorkspaceAvailability;
  settings: CortexSettings;
  inspectorOpen: boolean;
  sidebarCollapsed: boolean;
  capabilities: { upload_file: boolean; take_screenshot: boolean };
  rekeyConflict: RekeyConflict | null;
  rekeyResolutionAllowed: boolean;
  onDraftChange: (key: ConversationKey, draft: string) => void;
  onAttachmentStaged: (key: ConversationKey, attachment: File | null) => void;
  onToggleSidebar: () => void;
  onToggleInspector: () => void;
  onSendChat: (key: ConversationKey, text: string) => Promise<boolean>;
  onSendAttachment: (key: ConversationKey, text: string, file: File) => Promise<boolean>;
  onSendScreenshot: (key: ConversationKey, text: string) => Promise<boolean>;
  onStartMission: (key: ConversationKey, text: string, preflight: ExecutionPreflight) => Promise<boolean>;
  onCancelChat: (key: ConversationKey) => void;
  onRetryChatRecovery: (key: ConversationKey) => void;
  onReloadConversation: (key: ConversationKey) => void;
  onResolveRekeyConflict: (
    fromKey: ConversationKey,
    toKey: ConversationKey,
    choice: "source" | "target",
  ) => void;
  onPauseMission: (key: ConversationKey) => void;
  onResumeMission: (key: ConversationKey) => void;
  onCancelMission: (key: ConversationKey) => void;
  onApprove: (key: ConversationKey, scope: "once" | "tool" | "all-writes") => void;
  onReject: (key: ConversationKey) => void;
}

function cleanMessageText(text: string): string {
  return text
    .replace(/Copy\s*$/g, "")
    .replace(/Réfléchi pendant\s+\d+[smh]\s*/gi, "")
    .replace(/Thinking completed/gi, "")
    .trim();
}

function MessageActions({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="message-actions">
      <button
        title="Copier"
        onClick={async () => {
          await navigator.clipboard?.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1200);
        }}
      >
        {copied ? <CheckIcon size={14} /> : <CopyIcon size={14} />}
      </button>
      <button title="Plus d'actions"><MoreIcon size={15} /></button>
    </div>
  );
}

function CodeBlock({ language, text }: { language?: string; text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="message-code-block">
      <div className="message-code-head">
        <span>{language || "code"}</span>
        <button
          onClick={async () => {
            await navigator.clipboard?.writeText(text);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1200);
          }}
        >
          {copied ? <CheckIcon size={13} /> : <CopyIcon size={13} />}
          {copied ? "Copié" : "Copier"}
        </button>
      </div>
      <pre><code>{text}</code></pre>
    </div>
  );
}

function UserMessage({ message }: { message: ConversationMessage }) {
  const deliveryLabel: Record<NonNullable<ConversationMessage["delivery"]>, string> = {
    queued: "En attente locale",
    sending: "Envoi à ChatGPT",
    sent: "Envoyé",
    visible: "Visible dans ChatGPT",
    waiting: "En attente de réponse",
    received: "Réponse reçue",
    uncertain: "Livraison incertaine",
    failed: "Échec de l’envoi",
  };
  return (
    <article className="message-row message-user">
      <div className="user-bubble">
        <p>{cleanMessageText(message.text)}</p>
        <div className="user-message-meta">
          <span>
            {deliveryLabel[message.delivery || "sent"]}
          </span>
          <time>{shortTime(message.created_at)}</time>
          {message.delivery === "received" || message.delivery === "visible" ? <DoubleCheckIcon size={14} /> : <CheckIcon size={14} />}
        </div>
      </div>
    </article>
  );
}

function AssistantMessage({ message }: { message: ConversationMessage }) {
  const text = cleanMessageText(message.text);
  return (
    <article className="message-row message-assistant">
      <div className="assistant-avatar"><SparkIcon size={15} /></div>
      <div className="assistant-content">
        <div className="assistant-message-head">
          <strong>ChatGPT</strong>
          <span>{message.streaming ? "Réponse en cours" : shortTime(message.created_at)}</span>
          {message.latency_ms != null && <span className="message-latency"><ClockIcon size={12} /> {formatDuration(message.latency_ms)}</span>}
        </div>
        {message.streaming && !text && (
          <div className="thinking-line"><span className="thinking-spinner" /><span>ChatGPT analyse la demande…</span></div>
        )}
        {text && <div className={`assistant-text ${message.streaming ? "is-streaming" : ""}`}>{text}</div>}
        {!!message.code_blocks?.length && message.code_blocks.map((block, index) => (
          <CodeBlock key={`${message.id}-code-${index}`} language={block.lang} text={block.text} />
        ))}
        {!!message.images?.length && (
          <div className="message-image-grid">
            {message.images.map((image, index) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={image.src} alt={image.alt || `Image ${index + 1}`} key={`${message.id}-image-${index}`} />
            ))}
          </div>
        )}
        {!message.streaming && <MessageActions text={text} />}
      </div>
    </article>
  );
}

function EmptyConversation({ onExample }: { onExample: (text: string) => void }) {
  const examples = [
    { icon: <TerminalIcon />, label: "Auditer un projet", text: "Inspecte ce projet, exécute les tests, corrige les erreurs et valide le résultat." },
    { icon: <BrowserIcon />, label: "Valider dans Chrome", text: "Lance l'application locale, inspecte l'interface dans Chrome et capture les preuves utiles." },
    { icon: <FolderIcon />, label: "Organiser un workspace", text: "Analyse les fichiers du workspace, documente la structure et archive les éléments temporaires sans les supprimer." },
  ];
  return (
    <div className="empty-conversation">
      <div className="empty-orb"><SparkIcon size={26} /></div>
      <h1>Que doit accomplir Cortex Bridge&nbsp;?</h1>
      <p>Écris une mission complète. ChatGPT planifie, le bridge autorise, l&apos;exécuteur déterministe agit et les preuves reviennent automatiquement dans la conversation.</p>
      <div className="empty-examples">
        {examples.map((example) => (
          <button key={example.label} onClick={() => onExample(example.text)}>
            <span>{example.icon}</span>
            <strong>{example.label}</strong>
            <small>{example.text}</small>
          </button>
        ))}
      </div>
    </div>
  );
}

export function ChatWorkspace({
  conversationKey,
  conversation,
  messages,
  loadingMessages,
  sending,
  cancelPending,
  recoveryPending,
  draft,
  attachment,
  chatRun,
  mission,
  pipeline,
  availability,
  settings,
  inspectorOpen,
  sidebarCollapsed,
  capabilities,
  rekeyConflict,
  rekeyResolutionAllowed,
  onDraftChange,
  onAttachmentStaged,
  onToggleSidebar,
  onToggleInspector,
  onSendChat,
  onSendAttachment,
  onSendScreenshot,
  onStartMission,
  onCancelChat,
  onRetryChatRecovery,
  onReloadConversation,
  onResolveRekeyConflict,
  onResumeMission,
  onCancelMission,
  onApprove,
  onReject,
}: ChatWorkspaceProps) {
  const [executionExpanded, setExecutionExpanded] = useState(false);
  const [preflightOpen, setPreflightOpen] = useState(false);
  const [preflightConfirming, setPreflightConfirming] = useState(false);
  const [preflight, setPreflight] = useState<ExecutionPreflight | null>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const nearBottomRef = useRef(true);

  const activeMissionState = mission?.mission.state;
  const missionRunning = !!activeMissionState && !["COMPLETED", "FAILED", "BLOCKED", "CANCELLED"].includes(activeMissionState);
  const chatActive = !!chatRun && !["COMPLETED", "FAILED", "CANCELLED", "DELIVERY_UNCERTAIN"].includes(chatRun.state);
  const ambiguousProvisional = !!conversationKey && rekeyConflict?.fromKey === conversationKey;
  const composerBlocked = !conversationKey || sending || ambiguousProvisional;
  const executionBlocked = composerBlocked
    || missionRunning
    || chatActive
    || cancelPending
    || recoveryPending;

  const mergedMessages = useMemo(() => {
    const source = [...messages];
    if (chatRun) {
      const hasUser = source.some((message) => message.id === `local-${chatRun.id}`);
      if (!hasUser) {
        source.push({
          id: `local-${chatRun.id}`,
          role: "user",
          text: chatRun.text,
          created_at: chatRun.created_at,
          delivery:
            chatRun.state === "FAILED"
              ? "failed"
              : chatRun.state === "DELIVERY_UNCERTAIN"
                ? "uncertain"
                : chatRun.state === "COMPLETED"
                  ? "received"
                  : ["WAITING_FOR_CHATGPT", "CHATGPT_STREAMING"].includes(chatRun.state)
                    ? "waiting"
                    : chatRun.state === "VISIBLE_IN_CHATGPT"
                      ? "visible"
                : chatRun.state === "SENDING_TO_CHATGPT"
                  ? "sending"
                  : "queued",
        });
      }
      if (chatRun.response_text || chatRun.state === "WAITING_FOR_CHATGPT" || chatRun.state === "CHATGPT_STREAMING") {
        source.push({
          id: `local-response-${chatRun.id}`,
          role: "assistant",
          text: chatRun.response_text || "",
          created_at: chatRun.first_response_at || chatRun.created_at,
          latency_ms: chatRun.latency?.first_response_ms || undefined,
          streaming: chatRun.state !== "COMPLETED",
        });
      }
    }
    return source;
  }, [messages, chatRun]);

  useEffect(() => {
    if (!nearBottomRef.current) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    window.requestAnimationFrame(() => viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" }));
  }, [mergedMessages.length, chatRun?.response_text, mission?.mission.state]);

  async function submit() {
    const key = conversationKey;
    const text = draft;
    const stagedFile = attachment;
    if (!key || (!text.trim() && !stagedFile) || executionBlocked) return;
    if (stagedFile) await onSendAttachment(key, text, stagedFile);
    else await onSendChat(key, text);
  }

  async function submitScreenshot() {
    const key = conversationKey;
    if (!key || executionBlocked) return;
    await onSendScreenshot(key, draft);
  }

  function prepareExecution() {
    if (!conversationKey || (!draft.trim() && !attachment) || executionBlocked) return;
    setPreflight({
      conversationKey,
      workspace: settings.default_workspace,
      executorKind: settings.primary_executor.toLowerCase().includes("ollama") ? "ollama" : "deterministic",
      capabilities: { read: true, write: false, processes: false, network: false, delete: false },
      approvalPolicy: "read-only",
      maxIterations: settings.max_iterations,
      maxDurationMinutes: settings.max_duration_minutes,
      attachmentTokens: [],
    });
    setPreflightOpen(true);
  }

  const title = conversation?.title || "Nouvelle conversation";
  return (
    <section className="chat-workspace">
      <div className="conversation-toolbar">
        <div className="toolbar-left">
          {!sidebarCollapsed && <button className="toolbar-icon-button mobile-only" onClick={onToggleSidebar} title="Masquer les conversations" aria-label="Masquer les conversations"><MenuIcon /></button>}
          {sidebarCollapsed && <button className="toolbar-icon-button" onClick={onToggleSidebar} title="Afficher les conversations" aria-label="Afficher les conversations"><MenuIcon /></button>}
          <div className="conversation-title-block">
            <div><h1>{title}</h1><button aria-label="Options de conversation"><MoreIcon size={17} /></button></div>
            <p>
              <span>{settings.planner_model}</span>
              <i />
              <span>{executorDisplay(mission?.mission || pipeline.runtime_execution)}</span>
              {conversation?.sync_state === "stale" && <><i /><span className="warning-label" title={conversation.sync_error || undefined}>Cache obsolète · synchronisation en échec</span></>}
              <i />
              <span className={settings.never_delete_files ? "safe-label" : "warning-label"}><ShieldIcon size={12} /> {settings.never_delete_files ? "Aucune suppression" : "Suppression non protégée"}</span>
            </p>
          </div>
          {conversation?.sync_state === "stale" && conversationKey && (
            <button className="reload-conversation-button" onClick={() => onReloadConversation(conversationKey)}>
              Recharger la conversation
            </button>
          )}
          {conversation?.url && <a className="open-chatgpt-link" href={conversation.url} target="_blank" rel="noreferrer">Ouvrir dans ChatGPT</a>}
        </div>
        <StatusRail transport={chatActive ? "running" : availability.chatState} executor={availability.agentState} execution={mission?.mission.state || null} latencyMs={availability.transportLatencyMs} />
        <div className="toolbar-right">
          <button className={`toolbar-icon-button ${inspectorOpen ? "is-active" : ""}`} onClick={onToggleInspector} title="Détails du bridge (pipeline, logs, transport)"><PanelIcon /></button>
        </div>
      </div>

      <div
        className="chat-scroll-viewport"
        ref={viewportRef}
        onScroll={(event) => {
          const el = event.currentTarget;
          nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
        }}
      >
        <div className="chat-background-grid" aria-hidden="true" />
        <div className="chat-blue-signal" aria-hidden="true" />
        <div className="message-column">
          {loadingMessages && mergedMessages.length === 0 && (
            <div className="message-loading-state"><span className="thinking-spinner" /><p>Synchronisation de « {title} »…</p></div>
          )}
          {!loadingMessages && mergedMessages.length === 0 && (
            <EmptyConversation
              onExample={(text) => {
                if (conversationKey) onDraftChange(conversationKey, text);
              }}
            />
          )}
          {mergedMessages.map((message) => {
            if (message.role === "user") return <UserMessage key={message.id} message={message} />;
            if (message.role === "assistant") return <AssistantMessage key={message.id} message={message} />;
            return null;
          })}

          {mission && (
            <div className="message-row message-cortex">
              <div className="assistant-avatar cortex-avatar"><ActivityIcon size={15} /></div>
              <div className="assistant-content execution-content">
                <div className="assistant-message-head"><strong>Cortex Bridge</strong><span>exécution locale</span></div>
                <ExecutionCard
                  mission={mission}
                  pipeline={pipeline}
                  expanded={executionExpanded}
                  onToggle={() => setExecutionExpanded((value) => !value)}
                  onApprove={(scope) => {
                    if (conversationKey) onApprove(conversationKey, scope);
                  }}
                  onReject={() => {
                    if (conversationKey) onReject(conversationKey);
                  }}
                />
              </div>
            </div>
          )}

          {chatRun?.state === "FAILED" && (
            <div className="inline-chat-error"><ShieldIcon size={17} /><span><strong>Transport interrompu</strong><small>{chatRun.error || "Le message n'a pas pu être confirmé dans ChatGPT."}</small></span></div>
          )}
          {chatRun?.state === "DELIVERY_UNCERTAIN" && (
            <output className="inline-chat-error">
              <ShieldIcon size={17} />
              <span>
                <strong>Livraison incertaine</strong>
                <small>{chatRun.error || "Le bridge ne peut pas confirmer la réception. Le contenu reste dans le composer et ne sera pas renvoyé automatiquement."}</small>
              </span>
              <button
                disabled={recoveryPending}
                onClick={() => conversationKey && onRetryChatRecovery(conversationKey)}
              >
                {recoveryPending ? "Synchronisation en cours…" : "Réessayer la synchronisation"}
              </button>
            </output>
          )}
          {chatActive && (
            <output className="inline-chat-status">
              Une réponse est déjà en cours pour cette conversation.
            </output>
          )}
          {ambiguousProvisional && rekeyConflict && (
            <div className="inline-chat-error" role="alert">
              <ShieldIcon size={17} />
              <span>
                <strong>Identité de conversation ambiguë</strong>
                <small>La conversation canonique existe déjà. Aucun envoi ni aucune exécution ne démarrera depuis cette copie provisoire.</small>
              </span>
              <div>
                <button
                  disabled={!rekeyResolutionAllowed}
                  onClick={() => onResolveRekeyConflict(
                    rekeyConflict.fromKey,
                    rekeyConflict.toKey,
                    "source",
                  )}
                >
                  Conserver le brouillon provisoire
                </button>
                <button
                  disabled={!rekeyResolutionAllowed}
                  onClick={() => onResolveRekeyConflict(
                    rekeyConflict.fromKey,
                    rekeyConflict.toKey,
                    "target",
                  )}
                >
                  Conserver le brouillon canonique
                </button>
              </div>
            </div>
          )}
          <div className="scroll-anchor" />
        </div>
      </div>

      <div className="composer-shell">
        <Composer
          value={draft}
          attachment={attachment}
          blocked={composerBlocked}
          executionBlocked={executionBlocked}
          chatActive={chatActive}
          cancelPending={cancelPending}
          capabilities={capabilities}
          workspaceLabel={settings.default_workspace.split("/").filter(Boolean).at(-1) || "workspace"}
          onChange={(value) => conversationKey && onDraftChange(conversationKey, value)}
          onAttachmentStaged={(file) => conversationKey && onAttachmentStaged(conversationKey, file)}
          onSend={() => void submit()}
          onScreenshot={() => void submitScreenshot()}
          onPrepareExecution={prepareExecution}
          onCancelChat={() => conversationKey && onCancelChat(conversationKey)}
        />
        <div className="composer-footer">
          <span><ShieldIcon size={12} /> Profil {settings.access_profile} · suppression remplacée par archivage</span>
          <div>
            {activeMissionState === "PAUSED" || activeMissionState === "PAUSED_RECOVERY_REQUIRED" ? (
              <button onClick={() => {
                if (conversationKey) onResumeMission(conversationKey);
              }}><PlayIcon size={13} /> Reprendre</button>
            ) : missionRunning ? (
              <button onClick={() => {
                if (conversationKey) onCancelMission(conversationKey);
              }}><StopIcon size={13} /> Annuler la mission</button>
            ) : null}
            <label className="mini-toggle"><span>Auto-continue</span><input type="checkbox" checked={settings.auto_continue} readOnly /><i /></label>
          </div>
        </div>
      </div>
      {preflight && (
        <ExecutionPreflightDialog
          open={preflightOpen}
          value={preflight}
          attachmentName={attachment?.name || null}
          confirming={preflightConfirming}
          onChange={setPreflight}
          onClose={() => setPreflightOpen(false)}
          onConfirm={() => {
            if (!conversationKey) return;
            setPreflightConfirming(true);
            void onStartMission(conversationKey, draft, preflight).then((accepted) => {
              if (accepted) setPreflightOpen(false);
            }).finally(() => setPreflightConfirming(false));
          }}
        />
      )}
    </section>
  );
}
