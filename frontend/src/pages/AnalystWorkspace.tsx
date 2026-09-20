/**
 * Unified analyst workspace: Review Setup (left) + Results (right).
 * Architectural responsibility: orchestrate modals and result views without duplicate pipelines.
 */
import { useCallback, useRef, useState } from "react";
import { BatchResultsView } from "../components/workspace/BatchResultsView";
import { BatchSetupModal } from "../components/workspace/BatchSetupModal";
import { HowItWorksModal } from "../components/workspace/HowItWorksModal";
import { SingleLabelModal } from "../components/workspace/SingleLabelModal";
import {
  BatchReviewIcon,
  HowItWorksIcon,
  ResultsReadyIcon,
  SingleLabelIcon,
} from "../components/workspace/SetupIcons";
import { VerificationResultsPanel } from "../components/verification/VerificationResultsPanel";
import { ApiRequestError, analyzeLabel, createBatch, fetchBatchStatus } from "../services/api";
import type { BatchJobStatus } from "../types/batch";
import type { SingleReviewVerificationResponse } from "../types/verification";

type WorkspaceState =
  | { kind: "empty" }
  | { kind: "single_processing"; filename: string }
  | { kind: "single_error"; filename: string; message: string }
  | { kind: "single_done"; result: SingleReviewVerificationResponse }
  | { kind: "batch_processing"; batchId: string; status: BatchJobStatus | null; labelCount: number }
  | { kind: "batch_done"; batchId: string; status: BatchJobStatus; labelCount: number };

