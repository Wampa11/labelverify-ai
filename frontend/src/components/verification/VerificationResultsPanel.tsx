/**
 * Single-label results: overall finding, image, extracted fields, checks.
 * Architectural responsibility: scannable label-first results without duplicating evidence text.
 */
import { useMemo, useRef, useState } from "react";
import { StatusBadge } from "../common/StatusBadge";
import type { ExtractedField } from "../../types/extraction";
import { FIELD_LABELS } from "../../types/extraction";
import type {
  FieldCheckResult,
  SingleReviewVerificationResponse,
} from "../../types/verification";
import { ApiRequestError, downloadSingleExcelReport } from "../../services/api";

interface VerificationResultsPanelProps {
  result: SingleReviewVerificationResponse;
  onClear: () => void;
  clearLabel?: string;
  showExcelDownload?: boolean;
}

const CHECK_TO_FIELD: Record<string, string> = {
  "Brand Name": "brand_name",
  "Class / Type": "class_type",
  "Alcohol Content / ABV": "alcohol_content",
  "Net Contents": "net_contents",
  "Government Health Warning": "government_warning",
};

const EXTRACTED_FIELD_ORDER = [
  "brand_name",
  "class_type",
  "alcohol_content",
  "net_contents",
  "government_warning",
] as const;

