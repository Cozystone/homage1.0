from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .detectors import detect_field_sensitivities
from .generalization import generalize_record
from .models import PrivacyPolicy, TabularRecord
from .redaction import redact_record
from .report import build_privacy_report
from .synthetic import create_aggregate_records


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "audits" / "tabularis_privacy"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sanitize(record: TabularRecord, policy: PrivacyPolicy) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    sensitivities = detect_field_sensitivities(record)
    redacted = redact_record(record, sensitivities, policy)
    generalized = generalize_record(redacted, sensitivities, policy)
    report = build_privacy_report([generalized], sensitivities, policy)
    return [item.to_dict() for item in sensitivities], generalized.to_dict(), report.to_dict()


def run_proof(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    policy = PrivacyPolicy()
    direct = TabularRecord("direct_fixture", {"name": "Ada Lovelace", "email": "ada@example.test", "phone": "555-0101", "generic_topic": "math"})
    quasi = TabularRecord("quasi_fixture", {"age": 34, "zipcode": "12345", "workplace": "Example Research Lab", "generic_topic": "research"})
    sensitive = TabularRecord("sensitive_fixture", {"income": 88000, "debt": 12000, "diagnosis": "fixture_condition", "generic_topic": "finance_health"})
    aggregate_records = [
        TabularRecord("agg_1", {"name": "Person A", "age": 31, "zipcode": "12345", "product_category": "books"}),
        TabularRecord("agg_2", {"name": "Person B", "age": 32, "zipcode": "12349", "product_category": "books"}),
        TabularRecord("agg_3", {"name": "Person C", "age": 41, "zipcode": "98765", "product_category": "tools"}),
    ]
    small_group = [
        TabularRecord("small_1", {"email": "one@example.test", "age": 77, "zipcode": "00001", "diagnosis": "fixture_condition"}),
    ]

    direct_sensitivities, direct_output, direct_report = _sanitize(direct, policy)
    quasi_sensitivities, quasi_output, quasi_report = _sanitize(quasi, policy)
    sensitive_sensitivities, sensitive_output, sensitive_report = _sanitize(sensitive, policy)
    aggregate_output = create_aggregate_records(aggregate_records, policy)
    aggregate_sensitivities = [item for record in aggregate_records for item in detect_field_sensitivities(record)]
    aggregate_report = build_privacy_report(aggregate_output, aggregate_sensitivities, policy)
    small_output = create_aggregate_records(small_group, policy)
    small_sensitivities = [item for record in small_group for item in detect_field_sensitivities(record)]
    small_report = build_privacy_report(small_output, small_sensitivities, policy)

    results = {
        "direct_identifier_redaction": {
            "sensitivities": direct_sensitivities,
            "sanitized": direct_output,
            "report": direct_report,
            "pass": direct_output["raw_private_data_removed"]
            and "[REDACTED_EMAIL]" in direct_output["fields"].values()
            and "[REDACTED_PHONE]" in direct_output["fields"].values()
            and "[REDACTED_NAME]" in direct_output["fields"].values(),
        },
        "quasi_identifier_generalization": {
            "sensitivities": quasi_sensitivities,
            "sanitized": quasi_output,
            "report": quasi_report,
            "pass": quasi_output["fields"]["age"] == "30-39" and quasi_output["fields"]["zipcode"] == "123**",
        },
        "sensitive_finance_health": {
            "sensitivities": sensitive_sensitivities,
            "sanitized": sensitive_output,
            "report": sensitive_report,
            "pass": "diagnosis" in sensitive_report["sensitive_fields"] and sensitive_report["safe_for_cloud_brain"] is False,
        },
        "synthetic_aggregate": {
            "records": [record.to_dict() for record in aggregate_output],
            "report": aggregate_report.to_dict(),
            "pass": all(record.synthetic and record.raw_private_data_removed for record in aggregate_output),
        },
        "unsafe_small_group": {
            "records": [record.to_dict() for record in small_output],
            "report": small_report.to_dict(),
            "pass": small_report.safe_for_atlas is False and any("K-anonymity" in note for note in small_report.notes),
        },
    }
    results["summary"] = {key: value["pass"] for key, value in results.items()}
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    json_path = output_dir / f"tabularis_proof_{timestamp}.json"
    md_path = output_dir / f"tabularis_proof_{timestamp}.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_proof_markdown(results), encoding="utf-8")
    results["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return results


def _proof_markdown(results: dict[str, Any]) -> str:
    lines = ["# Tabularis Privacy Shield Proof", ""]
    for key, passed in results["summary"].items():
        lines.append(f"- {key}: `{passed}`")
    lines.append("")
    lines.append("This proof uses deterministic fixture data only and does not claim perfect anonymity.")
    lines.append("Generated proof output is audit data and should not be committed.")
    return "\n".join(lines) + "\n"


def main() -> None:
    print(json.dumps(run_proof(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

