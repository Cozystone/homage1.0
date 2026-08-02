"""Read-only Korean mojibake audit for Cloud Brain verified_store_v0."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
CGSR_ROOT = REPO_ROOT / "packages" / "cgsr"
if str(CGSR_ROOT) not in sys.path:
    sys.path.insert(0, str(CGSR_ROOT))

from cgsr.ingestion.korean_text_quality import detect_mojibake, validate_korean_sentence


DEFAULT_STORE = REPO_ROOT / "data" / "cloud_brain" / "verified_store_v0"
DEFAULT_AUDIT_DIR = REPO_ROOT / "data" / "audits"


COLLECTION_FILES = {
    "concepts": "concepts.jsonl",
    "relations": "relations.jsonl",
    "evidence": "evidence.jsonl",
    "case_frames": "case_frames.jsonl",
}


def utc_stamp() -> str:
    """Return a filesystem-safe UTC timestamp."""

    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    """Yield JSON rows from ``path`` without mutating the store."""

    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="strict") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                yield {"_json_error": str(exc), "_line": line_number, "_raw": line[:500]}
                continue
            row["_line"] = line_number
            yield row


def text_fields(collection: str, row: dict[str, Any]) -> Iterable[tuple[str, str, bool]]:
    """Yield ``(field_path, value, expect_korean)`` for audited text fields."""

    if collection == "concepts":
        yield "canonical_name", str(row.get("canonical_name") or ""), False
    elif collection == "relations":
        yield "relation", str(row.get("relation") or ""), False
        role = row.get("case_role") or {}
        if isinstance(role, dict):
            yield "case_role.marker", str(role.get("marker") or ""), True
            yield "case_role.head", str(role.get("head") or ""), False
    elif collection == "evidence":
        yield "text", str(row.get("text") or ""), True
        yield "title", str(row.get("title") or ""), False
        yield "source_id", str(row.get("source_id") or ""), False
    elif collection == "case_frames":
        yield "predicate", str(row.get("predicate") or ""), True
        yield "canonical_form", str(row.get("canonical_form") or ""), False
        for index, role in enumerate(row.get("case_roles") or []):
            if not isinstance(role, dict):
                continue
            yield f"case_roles[{index}].marker", str(role.get("marker") or ""), True
            yield f"case_roles[{index}].head", str(role.get("head") or ""), False
    provenance = row.get("provenance") or {}
    if isinstance(provenance, dict):
        yield "provenance.title", str(provenance.get("title") or ""), False
        yield "provenance.source_id", str(provenance.get("source_id") or ""), False


def audit_store(store: Path) -> dict[str, Any]:
    """Return corruption metrics for the verified store."""

    rows_by_collection: Counter[str] = Counter()
    corrupted_by_collection: Counter[str] = Counter()
    corrupted_by_field: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    suspicious_strings: Counter[str] = Counter()
    corrupted_samples: list[dict[str, Any]] = []
    clean_samples: list[dict[str, Any]] = []

    for collection, relative in COLLECTION_FILES.items():
        path = store / relative
        for row in read_jsonl(path):
            rows_by_collection[collection] += 1
            row_issues: list[dict[str, Any]] = []
            if "_json_error" in row:
                row_issues.append({"field": "_json", "issues": ["json_decode_error"], "sample": row.get("_raw", "")})
            for field, value, expect_korean in text_fields(collection, row):
                if not value:
                    continue
                quality = validate_korean_sentence(value, expect_korean=expect_korean)
                hard_issues = list(detect_mojibake(value))
                issues = list(dict.fromkeys([*hard_issues, *quality.issues]))
                if issues:
                    row_issues.append({"field": field, "issues": issues, "sample": value[:160]})
                    corrupted_by_field[f"{collection}.{field}"] += 1
                    issue_counts.update(issues)
                    suspicious_strings[value[:120]] += 1
            if row_issues:
                corrupted_by_collection[collection] += 1
                if len(corrupted_samples) < 50:
                    corrupted_samples.append(
                        {
                            "collection": collection,
                            "line": row.get("_line"),
                            "id": row.get("frame_id") or row.get("concept_id") or row.get("relation_id") or row.get("source_id"),
                            "issues": row_issues[:8],
                        }
                    )
            elif len(clean_samples) < 30:
                clean_samples.append(
                    {
                        "collection": collection,
                        "line": row.get("_line"),
                        "id": row.get("frame_id") or row.get("concept_id") or row.get("relation_id") or row.get("source_id"),
                        "sample": next((value[:160] for _, value, _ in text_fields(collection, row) if value), ""),
                    }
                )

    total_rows = sum(rows_by_collection.values())
    total_corrupted = sum(corrupted_by_collection.values())
    ratios = {
        key: round(corrupted_by_collection[key] / max(1, rows_by_collection[key]), 6)
        for key in COLLECTION_FILES
    }
    evidence_ratio = ratios.get("evidence", 0.0)
    case_frame_ratio = ratios.get("case_frames", 0.0)
    rebuild_recommended = evidence_ratio > 0.005 or case_frame_ratio > 0.005
    return {
        "audit_kind": "korean_mojibake_verified_store_v0",
        "store": str(store),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "read_only": True,
        "total_rows_scanned": total_rows,
        "total_corrupted_rows": total_corrupted,
        "corrupted_ratio": round(total_corrupted / max(1, total_rows), 6),
        "rows_by_collection": dict(rows_by_collection),
        "corrupted_by_collection": dict(corrupted_by_collection),
        "corrupted_ratio_by_collection": ratios,
        "top_fields_by_corruption": corrupted_by_field.most_common(50),
        "issue_counts": issue_counts.most_common(50),
        "top_50_suspicious_strings": suspicious_strings.most_common(50),
        "sample_corrupted_rows": corrupted_samples,
        "sample_clean_rows": clean_samples,
        "gate": {
            "case_frame_or_evidence_threshold": 0.005,
            "store_reusable": not rebuild_recommended,
            "rebuild_recommended": rebuild_recommended,
            "reason": (
                "case_frames_or_evidence_corruption_above_0.5_percent"
                if rebuild_recommended
                else "case_frames_and_evidence_corruption_at_or_below_0.5_percent"
            ),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render a compact Markdown audit report."""

    lines = [
        "# Korean Mojibake Audit",
        "",
        f"- Store: `{report['store']}`",
        f"- Generated: `{report['generated_at']}`",
        f"- Read only: `{report['read_only']}`",
        f"- Total rows scanned: `{report['total_rows_scanned']}`",
        f"- Total corrupted rows: `{report['total_corrupted_rows']}`",
        f"- Corrupted ratio: `{report['corrupted_ratio']}`",
        f"- Store reusable: `{report['gate']['store_reusable']}`",
        f"- Rebuild recommended: `{report['gate']['rebuild_recommended']}`",
        f"- Gate reason: `{report['gate']['reason']}`",
        "",
        "## Collection Ratios",
        "",
        "| collection | rows | corrupted | ratio |",
        "|---|---:|---:|---:|",
    ]
    for collection in COLLECTION_FILES:
        lines.append(
            f"| {collection} | {report['rows_by_collection'].get(collection, 0)} | "
            f"{report['corrupted_by_collection'].get(collection, 0)} | "
            f"{report['corrupted_ratio_by_collection'].get(collection, 0.0)} |"
        )
    lines.extend(["", "## Top Fields", ""])
    if report["top_fields_by_corruption"]:
        for field, count in report["top_fields_by_corruption"][:20]:
            lines.append(f"- `{field}`: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "## Top Issues", ""])
    if report["issue_counts"]:
        for issue, count in report["issue_counts"][:20]:
            lines.append(f"- `{issue}`: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "## Corrupted Samples", ""])
    if report["sample_corrupted_rows"]:
        for row in report["sample_corrupted_rows"][:10]:
            lines.append(f"- `{row['collection']}` line `{row.get('line')}` id `{row.get('id')}`: {row['issues'][:2]}")
    else:
        lines.append("- none")
    lines.extend(["", "## Clean Samples", ""])
    for row in report["sample_clean_rows"][:10]:
        lines.append(f"- `{row['collection']}` line `{row.get('line')}`: {row.get('sample')}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit verified_store_v0 for Korean mojibake without mutating it.")
    parser.add_argument("--store", default=str(DEFAULT_STORE))
    parser.add_argument("--out-dir", default=str(DEFAULT_AUDIT_DIR))
    args = parser.parse_args()

    store = Path(args.store)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = audit_store(store)
    stamp = utc_stamp()
    json_path = out_dir / f"korean_mojibake_audit_{stamp}.json"
    md_path = out_dir / f"korean_mojibake_audit_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "gate": report["gate"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
