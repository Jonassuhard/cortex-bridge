"use client";
/* eslint-disable react/no-unescaped-entities */

import { useMemo } from "react";
import type { MissionDetail, PipelineStatus } from "@/lib/types";
import { formatDuration } from "@/lib/api";
import { executionStateLabel } from "@/lib/runtimeTruth";
import { TaskProgress } from "./TaskProgress";
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

function missionCardStateLabel(state?: string): string {
  if (state === "COMPLETED") return "Mission terminée";
  if (state === "BLOCKED") return "Mission bloquée";
  if (state === "FAILED") return "Mission échouée";
  if (state === "CANCELLED") return "Mission annulée";
  return executionStateLabel(state) || "État de mission inconnu";
}

function pauseReasonMessage(reason?: string | null): string | null {
  if (!reason) return null;
  const code = reason.toUpperCase();
  if (code.includes("RATE_LIMIT") || code.includes("USAGE_LIMIT")) {
    return "ChatGPT a atteint sa limite d'utilisation. C'est temporaire : attends la fin de la limitation, puis appuie sur Reprendre.";
  }
  if (code.includes("LOGIN")) {
    return "ChatGPT demande une connexion. Connecte-toi dans l'onglet ChatGPT de Chrome, puis appuie sur Reprendre.";
  }
  if (code.includes("CAPTCHA")) {
    return "ChatGPT demande une vérification humaine. Termine-la dans l'onglet ChatGPT, puis appuie sur Reprendre.";
  }
  if (code.includes("WORK_SURFACE")) {
    return "Cortex n'écrit que sur un chat ChatGPT classique, jamais sur une surface Work. Ouvre un chat classique, puis appuie sur Reprendre.";
  }
  if (code.includes("TAB_CLOSED")) {
    return "L'onglet ChatGPT a été fermé. Rouvre et connecte ChatGPT, puis appuie sur Reprendre.";
  }
  return reason;
}

function recordedObject(value: unknown): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(typeof value === "string" ? value : "null");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null;
  } catch { return null; }
}

