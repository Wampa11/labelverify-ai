# Docker image for the LabelVerify FastAPI backend (release candidate).
# Architectural responsibility: self-contained API + Tesseract — no host OCR dependency.
# Secrets (OPENAI_API_KEY, Cloudflare tokens) are never copied into this image.

FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production

# System libs for OpenCV + Tesseract OCR (must be in-image for portable deploy).
# Prefer native linux/arm64 on Apple Silicon — do not force linux/amd64.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --version

COPY pyproject.toml README.md ./
COPY app ./app

# Install runtime package including pytesseract adapter.
# RapidOCR remains optional and is not installed in the production image.
RUN pip install --no-cache-dir -e ".[ocr-tesseract]"

# Non-root user for prototype hardening (writable data dir for optional SQLite).
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/uploads \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health/live || exit 1

# --proxy-headers: honor X-Forwarded-* from the trusted frontend nginx hop only
# (backend is not published to the host). Cloudflare terminates HTTPS externally.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
