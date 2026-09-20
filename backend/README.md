# LabelVerify AI backend

FastAPI service for alcohol label verification (decision support only).

Install: `pip install -e ".[dev,ocr-tesseract]"`  
Run: `uvicorn app.main:app --reload`

Production image embeds Tesseract — see repository `docs/DEPLOYMENT.md`.
