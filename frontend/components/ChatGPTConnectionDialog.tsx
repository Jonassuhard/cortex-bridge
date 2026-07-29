"use client";

import { useAccessibleDialog } from "@/hooks/useAccessibleDialog";
import type { ChromeConnectionResult } from "@/lib/types";
import { BrowserIcon } from "./Icons";

interface ChatGPTConnectionDialogProps {
  open: boolean;
  result: ChromeConnectionResult;
  busy: boolean;
  onRetry: () => void;
  onClose: () => void;
}

export function ChatGPTConnectionDialog({
  open,
  result,
  busy,
  onRetry,
  onClose,
}: ChatGPTConnectionDialogProps) {
  const dialogRef = useAccessibleDialog<HTMLDialogElement>({ open, onClose });
  if (!open) return null;
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy) onClose();
    }}>
      <dialog
        ref={dialogRef}
        open
        className={`chatgpt-connection-dialog is-${result.state}`}
        aria-modal="true"
        aria-labelledby="chatgpt-connection-title"
        aria-describedby="chatgpt-connection-message"
      >
        <header>
          <span><BrowserIcon size={19} /></span>
          <div>
            <p className="connection-eyebrow">Connexion Chrome</p>
            <h2 id="chatgpt-connection-title">{result.title}</h2>
          </div>
          <button type="button" aria-label="Fermer la fenêtre" onClick={onClose} disabled={busy}>×</button>
        </header>
        <div className="connection-dialog-body">
          {busy && <span className="connection-spinner" aria-hidden="true" />}
          <p id="chatgpt-connection-message">{result.message}</p>
          {result.url && <small>Onglet vérifié : {new URL(result.url).hostname}</small>}
        </div>
        <footer>
          <button type="button" onClick={onClose} disabled={busy}>Fermer</button>
          {result.recoverable && (
            <button type="button" className="approve-button" onClick={onRetry} disabled={busy}>
              {busy ? "Vérification en cours…" : "Réessayer"}
            </button>
          )}
        </footer>
      </dialog>
    </div>
  );
}
