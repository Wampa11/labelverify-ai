"""
CSV manifest parsing and batch input validation.

Architectural responsibility: associate application rows with uploaded images safely —
no OCR/rules. Rejects invalid associations before processing starts.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import PurePosixPath

from pydantic import ValidationError

from app.batch.models import (
    REQUIRED_MANIFEST_COLUMNS,
    BatchValidationIssue,
    BatchValidationResult,
    ManifestRow,
)
from app.core.config import Settings
from app.models.verification import ApplicationData

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._ -]+$")
_SUPPORTED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def sanitize_upload_filename(raw: str | None) -> str | None:
    """
    Return a safe basename or None if the name is unsafe / empty.

    Rejects path traversal and directory components.
    """
    if raw is None:
        return None
    name = raw.strip()
    if not name:
        return None
    # Reject any path-like input before taking basename.
    if "/" in name or "\\" in name or ".." in name:
        return None
    base = PurePosixPath(name).name
    if not base or base in {".", ".."}:
        return None
    if not _SAFE_FILENAME.match(base):
        return None
    return base


def parse_and_validate_manifest(
    csv_bytes: bytes,
    image_filenames: list[str],
    *,
    settings: Settings,
) -> BatchValidationResult:
    """
    Validate CSV + image set. Does not start processing.

    `image_filenames` must already be sanitized basenames (duplicates reported).
    """
    issues: list[BatchValidationIssue] = []
    max_items = settings.batch_max_items

    if not csv_bytes.strip():
        return BatchValidationResult(
            valid=False,
            issues=[
                BatchValidationIssue(
                    code="empty_manifest",
                    message="The manifest CSV is empty.",
                ),
            ],
        )

    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return BatchValidationResult(
            valid=False,
            issues=[
                BatchValidationIssue(
                    code="manifest_encoding",
                    message="Manifest must be UTF-8 encoded CSV.",
                ),
            ],
        )

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return BatchValidationResult(
            valid=False,
            issues=[
                BatchValidationIssue(
                    code="missing_header",
                    message="Manifest is missing a header row.",
                ),
            ],
        )

    headers = [h.strip().lower() for h in reader.fieldnames if h is not None]
    missing_cols = [c for c in REQUIRED_MANIFEST_COLUMNS if c not in headers]
    if missing_cols:
        return BatchValidationResult(
            valid=False,
            issues=[
                BatchValidationIssue(
                    code="missing_columns",
                    message=(
                        "Manifest is missing required columns: "
                        + ", ".join(missing_cols)
                        + ". Expected: "
                        + ", ".join(REQUIRED_MANIFEST_COLUMNS)
                    ),
                ),
            ],
        )

    # Normalize row keys to lowercase
    rows_raw: list[dict[str, str]] = []
    for _index, row in enumerate(reader, start=2):
        normalized = {
            (k.strip().lower() if k else ""): (v or "").strip()
            for k, v in row.items()
            if k is not None
        }
        rows_raw.append(normalized)

    if not rows_raw:
        return BatchValidationResult(
            valid=False,
            issues=[
                BatchValidationIssue(
                    code="empty_manifest",
                    message="Manifest has a header but no data rows.",
                ),
            ],
        )

    if len(rows_raw) > max_items:
        return BatchValidationResult(
            valid=False,
            row_count=len(rows_raw),
            issues=[
                BatchValidationIssue(
                    code="batch_too_large",
                    message=(
                        f"Manifest has {len(rows_raw)} rows; "
                        f"prototype maximum is {max_items}."
                    ),
                ),
            ],
        )

    # Image filename inventory
    image_count = len(image_filenames)
    seen_images: dict[str, int] = {}
    for name in image_filenames:
        safe = sanitize_upload_filename(name)
        if safe is None:
            issues.append(
                BatchValidationIssue(
                    code="unsafe_image_filename",
                    message=f"Uploaded image name is not allowed: {name!r}",
                    filename=name,
                ),
            )
            continue
        ext = PurePosixPath(safe).suffix.lower()
        if ext not in _SUPPORTED_IMAGE_EXT:
            issues.append(
                BatchValidationIssue(
                    code="unsupported_image",
                    message=f"Unsupported image format for {safe}. Use JPEG, PNG, or WebP.",
                    filename=safe,
                ),
            )
            continue
        seen_images[safe] = seen_images.get(safe, 0) + 1

    for fname, count in seen_images.items():
        if count > 1:
            issues.append(
                BatchValidationIssue(
                    code="duplicate_image",
                    message=f"Duplicate uploaded image filename: {fname}",
                    filename=fname,
                ),
            )

    unique_images = {k for k, v in seen_images.items() if v == 1}

    parsed_rows: list[ManifestRow] = []
    manifest_names: list[str] = []
    for index, raw in enumerate(rows_raw, start=2):
        fname_raw = raw.get("filename", "")
        safe = sanitize_upload_filename(fname_raw)
        if safe is None:
            issues.append(
                BatchValidationIssue(
                    code="invalid_filename",
                    message=(
                        f"Row {index}: filename is missing or unsafe "
                        f"(use a simple basename like label-001.jpg)."
                    ),
                    row_number=index,
                    filename=fname_raw or None,
                ),
            )
            continue
        if safe in manifest_names:
            issues.append(
                BatchValidationIssue(
                    code="duplicate_filename",
                    message=f"Row {index}: duplicate filename in manifest: {safe}",
                    row_number=index,
                    filename=safe,
                ),
            )
            continue
        manifest_names.append(safe)

        try:
            app = ApplicationData(
                brand_name=raw.get("brand_name", ""),
                class_type=raw.get("class_type", ""),
                alcohol_content_abv=raw.get("alcohol_content", ""),
                net_contents=raw.get("net_contents", ""),
            )
        except ValidationError:
            issues.append(
                BatchValidationIssue(
                    code="invalid_application_values",
                    message=f"Row {index}: application values are incomplete or invalid.",
                    row_number=index,
                    filename=safe,
                ),
            )
            continue

        if safe not in unique_images and safe not in seen_images:
            issues.append(
                BatchValidationIssue(
                    code="missing_image",
                    message=f"Row {index}: no uploaded image matches {safe}",
                    row_number=index,
                    filename=safe,
                ),
            )
            continue
        if safe in seen_images and safe not in unique_images:
            # Duplicate image already reported; still mark association failure.
            issues.append(
                BatchValidationIssue(
                    code="missing_image",
                    message=(
                        f"Row {index}: cannot uniquely match {safe} "
                        "(duplicate uploads)."
                    ),
                    row_number=index,
                    filename=safe,
                ),
            )
            continue

        parsed_rows.append(
            ManifestRow(
                row_number=index,
                filename=safe,
                brand_name=app.brand_name,
                class_type=app.class_type,
                alcohol_content=app.alcohol_content_abv,
                net_contents=app.net_contents,
            ),
        )

    matched = {r.filename for r in parsed_rows}
    missing = [n for n in manifest_names if n not in matched]
    unreferenced = sorted(unique_images - matched)
    for name in unreferenced:
        issues.append(
            BatchValidationIssue(
                code="unreferenced_image",
                message=f"Uploaded image is not referenced by the manifest: {name}",
                filename=name,
            ),
        )

    # Structural association errors block processing.
    blocking_codes = {
        "empty_manifest",
        "manifest_encoding",
        "missing_header",
        "missing_columns",
        "batch_too_large",
        "duplicate_filename",
        "duplicate_image",
        "missing_image",
        "invalid_filename",
        "unsafe_image_filename",
        "unsupported_image",
        "invalid_application_values",
    }
    has_blocking = any(i.code in blocking_codes for i in issues)
    # Unreferenced images are reported but do not block if all rows match.
    only_unreferenced = issues and all(i.code == "unreferenced_image" for i in issues)
    valid = (
        len(parsed_rows) > 0
        and len(parsed_rows) == len(rows_raw)
        and not has_blocking
    ) or (
        len(parsed_rows) == len(rows_raw)
        and only_unreferenced
        and len(parsed_rows) > 0
    )

    # Stricter: unreferenced is warning — allow process if all rows matched uniquely.
    valid = (
        len(parsed_rows) > 0
        and len(parsed_rows) == len(rows_raw)
        and not any(i.code != "unreferenced_image" for i in issues)
    )

    return BatchValidationResult(
        valid=valid,
        row_count=len(rows_raw),
        image_count=image_count,
        matched_count=len(parsed_rows),
        missing_count=len(missing) if not valid else 0,
        unreferenced_count=len(unreferenced),
        issues=issues,
        rows=parsed_rows if valid else [],
    )


def sample_manifest_csv() -> str:
    """Return a documented synthetic sample manifest (not official COLA data)."""
    return (
        "filename,brand_name,class_type,alcohol_content,net_contents\n"
        "old-tom-001.jpg,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,45%,750 mL\n"
        "stones-throw-002.jpg,Stone's Throw,Straight Bourbon Whiskey,40%,750 mL\n"
        "demo-review-003.jpg,North Peak Distilling,Bourbon Whiskey,45%,750 mL\n"
    )
