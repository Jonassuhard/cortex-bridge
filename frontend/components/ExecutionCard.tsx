"use client";
/* eslint-disable react/no-unescaped-entities */

import { useMemo } from "react";
import type { MissionDetail, PipelineStatus } from "@/lib/types";
import { formatDuration } from "@/lib/api";
import { executionStateLabel } from "@/lib/runtimeTruth";
import {
  ActivityIcon,
  BrowserIcon,
  CheckIcon,
  ChevronDownIcon,
  ClockIcon,
  FolderIcon,
  ShieldIcon,
  TerminalIcon,
} from "./Icons";

interface ExecutionCardProps {
  mission: MissionDetail | null;
  pipeline: PipelineStatus;
  expanded: boolean;
  onToggle: () => void;
  onApprove: (scope: "once" | "tool" | "all-writes") => void;
  onReject: () => void;
}

const stageOrder = [
  "Dépôt inspecté",
  "Décision ChatGPT reçue",
  "Action locale autorisée",
  "Exécution en cours",
  "Validation déterministe",
  "Rapport renvoyé à ChatGPT",
];

function stateLabel(state?: string) {
  const labels: Record<string, string> = {
    INITIALIZING_MISSION: "Initialisation",
    SENDING_OBJECTIVE: "Envoi à ChatGPT",
    WAITING_FOR_CHATGPT: "ChatGPT analyse",
    PARSING_DECISION: "Décision reçue",
    WAITING_FOR_APPROVAL: "Approbation requise",
    EXECUTING_LOCAL_ACTION: "Exécution locale",
    VALIDATING_ACTION: "Validation",
    SENDING_REPORT: "Rapport vers ChatGPT",
    FINAL_VALIDATION: "Validation finale",
    COMPLETED: "Mission terminée",
    BLOCKED: "Mission bloquée",
    FAILED: "Mission échouée",
    PAUSED: "Mission en pause",
    PAUSED_RECOVERY_REQUIRED: "Reprise requise",
    CANCELLED: "Mission annulée",
  };
  return labels[state || ""] || state || "Exécution locale";
}

