/**
 * PASS / REVIEW / FAIL status badge with text + icon (color never sole indicator).
 * Architectural responsibility: shared semantic status presentation for verification UI.
 */
import type { CheckStatus } from "../../types/verification";

const STATUS_LABEL: Record<CheckStatus, string> = {
  PASS: "Pass",
  REVIEW: "Review",
  FAIL: "Fail",
};

const STATUS_ICON: Record<CheckStatus, string> = {
  PASS: "✓",
  REVIEW: "?",
  FAIL: "✕",
};

const STATUS_CLASS: Record<CheckStatus, string> = {
  PASS: "bg-pass text-pass-foreground",
  REVIEW: "bg-review text-review-foreground",
  FAIL: "bg-fail text-fail-foreground",
};

interface StatusBadgeProps {
  status: CheckStatus;
  large?: boolean;
}

/** Accessible status chip: icon + text + semantic color. */
export function StatusBadge({ status, large = false }: StatusBadgeProps) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1 border border-transparent px-2 py-0.5 font-bold uppercase tracking-wide",
        STATUS_CLASS[status],
        large ? "text-sm" : "text-xs",
      ].join(" ")}
      style={{ borderRadius: "var(--radius)" }}
      role="status"
      aria-label={`Status: ${STATUS_LABEL[status]}`}
    >
      <span aria-hidden="true">{STATUS_ICON[status]}</span>
      {STATUS_LABEL[status]}
    </span>
  );
}
