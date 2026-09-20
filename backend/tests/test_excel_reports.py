"""
Excel report generation tests.

Architectural responsibility: verify .xlsx structure, content, and injection defense.
"""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.batch.export import sanitize_csv_cell
from app.batch.models import (
    BatchItemProcessingState,
    BatchJobState,
    BatchValidationResult,
    ManifestRow,
)
from app.batch.store import BatchItemRecord, BatchJobRecord, get_batch_store
from app.main import app
from app.models.extraction import (
    ExtractedField,
    ExtractedLabelResult,
    ExtractionMethod,
    ExtractionStatus,
    OcrPassSummary,
    ResultSelection,
    RetryDecision,
)
from app.models.verification import (
    CheckStatus,
    DecisionMethod,
    FieldCheckResult,
    SingleReviewVerificationResponse,
    VerificationResult,
)
from app.reporting.batch_report import build_batch_xlsx
from app.reporting.sanitize import sanitize_spreadsheet_value
from app.reporting.single_report import build_single_review_xlsx

client = TestClient(app)


def _field(name: str, text: str) -> ExtractedField:
    return ExtractedField(
        field_name=name,
        status=ExtractionStatus.FOUND,
        raw_text=text,
        normalized_value=text,
        normalized_numeric=None,
        normalized_unit=None,
        candidates=[],
        ocr_regions=[],
        extraction_method=ExtractionMethod.LAYOUT_HEURISTIC,
        explanation="ok",
        ai_fallback_hints={},
    )


def _single_result(
    *,
    ai_used: bool = False,
    brand: str = "OLD TOM",
) -> SingleReviewVerificationResponse:
    fields = {
        "brand_name": _field("brand_name", brand),
        "class_type": _field("class_type", "Bourbon"),
        "alcohol_content": _field("alcohol_content", "45%"),
        "net_contents": _field("net_contents", "750 mL"),
        "government_warning": _field("government_warning", "GOVERNMENT WARNING: test"),
    }
    checks = [
        FieldCheckResult(
            check_name="Brand Name",
            detected_label_value=brand,
            status=CheckStatus.PASS,
            explanation="Recovered from label.",
            decision_method=DecisionMethod.DETERMINISTIC_RULE,
            reason_code="BRAND_MATCH",
            technical_details={"ai_assisted_evidence": ai_used},
        ),
        FieldCheckResult(
            check_name="Government Health Warning",
            detected_label_value="GOVERNMENT WARNING: test",
            status=CheckStatus.PASS,
            explanation="Warning present.",
            decision_method=DecisionMethod.DETERMINISTIC_RULE,
            reason_code="WARNING_PRESENT_MATCH",
        ),
    ]
    verification = VerificationResult(
        verification_id="ver-test-1",
        verification_mode="label_only",
        overall_status=CheckStatus.PASS,
        checks=checks,
        pass_count=2,
        review_count=0,
        fail_count=0,
        processing_time_ms=100.0,
        ai_used=ai_used,
        ai_degraded=False,
        degradation_notes=[],
    )
    extraction = ExtractedLabelResult(
        analysis_id="a1",
        selected_fields=fields,
        fast_pass=OcrPassSummary(
            profile="fast",
            max_edge_px=1600,
            provider_name="tesseract",
            preprocessing_time_ms=1,
            ocr_time_ms=1,
            extraction_time_ms=1,
            total_pass_time_ms=3,
            ocr_text_preview="x",
            word_count=1,
            image_width_px=100,
            image_height_px=100,
            fields={},
            found_count=5,
            uncertain_count=0,
            not_found_count=0,
        ),
        enhanced_pass=None,
        retry=RetryDecision(triggered=False, reasons=[], performed=False),
        selection=ResultSelection(
            selected_profile="fast",
            reason="test",
            fast_score=1,
            enhanced_score=None,
        ),
        ocr_image_width_px=100,
        ocr_image_height_px=100,
        display_image_width_px=100,
        display_image_height_px=100,
        stage_timings_ms={},
        processing_time_ms=50,
        disclaimer="Extraction only.",
    )
    return SingleReviewVerificationResponse(
        analysis_id="a1",
        verification_id="ver-test-1",
        filename="old-tom-demo.jpg",
        verification_mode="label_only",
        application=None,
        display_image_base64="QQ==",
        display_media_type="image/jpeg",
        metadata_width_px=100,
        metadata_height_px=100,
        quality_status="GOOD",
        quality_warnings=[],
        extraction=extraction,
        verification=verification,
        processing_time_ms=100,
        stage_timings_ms={},
    )


