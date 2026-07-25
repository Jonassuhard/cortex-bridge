"use client";

/**
 * Animated architecture diagram for Settings › Info.
 * Pure SVG + CSS animations (globals.css), no JS timers.
 * Labels are French, matching the product UI.
 */
export function BridgeDiagram() {
  return (
    <div className="bridge-diagram" role="img" aria-label="Schéma de fonctionnement de Cortex Bridge">
      <svg viewBox="0 0 720 300" width="100%">
        <defs>
          <linearGradient id="bd-cloud" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="rgba(129,140,248,0.16)" />
            <stop offset="100%" stopColor="rgba(56,189,248,0.10)" />
          </linearGradient>
          <linearGradient id="bd-local" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="rgba(52,211,153,0.14)" />
            <stop offset="100%" stopColor="rgba(45,212,191,0.08)" />
          </linearGradient>
        </defs>

        {/* Cloud zone */}
        <rect className="bd-zone" x="16" y="18" width="220" height="264" rx="16" fill="url(#bd-cloud)" />
        <text className="bd-zone-label" x="126" y="44">☁️ Cloud</text>

        {/* Local zone */}
        <rect className="bd-zone" x="292" y="18" width="412" height="264" rx="16" fill="url(#bd-local)" />
        <text className="bd-zone-label" x="498" y="44">💻 Ton Mac — tout reste local</text>

        {/* Cloud node: ChatGPT */}
        <g className="bd-node">
          <rect x="46" y="96" width="160" height="72" rx="12" />
          <text className="bd-node-title" x="126" y="126">ChatGPT</text>
          <text className="bd-node-sub" x="126" y="148">le cerveau · planifie</text>
        </g>

        {/* Bridge node */}
        <g className="bd-node bd-node-bridge">
          <rect x="342" y="96" width="160" height="72" rx="12" />
          <text className="bd-node-title" x="422" y="126">Cortex Bridge</text>
          <text className="bd-node-sub" x="422" y="148">boucle + garde-fous</text>
        </g>

        {/* Ollama node */}
        <g className="bd-node">
          <rect x="552" y="66" width="132" height="58" rx="12" />
          <text className="bd-node-title" x="618" y="90">Ollama</text>
          <text className="bd-node-sub" x="618" y="108">les mains · exécute</text>
        </g>

        {/* Filesystem node */}
        <g className="bd-node">
          <rect x="552" y="168" width="132" height="58" rx="12" />
          <text className="bd-node-title" x="618" y="192">Workspace</text>
          <text className="bd-node-sub" x="618" y="210">fichiers · commandes</text>
        </g>

        {/* Console node */}
        <g className="bd-node bd-node-console">
          <rect x="322" y="210" width="200" height="46" rx="12" />
          <text className="bd-node-title" x="422" y="238">Console locale · 127.0.0.1:8420</text>
        </g>

        {/* Edges */}
        {/* ChatGPT -> Bridge (task) */}
        <path className="bd-edge" d="M206 120 H 342" />
        <path className="bd-pulse" d="M206 120 H 342" />
        <text className="bd-edge-label" x="274" y="110">tâche</text>

        {/* Bridge -> ChatGPT (report) */}
        <path className="bd-edge" d="M342 156 H 206" />
        <path className="bd-pulse bd-pulse-rev" d="M342 156 H 206" />
        <text className="bd-edge-label" x="274" y="178">rapport</text>

        {/* Bridge -> Ollama */}
        <path className="bd-edge" d="M502 116 H 552" />
        <path className="bd-pulse bd-pulse-fast" d="M502 116 H 552" />
        <text className="bd-edge-label" x="527" y="106">action</text>

        {/* Ollama -> Workspace */}
        <path className="bd-edge" d="M618 124 V 168" />
        <path className="bd-pulse bd-pulse-fast" d="M618 124 V 168" />

        {/* Console -> Bridge */}
        <path className="bd-edge" d="M422 210 V 168" />
        <path className="bd-pulse bd-pulse-slow" d="M422 210 V 168" />
        <text className="bd-edge-label" x="446" y="196">pilotage</text>
      </svg>
      <p className="bridge-diagram-caption">
        ChatGPT planifie dans ta conversation, le bridge fait exécuter par Ollama sur ta machine,
        puis renvoie le rapport pour continuer la boucle. Aucune clé API, aucun envoi externe.
      </p>
    </div>
  );
}