export function ExecutionCard({ mission, pipeline, expanded, onToggle, onApprove, onReject }: ExecutionCardProps) {
  const active = mission?.mission;
  const missionState = active?.state || pipeline.active_mission_state || "EXECUTING_LOCAL_ACTION";
  const terminal = ["COMPLETED", "BLOCKED", "FAILED", "CANCELLED"].includes(missionState);
  const completed = missionState === "COMPLETED";
  const terminalLabel = executionStateLabel(missionState);
  const waitingApproval = !!mission?.awaiting_approval;

  const evidence = useMemo(() => {
    if (!mission) return [];
    const rows = mission.timeline;
    const items: { icon: "check" | "terminal" | "folder" | "browser" | "shield"; label: string; detail: string; done: boolean }[] = [];
    if ((rows.conversation_bindings || []).length) {
      items.push({ icon: "check", label: "Conversation verrouillée", detail: String(rows.conversation_bindings.at(-1)?.conversation_title || "ChatGPT"), done: true });
    }
    if ((rows.orchestrator_decisions || []).length) {
      const row = rows.orchestrator_decisions.at(-1) || {};
      let detail = "Décision cortex.v1";
      try {
        const parsed = JSON.parse(String(row.decision_json || row.raw_json || "{}"));
        detail = parsed.action?.tool || parsed.state || detail;
      } catch {}
      items.push({ icon: "shield", label: "Décision validée", detail, done: true });
    }
    if ((rows.tool_executions || []).length) {
      const row = rows.tool_executions.at(-1) || {};
      items.push({ icon: "terminal", label: "Action locale", detail: String(row.tool || "outil structuré"), done: row.exit_code !== null && row.exit_code !== undefined });
    }
    if ((rows.validation_results || []).length) {
      const row = rows.validation_results.at(-1) || {};
      items.push({ icon: "check", label: "Validation", detail: Number(row.passed) === 1 ? "Preuve acceptée" : "Échec détecté", done: Number(row.passed) === 1 });
    }
    if ((rows.artifacts || []).length) {
      items.push({ icon: "folder", label: "Artefacts", detail: `${rows.artifacts.length} élément(s)`, done: true });
    }
    return items.slice(-5);
  }, [mission]);

  const iconFor = (icon: string) => {
    if (icon === "terminal") return <TerminalIcon size={15} />;
    if (icon === "folder") return <FolderIcon size={15} />;
    if (icon === "browser") return <BrowserIcon size={15} />;
    if (icon === "shield") return <ShieldIcon size={15} />;
    return <CheckIcon size={15} />;
  };

  return (
    <article className={`execution-card ${waitingApproval ? "needs-approval" : ""} ${terminal ? "is-terminal" : ""}`}>
      <header className="execution-card-head">
        <div className="execution-card-title">
          <span className={`execution-orb ${completed ? "is-done" : terminal ? "is-error" : ""}`} aria-hidden="true"><span /></span>
          <div>
            <strong>{stateLabel(missionState)}</strong>
            <small>{active?.objective || "Cortex Bridge exécute et vérifie l'action demandée."}</small>
          </div>
        </div>
        <div className="execution-card-meta">
          {!terminal && <span className="live-label"><span className="live-dot" /> actif</span>}
          <span className="eta-chip"><ClockIcon size={13} /> {pipeline.latency?.total_iteration_ms ? `env. ${formatDuration(pipeline.latency.total_iteration_ms)}` : "estimation…"}</span>
          <button className="card-expand-button" onClick={onToggle} aria-label={expanded ? "Réduire le détail" : "Afficher le détail"}><ChevronDownIcon className={expanded ? "is-rotated" : ""} /></button>
        </div>
      </header>

      <div className="execution-progress-row">
        <div className="execution-progress-track"><span style={{ width: terminal ? "100%" : waitingApproval ? "48%" : "67%" }} /></div>
        <span>{terminalLabel || (waitingApproval ? "En attente de validation humaine" : "Boucle autonome en cours")}</span>
      </div>

      {waitingApproval && (
        <div className="inline-approval">
          <div>
            <ShieldIcon size={18} />
            <span><strong>Approbation requise</strong><small>L'action suivante peut modifier le workspace. Un point de restauration est conservé.</small></span>
          </div>
          <div className="inline-approval-actions">
            <button onClick={() => onApprove("once")} className="approve-button">Approuver une fois</button>
            <button onClick={onReject} className="reject-button">Refuser</button>
          </div>
        </div>
      )}

      <div className="execution-steps">
        {(evidence.length ? evidence : stageOrder.slice(0, 4).map((label, index) => ({
          icon: index === 3 ? "terminal" : "check",
          label,
          detail: index < 2 ? "Étape enregistrée" : index === 2 ? "cortex.v1" : "Exécuteur déterministe",
          done: index < 3,
        }))).map((step, index) => (
          <div className={`execution-step ${step.done ? "is-done" : index === evidence.length - 1 ? "is-current" : ""}`} key={`${step.label}-${index}`}>
            <span className="execution-step-icon">{step.done ? <CheckIcon size={13} /> : iconFor(step.icon)}</span>
            <span><strong>{step.label}</strong><small>{step.detail}</small></span>
          </div>
        ))}
      </div>

      {expanded && (
        <div className="execution-details">
          <div className="execution-detail-grid">
            <div><span>Mission</span><strong>{active?.id?.slice(0, 8) || "locale"}</strong></div>
            <div><span>État</span><strong>{missionState}</strong></div>
            <div><span>Workspace</span><strong>{active?.workspace || "workspace actif"}</strong></div>
            <div><span>File d'attente</span><strong>{pipeline.queue_pending}</strong></div>
          </div>
          <details>
            <summary><ActivityIcon size={14} /> Voir les preuves techniques</summary>
            <pre>{JSON.stringify(mission?.timeline || pipeline.events, null, 2)}</pre>
          </details>
        </div>
      )}
    </article>
  );
}
