"use client";

import type { MissionDetail, PipelineComponent, PipelineStatus, RuntimeStatus, TransportStatus } from "@/lib/types";
import { formatDuration, shortTime } from "@/lib/api";
import {
  executionStateLabel,
  executorDiagnosticsLabel,
  executorDisplay,
  statusPresentation,
} from "@/lib/runtimeTruth";
import { useAccessibleDialog } from "@/hooks/useAccessibleDialog";
import {
  ActivityIcon,
  AlertIcon,
  BrowserIcon,
  CameraIcon,
  CheckIcon,
  ClockIcon,
  CpuIcon,
  DatabaseIcon,
  FolderIcon,
  GlobeIcon,
  ListIcon,
  PauseIcon,
  PlayIcon,
  ShieldIcon,
  StopIcon,
  TerminalIcon,
  XIcon,
} from "./Icons";

interface PipelineInspectorProps {
  open: boolean;
  pipeline: PipelineStatus;
  runtime: RuntimeStatus;
  transport: TransportStatus;
  mission: MissionDetail | null;
  onClose: () => void;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
  onStopAll: () => void;
  onResetStop: () => void;
}

function componentIcon(id: string) {
  if (id.includes("transport") || id.includes("webbridge")) return <GlobeIcon />;
  if (id.includes("validator") || id.includes("policy") || id.includes("approval")) return <ShieldIcon />;
  if (id.includes("chrome") || id.includes("browser")) return <BrowserIcon />;
  if (id.includes("screenshot")) return <CameraIcon />;
  if (id.includes("file")) return <FolderIcon />;
  if (id.includes("ollama") || id.includes("model")) return <CpuIcon />;
  if (id.includes("database") || id.includes("sqlite")) return <DatabaseIcon />;
  if (id.includes("queue")) return <ListIcon />;
  if (id.includes("task") || id.includes("mission")) return <TerminalIcon />;
  return <ActivityIcon />;
}

function stateTone(state: PipelineComponent["state"]) {
  if (["healthy", "connected", "available", "idle"].includes(state)) return "good";
  if (["running", "waiting"].includes(state)) return "active";
  if (["degraded", "blocked"].includes(state)) return "warning";
  if (["failed", "disconnected", "unavailable"].includes(state)) return "danger";
  return "muted";
}

const componentLabels: Record<string, string> = {
  transport: "Transport ChatGPT",
  validator: "Validateur Cortex",
  task: "Tâche courante",
  chrome: "Recherche Chrome",
  screenshots: "Captures",
  filesystem: "Fichiers",
  ollama: "Disponibilité Ollama",
  executor: "Exécuteur réellement utilisé",
  approvals: "Approbations",
  queue: "File d’attente",
  database: "Persistance",
};

function translatedDetail(component: PipelineComponent, pipeline: PipelineStatus) {
  if (component.id === "task") {
    return executionStateLabel(component.detail) || component.detail;
  }
  if (component.id === "executor") {
    return executorDisplay(pipeline.runtime_execution);
  }
  return component.detail
    .replace(/chrome_extension/g, "Extension Chrome")
    .replace(/playwright/gi, "Pilote Chrome")
    .replace(/\bdaemon\b/gi, "service local")
    .replace(/\bworkspace\b/gi, "espace de travail")
    .replace(/\bhealthy\b/gi, "opérationnel")
    .replace(/\bunavailable\b/gi, "indisponible")
    .replace(/\bavailable\b/gi, "disponible")
    .replace(/\bloaded\b/gi, "chargé")
    .replace(/\binstalled\b/gi, "installé")
    .replace(/\bready\b/gi, "prêt")
    .replace(/\bmissing\b/gi, "absent");
}