def test_sanitize_formula_injection() -> None:
    assert sanitize_spreadsheet_value("=1+1").startswith("'")
    assert sanitize_spreadsheet_value("+cmd").startswith("'")
    assert sanitize_spreadsheet_value("-1").startswith("'")
    assert sanitize_spreadsheet_value("@sum").startswith("'")
    assert sanitize_csv_cell("=CMD") == sanitize_spreadsheet_value("=CMD")
    assert sanitize_spreadsheet_value("normal") == "normal"


def test_single_xlsx_structure() -> None:
    data = build_single_review_xlsx(_single_result(ai_used=True, brand="=HACK"))
    wb = load_workbook(BytesIO(data))
    assert "Review Summary" in wb.sheetnames
    ws = wb["Review Summary"]
    # Title present
    assert "LabelVerify" in str(ws["A1"].value)
    joined = " ".join(str(c.value) for row in ws.iter_rows(max_row=40) for c in row if c.value)
    assert "PASS" in joined
    assert "Prototype decision-support" in joined
    assert "'=HACK" in joined or "=HACK" in joined  # sanitized as literal
    assert "ver-test-1" in joined


def test_single_report_api() -> None:
    payload = _single_result().model_dump(mode="json")
    response = client.post("/api/v1/reports/single", json=payload)
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    assert "labelverify-review-" in response.headers.get("content-disposition", "")
    wb = load_workbook(BytesIO(response.content))
    assert "Review Summary" in wb.sheetnames


def test_batch_xlsx_sheets_and_error_row() -> None:
    store = get_batch_store()
    store.clear()
    row = ManifestRow(
        row_number=2,
        filename="a.jpg",
        brand_name="Brand",
        class_type="Bourbon",
        alcohol_content="40%",
        net_contents="750 mL",
    )
    ok_item = BatchItemRecord(
        item_id="i1",
        filename="a.jpg",
        row=row,
        image_bytes=b"x",
        content_type="image/jpeg",
        processing_state=BatchItemProcessingState.COMPLETED,
        overall_status="PASS",
        result=_single_result(),
        processing_time_ms=10,
    )
    err_item = BatchItemRecord(
        item_id="i2",
        filename="b.jpg",
        row=row.model_copy(update={"filename": "b.jpg", "brand_name": "=EVIL"}),
        image_bytes=b"x",
        content_type="image/jpeg",
        processing_state=BatchItemProcessingState.ERROR,
        error_code="ocr_failed",
        error_message="OCR failed",
    )
    job = BatchJobRecord(
        batch_id="batch-xyz-999",
        state=BatchJobState.COMPLETED,
        concurrency=2,
        ai_budget_max=25,
        validation=BatchValidationResult(valid=True, row_count=2, image_count=2, matched_count=2),
        items=[ok_item, err_item],
        started_at=1.0,
        finished_at=2.5,
    )
    store.put(job)
    data = build_batch_xlsx(job)
    wb = load_workbook(BytesIO(data))
    assert wb.sheetnames == ["Batch Summary", "Review Results"]
    summary = " ".join(
        str(c.value) for row in wb["Batch Summary"].iter_rows(max_row=30) for c in row if c.value
    )
    assert "batch-xyz-999" in summary
    assert "ERROR" in summary or "1" in summary
    results = wb["Review Results"]
    # Header row 4
    headers = [c.value for c in results[4]]
    assert "Filename" in headers
    assert "Overall Status" in headers
    blob = " ".join(
        str(c.value)
        for row in results.iter_rows(min_row=5, max_row=10)
        for c in row
        if c.value
    )
    assert "a.jpg" in blob
    assert "b.jpg" in blob
    assert "'=EVIL" in blob or "EVIL" in blob

    api = client.get("/api/v1/reports/batches/batch-xyz-999")
    assert api.status_code == 200
    assert "labelverify-batch-" in api.headers.get("content-disposition", "")
