"use client";
/* eslint-disable react/no-unescaped-entities */

import { useCallback, useEffect, useState } from "react";
import type { MissionDetail, MissionSummary } from "@/lib/types";
import { api } from "@/lib/api";
import { executionStateLabel } from "@/lib/runtimeTruth";
import { ChevronDownIcon, ClockIcon, RefreshIcon, XIcon } from "./Icons";

interface HistoryPanelProps {
  open: boolean;
  onClose: () => void;
}

function formatEpoch(value?: number): string {
  if (!value) return "";
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  const time = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(date);
  if (date.toDateString() === now.toDateString()) return `Aujourd'hui ${time}`;
  return `${new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short" }).format(date)} ${time}`;
}

function stateChipClass(state: string): string {
  if (state === "COMPLETED") return "is-done";
  if (state === "FAILED" || state === "BLOCKED") return "is-error";
  if (state === "CANCELLED") return "is-idle";
  return "is-active";
}

function legacyDetailLines(detail: MissionDetail | null): { label: string; value: string }[] {
  if (!detail?.mission?.legacy) return [];
  const data = (detail.mission.legacy_detail || {}) as Record<string, unknown>;
  const lines: { label: string; value: string }[] = [];
  if (typeof data.response_text === "string" && data.response_text) {
    lines.push({ label: "Réponse", value: data.response_text.slice(0, 600) });
  }
  if (typeof data.summary === "string" && data.summary) {
    lines.push({ label: "Résumé", value: data.summary });
  }
  if (Array.isArray(data.files_changed) && data.files_changed.length) {
    lines.push({ label: "Fichiers modifiés", value: data.files_changed.join(", ") });
  }
  if (Array.isArray(data.blockers) && data.blockers.length) {
    lines.push({ label: "Blocages", value: data.blockers.join(", ") });
  }
  if (typeof data.error === "string" && data.error) {
    lines.push({ label: "Erreur", value: data.error });
  }
  if (typeof data.conversation_url === "string" && data.conversation_url) {
    lines.push({ label: "Conversation", value: data.conversation_url });
  }
  return lines;
}

export function HistoryPanel({ open, onClose }: HistoryPanelProps) {
  const [missions, setMissions] = useState<MissionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MissionDetail | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await api<MissionSummary[]>("/api/missions");
      setMissions(rows);
    } catch {
      setError("Impossible de charger l'historique. La console est-elle démarrée ?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  const toggle = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(id);
    setDetail(null);
    try {
      setDetail(await api<MissionDetail>(`/api/missions/${id}`));
    } catch {
      setDetail(null);
    }
  };

  if (!open) return null;

  const detailLines = legacyDetailLines(detail);
  const timeline = detail?.timeline || {};
  const counts: { label: string; value: number }[] = detail && !detail.mission.legacy
    ? [
        { label: "Décisions", value: (timeline.orchestrator_decisions || []).length },
        { label: "Actions locales", value: (timeline.tool_executions || []).length },
        { label: "Validations", value: (timeline.validation_results || []).length },
        { label: "Événements transport", value: (timeline.transport_events || []).length },
      ]
    : [];

  return (
    // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- styled overlay controlled by React.
    <div className="settings-overlay" role="dialog" aria-modal="true" aria-label="Historique des missions Cortex Bridge">
      <button className="settings-backdrop" onClick={onClose} aria-label="Fermer l'historique" />
      <section className="settings-panel history-panel">
        <header className="settings-head">
          <div>
            <span className="panel-eyebrow">Cortex Bridge</span>
            <h2>Historique des missions</h2>
            <p>Toutes les missions et exécutions passées, y compris les archives antérieures à la v0.5.</p>
          </div>
          <div>
            <button className="icon-button" onClick={() => void refresh()} aria-label="Recharger l'historique"><RefreshIcon /></button>
            <button className="icon-button" onClick={onClose} aria-label="Fermer l'historique"><XIcon /></button>
          </div>
        </header>
        <div className="history-content">
          {loading && <p className="history-empty">Chargement…</p>}
          {error && <p className="history-empty">{error}</p>}
          {!loading && !error && missions.length === 0 && (
            <p className="history-empty">Aucune mission pour l'instant. Lance une mission depuis une conversation pour la voir ici.</p>
          )}
          {!loading && missions.map((mission) => (
            <article key={mission.id} className={`history-row ${expandedId === mission.id ? "is-expanded" : ""}`}>
              <button className="history-row-main" onClick={() => void toggle(mission.id)} aria-expanded={expandedId === mission.id}>
                <span className={`history-state ${stateChipClass(mission.state)}`}>{executionStateLabel(mission.state)}</span>
                <span className="history-copy">
                  <strong>{mission.objective || "Mission sans objectif"}</strong>
                  <small>
                    {formatEpoch(mission.created_at)}
                    {mission.legacy ? " · archive" : ""}
                    {mission.pause_reason ? ` · ${mission.pause_reason}` : ""}
                  </small>
                </span>
                <ChevronDownIcon className={expandedId === mission.id ? "is-rotated" : ""} />
              </button>
              {expandedId === mission.id && (
                <div className="history-detail">
                  {!detail && <p className="history-empty">Chargement du détail…</p>}
                  {detail && detailLines.map((line) => (
                    <p key={line.label}><strong>{line.label} :</strong> {line.value}</p>
                  ))}
                  {detail && counts.map((count) => (
                    <p key={count.label}><strong>{count.label} :</strong> {count.value}</p>
                  ))}
                  {detail?.mission.workspace && <p><strong>Workspace :</strong> {detail.mission.workspace}</p>}
                  {detail?.mission.pause_reason && (
                    <p><strong><ClockIcon size={12} /> Pause :</strong> {detail.mission.pause_reason}</p>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