export function PipelineInspector({
  open,
  pipeline,
  runtime,
  transport,
  mission,
  onClose,
  onPause,
  onResume,
  onCancel,
  onStopAll,
  onResetStop,
}: PipelineInspectorProps) {
  const missionState = mission?.mission.state;
  const running = !!missionState && !["COMPLETED", "BLOCKED", "FAILED", "CANCELLED", "PAUSED", "PAUSED_RECOVERY_REQUIRED"].includes(missionState);
  const paused = missionState === "PAUSED" || missionState === "PAUSED_RECOVERY_REQUIRED";
  const pipelinePresentation = statusPresentation(pipeline.overall);
  const pipelineLabel = !missionState && pipeline.overall === "healthy" && !transport.global_stop
    ? "Prêt"
    : pipelinePresentation.label;
  const missionLabel = executionStateLabel(missionState) || (missionState ? "En cours" : "Aucune");
  const inspectorRef = useAccessibleDialog<HTMLElement>({ open, onClose });

  return (
    <aside ref={inspectorRef} className={`pipeline-inspector ${open ? "is-open" : ""}`} aria-label="État du pipeline" aria-hidden={!open} inert={open ? undefined : true}>
      <div className="inspector-head">
        <div>
          <span className="panel-eyebrow">Pipeline</span>
          <h2>État du bridge</h2>
        </div>
        <div className="inspector-head-actions">
          <span className={`pipeline-live is-${pipelinePresentation.tone}`}><i /> {pipelineLabel}</span>
          <button className="icon-button" onClick={onClose} aria-label="Fermer le panneau Pipeline"><XIcon /></button>
        </div>
      </div>

      <details className="inspector-diagnostics">
      <summary>Diagnostics des composants · {pipeline.components.length}</summary>
      <div className="pipeline-component-grid">
        {pipeline.components.map((component) => (
          <div className={`pipeline-component tone-${stateTone(component.state)}`} key={component.id}>
            <span className="pipeline-component-icon">{componentIcon(component.id)}</span>
            <span className="pipeline-component-copy">
              <strong>{componentLabels[component.id] || component.label}</strong>
              <small>{translatedDetail(component, pipeline)}</small>
            </span>
            <span className="pipeline-component-status">
              <i />
              {statusPresentation(component.state).label}
              {component.latency_ms != null ? ` · ${formatDuration(component.latency_ms)}` : ""}
            </span>
          </div>
        ))}
      </div>
      </details>

      <section className="inspector-section">
        <div className="inspector-section-head">
          <div><span className="panel-eyebrow">Activité</span><h3>Chronologie en direct</h3></div>
        </div>
        <div className="activity-timeline">
          {pipeline.events.slice(0, 8).map((event, index) => (
            <div className="activity-event" key={event.id}>
              <span className={`activity-event-dot ${index === 0 ? "is-current" : ""}`} />
              <time>{shortTime(event.ts)}</time>
              <span><strong>{event.label}</strong>{event.detail && <small>{executionStateLabel(event.detail) || event.detail}</small>}</span>
              <em>{event.duration_ms != null ? formatDuration(event.duration_ms) : ""}</em>
            </div>
          ))}
          {!pipeline.events.length && (
            <p className="inspector-empty">{missionState ? "Aucun événement récent." : "Aucune mission active."}</p>
          )}
        </div>
      </section>

      {missionState && (
        <section className="inspector-section">
          <div className="inspector-section-head"><div><span className="panel-eyebrow">Contrôles</span><h3>Mission active</h3></div></div>
          <div className="pipeline-controls">
            <button onClick={onPause} disabled={!running}><PauseIcon /> Pause</button>
            <button onClick={onResume} disabled={!paused}><PlayIcon /> Reprendre</button>
            <button className="danger" onClick={onCancel}><StopIcon /> Annuler</button>
          </div>
        </section>
      )}

      <section className="inspector-section security-section">
        <div className="inspector-section-head"><div><span className="panel-eyebrow">Sécurité</span><h3>Arrêt général</h3></div></div>
        {transport.global_stop ? (
          <div className="global-stop-card">
            <AlertIcon />
            <span><strong>Arrêt général actif</strong><small>Aucun nouveau message ni aucune action locale ne peut démarrer.</small></span>
            <button onClick={onResetStop}>Réarmer</button>
          </div>
        ) : (
          <>
            <p className="security-copy">Interrompt les nouveaux messages et toutes les actions locales.</p>
            <button className="stop-all-button" onClick={onStopAll}><StopIcon /> Tout arrêter</button>
          </>
        )}
      </section>

      <section className="inspector-section runtime-summary">
        <div className="inspector-section-head"><div><span className="panel-eyebrow">Système local</span><h3>Exécution locale</h3></div></div>
        <dl>
          <div><dt>Candidat exécuteur détecté</dt><dd className={runtime.executor_available ? "good" : "danger"}>{runtime.executor_available ? "Oui" : "Non"}</dd></div>
          <div><dt>Exécuteur vérifié</dt><dd className={runtime.executor_verified ? "good" : "danger"}>{runtime.executor_verified ? "Oui" : "Non — aucun run confirmé"}</dd></div>
          <div><dt>Modèle candidat</dt><dd>{runtime.primary.name}</dd></div>
          <div><dt>Exécuteur utilisé</dt><dd>{executorDisplay(pipeline.runtime_execution)}</dd></div>
          <div><dt>Modèle réellement utilisé</dt><dd>{pipeline.runtime_execution.executor_model_used || "Aucun"}</dd></div>
          <div><dt>Mode d&apos;exécution</dt><dd>{executorDiagnosticsLabel(pipeline.runtime_execution)}</dd></div>
          <div><dt>Stockage local</dt><dd className={runtime.volume_mounted ? "good" : "danger"}>{runtime.volume_mounted ? "Monté" : "Absent"}</dd></div>
          <div><dt>Stockage</dt><dd title={runtime.storage_path}>{runtime.storage_path.split("/").slice(-3).join("/")}</dd></div>
          <div><dt>Mission</dt><dd>{missionLabel}</dd></div>
          <div><dt>Session</dt><dd>{mission?.mission.id?.slice(0, 8) || "—"}</dd></div>
        </dl>
      </section>

      <footer className="inspector-footer">
        <span><CheckIcon size={13} /> État mis à jour {shortTime(pipeline.updated_at)}</span>
        <span><ClockIcon size={13} /> Itération {formatDuration(pipeline.latency?.total_iteration_ms)}</span>
      </footer>
    </aside>
  );
}
