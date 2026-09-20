/**
 * Application shell: institutional header and utility footer.
 * Architectural responsibility: chrome for the unified analyst workspace (no mode tabs).
 */
import type { ReactNode } from "react";
import { LabelVerifyMark } from "./LabelVerifyMark";

interface AppShellProps {
  children: ReactNode;
}

/** Top-level chrome: brand lockup, prototype designation, decision-support banner. */
export function AppShell({ children }: AppShellProps) {
  // Release builds set VITE_APP_VERSION at image/build time; default is RC version, not "dev".
  const appVersion = import.meta.env.VITE_APP_VERSION ?? "0.8.0";

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:border focus:border-border focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to main content
      </a>

      <header className="border-b border-border bg-navy text-primary-foreground">
        <div className="mx-auto flex max-w-workspace flex-wrap items-center justify-between gap-3 px-4 py-3.5 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <LabelVerifyMark className="h-9 w-9 shrink-0 text-primary-foreground" decorative />
            <div className="min-w-0 leading-tight">
              <p className="font-display text-lg font-bold tracking-tight sm:text-xl">
                LabelVerify
              </p>
              <p className="truncate text-xs text-primary-foreground/80 sm:text-[13px]">
                AI-Assisted Alcohol Label Verification
              </p>
            </div>
          </div>
          <p
            className="shrink-0 border border-primary-foreground/35 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary-foreground/95"
            style={{ borderRadius: "var(--radius)" }}
          >
            Prototype · AI-Assisted Review
          </p>
        </div>
      </header>

      <p className="border-b border-border bg-muted px-4 py-2 text-center text-xs text-muted-foreground sm:px-6">
        Decision support only. Final determinations remain with authorized personnel.
      </p>

      <main id="main-content" className="mx-auto w-full max-w-workspace flex-1 px-4 py-5 sm:px-6 sm:py-6">
        {children}
      </main>

      <footer className="border-t border-border bg-surface">
        <div className="mx-auto flex max-w-workspace items-center justify-between gap-3 px-4 py-2.5 text-xs text-muted-foreground sm:px-6">
          <p>LabelVerify · Prototype Decision Support</p>
          <p className="shrink-0 tabular-nums" title="Application version">
            v{appVersion}
          </p>
        </div>
      </footer>
    </div>
  );
}
