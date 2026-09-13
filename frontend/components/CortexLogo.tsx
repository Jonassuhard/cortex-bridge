export function CortexLogo({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`cortex-logo ${compact ? "is-compact" : ""}`}>
      <svg viewBox="0 0 64 64" aria-hidden="true" className="cortex-logo-mark">
        <path d="M46 16a23 23 0 1 0 0 32" fill="none" stroke="currentColor" strokeWidth="9" strokeLinecap="square" />
        <path d="M27 32h26" fill="none" stroke="var(--blue)" strokeWidth="8" strokeLinecap="round" />
        <circle cx="27" cy="32" r="5" fill="var(--blue)" />
        <circle cx="53" cy="32" r="5" fill="var(--blue)" />
      </svg>
      {!compact && <span className="cortex-logo-word">Cortex <span>Bridge</span></span>}
    </div>
  );
}
