"""
CLI entrypoint for OCR evaluation.

Architectural responsibility: generate corpus (if needed), run the matrix, write reports.

Usage (from backend/ with package installed):

    python -m app.ocr.evaluate
    python -m app.ocr.evaluate --generate-corpus-only
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.ocr.evaluate.corpus import default_corpus_root, generate_corpus
from app.ocr.evaluate.report import (
    write_csv_report,
    write_json_report,
    write_markdown_summary,
)
from app.ocr.evaluate.runner import run_evaluation
from app.preprocessing.ocr_prepare import OcrPreprocessProfile


def main(argv: list[str] | None = None) -> int:
    """Parse CLI args, run evaluation, write artifacts under results/."""
    parser = argparse.ArgumentParser(description="LabelVerify AI OCR evaluation harness")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=None,
        help="Corpus root containing fixtures/ and ground-truth/",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help="Directory for JSON/CSV/Markdown outputs",
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["tesseract", "paddleocr"],
        help="OCR provider names to evaluate",
    )
    parser.add_argument(
        "--max-edges",
        nargs="+",
        type=int,
        default=[1200, 1600, 2200],
        help="Working max-edge sizes in pixels",
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["fast", "enhanced"],
        choices=["fast", "enhanced"],
        help="Preprocessing profiles",
    )
    parser.add_argument(
        "--generate-corpus",
        action="store_true",
        default=True,
        help="Generate/refresh synthetic corpus before evaluation (default: true)",
    )
    parser.add_argument(
        "--no-generate-corpus",
        action="store_true",
        help="Skip corpus generation",
    )
    parser.add_argument(
        "--generate-corpus-only",
        action="store_true",
        help="Only generate corpus; skip OCR runs",
    )
    args = parser.parse_args(argv)

    corpus_dir = args.corpus_dir or default_corpus_root()
    results_dir = args.results_dir or (corpus_dir / "results")

    generate = args.generate_corpus and not args.no_generate_corpus
    if generate or args.generate_corpus_only:
        generate_corpus(corpus_dir, overwrite=True)
        print(f"Corpus ready at {corpus_dir}")

    if args.generate_corpus_only:
        return 0

    profiles = [OcrPreprocessProfile(p) for p in args.profiles]
    report = run_evaluation(
        corpus_dir,
        providers=list(args.providers),
        profiles=profiles,
        max_edges=list(args.max_edges),
    )

    json_path = results_dir / "ocr_evaluation.json"
    csv_path = results_dir / "ocr_evaluation.csv"
    md_path = results_dir / "ocr_evaluation_summary.md"
    write_json_report(report, json_path)
    write_csv_report(report, csv_path)
    summary = write_markdown_summary(report, md_path)

    print(summary.encode("ascii", errors="replace").decode("ascii"))
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
