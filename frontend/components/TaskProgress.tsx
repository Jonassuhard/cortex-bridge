"use client";

import { useEffect, useState } from "react";

type Step = { label: string; detail: string; busy?: boolean; tone?: "warning" | "error" | "success" };
const chat: Record<string, Step> = {
  PREPARING: { label: "Préparation de l’envoi", detail: "Préparation des pièces jointes et prise en charge locale. Réception non confirmée.", busy: true },
  QUEUED: { label: "Message en attente", detail: "Le message attend sa prise en charge. Pas encore envoyé." },
  SELECTING_CONVERSATION: { label: "Ouverture de la conversation", detail: "Cortex vérifie la conversation cible.", busy: true },
  SENDING_TO_CHATGPT: { label: "Envoi à ChatGPT", detail: "Envoi en cours. La réception n’est pas encore confirmée.", busy: true },
  VISIBLE_IN_CHATGPT: { label: "Message visible dans ChatGPT", detail: "La présence du texte ne confirme pas encore sa soumission.", busy: true },
  WAITING_FOR_CHATGPT: { label: "En attente de ChatGPT", detail: "Le message est transmis ; Cortex attend la réponse.", busy: true },
  CHATGPT_STREAMING: { label: "Réponse en cours", detail: "La réponse arrive progressivement.", busy: true },
  COMPLETED: { label: "Réponse terminée", detail: "Le transport a signalé la fin de la réponse.", tone: "success" },
  FAILED: { label: "Envoi interrompu", detail: "Consulte l’erreur avant de réessayer.", tone: "error" },
  CANCELLED: { label: "Réponse arrêtée", detail: "Le texte déjà reçu est conservé. Le message envoyé n’est pas effacé." },
  DELIVERY_UNCERTAIN: { label: "Réception à vérifier", detail: "Pas de nouvel envoi automatique : vérifie d’abord la conversation.", tone: "warning" },
  RECOVERING: { label: "Vérification de la réception", detail: "Synchronisation seulement, sans renvoyer le message.", busy: true },
  CANCELLING: { label: "Arrêt demandé", detail: "En attente de confirmation de l’arrêt.", busy: true },
};
const mission: Record<string, Step> = {
  SENDING_OBJECTIVE: { label: "Transmission de l’objectif", detail: "Cortex transmet le périmètre de la mission.", busy: true },
  PARSING_DECISION: { label: "Lecture de la décision", detail: "Vérification de l’action proposée et de ses permissions.", busy: true },
  SENDING_REPORT: { label: "Transmission du rapport", detail: "Envoi des résultats de l’action à ChatGPT.", busy: true },
  FINAL_VALIDATION: { label: "Vérification finale", detail: "Contrôle des critères de fin de mission.", busy: true },
  INITIALIZING_MISSION: { label: "Préparation de la mission", detail: "Vérification du projet et des limites.", busy: true },
  EXECUTING_LOCAL_ACTION: { label: "Action locale en cours", detail: "L’exécuteur traite l’action autorisée.", busy: true },
  VALIDATING_ACTION: { label: "Vérification du résultat", detail: "Cortex contrôle les preuves de l’action.", busy: true },
  WAITING_FOR_CHATGPT: { label: "En attente du plan", detail: "Cortex attend la décision de ChatGPT.", busy: true },
  WAITING_FOR_APPROVAL: { label: "À toi de décider", detail: "Cette action attend ton accord. Rien à approuver automatiquement.", tone: "warning" },
  PAUSED: { label: "Mission en pause", detail: "Reprendre continue la mission ; cela n’annule pas les actions déjà effectuées.", tone: "warning" },
  PAUSED_RECOVERY_REQUIRED: { label: "Intervention nécessaire", detail: "Résous le blocage indiqué avant de reprendre.", tone: "warning" },
  COMPLETED: { label: "Exécution terminée", detail: "Consulte le bilan des preuves ci-dessous.", tone: "success" },
  FAILED: { label: "Mission échouée", detail: "Des changements peuvent déjà avoir été effectués. Consulte les preuves.", tone: "error" },
  BLOCKED: { label: "Mission bloquée", detail: "Consulte le motif. Aucune progression n’est présumée.", tone: "warning" },
  CANCELLED: { label: "Mission annulée", detail: "Les changements déjà effectués ne sont pas restaurés automatiquement." },
};

export function TaskProgress({ kind, state, startedAt }: { kind: "chat" | "mission"; state: string; startedAt?: string | number }) {
  const step = (kind === "chat" ? chat : mission)[state] || { label: "État non disponible", detail: "Aucune activité confirmée à afficher." };
  const [now, setNow] = useState(() => Date.now());
  const start = typeof startedAt === "number" ? startedAt * 1000 : Date.parse(startedAt || "");
  const timed = step.busy && Number.isFinite(start) && start <= now;
  useEffect(() => {
    if (!step.busy || !Number.isFinite(start)) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [step.busy, start]);
  const seconds = Math.max(0, Math.floor((now - start) / 1000));
  return <section className={`task-progress tone-${step.tone || "neutral"}`} aria-label={kind === "chat" ? "Suivi du message" : "Suivi de la mission"}>
    <div className="task-progress-heading">
      <span className={step.busy ? "task-spinner" : "task-state-dot"} aria-hidden="true" />
      <output aria-live="polite"><strong>{step.label}</strong><span className="task-detail">{step.detail}</span></output>
      {timed && <span className="task-elapsed" aria-label="Temps depuis le démarrage">{Math.floor(seconds / 60)} min {seconds % 60} s</span>}
    </div>
    {step.busy && <progress aria-label={step.label} />}
  </section>;
}
