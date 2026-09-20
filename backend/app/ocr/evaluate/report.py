"""
Human-readable and machine-readable OCR evaluation report writers.

Architectural responsibility: persist benchmark outputs for review and ADRs.
"""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

from app.ocr.evaluate.runner import EvaluationReport, RunRecord


def write_json_report(report: EvaluationReport, path: Path) -> None:
    """Write full machine-readable JSON results."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")


def write_csv_report(report: EvaluationReport, path: Path) -> None:
    """Write flattened CSV of run records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not report.records:
        path.write_text("", encoding="utf-8")
        return
    expanded = []
    for record in report.records:
        row = asdict_flat(record)
        expanded.append(row)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(expanded[0].keys()))
        writer.writeheader()
        writer.writerows(expanded)


def asdict_flat(record: RunRecord) -> dict:
    """Flatten nested field_recovery for CSV."""
    base = {
        "fixture_id": record.fixture_id,
        "category": record.category,
        "provider": record.provider,
        "preprocess_profile": record.preprocess_profile,
        "max_edge_px": record.max_edge_px,
        "success": record.success,
        "failure_kind": record.failure_kind,
        "failure_message": record.failure_message,
        "preprocessing_time_ms": record.preprocessing_time_ms,
        "ocr_time_ms": record.ocr_time_ms,
        "total_pipeline_time_ms": record.total_pipeline_time_ms,
        "character_error_rate": record.character_error_rate,
        "fields_recovered_count": record.fields_recovered_count,
        "fields_total": record.fields_total,
        "has_bounding_boxes": record.has_bounding_boxes,
        "word_count": record.word_count,
        "ocr_text_preview": record.ocr_text_preview.replace("\n", " | "),
    }
    for key, value in record.field_recovery.items():
        base[f"field_{key}"] = value
    return base


