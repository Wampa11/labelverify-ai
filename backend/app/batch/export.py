"""
CSV export for batch results with spreadsheet formula-injection protection.

Architectural responsibility: operational export only — no secrets or stack traces.
"""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

from app.reporting.sanitize import sanitize_spreadsheet_value

if TYPE_CHECKING:
    from app.batch.orchestrator import BatchJobRecord

# Backward-compatible alias used by existing tests/callers.
sanitize_csv_cell = sanitize_spreadsheet_value

EXPORT_COLUMNS: tuple[str, ...] = (
    "filename",
    "processing_state",
    "overall_status",
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "brand_status",
    "class_type_status",
    "alcohol_content_status",
    "net_contents_status",
    "government_warning_status",
    "ai_assisted",
    "processing_time_ms",
    "review_reason_codes",
    "error_code",
    "error",
)


def build_export_csv(job: BatchJobRecord) -> str:
    """Serialize batch item outcomes to CSV text (UTF-8)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(EXPORT_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for item in job.items:
        check_status = _check_statuses(item)
        writer.writerow(
            {
                "filename": sanitize_csv_cell(item.filename),
                "processing_state": sanitize_csv_cell(item.processing_state.value),
                "overall_status": sanitize_csv_cell(item.overall_status),
                "brand_name": sanitize_csv_cell(item.row.brand_name),
                "class_type": sanitize_csv_cell(item.row.class_type),
                "alcohol_content": sanitize_csv_cell(item.row.alcohol_content),
                "net_contents": sanitize_csv_cell(item.row.net_contents),
                "brand_status": sanitize_csv_cell(check_status.get("Brand Name")),
                "class_type_status": sanitize_csv_cell(check_status.get("Class / Type")),
                "alcohol_content_status": sanitize_csv_cell(
                    check_status.get("Alcohol Content / ABV"),
                ),
                "net_contents_status": sanitize_csv_cell(check_status.get("Net Contents")),
                "government_warning_status": sanitize_csv_cell(
                    check_status.get("Government Health Warning"),
                ),
                "ai_assisted": "true" if item.ai_assisted else "false",
                "processing_time_ms": sanitize_csv_cell(
                    f"{item.processing_time_ms:.1f}" if item.processing_time_ms is not None else "",
                ),
                "review_reason_codes": sanitize_csv_cell(";".join(item.review_reason_codes)),
                "error_code": sanitize_csv_cell(item.error_code),
                "error": sanitize_csv_cell(item.error_message),
            },
        )
    return buffer.getvalue()


def _check_statuses(item: object) -> dict[str, str]:
    result = getattr(item, "result", None)
    if result is None:
        return {}
    verification = result.verification
    return {c.check_name: c.status.value for c in verification.checks}
