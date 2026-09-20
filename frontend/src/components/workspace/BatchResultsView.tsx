/**
 * Batch results table, filters, and item detail for the Results workspace.
 * Architectural responsibility: present BatchJobStatus without owning setup intake.
 */
import { useEffect, useMemo, useState } from "react";
import { StatusBadge } from "../common/StatusBadge";
import { VerificationResultsPanel } from "../verification/VerificationResultsPanel";
import {
  ApiRequestError,
  downloadBatchExcelReport,
  fetchBatchItemDetail,
  fetchBatchStatus,
} from "../../services/api";
import type { BatchItemSummary, BatchJobStatus } from "../../types/batch";

type FilterKey = "all" | "PASS" | "REVIEW" | "FAIL" | "ERROR" | "attention";

interface BatchResultsViewProps {
  batchId: string;
  status: BatchJobStatus | null;
  onStatus: (status: BatchJobStatus) => void;
}

/** Operational batch results: progress, filters, table, Excel download. */
export function BatchResultsView({ batchId, status, onStatus }: BatchResultsViewProps) {
  const [filter, setFilter] = useState<FilterKey>("all");
  const [search, setSearch] = useState("");
  const [detailResult, setDetailResult] = useState<
    import("../../types/verification").SingleReviewVerificationResponse | null
  >(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    if (!batchId) return;
    if (status?.state === "COMPLETED" || status?.state === "FAILED") return;
    const id = window.setInterval(() => {
      void fetchBatchStatus(batchId)
        .then(onStatus)
        .catch(() => undefined);
    }, 800);
    return () => window.clearInterval(id);
  }, [batchId, status?.state, onStatus]);

  const filteredItems = useMemo(() => {
    if (!status) return [];
    let rows = [...status.items];
    if (filter === "PASS") rows = rows.filter((i) => i.overall_status === "PASS");
    else if (filter === "REVIEW") rows = rows.filter((i) => i.overall_status === "REVIEW");
    else if (filter === "FAIL") rows = rows.filter((i) => i.overall_status === "FAIL");
    else if (filter === "ERROR") rows = rows.filter((i) => i.processing_state === "ERROR");
    else if (filter === "attention") {
      rows = rows.filter(
        (i) =>
          i.processing_state === "ERROR" ||
          i.overall_status === "REVIEW" ||
          i.overall_status === "FAIL",
      );
    }
    const q = search.trim().toLowerCase();
    if (q) {
      rows = rows.filter(
        (i) =>
          i.filename.toLowerCase().includes(q) || i.brand_name.toLowerCase().includes(q),
      );
    }
    if (filter === "all") {
      const rank = (i: BatchItemSummary) => {
        if (i.processing_state === "ERROR") return 0;
        if (i.overall_status === "FAIL") return 1;
        if (i.overall_status === "REVIEW") return 2;
        return 3;
      };
      rows.sort((a, b) => rank(a) - rank(b) || a.filename.localeCompare(b.filename));
    }
    return rows;
  }, [status, filter, search]);

  async function openItem(item: BatchItemSummary) {
    setDetailError(null);
    setDetailResult(null);
    if (item.processing_state === "ERROR") {
      setDetailError(item.error_message ?? "This item failed during processing.");
      return;
    }
    if (item.processing_state !== "COMPLETED") {
      setDetailError("This item is still processing.");
      return;
    }
    try {
      const detail = await fetchBatchItemDetail(batchId, item.item_id);
      if (detail.result) setDetailResult(detail.result);
      else setDetailError("No verification result is available for this item.");
    } catch (err) {
      setDetailError(err instanceof ApiRequestError ? err.message : "Unable to load item detail.");
    }
  }

  async function handleExcel() {
    setExportError(null);
    try {
      const blob = await downloadBatchExcelReport(batchId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `labelverify-batch-${batchId.slice(0, 8)}.xlsx`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof ApiRequestError ? err.message : "Unable to download Excel report.");
    }
  }

  if (detailResult) {
    return (
      <div className="space-y-3">
        <button type="button" className="lv-btn-secondary" onClick={() => setDetailResult(null)}>
          Back to batch results
        </button>
        <VerificationResultsPanel
          result={detailResult}
          onClear={() => setDetailResult(null)}
          clearLabel="Back to batch results"
          showExcelDownload={false}
        />
      </div>
    );
  }

  if (!status) {
    return (
      <p className="text-sm text-muted-foreground" role="status">
        Starting batch…
      </p>
    );
  }

  const s = status.summary;
  const done = status.state === "COMPLETED" || status.state === "FAILED";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold text-navy">Batch results</h2>
          <p className="text-xs text-muted-foreground">
            {status.state}
            {status.elapsed_ms != null ? ` · ${status.elapsed_ms.toFixed(0)} ms` : null}
          </p>
        </div>
        {done ? (
          <button type="button" className="lv-btn-primary" onClick={() => void handleExcel()}>
            Download Excel Report
          </button>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-4 text-sm">
        <span>
          <span className="font-semibold tabular-nums">{s.total}</span> Total
        </span>
        <span className="text-pass">
          <span className="font-semibold tabular-nums">{s.pass_count}</span> PASS
        </span>
        <span className="text-review">
          <span className="font-semibold tabular-nums">{s.review_count}</span> REVIEW
        </span>
        <span className="text-fail">
          <span className="font-semibold tabular-nums">{s.fail_count}</span> FAIL
        </span>
        <span>
          <span className="font-semibold tabular-nums">{s.error_count}</span> ERROR
        </span>
      </div>

      {!done ? (
        <p className="text-sm text-muted-foreground" role="status" aria-live="polite">
          Processed {s.completed + s.error_count} of {s.total}…
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["all", "All"],
            ["attention", "Needs attention"],
            ["PASS", "PASS"],
            ["REVIEW", "REVIEW"],
            ["FAIL", "FAIL"],
            ["ERROR", "ERROR"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={filter === key ? "lv-btn-primary px-2 py-1 text-xs" : "lv-btn-ghost px-2 py-1 text-xs"}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
        <input
          type="search"
          placeholder="Search filename or brand"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="lv-input max-w-xs text-sm"
          aria-label="Search batch results"
        />
      </div>

      {detailError ? (
        <p className="text-sm text-fail" role="alert">
          {detailError}
        </p>
      ) : null}
      {exportError ? (
        <p className="text-sm text-fail" role="alert">
          {exportError}
        </p>
      ) : null}

      <div className="overflow-x-auto border border-border">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="bg-muted text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-2 py-2 font-semibold">Filename</th>
              <th className="px-2 py-2 font-semibold">Status</th>
              <th className="px-2 py-2 font-semibold">Brand</th>
              <th className="px-2 py-2 font-semibold">AI</th>
              <th className="px-2 py-2 font-semibold"> </th>
            </tr>
          </thead>
          <tbody>
            {filteredItems.map((item) => (
              <tr key={item.item_id} className="border-t border-border">
                <td className="px-2 py-2">{item.filename}</td>
                <td className="px-2 py-2">
                  {item.processing_state === "ERROR" ? (
                    <StatusBadge status="FAIL" />
                  ) : item.overall_status ? (
                    <StatusBadge status={item.overall_status as "PASS" | "REVIEW" | "FAIL"} />
                  ) : (
                    <span className="text-xs text-muted-foreground">{item.processing_state}</span>
                  )}
                </td>
                <td className="px-2 py-2">{item.brand_name}</td>
                <td className="px-2 py-2 text-xs">{item.ai_assisted ? "Yes" : "—"}</td>
                <td className="px-2 py-2">
                  <button
                    type="button"
                    className="lv-btn-ghost px-0 py-0 text-xs"
                    onClick={() => void openItem(item)}
                  >
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
