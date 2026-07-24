export function CortexLogo({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`cortex-logo ${compact ? "is-compact" : ""}`}>
      <svg viewBox="0 0 64 64" aria-hidden="true" className="cortex-logo-mark">
        <defs>
          <linearGradient id="cortexStroke" x1="8" y1="10" x2="56" y2="54" gradientUnits="userSpaceOnUse">
            <stop stopColor="#f8fafc" />
            <stop offset=".52" stopColor="#dbeafe" />
            <stop offset="1" stopColor="#3b82f6" />
          </linearGradient>
        </defs>
        <path d="M29 12c-7-5-16 0-15 8-7 2-8 12-2 16-4 7 2 15 10 14 1 5 5 8 10 7V18c0-3-1-5-3-6Z" fill="none" stroke="url(#cortexStroke)" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M35 12c7-5 16 0 15 8 7 2 8 12 2 16 4 7-2 15-10 14-1 5-5 8-10 7V18c0-3 1-5 3-6Z" fill="none" stroke="url(#cortexStroke)" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M16 37c7-7 25-7 32 0M19 42h26M21 42v8M43 42v8" fill="none" stroke="url(#cortexStroke)" strokeWidth="2.7" strokeLinecap="round" />
        <path d="M22 24c4-5 9-3 10 1M42 24c-4-5-9-3-10 1M17 31c4-2 7 0 8 4M47 31c-4-2-7 0-8 4" fill="none" stroke="url(#cortexStroke)" strokeWidth="2.2" strokeLinecap="round" />
        <path d="M22 49c-1 6 4 9 10 9s11-3 10-9" fill="#07090b" stroke="url(#cortexStroke)" strokeWidth="2.7" />
        <circle cx="27" cy="51.5" r="1.2" fill="#93c5fd" />
        <circle cx="32" cy="51.5" r="1.2" fill="#93c5fd" />
        <circle cx="37" cy="51.5" r="1.2" fill="#93c5fd" />
      </svg>
      {!compact && <span className="cortex-logo-word">Cortex<span>Bridge</span></span>}
    </div>
  );
}
