/** Route from a start node, through one fuel stop, to the finish. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
      <path
        d="M4.5 19.5c5 0 3-7.5 7.5-7.5s2.5-7.5 7.5-7.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeDasharray="0.1 3.4"
        opacity="0.55"
      />
      <circle cx="4.5" cy="19.5" r="2.2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="2.4" fill="var(--color-brand)" />
      <circle cx="19.5" cy="4.5" r="2.2" fill="currentColor" />
    </svg>
  );
}