/** Main two-panel compliance workstation. */
export function AnalystWorkspace() {
  const [state, setState] = useState<WorkspaceState>({ kind: "empty" });
  const [singleOpen, setSingleOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [howItWorksOpen, setHowItWorksOpen] = useState(false);
  const singleTriggerRef = useRef<HTMLButtonElement>(null);
  const batchTriggerRef = useRef<HTMLButtonElement>(null);
  const howItWorksTriggerRef = useRef<HTMLButtonElement>(null);

  async function runSingle(file: File) {
    setSingleOpen(false);
    setState({ kind: "single_processing", filename: file.name });
    try {
      const result = await analyzeLabel(file);
      setState({ kind: "single_done", result });
    } catch (err) {
      setState({
        kind: "single_error",
        filename: file.name,
        message:
          err instanceof ApiRequestError
            ? err.message
            : "Unable to analyze this label. Check the image and try again.",
      });
    }
  }

  async function runBatch(manifest: File, images: File[]) {
    setBatchOpen(false);
    try {
      const created = await createBatch(manifest, images);
      const initial = await fetchBatchStatus(created.batch_id);
      setState({
        kind: "batch_processing",
        batchId: created.batch_id,
        status: initial,
        labelCount: images.length,
      });
    } catch (err) {
      setState({
        kind: "single_error",
        filename: "Batch",
        message: err instanceof ApiRequestError ? err.message : "Unable to start batch.",
      });
    }
  }

  const onBatchStatus = useCallback((status: BatchJobStatus) => {
    setState((prev) => {
      if (prev.kind !== "batch_processing" && prev.kind !== "batch_done") return prev;
      if (status.state === "COMPLETED" || status.state === "FAILED") {
        return {
          kind: "batch_done",
          batchId: prev.batchId,
          status,
          labelCount: prev.labelCount,
        };
      }
      return { ...prev, kind: "batch_processing", status };
    });
  }, []);

  function startAnother() {
    setState({ kind: "empty" });
  }

  /** Clear completed single-label results and open a fresh Single Label upload modal. */
  function analyzeAnotherLabel() {
    setState({ kind: "empty" });
    setSingleOpen(true);
  }

  const contextLabel =
    state.kind === "single_processing" || state.kind === "single_error"
      ? state.filename
      : state.kind === "single_done"
        ? state.result.filename ?? "Label"
        : state.kind === "batch_processing" || state.kind === "batch_done"
          ? `${state.labelCount} labels`
          : null;

  const contextKind =
    state.kind.startsWith("single")
      ? "Single Label"
      : state.kind.startsWith("batch")
        ? "Batch Review"
        : null;

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(15rem,0.28fr)_minmax(0,0.72fr)] lg:gap-5">
      <aside className="lv-workspace-panel h-fit" aria-labelledby="setup-heading">
        <div className="lv-workspace-panel-header">
          <h1 id="setup-heading" className="font-display text-base font-semibold tracking-tight text-navy sm:text-lg">
            Review Setup
          </h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Choose a review type to begin.
          </p>
        </div>

        <div className="flex flex-col gap-2.5 p-4 sm:p-5">
          <button
            ref={singleTriggerRef}
            type="button"
            className="lv-setup-tile"
            onClick={() => setSingleOpen(true)}
          >
            <SingleLabelIcon className="mt-0.5 h-5 w-5 shrink-0 text-navy" />
            <span className="min-w-0">
              <span className="block text-[11px] font-semibold uppercase tracking-wide text-navy">
                Single Label
              </span>
              <span className="mt-0.5 block text-sm text-muted-foreground">Analyze one label</span>
            </span>
          </button>
          <button
            ref={batchTriggerRef}
            type="button"
            className="lv-setup-tile"
            onClick={() => setBatchOpen(true)}
          >
            <BatchReviewIcon className="mt-0.5 h-5 w-5 shrink-0 text-navy" />
            <span className="min-w-0">
              <span className="block text-[11px] font-semibold uppercase tracking-wide text-navy">
                Batch Review
              </span>
              <span className="mt-0.5 block text-sm text-muted-foreground">
                Process multiple labels
              </span>
            </span>
          </button>

          <div
            className="mt-4 border-t border-border/70 pt-4"
            data-testid="how-it-works-rail"
          >
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/90">
              Information
            </p>
            <button
              ref={howItWorksTriggerRef}
              type="button"
              className="lv-setup-info"
              onClick={() => setHowItWorksOpen(true)}
            >
              <HowItWorksIcon className="mt-0.5 h-5 w-5 shrink-0 opacity-80" />
              <span className="min-w-0">
                <span className="block text-[11px] font-semibold uppercase tracking-wide">
                  How It Works
                </span>
                <span className="mt-0.5 block text-sm">
                  Learn how LabelVerify reviews labels
                </span>
              </span>
            </button>
          </div>

          {contextKind && contextLabel ? (
            <div className="mt-3 border-t border-border/80 pt-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Current review
              </p>
              <p className="mt-1 text-sm font-semibold text-foreground">{contextKind}</p>
              <p className="text-sm text-muted-foreground break-all">{contextLabel}</p>
              {(state.kind === "single_done" ||
                state.kind === "batch_done" ||
                state.kind === "single_error") && (
                <button type="button" className="lv-btn-secondary mt-3 w-full" onClick={startAnother}>
                  Start another review
                </button>
              )}
              {state.kind === "batch_processing" || state.kind === "single_processing" ? (
                <p className="mt-2 text-xs text-muted-foreground">Processing…</p>
              ) : null}
            </div>
          ) : null}
        </div>
      </aside>

      <section
        className={`lv-workspace-panel${state.kind === "empty" ? " min-h-[26.5rem]" : ""}`}
        aria-labelledby="results-heading"
      >
        {state.kind === "empty" ? (
          <>
            <div className="lv-workspace-panel-header">
              <h2 id="results-heading" className="font-display text-base font-semibold tracking-tight text-navy sm:text-lg">
                Results
              </h2>
            </div>
            <div className="flex min-h-[21rem] flex-1 flex-col items-center justify-center px-6 py-10 text-center">
              <ResultsReadyIcon className="mb-4 h-11 w-11 text-navy/50" />
              <p className="font-display text-base font-semibold text-navy">Ready for review</p>
              <p className="mt-1.5 max-w-xs text-sm text-muted-foreground">
                Select Single Label or Batch Review to begin.
              </p>
            </div>
          </>
        ) : null}

        {state.kind === "single_processing" ? (
          <div className="p-4 sm:p-5" role="status" aria-live="polite">
            <h2 id="results-heading" className="font-display text-base font-semibold text-navy sm:text-lg">
              Results
            </h2>
            <p className="mt-3 text-sm text-muted-foreground">
              Analyzing <span className="font-semibold text-foreground">{state.filename}</span>…
            </p>
          </div>
        ) : null}

        {state.kind === "single_error" ? (
          <div className="p-4 sm:p-5">
            <h2 id="results-heading" className="font-display text-base font-semibold text-navy sm:text-lg">
              Results
            </h2>
            <div
              className="mt-3 border border-fail bg-fail-soft px-3 py-2 text-sm"
              role="alert"
            >
              <p className="font-semibold text-fail">Unable to complete review</p>
              <p className="mt-1">{state.message}</p>
            </div>
            <button type="button" className="lv-btn-secondary mt-3" onClick={startAnother}>
              Start another review
            </button>
          </div>
        ) : null}

        {state.kind === "single_done" ? (
          <div className="p-4 sm:p-5">
            <VerificationResultsPanel result={state.result} onClear={analyzeAnotherLabel} />
          </div>
        ) : null}

        {state.kind === "batch_processing" || state.kind === "batch_done" ? (
          <div className="p-4 sm:p-5">
            <BatchResultsView
              batchId={state.batchId}
              status={state.status}
              onStatus={onBatchStatus}
            />
          </div>
        ) : null}
      </section>

      <SingleLabelModal
        open={singleOpen}
        onClose={() => setSingleOpen(false)}
        onAnalyze={(file) => void runSingle(file)}
        returnFocusRef={singleTriggerRef}
      />
      <BatchSetupModal
        open={batchOpen}
        onClose={() => setBatchOpen(false)}
        onProcess={(manifest, images) => void runBatch(manifest, images)}
        returnFocusRef={batchTriggerRef}
      />
      <HowItWorksModal
        open={howItWorksOpen}
        onClose={() => setHowItWorksOpen(false)}
        returnFocusRef={howItWorksTriggerRef}
      />
    </div>
  );
}
