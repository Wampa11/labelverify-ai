"""
Batch Review HTTP endpoints.

Architectural responsibility: multipart intake and poll/export — no verification rules.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import JSONResponse, Response

from app.batch.manifest import sample_manifest_csv
from app.batch.models import (
    BatchCreateResponse,
    BatchItemDetail,
    BatchJobStatus,
    BatchValidationResult,
)
from app.batch.orchestrator import (
    BatchOrchestrator,
    BatchValidationError,
    prepare_image_uploads,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batches", tags=["batches"])


@router.get(
    "/sample-manifest",
    summary="Download sample batch CSV manifest (synthetic demo data)",
)
async def download_sample_manifest() -> Response:
    """Synthetic evaluator fixture — not official COLA records."""
    content = sample_manifest_csv()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="labelverify-sample-manifest.csv"',
        },
    )


@router.post(
    "/validate",
    response_model=BatchValidationResult,
    summary="Validate batch CSV manifest against uploaded label images",
)
async def validate_batch(
    manifest: Annotated[UploadFile, File(description="CSV manifest")],
    files: Annotated[list[UploadFile], File(description="Label images")],
) -> BatchValidationResult | JSONResponse:
    csv_bytes = await manifest.read()
    uploads: list[tuple[str | None, bytes, str | None]] = []
    for upload in files:
        uploads.append((upload.filename, await upload.read(), upload.content_type))
    names, _images = prepare_image_uploads(uploads)
    orchestrator = BatchOrchestrator()
    result = orchestrator.validate(csv_bytes, names)
    if not result.valid:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=result.model_dump(),
        )
    return result


@router.post(
    "",
    response_model=BatchCreateResponse,
    summary="Create and start a batch job",
)
async def create_batch(
    manifest: Annotated[UploadFile, File(description="CSV manifest")],
    files: Annotated[list[UploadFile], File(description="Label images")],
) -> BatchCreateResponse | JSONResponse:
    csv_bytes = await manifest.read()
    uploads: list[tuple[str | None, bytes, str | None]] = []
    for upload in files:
        uploads.append((upload.filename, await upload.read(), upload.content_type))
    names, images = prepare_image_uploads(uploads)
    orchestrator = BatchOrchestrator()
    try:
        return orchestrator.create_and_start(
            csv_bytes,
            images,
            names,
            start_background=True,
        )
    except BatchValidationError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=exc.validation.model_dump(),
        )


@router.get(
    "/{batch_id}",
    response_model=BatchJobStatus,
    summary="Poll batch job status and item summaries",
)
async def get_batch(batch_id: str) -> BatchJobStatus | JSONResponse:
    status_payload = BatchOrchestrator().get_status(batch_id)
    if status_payload is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": "Batch not found.",
                "code": "batch_not_found",
            },
        )
    return status_payload


@router.get(
    "/{batch_id}/items/{item_id}",
    response_model=BatchItemDetail,
    summary="Fetch detailed verification result for one batch item",
)
async def get_batch_item(batch_id: str, item_id: str) -> BatchItemDetail | JSONResponse:
    detail = BatchOrchestrator().get_item_detail(batch_id, item_id)
    if detail is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": "Batch item not found.",
                "code": "batch_item_not_found",
            },
        )
    return detail


@router.get(
    "/{batch_id}/export",
    summary="Export batch results as CSV",
)
async def export_batch(batch_id: str) -> Response:
    csv_text = BatchOrchestrator().export_csv(batch_id)
    if csv_text is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": "Batch not found.",
                "code": "batch_not_found",
            },
        )
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="labelverify-batch-{batch_id[:8]}.csv"',
        },
    )
