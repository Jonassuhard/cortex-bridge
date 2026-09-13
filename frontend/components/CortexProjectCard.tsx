"use client";

interface CortexProjectCardProps {
  active: boolean;
  chatState?: string;
  missionState?: string;
  sending?: boolean;
  recoveryPending?: boolean;
  cancelPending?: boolean;
}

const movingChat = new Set(["SELECTING_CONVERSATION", "SENDING_TO_CHATGPT", "VISIBLE_IN_CHATGPT", "WAITING_FOR_CHATGPT", "CHATGPT_STREAMING"]);
const movingMission = new Set(["INITIALIZING_MISSION", "SENDING_OBJECTIVE", "PARSING_DECISION", "EXECUTING_LOCAL_ACTION", "SENDING_REPORT", "VALIDATING_ACTION", "FINAL_VALIDATION", "WAITING_FOR_CHATGPT"]);

/** Visual metaphor only: these four symbols do not assert which AI model is running. */
export function CortexProjectCard({ active, chatState, missionState, sending = false, recoveryPending = false, cancelPending = false }: CortexProjectCardProps) {
  const busy = active && (sending || recoveryPending || cancelPending || movingChat.has(chatState || "") || movingMission.has(missionState || ""));
  return (
    <section className="cortex-project-card" aria-label="Carte projet Cortex" data-active={active} data-busy={busy}>
      <svg className="cortex-celestial" viewBox="0 0 400 240" aria-hidden="true" focusable="false">
        <g transform="translate(67 57)" data-astro="Luna"><g className="celestial-motion">
          <path fill="var(--celestial-ivory)" d="M10-27A28 28 0 1 0 26 18 29 29 0 0 1 10-27Z" />
        </g></g>
        <g transform="translate(332 58)" data-astro="Sol"><g className="celestial-motion">
          <circle r="20" fill="var(--celestial-sun)" />
          <path d="M0-37v8M0 29v8M-37 0h8M29 0h8M-26-26l6 6M20 20l6 6M26-26l-6 6M-20 20l-6 6" stroke="var(--celestial-sun)" strokeWidth="5" />
        </g></g>
        <g transform="translate(67 178)" data-astro="Astra"><g className="celestial-motion">
          <g fill="var(--celestial-galaxy)">
            <path d="M0 0C-8-12-30-14-31 8C-39-18-8-38 18-22C5-26-3-14 0 0Z" />
            <path transform="rotate(120)" d="M0 0C-8-12-30-14-31 8C-39-18-8-38 18-22C5-26-3-14 0 0Z" />
            <path transform="rotate(240)" d="M0 0C-8-12-30-14-31 8C-39-18-8-38 18-22C5-26-3-14 0 0Z" />
          </g><circle r="6" fill="var(--celestial-galaxy)" />
        </g></g>
        <g transform="translate(332 178)" data-astro="Terra"><g className="celestial-motion">
          <circle r="31" fill="var(--celestial-earth)" />
          <path fill="var(--celestial-ivory)" d="M-19-22-6-27 2-18-4-8-15-8-9 3-15 7-23-5-28-8ZM2 0 18 4 22 13 12 26 5 28 2 14-5 7ZM17-25 26-16 28-5 19-7 11-17Z" />
        </g></g>
        <g className="celestial-head" transform="translate(-30 0) scale(1.15 1)">
          <path fill="var(--celestial-ivory)" d="M165 39 200 23 235 39 251 68 249 111 258 107 261 127 248 146 235 159 231 190 257 207 200 230 143 207 169 190 165 159 152 146 139 127 142 107 151 111 149 68Z" />
          <path fill="var(--celestial-shade)" d="M165 39 149 68 152 126 176 151 166 106ZM235 39 249 68 248 126 224 151 234 106ZM169 167 200 188 231 167 231 190 200 230 169 190Z" />
          <path fill="var(--celestial-mid)" d="M200 25 200 139 186 132 192 110 187 82 165 39ZM200 188 176 165 166 140 186 153 214 153 234 140 224 165Z" />
          <path fill="var(--celestial-ink)" d="M162 86 174 78 188 85 190 91 174 85ZM238 86 226 78 212 85 210 91 226 85ZM188 133 200 137 212 133 205 142 195 142ZM183 157 197 152 203 152 217 157 201 156Z" />
          <path className="celestial-lids" d="M164 102 188 104M212 104 236 102" fill="none" stroke="var(--celestial-ink)" strokeWidth="3" />
          <g className="celestial-eyes" fill="var(--celestial-eye)">
            <path d="M162 100 174 94 188 100 180 107 170 106Z" />
            <path d="M238 100 226 94 212 100 220 107 230 106Z" />
          </g>
        </g>
      </svg>
      <div className="celestial-caption">
        <strong>Cortex</strong>
        <span>{busy ? "Tâche en cours" : active ? "Conversation sélectionnée" : "En veille"}</span>
        <p>Luna · Terra · Sol · Astra</p>
      </div>
    </section>
  );
}
