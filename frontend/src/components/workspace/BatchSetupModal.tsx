/**
 * Batch Review setup dialog — manifest + images, validate, process.
 * Architectural responsibility: modal intake; progress/results live in the workspace.
 */
import { useCallback, useState } from "react";
import { Modal } from "../common/Modal";
import { ApiRequestError, sampleManifestUrl, validateBatch } from "../../services/api";
import type { BatchValidationResult } from "../../types/batch";

interface BatchSetupModalProps {
  open: boolean;
  onClose: () => void;
  onProcess: (manifest: File, images: File[]) => void;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
}

/** Batch setup modal: CSV + images → validate → Process Batch. */
export function BatchSetupModal({
  open,
  onClose,
  onProcess,
  returnFocusRef,
}: BatchSetupModalProps) {
  const [manifest, setManifest] = useState<File | null>(null);
  const [images, setImages] = useState<File[]>([]);
  const [validation, setValidation] = useState<BatchValidationResult | null>(null);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function resetLocal() {
    setManifest(null);
    setImages([]);
    setValidation(null);
    setError(null);
  }

  function handleClose() {
    resetLocal();
    onClose();
  }

  const runValidate = useCallback(async () => {
    if (!manifest || images.length === 0) {
      setError("Upload a CSV manifest and at least one label image.");
      return;
    }
    setValidating(true);
    setError(null);
    try {
      const result = await validateBatch(manifest, images);
      setValidation(result);
      if (!result.valid) {
        setError(result.issues[0]?.message ?? "Batch validation found problems.");
      }
    } catch (err) {
      setValidation(null);
      setError(err instanceof ApiRequestError ? err.message : "Unable to validate batch.");
    } finally {
      setValidating(false);
    }
  }, [manifest, images]);

  function handleProcess() {
    if (!manifest || !validation?.valid || images.length === 0) return;
    const m = manifest;
    const imgs = images;
    resetLocal();
    onProcess(m, imgs);
  }

  const canProcess = Boolean(validation?.valid && manifest && images.length > 0);

  return (
    <Modal
      open={open}
      title="Process Batch"
      description="CSV application manifest plus matching label images."
      onClose={handleClose}
      returnFocusRef={returnFocusRef}
      size="lg"
    >
      <div className="space-y-4">
        <div>
          <label className="lv-label" htmlFor="batch-manifest">
            CSV manifest
          </label>
          <input
            id="batch-manifest"
            type="file"
            accept=".csv,text/csv"
            className="mt-1 block w-full text-sm"
            onChange={(e) => {
              setManifest(e.target.files?.[0] ?? null);
              setValidation(null);
            }}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            <a className="text-primary underline" href={sampleManifestUrl()} download>
              Download sample manifest
            </a>
          </p>
        </div>
        <div>
          <label className="lv-label" htmlFor="batch-images">
            Label images
          </label>
          <input
            id="batch-images"
            type="file"
            accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
            multiple
            className="mt-1 block w-full text-sm"
            onChange={(e) => {
              setImages(Array.from(e.target.files ?? []));
              setValidation(null);
            }}
          />
          {images.length > 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">{images.length} image(s) selected</p>
          ) : null}
        </div>

        {validation ? (
          <div className="border border-border bg-muted px-3 py-2 text-sm">
            <p>
              Rows: {validation.row_count} · Images: {validation.image_count} · Matched:{" "}
              {validation.matched_count}
            </p>
            {!validation.valid && validation.issues.length > 0 ? (
              <ul className="mt-1 list-disc pl-4 text-fail">
                {validation.issues.slice(0, 5).map((issue) => (
                  <li key={`${issue.code}-${issue.filename}-${issue.message}`}>{issue.message}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        {error ? (
          <p className="border border-fail bg-fail-soft px-3 py-2 text-sm text-fail" role="alert">
            {error}
          </p>
        ) : null}

        <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-3">
          <button type="button" className="lv-btn-secondary" onClick={handleClose}>
            Cancel
          </button>
          <button
            type="button"
            className="lv-btn-secondary"
            disabled={validating || !manifest || images.length === 0}
            onClick={() => void runValidate()}
          >
            {validating ? "Validating…" : "Validate"}
          </button>
          <button
            type="button"
            className="lv-btn-primary"
            disabled={!canProcess}
            onClick={handleProcess}
          >
            Process Batch
          </button>
        </div>
      </div>
    </Modal>
  );
}
