"use client";

import type { ExecutionPreflight } from "@/lib/types";
import { ShieldIcon } from "./Icons";

interface ExecutionPreflightDialogProps {
  open: boolean;
  value: ExecutionPreflight;
  attachmentName: string | null;
  confirming: boolean;
  onChange: (value: ExecutionPreflight) => void;
  onClose: () => void;
  onConfirm: () => void;
}

export function ExecutionPreflightDialog({
  open,
  value,
  attachmentName,
  confirming,
  onChange,
  onClose,
  onConfirm,
}: ExecutionPreflightDialogProps) {
  if (!open) return null;
  const setCapability = (key: "write" | "processes" | "network", enabled: boolean) => {
    onChange({
      ...value,
      capabilities: { ...value.capabilities, [key]: enabled },
      approvalPolicy: enabled && value.approvalPolicy === "read-only"
        ? key === "processes" ? "reviewed-processes" : "write-with-approvals"
        : value.approvalPolicy,
    });
  };

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <dialog open className="execution-preflight-dialog" aria-modal="true" aria-labelledby="execution-preflight-title">
        <header>
          <span><ShieldIcon size={18} /></span>
          <div>
            <h2 id="execution-preflight-title">Vérifier l’exécution locale</h2>
            <p>Aucune action ne démarre avant ta confirmation.</p>
          </div>
          <button type="button" aria-label="Fermer le préflight" onClick={onClose}>×</button>
        </header>
        <dl className="preflight-facts">
          <div><dt>Conversation</dt><dd>{value.conversationKey}</dd></div>
          <div><dt>Workspace</dt><dd>{value.workspace}</dd></div>
          <div><dt>Exécuteur</dt><dd>{value.executorKind === "ollama" ? "Ollama" : "Déterministe"}</dd></div>
          <div><dt>Limites</dt><dd>{value.maxIterations} itérations · {value.maxDurationMinutes} min</dd></div>
          <div><dt>Pièce jointe</dt><dd>{attachmentName || "Aucune"}</dd></div>
        </dl>
        <fieldset>
          <legend>Capacités demandées</legend>
          <label><input type="checkbox" checked disabled /> Lecture</label>
          <label><input type="checkbox" checked={value.capabilities.write} onChange={(event) => setCapability("write", event.target.checked)} /> Écriture avec approbations</label>
          <label><input type="checkbox" checked={value.capabilities.processes} onChange={(event) => setCapability("processes", event.target.checked)} /> Commandes revues</label>
          <label><input type="checkbox" checked={value.capabilities.network} onChange={(event) => setCapability("network", event.target.checked)} /> Réseau</label>
          <label><input type="checkbox" checked={false} disabled /> Suppression</label>
        </fieldset>
        <footer>
          <button type="button" onClick={onClose} disabled={confirming}>Annuler</button>
          <button type="button" className="approve-button" onClick={onConfirm} disabled={confirming}>
            {confirming ? "Démarrage…" : value.approvalPolicy === "read-only"
              ? "Démarrer en lecture seule"
              : value.approvalPolicy === "reviewed-processes"
                ? "Démarrer avec commandes revues"
                : "Démarrer avec approbations d’écriture"}
          </button>
        </footer>
      </dialog>
    </div>
  );
}
