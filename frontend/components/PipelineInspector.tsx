"use client";

import type { MissionDetail, PipelineComponent, PipelineStatus, RuntimeStatus, TransportStatus } from "@/lib/types";
import { formatDuration, shortTime } from "@/lib/api";
import {
  ActivityIcon,
  AlertIcon,
  BrowserIcon,
  CameraIcon,
  CheckIcon,
  ChevronRightIcon,
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
  if (["healthy", "connected", "idle"].includes(state)) return "good";
  if (["running", "waiting"].includes(state)) return "active";
  if (["degraded", "blocked"].includes(state)) return "warning";
  if (["failed", "disconnected"].includes(state)) return "danger";
  return "muted";
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
  const missionState = mission?.mission.state || pipeline.active_mission_state;
  const running = !!missionState && !["COMPLETED", "BLOCKED", "FAILED", "CANCELLED", "PAUSED", "PAUSED_RECOVERY_REQUIRED"].includes(missionState);
  const paused = missionState === "PAUSED" || missionState === "PAUSED_RECOVERY_REQUIRED";

  return (
    <aside className={`pipeline-inspector ${open ? "is-open" : ""}`} aria-label="État de la pipeline">
      <div className="inspector-head">
        <div>
          <span className="panel-eyebrow">Pipeline</span>
          <h2>État du bridge</h2>
        </div>
        <div className="inspector-head-actions">
          <span className={`pipeline-live ${pipeline.overall === "failed" ? "is-error" : ""}`}><i /> {pipeline.overall === "failed" ? "Dégradé" : "Live"}</span>
          <button className="icon-button" onClick={onClose} aria-label="Fermer la pipeline"><XIcon /></button>
        </div>
      </div>

      {transport.global_stop && (
        <div className="global-stop-card">
          <AlertIcon />
          <span><strong>STOP EVERYTHING actif</strong><small>Aucun nouveau message ni aucune action locale ne peut démarrer.</small></span>
          <button onClick={onResetStop}>Réarmer</button>
        </div>
      )}

      <div className="pipeline-component-grid">
        {pipeline.components.map((component) => (
          <div className={`pipeline-component tone-${stateTone(component.state)}`} key={component.id}>
            <span className="pipeline-component-icon">{componentIcon(component.id)}</span>
            <span className="pipeline-component-copy">
              <strong>{component.label}</strong>
              <small>{component.detail}</small>
            </span>
            <span className="pipeline-component-status">
              <i />
              {component.latency_ms != null ? formatDuration(component.latency_ms) : component.state}
            </span>
          </div>
        ))}
      </div>

      <section className="inspector-section">
        <div className="inspector-section-head">
          <div><span className="panel-eyebrow">Activité</span><h3>Chronologie en direct</h3></div>
          <button>Logs complets <ChevronRightIcon size={13} /></button>
        </div>
        <div className="activity-timeline">
          {pipeline.events.slice(0, 8).map((event, index) => (
            <div className="activity-event" key={event.id}>
              <span className={`activity-event-dot ${index === 0 ? "is-current" : ""}`} />
              <time>{shortTime(event.ts)}</time>
              <span><strong>{event.label}</strong>{event.detail && <small>{event.detail}</small>}</span>
              <em>{event.duration_ms != null ? formatDuration(event.duration_ms) : ""}</em>
            </div>
          ))}
          {!pipeline.events.length && <p className="inspector-empty">Aucun événement récent.</p>}
        </div>
      </section>

      <section className="inspector-section">
        <div className="inspector-section-head"><div><span className="panel-eyebrow">Contrôles</span><h3>Mission active</h3></div></div>
        <div className="pipeline-controls">
          <button onClick={onPause} disabled={!running}><PauseIcon /> Pause</button>
          <button onClick={onResume} disabled={!paused}><PlayIcon /> Reprendre</button>
          <button className="danger" onClick={onCancel} disabled={!missionState}><StopIcon /> Annuler</button>
        </div>
        <button className="stop-all-button" onClick={onStopAll}><StopIcon /> Stop everything</button>
      </section>

      <section className="inspector-section runtime-summary">
        <div className="inspector-section-head"><div><span className="panel-eyebrow">Runtime</span><h3>Exécution locale</h3></div></div>
        <dl>
          <div><dt>Disponibilité Ollama</dt><dd className={runtime.executor_available ? "good" : "danger"}>{runtime.executor_available ? "disponible" : "indisponible"}</dd></div>
          <div><dt>Modèle candidat</dt><dd>{runtime.primary.name}</dd></div>
          <div><dt>Exécuteur utilisé</dt><dd>{pipeline.runtime_execution.executor_kind}</dd></div>
          <div><dt>Modèle réellement utilisé</dt><dd>{pipeline.runtime_execution.executor_model_used || "aucun"}</dd></div>
          <div><dt>Disque DJO</dt><dd className={runtime.volume_mounted ? "good" : "danger"}>{runtime.volume_mounted ? "monté" : "absent"}</dd></div>
          <div><dt>Stockage</dt><dd title={runtime.storage_path}>{runtime.storage_path.split("/").slice(-3).join("/")}</dd></div>
          <div><dt>Mission</dt><dd>{missionState || "aucune"}</dd></div>
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