def write_markdown_summary(report: EvaluationReport, path: Path) -> str:
    """Write and return a human-readable Markdown summary with recommendation inputs."""
    lines: list[str] = []
    lines.append("# OCR Evaluation Summary")
    lines.append("")
    lines.append(f"Generated: `{report.generated_at}`")
    lines.append("")
    lines.append("## Environment")
    for key, value in report.environment.items():
        lines.append(f"- **{key}:** {value}")
    lines.append("")
    lines.append("## Providers")
    lines.append(f"- Requested: {', '.join(report.providers_requested) or '(none)'}")
    lines.append(f"- Available: {', '.join(report.providers_available) or '(none)'}")
    if report.providers_unavailable:
        lines.append("- Unavailable:")
        for name, reason in report.providers_unavailable.items():
            lines.append(f"  - `{name}`: {reason}")
    lines.append("")
    lines.append(
        f"Profiles: {', '.join(report.preprocess_profiles)}; "
        f"max edges: {', '.join(str(x) for x in report.max_edge_sizes)}",
    )
    lines.append("")

    if not report.records:
        lines.append("No evaluation records were produced.")
        text = "\n".join(lines) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return text

    lines.append("## Configuration leaderboard (by mean field recovery, then latency)")
    lines.append("")
    lines.append(
        "| Provider | Preprocess | Max edge | Mean fields/5 | Mean CER | "
        "Median total ms | p95 total ms | BBox rate | Success rate |",
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")

    groups: dict[tuple[str, str, int], list[RunRecord]] = defaultdict(list)
    for record in report.records:
        key = (record.provider, record.preprocess_profile, record.max_edge_px)
        groups[key].append(record)

    ranked = []
    for key, rows in groups.items():
        ranked.append((key, _aggregate(rows)))
    ranked.sort(
        key=lambda item: (
            -item[1]["mean_fields"],
            item[1]["median_total_ms"],
            item[1]["mean_cer"],
        ),
    )

    for (provider, profile, edge), stats in ranked:
        lines.append(
            f"| {provider} | {profile} | {edge} | "
            f"{stats['mean_fields']:.2f} | {stats['mean_cer']:.3f} | "
            f"{stats['median_total_ms']:.0f} | {stats['p95_total_ms']:.0f} | "
            f"{stats['bbox_rate']:.2f} | {stats['success_rate']:.2f} |",
        )

    lines.append("")
    lines.append("## Field recovery by provider (all configs pooled)")
    lines.append("")
    by_provider: dict[str, list[RunRecord]] = defaultdict(list)
    for record in report.records:
        by_provider[record.provider].append(record)
    field_names = [
        "brand_name",
        "class_type",
        "alcohol_content_abv",
        "net_contents",
        "government_health_warning",
    ]
    header = "| Provider | " + " | ".join(field_names) + " |"
    lines.append(header)
    lines.append("|---|" + "|".join(["---:"] * len(field_names)) + "|")
    for provider, rows in sorted(by_provider.items()):
        rates = []
        for fname in field_names:
            hits = sum(1 for r in rows if r.field_recovery.get(fname))
            rates.append(f"{hits / max(1, len(rows)):.2f}")
        lines.append(f"| {provider} | " + " | ".join(rates) + " |")

    lines.append("")
    lines.append("## FAST vs ENHANCED (pooled)")
    lines.append("")
    for profile in report.preprocess_profiles:
        rows = [r for r in report.records if r.preprocess_profile == profile]
        stats = _aggregate(rows)
        lines.append(
            f"- **{profile}:** mean fields={stats['mean_fields']:.2f}, "
            f"median total={stats['median_total_ms']:.0f} ms, "
            f"mean CER={stats['mean_cer']:.3f}",
        )

    lines.append("")
    lines.append("## Working resolution (pooled)")
    lines.append("")
    for edge in report.max_edge_sizes:
        rows = [r for r in report.records if r.max_edge_px == edge]
        stats = _aggregate(rows)
        lines.append(
            f"- **{edge}px:** mean fields={stats['mean_fields']:.2f}, "
            f"median total={stats['median_total_ms']:.0f} ms",
        )

    lines.append("")
    lines.append("## Failure cases")
    lines.append("")
    failures = [r for r in report.records if not r.success]
    if not failures:
        lines.append("No hard failures recorded.")
    else:
        by_kind: dict[str, int] = defaultdict(int)
        for row in failures:
            by_kind[row.failure_kind or "unknown"] += 1
        for kind, count in sorted(by_kind.items(), key=lambda x: -x[1]):
            lines.append(f"- `{kind}`: {count}")

    lines.append("")
    lines.append("## Evidence-based recommendation notes")
    lines.append("")
    if ranked:
        best = ranked[0]
        (provider, profile, edge), stats = best
        lines.append(
            f"Top configuration by field recovery then latency: "
            f"**{provider} / {profile} / {edge}px** "
            f"(mean fields {stats['mean_fields']:.2f}/5, "
            f"median {stats['median_total_ms']:.0f} ms).",
        )
        # Prefer configs under ~2s median for OCR stage budget guidance
        budget_ok = [
            item
            for item in ranked
            if item[1]["median_total_ms"] <= 2000 and item[1]["mean_fields"] >= 3.0
        ]
        if budget_ok:
            (p2, pr2, e2), s2 = budget_ok[0]
            lines.append(
                f"Best config with median total <= 2000 ms and mean fields >= 3.0: "
                f"**{p2} / {pr2} / {e2}px** "
                f"(mean fields {s2['mean_fields']:.2f}/5, "
                f"median {s2['median_total_ms']:.0f} ms).",
            )
        else:
            lines.append(
                "No configuration met both median <= 2000 ms and mean fields >= 3.0 "
                "on this corpus/environment.",
            )
    lines.append("")
    lines.append(
        "Final recommendation must weigh field recovery, latency headroom under the "
        "5-second end-to-end target, offline practicality, and maintainability. "
        "See `docs/OCR_EVALUATION.md` after results are interpreted.",
    )
    lines.append("")

    text = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def _aggregate(rows: list[RunRecord]) -> dict[str, float]:
    if not rows:
        return {
            "mean_fields": 0.0,
            "mean_cer": 1.0,
            "median_total_ms": 0.0,
            "p95_total_ms": 0.0,
            "bbox_rate": 0.0,
            "success_rate": 0.0,
        }
    totals = [r.total_pipeline_time_ms for r in rows]
    cers = [r.character_error_rate for r in rows if r.character_error_rate is not None]
    return {
        "mean_fields": statistics.fmean(r.fields_recovered_count for r in rows),
        "mean_cer": statistics.fmean(cers) if cers else 1.0,
        "median_total_ms": statistics.median(totals),
        "p95_total_ms": _percentile(totals, 95),
        "bbox_rate": sum(1 for r in rows if r.has_bounding_boxes) / len(rows),
        "success_rate": sum(1 for r in rows if r.success) / len(rows),
    }


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight
