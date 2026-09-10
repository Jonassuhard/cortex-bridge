"use client";

import { useRef, useState } from "react";
import {
  attachmentSizeError,
  DEFAULT_TRANSPORT_UPLOAD_LIMITS,
  type TransportUploadLimits,
} from "@/lib/types";
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
  capabilities: {
    upload_file: boolean;
    upload_image?: boolean;
    take_screenshot: boolean;
    limits?: TransportUploadLimits;
  };
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
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const empty = !value.trim() && !attachment;
  const uploadLimits = capabilities.limits || DEFAULT_TRANSPORT_UPLOAD_LIMITS;
  const uploadImage = capabilities.upload_image !== false;
  const canUploadAnything = capabilities.upload_file || uploadImage;
  const attachmentTitle = canUploadAnything
    ? `Joindre un fichier (${Math.round(uploadLimits.file_bytes / (1024 * 1024))} Mo max, images ${Math.round(uploadLimits.image_bytes / (1024 * 1024))} Mo max)`
    : "Pièces jointes indisponibles";
  const isImage = (file: File) => (
    file.type.toLowerCase().startsWith("image/")
    || /\.(?:gif|jpe?g|png|webp)$/iu.test(file.name)
  );

  return (
    <div className={`composer-box ${executionBlocked ? "is-busy" : ""}`}>
      <div className="composer-context"><FolderIcon size={16} /><span>Projet</span><strong title={workspaceLabel}>{workspaceLabel}</strong></div>
      <textarea
        aria-label="Message à envoyer"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.metaKey) {
            event.preventDefault();
            if (!empty && !blocked && !executionBlocked) onSend();
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
              const file = event.target.files?.[0] || null;
              const unsupported = file && (
                (isImage(file) && !uploadImage)
                || (!isImage(file) && !capabilities.upload_file)
              );
              const error = unsupported
                ? isImage(file)
                  ? "Les images sont indisponibles avec le transport actif."
                  : "Les fichiers sont indisponibles avec le transport actif."
                : file
                  ? attachmentSizeError(file, uploadLimits)
                  : null;
              setAttachmentError(error);
              if (!error) onAttachmentStaged(file);
              event.target.value = "";
            }}
          />
          <button
            type="button"
            aria-label="Joindre un fichier"
            title={attachmentTitle}
            disabled={!canUploadAnything || blocked}
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
              disabled={blocked || executionBlocked}
            >
              <BrowserIcon size={17} />
            </button>
          )}
          {attachment && (
            <span className="staged-file-pill">
              <PaperclipIcon size={12} /> {attachment.name}
              <button
                type="button"
                onClick={() => {
                  setAttachmentError(null);
                  onAttachmentStaged(null);
                }}
                disabled={blocked}
                aria-label="Retirer la pièce jointe"
              >×</button>
            </span>
          )}
          {attachmentError && <span role="alert" className="warning-label">{attachmentError}</span>}
        </div>
        <div className="composer-right-actions">
          <span className="composer-shortcut">Entrée pour envoyer · ⇧ Entrée pour une ligne</span>
          <button
            type="button"
            className="execution-preflight-button"
            onClick={onPrepareExecution}
            disabled={empty || blocked || executionBlocked}
          >
            <SparkIcon size={15} /> Exécuter sur ce Mac…
          </button>
          {chatActive ? (
            <button
              type="button"
              className="send-button is-stop"
              onClick={onCancelChat}
              disabled={cancelPending}
              title="Arrêter la réponse"
              aria-label="Arrêter la réponse"
            ><StopIcon size={17} /><span>{cancelPending ? "Arrêt demandé…" : "Arrêter la réponse"}</span></button>
          ) : (
            <button
              type="button"
              className="send-button"
              onClick={onSend}
              disabled={empty || blocked || executionBlocked}
              title="Envoyer à ChatGPT"
              aria-label="Envoyer à ChatGPT"
            ><SendIcon size={17} /><span>Envoyer à ChatGPT</span></button>
          )}
        </div>
      </div>
    </div>
  );
}
