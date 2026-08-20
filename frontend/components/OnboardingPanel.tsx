"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useState } from "react";
import { ApiError, api, postJson } from "@/lib/api";
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
export function OnboardingPanel({ onOpenSettings }: { onOpenSettings: () => void }) {
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

  if (!state || state.completed || hidden) return null;

  const dismiss = async () => {
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
      await postJson("/api/onboarding/browser/open", {});
      await refresh();
    } catch (error) {
      if (error instanceof ApiError) {
        const envelope = error.detail as { detail?: { error?: string } } | undefined;
        setBrowserError(
          envelope?.detail?.error
            ? `Le profil navigateur n’a pas pu être ouvert : ${envelope.detail.error}`
            : "Le profil navigateur n’a pas pu être ouvert. Vérifie l’installation de Chromium."
        );
      } else {
        setBrowserError("Le profil navigateur n’a pas pu être ouvert.");
      }
    } finally {
      setOpeningBrowser(false);
    }
  };

  return (
    // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- This styled overlay is controlled by React and does not use the native dialog lifecycle.
    <div className="settings-overlay" role="dialog" aria-modal="true" aria-label="Bienvenue dans Cortex Bridge">
      <div className="settings-backdrop" />
      <section className="settings-panel onboarding-panel">
        <header className="settings-head">
          <div>
            <span className="panel-eyebrow">Cortex Bridge</span>
            <h2>Bienvenue</h2>
            <p>Vérifions ensemble que tout est prêt. ChatGPT planifie, Ollama exécute sur ta machine.</p>
          </div>
          <button className="icon-button" onClick={() => void dismiss()} aria-label="Fermer l'assistant"><XIcon /></button>
        </header>
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
              {openingBrowser ? "Ouverture…" : "Ouvrir le profil de connexion"}
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
