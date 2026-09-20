/**
 * Accessible modal dialog with focus trap and Escape-to-close.
 * Architectural responsibility: reusable institutional dialog chrome for setup workflows.
 */
import {
  useEffect,
  useId,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";

interface ModalProps {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  /** Element that opened the dialog — focus returns here on close. */
  returnFocusRef?: React.RefObject<HTMLElement | null>;
  size?: "md" | "lg" | "xl";
}

/** Focus-trapping dialog overlay for Single/Batch setup and informational content. */
export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  returnFocusRef,
  size = "md",
}: ModalProps) {
  const titleId = useId();
  const descId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current =
      (document.activeElement as HTMLElement | null) ?? returnFocusRef?.current ?? null;
    const panel = panelRef.current;
    const focusables = panel ? getFocusable(panel) : [];
    (focusables[0] ?? panel)?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const nodes = getFocusable(panel);
      if (nodes.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = prevOverflow;
      const target = returnFocusRef?.current ?? previouslyFocused.current;
      target?.focus();
    };
  }, [open, onClose, returnFocusRef]);

  if (!open) return null;

  const widthClass =
    size === "xl" ? "max-w-3xl" : size === "lg" ? "max-w-2xl" : "max-w-lg";

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-navy/45 px-4 py-6 sm:py-10">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        ref={panelRef}
        tabIndex={-1}
        className={[
          "flex w-full flex-col border border-border bg-surface shadow-lg outline-none",
          widthClass,
          size === "xl" ? "max-h-[min(92vh,52rem)]" : "",
        ].join(" ")}
        style={{ borderRadius: "var(--radius)" }}
        onKeyDown={(event: ReactKeyboardEvent) => {
          if (event.key === "Escape") onClose();
        }}
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            <h2 id={titleId} className="font-display text-lg font-semibold text-navy">
              {title}
            </h2>
            {description ? (
              <p id={descId} className="mt-0.5 text-sm text-muted-foreground">
                {description}
              </p>
            ) : null}
          </div>
          <button type="button" className="lv-btn-ghost text-sm" onClick={onClose} aria-label="Close">
            Close
          </button>
        </div>
        <div
          className={[
            "px-4 py-4",
            size === "xl" ? "min-h-0 flex-1 overflow-y-auto" : "",
          ].join(" ")}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

function getFocusable(root: HTMLElement): HTMLElement[] {
  const selector =
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';
  return Array.from(root.querySelectorAll<HTMLElement>(selector)).filter(
    (el) => !el.hasAttribute("disabled") && el.tabIndex !== -1,
  );
}
