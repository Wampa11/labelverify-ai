/**
 * LabelVerify LV lettermark — independent product identity.
 * Architectural responsibility: geometric monogram for header lockup (not a Treasury seal).
 *
 * When placed beside the LabelVerify wordmark, pass decorative so assistive tech skips the SVG.
 */
interface LabelVerifyMarkProps {
  className?: string;
  /** When true (default), hidden from assistive tech — wordmark provides the name. */
  decorative?: boolean;
  title?: string;
}

/** Geometric LV monogram with a subtle verification accent on the V. */
export function LabelVerifyMark({
  className = "h-9 w-9",
  decorative = true,
  title = "LabelVerify",
}: LabelVerifyMarkProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 40 40"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden={decorative ? true : undefined}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : title}
    >
      {!decorative ? <title>{title}</title> : null}
      <rect
        x="1.5"
        y="1.5"
        width="37"
        height="37"
        rx="1.5"
        fill="currentColor"
        opacity="0.12"
      />
      <rect
        x="1.5"
        y="1.5"
        width="37"
        height="37"
        rx="1.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.25"
        opacity="0.45"
      />
      {/* L */}
      <path
        d="M9 9.5 V29.5 H18.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
      {/* V */}
      <path
        d="M20 9.5 L26.25 29.5 L32.5 9.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
      {/* Verification motif — short gold check seated in the V trough */}
      <path
        d="M23.5 21.75 L26.25 26.25 L31.75 16.5"
        fill="none"
        stroke="#C9A227"
        strokeWidth="2.5"
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
    </svg>
  );
}
