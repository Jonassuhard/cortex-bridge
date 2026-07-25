"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ChatRun,
  ConversationMessage,
  ConversationSummary,
  CortexSettings,
  MissionDetail,
  PipelineStatus,
} from "@/lib/types";
import { formatDuration, shortTime } from "@/lib/api";
import {
  ActivityIcon,
  BrowserIcon,
  CheckIcon,
  ClockIcon,
  CopyIcon,
  DoubleCheckIcon,
  EyeIcon,
  FolderIcon,
  MenuIcon,
  MoreIcon,
  PanelIcon,
  PaperclipIcon,
  PauseIcon,
  PlayIcon,
  SendIcon,
  ShieldIcon,
  SparkIcon,
  StopIcon,
  TerminalIcon,
} from "./Icons";
import { ExecutionCard } from "./ExecutionCard";

interface ChatWorkspaceProps {
  conversation: ConversationSummary | null;
  messages: ConversationMessage[];
  loadingMessages: boolean;
  chatRun: ChatRun | null;
  mission: MissionDetail | null;
  pipeline: PipelineStatus;
  settings: CortexSettings;
  inspectorOpen: boolean;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  onToggleInspector: () => void;
  onSendChat: (text: string) => Promise<void>;
  onStartMission: (text: string) => Promise<void>;
  onCancelChat: () => void;
  onPauseMission: () => void;
  onResumeMission: () => void;
  onCancelMission: () => void;
  onApprove: (scope: "once" | "tool" | "all-writes") => void;
  onReject: () => void;
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
  return (
    <article className="message-row message-user">
      <div className="user-bubble">
        <p>{cleanMessageText(message.text)}</p>
        <div className="user-message-meta">
          <span>
            {message.delivery === "failed"
              ? "Échec de l'envoi"
              : message.delivery === "queued"
                ? "Envoi en cours…"
                : message.delivery === "sending"
                  ? "Envoi en cours…"
                  : "Envoyé ✓"}
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
      <p>Écris une mission complète. ChatGPT planifie, le bridge autorise, Ollama exécute et les preuves reviennent automatiquement dans la conversation.</p>
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
  conversation,
  messages,
  loadingMessages,
  chatRun,
  mission,
  pipeline,
  settings,
  inspectorOpen,
  sidebarCollapsed,
  onToggleSidebar,
  onToggleInspector,
  onSendChat,
  onStartMission,
  onCancelChat,
  onPauseMission,
  onResumeMission,
  onCancelMission,
  onApprove,
  onReject,
}: ChatWorkspaceProps) {
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<"chat" | "mission">("mission");
  const [sending, setSending] = useState(false);
  const [executionExpanded, setExecutionExpanded] = useState(true);
  const viewportRef = useRef<HTMLDivElement>(null);
  const nearBottomRef = useRef(true);

  const activeMissionState = mission?.mission.state;
  const missionRunning = !!activeMissionState && !["COMPLETED", "FAILED", "BLOCKED", "CANCELLED"].includes(activeMissionState);
  const chatActive = !!chatRun && !["COMPLETED", "FAILED", "CANCELLED"].includes(chatRun.state);
  const busy = missionRunning || chatActive || sending;

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
              : ["VISIBLE_IN_CHATGPT", "WAITING_FOR_CHATGPT", "CHATGPT_STREAMING", "COMPLETED"].includes(chatRun.state)
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
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      setDraft("");
      if (mode === "mission") await onStartMission(text);
      else await onSendChat(text);
    } finally {
      setSending(false);
    }
  }

  const title = conversation?.title || "Nouvelle conversation";
  const online = pipeline.overall !== "failed" && pipeline.overall !== "disconnected";
  const latency = pipeline.latency?.transport_ms;
  const activeLabel = chatRun?.state === "CHATGPT_STREAMING"
    ? "Réponse en cours"
    : chatActive
      ? "Message en cours"
      : online
        ? "Connecté"
        : "Connexion dégradée";
  // P1a: the agent executor status sits next to the ChatGPT status.
  const ollamaComponent = pipeline.components?.find((component) => component.id === "ollama");
  const agentUp = ollamaComponent ? ollamaComponent.state === "healthy" : online;
  const agentLabel = missionRunning
    ? "en cours"
    : activeMissionState === "PAUSED" || activeMissionState === "PAUSED_RECOVERY_REQUIRED"
      ? "en pause"
      : agentUp
        ? "prêt"
        : "hors ligne";

  return (
    <section className="chat-workspace">
      <div className="conversation-toolbar">
        <div className="toolbar-left">
          {!sidebarCollapsed && <button className="toolbar-icon-button mobile-only" onClick={onToggleSidebar}><MenuIcon /></button>}
          {sidebarCollapsed && <button className="toolbar-icon-button" onClick={onToggleSidebar} title="Afficher les conversations"><MenuIcon /></button>}
          <div className="conversation-title-block">
            <div><h2>{title}</h2><button aria-label="Options de conversation"><MoreIcon size={17} /></button></div>
            <p>
              <span>{settings.planner_model}</span>
              <i />
              <span>{settings.primary_executor}</span>
              <i />
              <span className={settings.never_delete_files ? "safe-label" : "warning-label"}><ShieldIcon size={12} /> {settings.never_delete_files ? "Aucune suppression" : "Suppression non protégée"}</span>
            </p>
          </div>
        </div>
        <div className="toolbar-center-status">
          <span className={`status-pill ${online ? "is-online" : "is-offline"}`} title="Statut de la connexion ChatGPT">
            <span className={`presence-dot ${online ? "is-online" : "is-offline"}`} />
            <span>ChatGPT</span>
            <strong>{activeLabel}</strong>
          </span>
          <span className={`status-pill ${agentUp ? "is-online" : "is-offline"}`} title="Statut de l'agent exécutif local">
            <span className={`presence-dot ${agentUp ? "is-online" : "is-offline"}`} />
            <span>Agent {settings.primary_executor}</span>
            <strong>{agentLabel}</strong>
          </span>
        </div>
        <div className="toolbar-right">
          <span className="latency-badge"><ActivityIcon size={14} /><span>Latence</span><strong>{latency == null ? "—" : formatDuration(latency)}</strong></span>
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
          {!loadingMessages && mergedMessages.length === 0 && <EmptyConversation onExample={setDraft} />}
          {mergedMessages.map((message) => {
            if (message.role === "user") return <UserMessage key={message.id} message={message} />;
            if (message.role === "assistant") return <AssistantMessage key={message.id} message={message} />;
            return null;
          })}

          {(mission || pipeline.active_mission_id) && (
            <div className="message-row message-cortex">
              <div className="assistant-avatar cortex-avatar"><ActivityIcon size={15} /></div>
              <div className="assistant-content execution-content">
                <div className="assistant-message-head"><strong>Cortex Bridge</strong><span>exécution locale</span></div>
                <ExecutionCard
                  mission={mission}
                  pipeline={pipeline}
                  expanded={executionExpanded}
                  onToggle={() => setExecutionExpanded((value) => !value)}
                  onApprove={onApprove}
                  onReject={onReject}
                />
              </div>
            </div>
          )}

          {chatRun?.state === "FAILED" && (
            <div className="inline-chat-error"><ShieldIcon size={17} /><span><strong>Transport interrompu</strong><small>{chatRun.error || "Le message n'a pas pu être confirmé dans ChatGPT."}</small></span></div>
          )}
          <div className="scroll-anchor" />
        </div>
      </div>

      <div className="composer-shell">
        <div className="composer-mode-tabs" role="tablist">
          <button className={mode === "mission" ? "is-active" : ""} onClick={() => setMode("mission")}><SparkIcon size={14} /> Mission autonome</button>
          <button className={mode === "chat" ? "is-active" : ""} onClick={() => setMode("chat")}><EyeIcon size={14} /> Message simple</button>
        </div>
        <div className={`composer-box ${busy ? "is-busy" : ""}`}>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.metaKey) {
                event.preventDefault();
                void submit();
              }
            }}
            placeholder={mode === "mission" ? "Décris l'objectif. Cortex planifie, exécute et valide automatiquement…" : "Écrire dans la conversation ChatGPT sélectionnée…"}
            rows={1}
            disabled={sending}
          />
          <div className="composer-controls">
            <div className="composer-left-actions">
              <button title="Pièces jointes (non disponible tant que le transport ne les confirme pas)" disabled><PaperclipIcon size={18} /></button>
              <span className="workspace-pill"><FolderIcon size={13} /> {settings.default_workspace.split("/").filter(Boolean).at(-1) || "workspace"}</span>
            </div>
            <div className="composer-right-actions">
              <span className="composer-shortcut">Entrée pour envoyer · ⇧ Entrée pour une ligne</span>
              {chatActive ? (
                <button className="send-button is-stop" onClick={onCancelChat} title="Arrêter la réponse"><StopIcon size={17} /></button>
              ) : missionRunning ? (
                <button className="send-button is-stop" onClick={onPauseMission} title="Mettre la mission en pause"><PauseIcon size={17} /></button>
              ) : (
                <button className="send-button" onClick={() => void submit()} disabled={!draft.trim() || sending} title="Envoyer"><SendIcon size={17} /></button>
              )}
            </div>
          </div>
        </div>
        <div className="composer-footer">
          <span><ShieldIcon size={12} /> Profil {settings.access_profile} · suppression remplacée par archivage</span>
          <div>
            {activeMissionState === "PAUSED" || activeMissionState === "PAUSED_RECOVERY_REQUIRED" ? (
              <button onClick={onResumeMission}><PlayIcon size={13} /> Reprendre</button>
            ) : missionRunning ? (
              <button onClick={onCancelMission}><StopIcon size={13} /> Annuler la mission</button>
            ) : null}
            <label className="mini-toggle"><span>Auto-continue</span><input type="checkbox" checked={settings.auto_continue} readOnly /><i /></label>
          </div>
        </div>
      </div>
    </section>
  );
}