/** Present overall finding, extracted label info, and applicable checks. */
export function VerificationResultsPanel({
  result,
  onClear,
  clearLabel = "Analyze another label",
  showExcelDownload = true,
}: VerificationResultsPanelProps) {
  const [focusedCheck, setFocusedCheck] = useState<string | null>(null);
  const [openCheck, setOpenCheck] = useState<string | null>(null);
  const [showTiming, setShowTiming] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [renderSize, setRenderSize] = useState({ w: 0, h: 0 });

  const previewSrc = `data:${result.display_media_type};base64,${result.display_image_base64}`;
  const filename = result.filename ?? "Uploaded image";
  const verification = result.verification;
  const extraction = result.extraction;
  const labelOnly =
    (result.verification_mode ?? verification.verification_mode ?? "label_only") === "label_only";

  const selectedField = focusedCheck ? CHECK_TO_FIELD[focusedCheck] ?? null : null;

  const highlightBoxes = useMemo(() => {
    if (!selectedField) return [];
    const field = extraction.selected_fields[selectedField] as ExtractedField | undefined;
    if (!field) return [];
    return field.ocr_regions
      .map((region) => region.bounding_box)
      .filter((box): box is NonNullable<typeof box> => Boolean(box));
  }, [extraction.selected_fields, selectedField]);

  const ocrW = extraction.ocr_image_width_px ?? result.metadata_width_px;
  const ocrH = extraction.ocr_image_height_px ?? result.metadata_height_px;
  const qualityNote = humanQualityNote(result.quality_status, result.quality_warnings);

  async function handleExcel() {
    setExportError(null);
    try {
      const blob = await downloadSingleExcelReport(result);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `labelverify-review-${(result.verification_id || "review").slice(0, 12)}.xlsx`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof ApiRequestError ? err.message : "Unable to download Excel report.");
    }
  }

  return (
    <section aria-labelledby="verification-heading" className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="verification-heading" className="font-display text-lg font-semibold text-navy">
            Results
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {labelOnly ? "Label-only review" : "Application comparison"} · decision support only
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {showExcelDownload ? (
            <button type="button" className="lv-btn-primary" onClick={() => void handleExcel()}>
              Download Excel Report
            </button>
          ) : null}
          <button type="button" onClick={onClear} className="lv-btn-secondary">
            {clearLabel}
          </button>
        </div>
      </div>

      {exportError ? (
        <p className="text-sm text-fail" role="alert">
          {exportError}
        </p>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <figure className="m-0 space-y-2">
          <div className="relative border border-border bg-muted">
            <img
              ref={imgRef}
              src={previewSrc}
              alt={`Label image: ${filename}`}
              className="max-h-[min(70vh,36rem)] w-full object-contain"
              onLoad={(event) => {
                const el = event.currentTarget;
                setRenderSize({ w: el.clientWidth, h: el.clientHeight });
              }}
            />
            {highlightBoxes.length > 0 && ocrW > 0 && ocrH > 0 ? (
              <HighlightOverlay
                boxes={highlightBoxes}
                ocrWidth={ocrW}
                ocrHeight={ocrH}
                renderWidth={renderSize.w || imgRef.current?.clientWidth || 0}
                renderHeight={renderSize.h || imgRef.current?.clientHeight || 0}
                naturalWidth={result.metadata_width_px}
                naturalHeight={result.metadata_height_px}
              />
            ) : null}
          </div>
          <figcaption className="text-xs text-muted-foreground">
            {filename}
            {` · ${result.metadata_width_px}×${result.metadata_height_px}`}
            {selectedField ? (
              <span>
                {" "}
                · Highlighting{" "}
                {selectedField in FIELD_LABELS
                  ? FIELD_LABELS[selectedField as keyof typeof FIELD_LABELS]
                  : selectedField}
              </span>
            ) : null}
          </figcaption>
        </figure>

        <div className="space-y-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-end gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Overall finding
                </p>
                <div className="mt-1">
                  <StatusBadge status={verification.overall_status} large />
                </div>
              </div>
              <div className="flex flex-wrap gap-3 text-sm">
                <span className="text-pass">
                  <span className="font-semibold tabular-nums">{verification.pass_count}</span> Passed
                </span>
                <span className="text-review">
                  <span className="font-semibold tabular-nums">{verification.review_count}</span> Needs
                  Review
                </span>
                <span className="text-fail">
                  <span className="font-semibold tabular-nums">{verification.fail_count}</span> Failed
                </span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span>{result.processing_time_ms.toFixed(0)} ms</span>
              {verification.ai_used ? (
                <span className="font-medium text-foreground">AI-assisted evidence</span>
              ) : verification.ai_assist?.attempted && !verification.ai_assist?.ai_succeeded ? (
                <span className="font-medium text-review">AI recovery attempted (unavailable)</span>
              ) : null}
              <button
                type="button"
                className="lv-btn-ghost px-0 py-0 text-xs"
                onClick={() => setShowTiming((v) => !v)}
                aria-expanded={showTiming}
              >
                {showTiming ? "Hide timing" : "Timing"}
              </button>
            </div>
            {showTiming ? (
              <pre className="max-h-40 overflow-auto bg-muted px-3 py-2 text-xs text-muted-foreground">
                {JSON.stringify(
                  {
                    stage_timings_ms: result.stage_timings_ms ?? {},
                    ai_assist: verification.ai_assist
                      ? {
                          evidence_method: verification.ai_assist.evidence_method,
                          ai_configured: verification.ai_assist.ai_configured,
                          ai_eligible: verification.ai_assist.ai_eligible,
                          eligible_fields: verification.ai_assist.eligible_fields,
                          attempted: verification.ai_assist.attempted,
                          called: verification.ai_assist.called,
                          outcome: verification.ai_assist.outcome,
                          failure_category: verification.ai_assist.failure_category,
                          model: verification.ai_assist.model,
                          latency_ms: verification.ai_assist.latency_ms,
                          fields_requested: verification.ai_assist.fields_requested,
                          fields_proposed: verification.ai_assist.fields_proposed,
                          fields_updated: verification.ai_assist.fields_updated,
                          merge_outcomes: verification.ai_assist.merge_outcomes,
                        }
                      : null,
                  },
                  null,
                  2,
                )}
              </pre>
            ) : null}
            {qualityNote ? (
              <p className="text-sm text-review" role="status">
                <span className="font-semibold">Image quality:</span> {qualityNote}
              </p>
            ) : null}
          </div>

          <div>
            <h3 className="lv-section-title mb-1">Extracted label information</h3>
            <p className="mb-2 text-xs text-muted-foreground">What LabelVerify read from the image</p>
            <dl className="divide-y divide-border border-y border-border">
              {EXTRACTED_FIELD_ORDER.map((key) => {
                const field = extraction.selected_fields[key] as ExtractedField | undefined;
                return (
                  <ExtractedFieldRow
                    key={key}
                    label={FIELD_LABELS[key]}
                    field={field}
                    isWarning={key === "government_warning"}
                  />
                );
              })}
            </dl>
          </div>

          <div>
            <h3 className="lv-section-title mb-1">Verification checks</h3>
            <p className="mb-2 text-xs text-muted-foreground">
              What LabelVerify concluded from that evidence
            </p>
            <ul className="space-y-2">
              {verification.checks.map((check) => (
                <li key={check.check_name}>
                  <CheckRow
                    check={check}
                    labelOnly={labelOnly}
                    focused={focusedCheck === check.check_name}
                    open={openCheck === check.check_name}
                    onFocusCheck={() =>
                      setFocusedCheck((current) =>
                        current === check.check_name ? null : check.check_name,
                      )
                    }
                    onToggleDetails={() =>
                      setOpenCheck((current) =>
                        current === check.check_name ? null : check.check_name,
                      )
                    }
                  />
                </li>
              ))}
            </ul>
            <p className="pt-2 text-xs text-muted-foreground">{result.disclaimer}</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function ExtractedFieldRow({
  label,
  field,
  isWarning,
}: {
  label: string;
  field: ExtractedField | undefined;
  isWarning?: boolean;
}) {
  const status = field?.status ?? "NOT_FOUND";
  const value = field?.normalized_value || field?.raw_text;
  let display: string;
  let meta: string | null = null;

  if (status === "FOUND" && value) {
    if (isWarning) {
      display = "Detected";
      meta = truncate(value, 140);
    } else {
      display = value;
    }
  } else if (status === "UNCERTAIN") {
    display = "Uncertain";
    meta = value ? `Partial: “${truncate(value, 80)}”` : field?.explanation ?? null;
  } else {
    display = "Not found";
    meta = null;
  }

  const tone =
    status === "UNCERTAIN" || status === "NOT_FOUND" ? "text-review" : "text-foreground";

  return (
    <div className="grid gap-1 py-2.5 sm:grid-cols-[9.5rem_1fr] sm:gap-3">
      <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd>
        <p className={`text-sm font-semibold ${tone}`}>{display}</p>
        {meta ? <p className="mt-0.5 text-xs text-muted-foreground">{meta}</p> : null}
      </dd>
    </div>
  );
}

function CheckRow({
  check,
  labelOnly,
  focused,
  open,
  onFocusCheck,
  onToggleDetails,
}: {
  check: FieldCheckResult;
  labelOnly: boolean;
  focused: boolean;
  open: boolean;
  onFocusCheck: () => void;
  onToggleDetails: () => void;
}) {
  const borderAccent =
    check.status === "PASS"
      ? "border-l-pass"
      : check.status === "REVIEW"
        ? "border-l-review"
        : "border-l-fail";

  const showApplication = !labelOnly && check.application_value != null;

  return (
    <article className={["border-l-4 bg-surface py-2.5 pl-3 pr-1", borderAccent].join(" ")}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <button
          type="button"
          onClick={onFocusCheck}
          className="text-left text-sm font-semibold text-foreground hover:text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          aria-pressed={focused}
        >
          {check.check_name}
        </button>
        <StatusBadge status={check.status} />
      </div>

      {check.technical_details?.ai_assisted_evidence ? (
        <p className="mt-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          AI-assisted evidence
        </p>
      ) : null}

      {showApplication ? (
        <p className="mt-1.5 text-sm">
          <span className="text-muted-foreground">Application: </span>
          <span className="font-medium">{check.application_value}</span>
        </p>
      ) : null}

      <p className="mt-1.5 text-sm text-foreground">{check.explanation}</p>

      <button
        type="button"
        onClick={onToggleDetails}
        className="lv-btn-ghost mt-1.5 px-0 py-0 text-xs"
        aria-expanded={open}
      >
        {open ? "Hide technical details" : "Technical details"}
      </button>
      {open ? (
        <div className="mt-2 space-y-1 border-t border-border pt-2 text-xs text-muted-foreground">
          {check.detected_label_value ? (
            <p>
              <span className="font-semibold text-foreground">Detected evidence:</span>{" "}
              {truncate(check.detected_label_value, 160)}
            </p>
          ) : null}
          <p>
            <span className="font-semibold text-foreground">Method:</span> {check.decision_method}
          </p>
          {typeof check.technical_details?.evidence_method === "string" ? (
            <p>
              <span className="font-semibold text-foreground">Evidence path:</span>{" "}
              {String(check.technical_details.evidence_method)}
            </p>
          ) : null}
          {check.technical_details?.ai_assisted_evidence ? (
            <p>
              <span className="font-semibold text-foreground">AI evidence:</span> applied
              {check.technical_details.ai_merge_outcome
                ? ` (${String(check.technical_details.ai_merge_outcome)})`
                : ""}
            </p>
          ) : null}
          {check.technical_details?.ai_attempted_but_unavailable ? (
            <p>
              <span className="font-semibold text-foreground">AI evidence:</span> attempted but
              unavailable
              {check.technical_details.ai_failure_category
                ? ` (${String(check.technical_details.ai_failure_category)})`
                : ""}
            </p>
          ) : null}
          {Array.isArray(check.technical_details?.candidates) &&
          (check.technical_details.candidates as unknown[]).length > 0 ? (
            <p>
              <span className="font-semibold text-foreground">Candidates:</span>{" "}
              {(check.technical_details.candidates as string[]).slice(0, 5).join(" · ")}
            </p>
          ) : null}
          {check.technical_details?.ai_fallback_hints &&
          typeof check.technical_details.ai_fallback_hints === "object" ? (
            <p>
              <span className="font-semibold text-foreground">Extractor hints:</span>{" "}
              {truncate(JSON.stringify(check.technical_details.ai_fallback_hints), 220)}
            </p>
          ) : null}
          {check.technical_details?.brand_escalation &&
          typeof check.technical_details.brand_escalation === "object" ? (
            <p>
              <span className="font-semibold text-foreground">Brand OCR escalation:</span>{" "}
              {truncate(
                JSON.stringify(check.technical_details.brand_escalation),
                280,
              )}
            </p>
          ) : null}
          {check.reason_code ? (
            <p>
              <span className="font-semibold text-foreground">Reason code:</span> {check.reason_code}
            </p>
          ) : null}
          {check.limitations && check.limitations.length > 0 ? (
            <ul className="list-disc pl-4">
              {check.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function humanQualityNote(status: string, warnings: string[]): string | null {
  if (status === "GOOD" && warnings.length === 0) return null;
  if (warnings.length > 0) {
    const cleaned = warnings
      .map((w) => w.replace(/\bLaplacian\b/gi, "").replace(/\s+/g, " ").trim())
      .filter(Boolean);
    if (cleaned.length > 0) return cleaned.join(" ");
  }
  if (status === "WARNING") {
    return "Parts of the label may be harder to read.";
  }
  if (status === "POOR") {
    return "Image quality is limited. Review OCR carefully.";
  }
  return null;
}

interface Box {
  x_min: number;
  y_min: number;
  y_max: number;
  x_max: number;
}

function HighlightOverlay({
  boxes,
  ocrWidth,
  ocrHeight,
  renderWidth,
  renderHeight,
  naturalWidth,
  naturalHeight,
}: {
  boxes: Box[];
  ocrWidth: number;
  ocrHeight: number;
  renderWidth: number;
  renderHeight: number;
  naturalWidth: number;
  naturalHeight: number;
}) {
  if (!renderWidth || !renderHeight || !ocrWidth || !ocrHeight) return null;
  const displayAspect = naturalWidth / naturalHeight;
  const renderAspect = renderWidth / renderHeight;
  let contentW = renderWidth;
  let contentH = renderHeight;
  let offsetX = 0;
  let offsetY = 0;
  if (renderAspect > displayAspect) {
    contentW = renderHeight * displayAspect;
    offsetX = (renderWidth - contentW) / 2;
  } else {
    contentH = renderWidth / displayAspect;
    offsetY = (renderHeight - contentH) / 2;
  }
  const scaleX = contentW / ocrWidth;
  const scaleY = contentH / ocrHeight;
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
      {boxes.map((box, index) => (
        <rect
          key={`${index}-${box.x_min}-${box.y_min}`}
          x={offsetX + box.x_min * scaleX}
          y={offsetY + box.y_min * scaleY}
          width={Math.max((box.x_max - box.x_min) * scaleX, 2)}
          height={Math.max((box.y_max - box.y_min) * scaleY, 2)}
          fill="hsla(213, 54%, 28%, 0.22)"
          stroke="hsl(213, 54%, 28%)"
          strokeWidth={2}
        />
      ))}
    </svg>
  );
}
