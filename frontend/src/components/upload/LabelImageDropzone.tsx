/**
 * Accessible label image dropzone with browse and drag-and-drop.
 * Architectural responsibility: primary image intake control for Single Review.
 */
import { useId, useRef, useState, type DragEvent, type ChangeEvent, type KeyboardEvent } from "react";

const ACCEPTED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];
const ACCEPTED_MIME = ["image/jpeg", "image/png", "image/webp"];

interface LabelImageDropzoneProps {
  disabled?: boolean;
  selectedFileName?: string | null;
  onFileSelected: (file: File) => void;
  onInvalidFile: (message: string) => void;
}

/** Compact upload target for compliance agents. */
export function LabelImageDropzone({
  disabled = false,
  selectedFileName = null,
  onFileSelected,
  onInvalidFile,
}: LabelImageDropzoneProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  function validateAndEmit(file: File | undefined) {
    if (!file) {
      return;
    }
    const extensionOk = ACCEPTED_EXTENSIONS.some((ext) =>
      file.name.toLowerCase().endsWith(ext),
    );
    const mimeOk = !file.type || ACCEPTED_MIME.includes(file.type);
    if (!extensionOk && !mimeOk) {
      onInvalidFile(
        "That file type is not supported. Choose a JPEG, PNG, or WebP image, then try again.",
      );
      return;
    }
    if (file.size === 0) {
      onInvalidFile("That file is empty. Choose another image file.");
      return;
    }
    onFileSelected(file);
  }

  function onInputChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    validateAndEmit(file);
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    if (disabled) {
      return;
    }
    validateAndEmit(event.dataTransfer.files?.[0]);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (disabled) {
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      inputRef.current?.click();
    }
  }

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="Upload label image"
      aria-disabled={disabled || undefined}
      aria-describedby={`${inputId}-help`}
      onKeyDown={onKeyDown}
      onDragEnter={(event) => {
        event.preventDefault();
        if (!disabled) setDragActive(true);
      }}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragActive(true);
      }}
      onDragLeave={(event) => {
        event.preventDefault();
        setDragActive(false);
      }}
      onDrop={onDrop}
      onClick={() => {
        if (!disabled) inputRef.current?.click();
      }}
      className={[
        "border border-dashed px-5 py-8 text-center transition-colors",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        dragActive ? "border-primary bg-muted" : "border-border bg-surface",
        disabled ? "cursor-wait opacity-70" : "cursor-pointer hover:border-primary",
      ].join(" ")}
      style={{ borderRadius: "var(--radius)" }}
    >
      <input
        id={inputId}
        ref={inputRef}
        type="file"
        className="sr-only"
        accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
        disabled={disabled}
        onChange={onInputChange}
        aria-label="Choose label image file"
      />
      <p className="font-display text-sm font-semibold text-foreground">
        Drag and drop a label image here
      </p>
      <p className="mt-2 text-sm text-primary">or Choose Image</p>
      <p id={`${inputId}-help`} className="mt-2 text-xs text-muted-foreground">
        JPEG, PNG, or WebP
      </p>
      {selectedFileName ? (
        <p className="mt-3 text-sm font-medium text-foreground">Selected: {selectedFileName}</p>
      ) : null}
    </div>
  );
}
