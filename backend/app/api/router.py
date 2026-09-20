"""
Top-level API router composition.

Architectural responsibility: mount versioned route modules without embedding domain logic.
"""

from fastapi import APIRouter

from app.api import batches, extraction, health, images, reports, telemetry, verification

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(images.router, prefix="/api/v1", tags=["images"])
api_router.include_router(extraction.router, prefix="/api/v1", tags=["extraction"])
api_router.include_router(verification.router, prefix="/api/v1", tags=["verification"])
api_router.include_router(batches.router, prefix="/api/v1", tags=["batches"])
api_router.include_router(reports.router, prefix="/api/v1", tags=["reports"])
api_router.include_router(telemetry.router, prefix="/api/v1", tags=["telemetry"])