export function ExecutionCard({ mission, pipeline, expanded, onToggle, onApprove, onReject }: ExecutionCardProps) {
  const active = mission?.mission;
  const missionState = active?.state || pipeline.active_mission_state || "UNKNOWN";
  const terminal = ["COMPLETED", "BLOCKED", "FAILED", "CANCELLED"].includes(missionState);
  const completed = missionState === "COMPLETED";
  const terminalLabel = executionStateLabel(missionState);
  const waitingApproval = !!mission?.awaiting_approval;
  const running = !terminal && !waitingApproval && !["UNKNOWN", "PAUSED", "PAUSED_RECOVERY_REQUIRED"].includes(missionState);
  const policy = mission?.timeline.policy_decisions?.at(-1);
  const pendingDecision = waitingApproval && policy?.action_id && Number(policy.requires_approval) === 1
    ? mission?.timeline.orchestrator_decisions?.findLast((row) => row.action_id === policy.action_id && Number(row.valid) === 1)
    : undefined;
  const pendingAction = recordedObject(pendingDecision?.decision_json)?.action;
  const action = pendingAction && typeof pendingAction === "object" ? pendingAction as Record<string, unknown> : null;
  const args = action?.arguments && typeof action.arguments === "object" ? action.arguments as Record<string, unknown> : null;
  const actionNames: Record<string, string> = { write_file: "Écrire un fichier", apply_patch: "Modifier un fichier", create_directory: "Créer un dossier", run_process: "Exécuter une commande", run_tests: "Lancer les tests" };
  const diffs = (mission?.timeline.tool_executions || []).flatMap((row) => {
    const result = recordedObject(row.result_json);
    return result && typeof result.diff === "string" ? [{ id: String(row.id), path: String(result.path || row.tool || "résultat"), diff: result.diff }] : [];
  });

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
      items.push({ icon: "shield", label: Number(row.valid) === 1 ? "Décision validée" : "Décision non validée", detail, done: Number(row.valid) === 1 });
    }
    if ((rows.tool_executions || []).length) {
      const row = rows.tool_executions.at(-1) || {};
      items.push({ icon: "terminal", label: "Action locale", detail: `${String(row.tool || "outil structuré")} · ${row.exit_code == null ? "résultat en attente" : `code ${row.exit_code}`}`, done: row.exit_code === 0 });
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
          <span className={`execution-orb ${completed ? "is-done" : terminal ? "is-error" : !running ? "is-idle" : ""}`} aria-hidden="true"><span /></span>
          <div>
            <strong>{missionCardStateLabel(missionState)}</strong>
            <small>{active?.objective || "Objectif non disponible"}</small>
          </div>
        </div>
        <div className="execution-card-meta">
          {running && <span className="live-label"><span className="live-dot" /> actif</span>}
          {pipeline.latency?.total_iteration_ms != null && <span className="eta-chip"><ClockIcon size={13} /> Dernière itération : {formatDuration(pipeline.latency.total_iteration_ms)}</span>}
          <button className="card-expand-button" onClick={onToggle} aria-label={expanded ? "Réduire le détail" : "Afficher le détail"}><ChevronDownIcon className={expanded ? "is-rotated" : ""} /></button>
        </div>
      </header>

      <TaskProgress key={active?.id || "unknown"} kind="mission" state={waitingApproval ? "WAITING_FOR_APPROVAL" : missionState} startedAt={active?.created_at} />
      {terminal && <section className="mission-summary" aria-label="Bilan de la mission">
        <strong>Bilan · {terminalLabel || missionState}</strong>
        <p>{(mission?.timeline.validation_results || []).filter((row) => Number(row.passed) === 1).length} validation réussie · {(mission?.timeline.validation_results || []).filter((row) => row.passed != null && Number(row.passed) === 0).length} en échec</p>
        <p>{(mission?.timeline.tool_executions || []).length} action(s) enregistrée(s) · {(mission?.timeline.artifacts || []).length} artefact(s)</p>
        {!(mission?.timeline.validation_results || []).length && <p>Aucune validation enregistrée : réussite non vérifiable ici.</p>}
        {(mission?.timeline.validation_results || []).some((row) => row.passed != null && Number(row.passed) === 0) && <p className="warning-label">Au moins une validation a échoué. Consulte sa chronologie, même si la mission est terminée.</p>}
      </section>}

      {(missionState === "PAUSED" || missionState === "PAUSED_RECOVERY_REQUIRED") && pauseReasonMessage(active?.pause_reason) && (
        <div className="inline-approval pause-reason-banner">
          <div>
            <ClockIcon size={18} />
            <span><strong>{missionState === "PAUSED" ? "Pause expliquée" : "Action requise"}</strong><small>{pauseReasonMessage(active?.pause_reason)}</small></span>
          </div>
        </div>
      )}

      {waitingApproval && (
        <div className="inline-approval">
          <div>
            <ShieldIcon size={18} />
            <span><strong>Approbation requise</strong><small>L'action suivante peut modifier le projet. Consulte les preuves techniques avant d'approuver. Cette autorisation ne vaut que pour une action.</small></span>
          </div>
          <div className="inline-approval-actions">
            <button onClick={() => onApprove("once")} className="approve-button">Approuver une fois</button>
            <button onClick={onReject} className="reject-button">Refuser</button>
          </div>
          <details className="approval-action" open>
            <summary>Action soumise à approbation</summary>
            {action && <div className="approval-readable">
              <strong>{actionNames[String(action.tool)] || String(action.tool || "Action non précisée")}</strong>
              <p aria-label="Cible de l’action">{typeof args?.path === "string" ? args.path : typeof args?.cwd === "string" ? args.cwd : active?.workspace || "Cible non précisée"}</p>
              {Array.isArray(args?.argv) && <pre>{JSON.stringify(args.argv)}</pre>}
              <p>L’autorisation ne vaut que pour cette action. Les paramètres exacts sont affichés ci-dessous.</p>
            </div>}
            {pendingAction ? <pre>{JSON.stringify(pendingAction, null, 2)}</pre> : <p>Détail de l'action non disponible. Vérifie les preuves avant de décider.</p>}
          </details>
        </div>
      )}

      <div className="execution-steps">
        {!evidence.length && <p className="execution-evidence-empty">Aucune preuve détaillée disponible pour cette mission.</p>}
        {evidence.map((step, index) => (
          <div className={`execution-step ${step.done ? "is-done" : running && index === evidence.length - 1 ? "is-current" : ""}`} key={`${step.label}-${index}`}>
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
          <section className="mission-files" aria-label="Fichiers de la mission">
            <h3>Fichiers et résultats enregistrés</h3>
            {!(mission?.timeline.artifacts || []).length && <p>Aucun artefact enregistré.</p>}
            {(mission?.timeline.artifacts || []).map((file, index) => (
              <div className="mission-file" key={String(file.id || index)}>
                <strong>{String(file.name || "Artefact")}</strong>
                <code>{String(file.path || "Chemin non disponible")}</code>
                {typeof file.sha256 === "string" && <small>SHA-256 : <code>{file.sha256}</code></small>}
              </div>
            ))}
            {diffs.map((entry, index) => <details key={`${entry.id}-${index}`} className="mission-diff">
              <summary>Diff enregistré · {entry.path}</summary>
              <pre>{entry.diff}</pre>
            </details>)}
            {!diffs.length && <p>Aucun diff enregistré. Cortex ne reconstitue pas les modifications manquantes.</p>}
          </section>
          <details>
            <summary><ActivityIcon size={14} /> Voir les preuves techniques</summary>
            <pre>{JSON.stringify(mission?.timeline || pipeline.events, null, 2)}</pre>
          </details>
        </div>
      )}
    </article>
  );
}
