"use client";

import { useRef } from "react";
import {
  BrowserIcon,
  FolderIcon,
  PaperclipIcon,
  SendIcon,
  SparkIcon,
  StopIcon,
} from "./Icons";

interface ComposerProps {
  value: string;
  attachment: File | null;
  blocked: boolean;
  executionBlocked: boolean;
  chatActive: boolean;
  cancelPending: boolean;
  capabilities: { upload_file: boolean; take_screenshot: boolean };
  workspaceLabel: string;
  onChange: (value: string) => void;
  onAttachmentStaged: (file: File | null) => void;
  onSend: () => void;
  onScreenshot: () => void;
  onPrepareExecution: () => void;
  onCancelChat: () => void;
}

export function Composer({
  value,
  attachment,
  blocked,
  executionBlocked,
  chatActive,
  cancelPending,
  capabilities,
  workspaceLabel,
  onChange,
  onAttachmentStaged,
  onSend,
  onScreenshot,
  onPrepareExecution,
  onCancelChat,
}: ComposerProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const empty = !value.trim() && !attachment;

  return (
    <div className={`composer-box ${executionBlocked ? "is-busy" : ""}`}>
      <textarea
        aria-label="Message à envoyer"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.metaKey) {
            event.preventDefault();
            if (!empty && !executionBlocked) onSend();
          }
        }}
        placeholder="Écrire dans la conversation ChatGPT sélectionnée…"
        rows={1}
        disabled={blocked}
      />
      <div className="composer-controls">
        <div className="composer-left-actions">
          <input
            ref={fileInputRef}
            type="file"
            disabled={blocked}
            className="visually-hidden-file"
            onChange={(event) => {
              onAttachmentStaged(event.target.files?.[0] || null);
              event.target.value = "";
            }}
          />
          <button
            type="button"
            aria-label="Joindre un fichier"
            title={capabilities.upload_file ? "Joindre un fichier ou une image" : "Pièces jointes indisponibles"}
            disabled={!capabilities.upload_file || blocked}
            onClick={() => fileInputRef.current?.click()}
          >
            <PaperclipIcon size={18} />
          </button>
          {capabilities.take_screenshot && (
            <button
              type="button"
              aria-label="Capturer l'onglet ChatGPT et l'envoyer"
              title="Capturer l'onglet ChatGPT et l'envoyer"
              onClick={onScreenshot}
              disabled={executionBlocked}
            >
              <BrowserIcon size={17} />
            </button>
          )}
          {attachment && (
            <span className="staged-file-pill">
              <PaperclipIcon size={12} /> {attachment.name}
              <button
                type="button"
                onClick={() => onAttachmentStaged(null)}
                disabled={blocked}
                aria-label="Retirer la pièce jointe"
              >×</button>
            </span>
          )}
          <span className="workspace-pill"><FolderIcon size={13} /> {workspaceLabel}</span>
        </div>
        <div className="composer-right-actions">
          <span className="composer-shortcut">Entrée pour envoyer · ⇧ Entrée pour une ligne</span>
          <button
            type="button"
            className="execution-preflight-button"
            onClick={onPrepareExecution}
            disabled={empty || executionBlocked}
          >
            <SparkIcon size={15} /> Exécuter…
          </button>
          {chatActive ? (
            <button
              type="button"
              className="send-button is-stop"
              onClick={onCancelChat}
              disabled={cancelPending}
              title="Arrêter la réponse"
              aria-label="Arrêter la réponse"
            ><StopIcon size={17} /></button>
          ) : (
            <button
              type="button"
              className="send-button"
              onClick={onSend}
              disabled={empty || executionBlocked}
              title="Envoyer"
              aria-label="Envoyer"
            ><SendIcon size={17} /></button>
          )}
        </div>
      </div>
    </div>
  );
}
