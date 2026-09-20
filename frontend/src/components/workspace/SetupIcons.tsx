/**
 * Compact line icons for Review Setup tiles.
 * Architectural responsibility: restrained institutional glyphs — decorative beside tile labels.
 */
interface IconProps {
  className?: string;
}

/** Single document / label glyph. */
export function SingleLabelIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect x="5" y="3" width="14" height="18" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="square" />
    </svg>
  );
}

/** Stacked documents glyph for batch. */
export function BatchReviewIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect x="7" y="5" width="12" height="15" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M5 16V6.5A1.5 1.5 0 0 1 6.5 5H16"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="square"
      />
      <path d="M10 10h6M10 14h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="square" />
    </svg>
  );
}

/** Process / information glyph for secondary How It Works control. */
export function HowItWorksIcon({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="8.25" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 10.5V17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="square" />
      <circle cx="12" cy="7.75" r="1" fill="currentColor" />
    </svg>
  );
}

/** Low-emphasis document-analysis mark for empty Results state. */
export function ResultsReadyIcon({ className = "h-10 w-10" }: IconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect
        x="10"
        y="6"
        width="28"
        height="36"
        rx="1.5"
        stroke="currentColor"
        strokeWidth="1.5"
        opacity="0.55"
      />
      <path
        d="M16 16h16M16 22h16M16 28h10"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="square"
        opacity="0.4"
      />
      <path
        d="M28 31 L32 35 L39 26"
        stroke="hsl(var(--accent-gold))"
        strokeWidth="2"
        strokeLinecap="square"
        strokeLinejoin="miter"
        opacity="0.85"
      />
    </svg>
  );
}
