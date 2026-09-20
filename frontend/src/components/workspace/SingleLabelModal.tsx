/**
 * Single Label setup dialog — upload image and start label-only analysis.
 * Architectural responsibility: modal intake only; results render in the workspace.
 */
import { useEffect, useState } from "react";
import { LabelImageDropzone } from "../upload/LabelImageDropzone";
import { Modal } from "../common/Modal";

interface SingleLabelModalProps {
  open: boolean;
  onClose: () => void;
  onAnalyze: (file: File) => void;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
}

/** Extremely simple Single Label modal: image + Analyze Label. */
export function SingleLabelModal({
  open,
  onClose,
  onAnalyze,
  returnFocusRef,
}: SingleLabelModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function resetLocal() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null);
    setPreviewUrl(null);
    setError(null);
  }

  // Fresh intake whenever the dialog opens (tile or "Analyze another label").
  useEffect(() => {
    if (!open) return;
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setFile(null);
    setError(null);
  }, [open]);

  function handleClose() {
    resetLocal();
    onClose();
  }

  function handleFile(next: File) {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setError(null);
    setFile(next);
    setPreviewUrl(URL.createObjectURL(next));
  }

  function handleAnalyze() {
    if (!file) {
      setError("Choose a label image before analyzing.");
      return;
    }
    const selected = file;
    resetLocal();
    onAnalyze(selected);
  }

  return (
    <Modal
      open={open}
      title="Analyze Single Label"
      description="Upload one distilled spirits label. No application data is required."
      onClose={handleClose}
      returnFocusRef={returnFocusRef}
    >
      <div className="space-y-4">
        <LabelImageDropzone
          selectedFileName={file?.name ?? null}
          onFileSelected={handleFile}
          onInvalidFile={setError}
        />
        {previewUrl && file ? (
          <figure className="m-0 border border-border bg-muted p-2">
            <img
              src={previewUrl}
              alt={`Selected label: ${file.name}`}
              className="max-h-40 w-full object-contain"
            />
            <figcaption className="mt-1 text-xs text-muted-foreground">{file.name}</figcaption>
          </figure>
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
            className="lv-btn-primary"
            disabled={!file}
            onClick={handleAnalyze}
          >
            Analyze Label
          </button>
        </div>
      </div>
    </Modal>
  );
}
