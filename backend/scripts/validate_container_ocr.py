"""
Validate OCR + verification inside a running backend container (or against local API).

Architectural responsibility: Phase 8 release check — prove Tesseract works in-image.
Does not replace Tesseract with PaddleOCR. Not part of CI.

Usage (from repo root, with Compose up):
  docker compose exec backend python -c "..."  # or copy this script in
  python backend/scripts/validate_container_ocr.py --base-url http://localhost:8080

Requires demo fixture at test-data/demo/old-tom-demo.jpg.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_IMAGE = REPO_ROOT / "test-data" / "demo" / "old-tom-demo.jpg"
APPLICATION = {
    "brand_name": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "alcohol_content_abv": "45%",
    "net_contents": "750 mL",
    "notes": "",
}


def check_tesseract_local() -> dict[str, object]:
    path = shutil.which("tesseract")
    version = None
    if path:
        try:
            version = subprocess.check_output(
                ["tesseract", "--version"],
                text=True,
                stderr=subprocess.STDOUT,
            ).splitlines()[0]
        except (OSError, subprocess.CalledProcessError):
            version = "unknown"
    return {"tesseract_on_path": bool(path), "version_line": version}


def verify_via_api(base_url: str) -> dict[str, object]:
    if not DEMO_IMAGE.is_file():
        raise SystemExit(f"Missing demo image: {DEMO_IMAGE}")
    url = f"{base_url.rstrip('/')}/api/v1/verify"
    started = time.perf_counter()
    with DEMO_IMAGE.open("rb") as handle:
        files = {"file": ("old-tom-demo.jpg", handle, "image/jpeg")}
        data = {"application": json.dumps(APPLICATION)}
        response = httpx.post(url, files=files, data=data, timeout=120.0)
    elapsed_ms = (time.perf_counter() - started) * 1000
    payload = (
        response.json()
        if "application/json" in response.headers.get("content-type", "")
        else {"raw": response.text[:500]}
    )
    if not isinstance(payload, dict):
        return {"http_status": response.status_code, "elapsed_ms": round(elapsed_ms, 1)}

    verification = payload.get("verification") or {}
    checks = verification.get("checks") or payload.get("checks") or []
    ai = verification.get("ai_assistance") or payload.get("ai_meta") or {}
    return {
        "http_status": response.status_code,
        "elapsed_ms": round(elapsed_ms, 1),
        "overall_status": verification.get("overall_status") or payload.get("overall_status"),
        "quality_status": payload.get("quality_status"),
        "processing_time_ms": payload.get("processing_time_ms"),
        "stage_timings_ms": payload.get("stage_timings_ms"),
        "ai_used": ai.get("used") if isinstance(ai, dict) else None,
        "checks_summary": [
            {
                "id": c.get("check_id") or c.get("id"),
                "status": c.get("status"),
                "reason": c.get("reason_code"),
            }
            for c in checks
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Container/host OCR validation helper")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API base (Compose via nginx: http://localhost:8080)",
    )
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Only print local tesseract check (useful inside container)",
    )
    args = parser.parse_args()

    report: dict[str, object] = {
        "tesseract": check_tesseract_local(),
        "demo_image": str(DEMO_IMAGE),
        "demo_exists": DEMO_IMAGE.is_file(),
    }
    if not args.skip_api:
        report["verify"] = verify_via_api(args.base_url)

    print(json.dumps(report, indent=2))
    if not args.skip_api:
        verify = report.get("verify") or {}
        if verify.get("http_status") != 200:
            sys.exit(1)


if __name__ == "__main__":
    main()
