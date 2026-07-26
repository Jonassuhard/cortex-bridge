"use client";
/* eslint-disable react/no-unescaped-entities */

import { useMemo, useState } from "react";
import type { ChatGPTModelInfo, CortexSettings, OllamaModelInfo, RuntimeTruth } from "@/lib/types";
import { formatBytes } from "@/lib/api";
import { executorDiagnosticsLabel, isAvailableComponentState } from "@/lib/runtimeTruth";
import {
  AlertIcon,
  BrowserIcon,
  CheckIcon,
  CpuIcon,
  DatabaseIcon,
  FolderIcon,
  GlobeIcon,
  InfoIcon,
  SettingsIcon,
  ShieldIcon,
  TrashBlockedIcon,
  XIcon,
} from "./Icons";
import { BridgeDiagram } from "./BridgeDiagram";

interface SettingsPanelProps {
  open: boolean;
  settings: CortexSettings;
  ollamaModels: OllamaModelInfo[];
  chatgptModels: ChatGPTModelInfo[];
  runtimeExecution: RuntimeTruth;
  saving: boolean;
  onClose: () => void;
  onSave: (settings: CortexSettings) => Promise<void>;
  onSelectChatGPTModel: (label: string) => Promise<void>;
}

type TabId = "general" | "models" | "permissions" | "transport" | "runtime" | "storage" | "diagnostics" | "info";

const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "general", label: "Général", icon: <SettingsIcon /> },
  { id: "models", label: "Modèles", icon: <CpuIcon /> },
  { id: "permissions", label: "Permissions", icon: <ShieldIcon /> },
  { id: "transport", label: "Transport", icon: <GlobeIcon /> },
  { id: "runtime", label: "Runtime", icon: <BrowserIcon /> },
  { id: "storage", label: "Stockage", icon: <DatabaseIcon /> },
  { id: "diagnostics", label: "Diagnostics", icon: <AlertIcon /> },
  { id: "info", label: "Info", icon: <InfoIcon /> },
];

function Toggle({ checked, onChange, label, description, danger = false, disabled = false }: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description: string;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    // oxlint-disable-next-line jsx-a11y/label-has-associated-control -- The checkbox is nested in its native label and the text is supplied by props.
    <label className={`settings-toggle-row ${danger ? "is-danger" : ""} ${disabled ? "is-disabled" : ""}`}>
      <span><strong>{label}</strong><small>{description}</small></span>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
      <i />
    </label>
  );
}

