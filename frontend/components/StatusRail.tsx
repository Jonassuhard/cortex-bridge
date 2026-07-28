import type { HealthState } from "@/lib/types";
import { formatDuration } from "@/lib/api";
import { statusPresentation } from "@/lib/runtimeTruth";
import { ActivityIcon } from "./Icons";

interface StatusRailProps {
  transport: HealthState;
  executor: HealthState;
  execution?: string | null;
  latencyMs?: number | null;
}

const executionLabels: Record<string, string> = {
  INITIALIZING_MISSION: "Initialisation",
  WAITING_FOR_CHATGPT: "ChatGPT analyse",
  WAITING_FOR_APPROVAL: "Approbation requise",
  EXECUTING_LOCAL_ACTION: "Travail en cours",
  PAUSED: "En pause",
  PAUSED_RECOVERY_REQUIRED: "Reprise requise",
  COMPLETED: "Terminé",
  FAILED: "Échec",
  BLOCKED: "Bloqué",
  CANCELLED: "Annulé",
};

export function StatusRail({ transport, executor, execution, latencyMs }: StatusRailProps) {
  const chat = statusPresentation(transport);
  const local = statusPresentation(executor);
  const localLabel = execution ? executionLabels[execution] || local.label : local.label;
  return (
    <div className="status-rail" aria-label="Statuts ChatGPT et exécuteur">
      <span className={`status-pill is-${chat.tone}`} title="Statut de la connexion ChatGPT"><span className={`presence-dot is-${chat.tone}`} /><span>ChatGPT</span><strong>{chat.label}</strong></span>
      <span className={`status-pill is-${local.tone}`} title="Statut de l'agent exécutif local"><span className={`presence-dot is-${local.tone}`} /><span>Exécuteur</span><strong>{localLabel}</strong></span>
      {latencyMs != null && <span className="latency-badge"><ActivityIcon size={14} /><span>Latence</span><strong>{formatDuration(latencyMs)}</strong></span>}
    </div>
  );
}
