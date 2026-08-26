"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useState } from "react";
import { api, postJson } from "@/lib/api";
import { AlertIcon, CheckIcon, RefreshIcon, XIcon } from "./Icons";

interface OnboardingCheck {
  id: string;
  label: string;
  state: "ok" | "missing";
  detail: string;
  hint: string;
}

interface OnboardingState {
  completed: boolean;
  ready: boolean;
  checks: OnboardingCheck[];
}

/**
 * First-launch assistant. Shown once (persisted server-side), re-checks the
 * real prerequisites on demand. Everything is French, matching the product.
 */
interface OnboardingPanelProps {
  onOpenSettings: () => void;
  onOpenChatGPTProfile: () => Promise<void> | void;
  forceOpen?: boolean;
  onCloseGuide?: () => void;
}

export function OnboardingPanel({ onOpenSettings, onOpenChatGPTProfile, forceOpen = false, onCloseGuide }: OnboardingPanelProps) {
  const [state, setState] = useState<OnboardingState | null>(null);
  const [hidden, setHidden] = useState(false);
  const [checking, setChecking] = useState(false);
  const [openingBrowser, setOpeningBrowser] = useState(false);
  const [browserError, setBrowserError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setChecking(true);
    try {
      setState(await api<OnboardingState>("/api/onboarding"));
    } catch {
      setState(null);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Quand le guide est rouvert manuellement, revérifier les prérequis réels.
  useEffect(() => {
    if (forceOpen) void refresh();
  }, [forceOpen, refresh]);

  if (!state || (!forceOpen && (state.completed || hidden))) return null;

  const dismiss = async () => {
    if (forceOpen && onCloseGuide) {
      onCloseGuide();
      return;
    }
    try {
      await postJson("/api/onboarding/dismiss", {});
    } catch {
      // Dismissal persistence failing must not trap the user on the panel.
    }
    setHidden(true);
  };

  const openBrowser = async () => {
    setOpeningBrowser(true);
    setBrowserError(null);
    try {
      await onOpenChatGPTProfile();
      await refresh();
    } catch {
      setBrowserError("La connexion à l’extension Chrome a échoué. Réessaie ou ouvre les paramètres.");
    } finally {
      setOpeningBrowser(false);
    }
  };

  const extensionOk = state.checks.some((c) => c.id === "browser-driver" && c.state === "ok");
  const chatgptOk = state.checks.some((c) => c.id === "chatgpt-tab" && c.state === "ok");
  const steps = [
    {
      title: "Couplage automatique",
      text: "L’extension Chrome se lie à cette console toute seule au chargement de la page — aucun code à copier.",
      done: extensionOk,
    },
    {
      title: "Ouvrir ChatGPT",
      text: "Le bouton ci-dessous ouvre ChatGPT dans le même groupe d’onglets Chrome « Cortex Bridge » que cette console.",
      done: chatgptOk,
    },
    {
      title: "Écrire une tâche",
      text: "Décris ta tâche dans le chat : ChatGPT propose un plan, tu valides chaque étape sensible, Cortex exécute sur ta machine et consigne tout dans l’historique.",
      done: false,
    },
  ];

  return (
    // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- This styled overlay is controlled by React and does not use the native dialog lifecycle.
    <div className="settings-overlay" role="dialog" aria-modal="true" aria-label="Bienvenue dans Cortex Bridge">
      <div className="settings-backdrop" />
      <section className="settings-panel onboarding-panel">
        <header className="settings-head">
          <div>
            <span className="panel-eyebrow">Cortex Bridge</span>
            <h2>{forceOpen ? "Guide de démarrage" : "Bienvenue"}</h2>
            <p>Trois gestes et tout fonctionne. ChatGPT planifie, tu valides, Cortex exécute sur ta machine.</p>
          </div>
          <button className="icon-button" onClick={() => void dismiss()} aria-label="Fermer l'assistant"><XIcon /></button>
        </header>
        <ol className="onboarding-steps">
          {steps.map((step, index) => (
            <li className={`onboarding-step ${step.done ? "ok" : ""}`} key={step.title}>
              <span className="onboarding-step-index" aria-hidden>{step.done ? "✓" : index + 1}</span>
              <span>
                <strong>{step.title}</strong>
                <small>{step.text}</small>
              </span>
            </li>
          ))}
        </ol>
        <div className="onboarding-checks">
          {state.checks.map((check) => (
            <div className={`onboarding-check ${check.state}`} key={check.id}>
              <span className="onboarding-check-icon">{check.state === "ok" ? <CheckIcon /> : <AlertIcon />}</span>
              <span>
                <strong>{check.label}</strong>
                <small>{check.detail}</small>
                {check.hint ? <em>{check.hint}</em> : null}
              </span>
            </div>
          ))}
          {browserError ? (
            <p className="diagnostic-result failed" role="alert">{browserError}</p>
          ) : null}
        </div>
        <footer className="settings-footer">
          <span>{state.ready ? "Tout est prêt." : "Certains prérequis manquent — tu peux quand même explorer."}</span>
          <div>
            <button className="secondary-button" disabled={openingBrowser} onClick={() => void openBrowser()}>
              {openingBrowser ? "Ouverture…" : "Ouvrir ChatGPT"}
            </button>
            <button className="secondary-button" onClick={onOpenSettings}>Ouvrir les paramètres</button>
            <button className="secondary-button" disabled={checking} onClick={() => void refresh()}>
              <RefreshIcon size={13} /> {checking ? "Vérification…" : "Revérifier"}
            </button>
            <button className="primary-button" onClick={() => void dismiss()}>
              {state.ready ? "Commencer" : "Continuer quand même"}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