export function SettingsPanel({
  open,
  settings,
  ollamaModels,
  chatgptModels,
  runtimeExecution,
  saving,
  onClose,
  onSave,
  onSelectChatGPTModel,
}: SettingsPanelProps) {
  const [tab, setTab] = useState<TabId>("general");
  const [draft, setDraft] = useState<CortexSettings>(settings);
  const [labConfirmation, setLabConfirmation] = useState("");
  const [diagTesting, setDiagTesting] = useState<string | null>(null);
  const [diagResult, setDiagResult] = useState<{ label: string; state: string; detail: string } | null>(null);

  const runDiagnostic = async (componentId: string, label: string) => {
    setDiagTesting(componentId);
    setDiagResult(null);
    try {
      const response = await fetch("/api/pipeline/status");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const component = (payload.components || []).find((row: { id: string }) => row.id === componentId);
      if (!component) throw new Error("composant introuvable");
      const ok = isAvailableComponentState(component.state) || component.state === "idle";
      setDiagResult({ label, state: ok ? "ok" : "failed", detail: String(component.detail || component.state) });
    } catch {
      setDiagResult({ label, state: "failed", detail: "Test impossible — la console est-elle démarrée ?" });
    } finally {
      setDiagTesting(null);
    }
  };

  const primaryOptions = useMemo(() => {
    const names = new Set(ollamaModels.map((model) => model.name));
    names.add(settings.primary_executor);
    return Array.from(names).filter(Boolean);
  }, [ollamaModels, settings.primary_executor]);

  if (!open) return null;

  const patch = <K extends keyof CortexSettings>(key: K, value: CortexSettings[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const exportDiagnostics = async () => {
    try {
      const response = await fetch("/api/diagnostics/export");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `cortex-diagnostic-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      window.alert("Impossible de générer le rapport de diagnostic. La console est-elle démarrée ?");
    }
  };

  return (
    // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- This styled overlay is controlled by React and does not use the native dialog lifecycle.
    <div className="settings-overlay" role="dialog" aria-modal="true" aria-label="Paramètres Cortex Bridge">
      <button className="settings-backdrop" onClick={onClose} aria-label="Fermer les paramètres" />
      <section className="settings-panel">
        <header className="settings-head">
          <div><span className="panel-eyebrow">Cortex Bridge</span><h2>Paramètres</h2><p>Configure les modèles, le transport et les limites d'accès sans exposer les identifiants.</p></div>
          <button className="icon-button" onClick={onClose}><XIcon /></button>
        </header>
        <div className="settings-layout">
          <nav className="settings-tabs">
            {tabs.map((item) => (
              <button className={tab === item.id ? "is-active" : ""} key={item.id} onClick={() => setTab(item.id)}>{item.icon}<span>{item.label}</span></button>
            ))}
          </nav>
          <div className="settings-content">
            {tab === "general" && (
              <div className="settings-section-stack">
                <div className="settings-section-title"><h3>Expérience générale</h3><p>Préférences de l'application locale et comportement de la conversation.</p></div>
                <div className="settings-grid two">
                  <label><span>Langue</span><select value={draft.language} onChange={(e) => patch("language", e.target.value as CortexSettings["language"])}><option value="fr">Français</option><option value="en">English</option></select></label>
                  <label><span>Thème</span><select value={draft.theme} onChange={(e) => patch("theme", e.target.value as CortexSettings["theme"])}><option value="dark">Sombre</option><option value="light">Clair</option><option value="system">Système</option></select></label>
                </div>
                <label className="settings-field"><span>Workspace par défaut</span><input value={draft.default_workspace} onChange={(e) => patch("default_workspace", e.target.value)} /><small>Les outils structurés restent confinés à ce dossier sauf profil étendu explicite.</small></label>
                <div className="settings-grid two">
                  <label><span>Itérations maximum</span><input type="number" min={1} max={100} value={draft.max_iterations} onChange={(e) => patch("max_iterations", Number(e.target.value))} /></label>
                  <label><span>Durée maximum (minutes)</span><input type="number" min={1} max={240} value={draft.max_duration_minutes} onChange={(e) => patch("max_duration_minutes", Number(e.target.value))} /></label>
                </div>
                <Toggle checked={draft.auto_continue} onChange={(value) => patch("auto_continue", value)} label="Continuer automatiquement" description="Renvoie les rapports à ChatGPT et attend la décision suivante sans copier-coller." />
                <Toggle checked={draft.persist_conversation_history} onChange={(value) => patch("persist_conversation_history", value)} label="Conserver l'historique local" description="Stocke les messages sélectionnés dans SQLite. Désactivé par défaut pour limiter la copie locale." />
              </div>
            )}

            {tab === "models" && (
              <div className="settings-section-stack">
                <div className="settings-section-title"><h3>Modèles</h3><p>ChatGPT planifie. Mode A exécute des outils déterministes ; Ollama n'est revendiqué que lorsqu'un appel local réussit réellement.</p></div>
                <label className="settings-field"><span>Modèle ChatGPT visible</span>
                  <select
                    value={draft.planner_model}
                    onChange={async (e) => {
                      patch("planner_model", e.target.value);
                      await onSelectChatGPTModel(e.target.value);
                    }}
                  >
                    {chatgptModels.length ? chatgptModels.map((model) => <option value={model.label} key={model.label}>{model.label}{model.selected ? " · sélectionné" : ""}</option>) : <option value={draft.planner_model}>{draft.planner_model}</option>}
                  </select>
                  <small>Le changement est confirmé uniquement si le sélecteur visible de ChatGPT affiche le modèle demandé.</small>
                </label>
                <label className="settings-field"><span>Modèle Ollama candidat</span><select value={draft.primary_executor} onChange={(e) => patch("primary_executor", e.target.value)}>{primaryOptions.map((name) => <option value={name} key={name}>{name}</option>)}</select><small>Installé ou chargé ne signifie pas exécuté. Le modèle utilisé apparaît seulement après un appel réussi.</small></label>
                <label className="settings-field"><span>Contexte Ollama</span><select value={draft.ollama_context} onChange={(e) => patch("ollama_context", Number(e.target.value))}><option value={4096}>4K — rapide</option><option value={8192}>8K — recommandé</option><option value={12288}>12K — Qwen fallback</option><option value={16384}>16K — pression mémoire élevée</option></select><small>Sur un M1 16 Go, le contexte est borné pour laisser de la mémoire au navigateur et aux tests.</small></label>
                <div className="model-table">
                  {ollamaModels.map((model) => (
                    <div className="model-table-row" key={model.name}>
                      <span className="model-state-dot" />
                      <span><strong>{model.name}</strong><small>{model.loaded ? "chargé en mémoire" : "installé localement"}</small></span>
                      <em>{formatBytes(model.size)}</em>
                    </div>
                  ))}
                  {!ollamaModels.length && <p className="settings-empty">Aucun modèle Ollama détecté.</p>}
                </div>
              </div>
            )}

            {tab === "permissions" && (
              <div className="settings-section-stack">
                <div className="settings-section-title"><h3>Permissions</h3><p>Le modèle propose des actions structurées. Le bridge décide et exécute les opérations réelles.</p></div>
                <label className="settings-field"><span>Profil d'accès</span><select value={draft.access_profile} onChange={(e) => patch("access_profile", e.target.value as CortexSettings["access_profile"])}><option value="observe">Observe — lecture uniquement</option><option value="workspace">Workspace — lecture / écriture bornée</option><option value="extended">Extended — plusieurs racines explicites</option><option value="browser-research">Browser Research — Chrome séparé</option><option value="lab">Lab Full Access — environnement isolé</option></select></label>
                <label className="settings-field"><span>Politique d'approbation</span><select value={draft.approval_policy} onChange={(e) => patch("approval_policy", e.target.value as CortexSettings["approval_policy"])}><option value="read-only-automatic">Lecture automatique</option><option value="workspace-write-with-approvals">Écritures avec approbation</option><option value="workspace-write-automatic">Écritures automatiques dans le workspace</option></select></label>
                <Toggle checked={draft.never_delete_files} onChange={() => {}} disabled label="Ne jamais supprimer les fichiers" description="Invariant permanent : toute demande de suppression devient une archive restaurable." />
                <Toggle checked={draft.browser_research} onChange={(value) => patch("browser_research", value)} label="Navigation Chrome séparée" description="Autorise recherche, navigation, snapshots et captures dans un profil distinct du chat de contrôle." />
                <Toggle checked={draft.network_access} onChange={(value) => patch("network_access", value)} label="Accès réseau sortant" description="Désactivé par défaut. Les destinations doivent être explicitement autorisées." />
                {draft.access_profile === "lab" && (
                  <div className="lab-warning">
                    <AlertIcon />
                    <div><strong>Mode laboratoire</strong><p>À utiliser uniquement dans un compte macOS dédié ou une VM. Le shell brut reste interdit et la suppression permanente reste bloquée.</p><input placeholder="Taper ACTIVER LE MODE LAB" value={labConfirmation} onChange={(e) => setLabConfirmation(e.target.value)} /></div>
                  </div>
                )}
              </div>
            )}

            {tab === "transport" && (
              <div className="settings-section-stack">
                <div className="settings-section-title"><h3>Transport ChatGPT</h3><p>Le bridge contrôle une conversation sélectionnée avec un profil navigateur Cortex dédié, sans API OpenAI.</p></div>
                <div className="settings-notice"><GlobeIcon /><span><strong>Transport expérimental</strong><small>La compatibilité dépend du DOM de ChatGPT. Aucun CAPTCHA, identifiant ou mécanisme anti-bot n'est contourné.</small></span></div>
                <div className="settings-grid two">
                  <label><span>Driver navigateur</span><select value={draft.browser_transport} onChange={(e) => patch("browser_transport", e.target.value as CortexSettings["browser_transport"])}><option value="playwright">Playwright — distribué</option><option value="webbridge">WebBridge — compatibilité</option></select></label>
                  <label><span>Racine des profils</span><input value={draft.browser_profile_root} onChange={(e) => patch("browser_profile_root", e.target.value)} /></label>
                </div>
                <div className="settings-grid two">
                  <label><span>Stabilité de réponse</span><input type="number" step="0.5" min={1} max={10} value={draft.response_stability_seconds} onChange={(e) => patch("response_stability_seconds", Number(e.target.value))} /></label>
                  <label><span>Timeout ChatGPT</span><input type="number" min={30} max={900} value={draft.chat_timeout_seconds} onChange={(e) => patch("chat_timeout_seconds", Number(e.target.value))} /></label>
                </div>
                <ul className="settings-check-list"><li><CheckIcon /> Verrouillage par URL et identité de conversation</li><li><CheckIcon /> Confirmation visuelle avant de considérer un message livré</li><li><CheckIcon /> Protection anti-doublon et livraison incertaine</li><li><CheckIcon /> Arrêt sur connexion, CAPTCHA ou rate-limit</li></ul>
              </div>
            )}

            {tab === "runtime" && (
              <div className="settings-section-stack">
                <div className="settings-section-title"><h3>Runtime local</h3><p>État des services utilisés par Cortex Bridge.</p></div>
                <div className="settings-runtime-cards">
                  <div><CpuIcon /><span><strong>Ollama</strong><small>127.0.0.1:11434 · loopback uniquement</small></span><em className="good">healthy</em></div>
                  <div><BrowserIcon /><span><strong>WebBridge</strong><small>127.0.0.1:10086 · Chrome signé</small></span><em className="good">connected</em></div>
                  <div><DatabaseIcon /><span><strong>SQLite</strong><small>missions, décisions, preuves et approbations</small></span><em className="good">ready</em></div>
                </div>
              </div>
            )}

            {tab === "storage" && (
              <div className="settings-section-stack">
                <div className="settings-section-title"><h3>Stockage</h3><p>Modèles, preuves, archives et historique local.</p></div>
                <div className="storage-path-card"><FolderIcon /><span><strong>Modèles Ollama</strong><small>/tmp/cortex-demo-workspace/models</small></span></div>
                <div className="storage-path-card"><DatabaseIcon /><span><strong>Base de missions</strong><small>console/data/cortex.db</small></span></div>
                <div className="storage-path-card"><TrashBlockedIcon /><span><strong>Archives restaurables</strong><small>.cortex-archive/&lt;mission&gt;/&lt;timestamp&gt;</small></span></div>
                <div className="settings-notice"><ShieldIcon /><span><strong>Repli interdit</strong><small>Si le stockage local est absent, Cortex n'enregistre pas silencieusement les modèles ailleurs.</small></span></div>
              </div>
            )}

            {tab === "diagnostics" && (
              <div className="settings-section-stack">
                <div className="settings-section-title"><h3>Diagnostics</h3><p>Les détails bruts restent séparés de l'interface de conversation.</p></div>
                <div className="diagnostic-actions">
                  <button disabled={diagTesting !== null} onClick={() => void runDiagnostic("transport", "WebBridge")}>{diagTesting === "transport" ? "Test…" : "Tester WebBridge"}</button>
                  <button disabled={diagTesting !== null} onClick={() => void runDiagnostic("ollama", "Ollama")}>{diagTesting === "ollama" ? "Test…" : "Tester Ollama"}</button>
                  <button disabled={diagTesting !== null} onClick={() => void runDiagnostic("database", "SQLite")}>{diagTesting === "database" ? "Test…" : "Vérifier SQLite"}</button>
                  <button onClick={() => void exportDiagnostics()}>Exporter le rapport</button>
                </div>
                {diagResult && (
                  <p className={`diagnostic-result ${diagResult.state}`}>
                    {diagResult.state === "ok" ? "✅" : "❌"} {diagResult.label} — {diagResult.detail}
                  </p>
                )}
                <p className="diagnostic-note">Le rapport est anonymisé : chemins personnels remplacés par ~, identifiants de conversation hachés, aucun contenu de message. Tu peux le coller tel quel dans une issue GitHub.</p>
                <pre className="diagnostic-console">{`Cortex Bridge UI\n- frontend: Next.js static export\n- backend: FastAPI\n- transport: WebBridge experimental\n- executor: ${executorDiagnosticsLabel(runtimeExecution)}\n- deletion: blocked / archive only`}</pre>
              </div>
            )}

            {tab === "info" && (
              <div className="settings-section-stack">
                <div className="settings-section-title"><h3>Comment ça marche</h3><p>Un cerveau dans le cloud, des mains sur ta machine, une seule boucle de conversation.</p></div>
                <BridgeDiagram />
                <ul className="settings-check-list">
                  <li><CheckIcon /> ChatGPT planifie et découpe — il ne touche à rien directement</li>
                  <li><CheckIcon /> Mode A exécute les outils déterministes ; Ollama reste un chemin local distinct</li>
                  <li><CheckIcon /> Le rapport repart dans la conversation et la boucle continue</li>
                  <li><CheckIcon /> Loopback uniquement : rien ne sort de ta machine sauf via ChatGPT</li>
                </ul>
                <div className="settings-notice"><GlobeIcon /><span><strong>Projet open source (MIT)</strong><small>Dépôt public Cortex Bridge — idées et contributions bienvenues via Issues et Discussions.</small></span></div>
              </div>
            )}
          </div>
        </div>
        <footer className="settings-footer">
          <span><ShieldIcon size={13} /> Les secrets ne sont jamais renvoyés au navigateur.</span>
          <div><button className="secondary-button" onClick={onClose}>Annuler</button><button className="primary-button" disabled={saving || (draft.access_profile === "lab" && labConfirmation !== "ACTIVER LE MODE LAB")} onClick={() => void onSave(draft)}>{saving ? "Enregistrement…" : "Enregistrer"}</button></div>
        </footer>
      </section>
    </div>
  );
}
