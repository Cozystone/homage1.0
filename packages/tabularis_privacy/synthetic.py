from __future__ import annotations

from collections import Counter
from typing import Any

from .detectors import detect_field_sensitivities
from .generalization import generalize_record
from .models import PrivacyPolicy, SanitizedRecord, TabularRecord
from .redaction import redact_record


def create_aggregate_records(
    records: list[TabularRecord],
    policy: PrivacyPolicy | None = None,
) -> list[SanitizedRecord]:
    """Create deterministic aggregate records without raw direct identifiers.

    This is proof-only synthetic output. It is not a statistical synthetic-data
    guarantee and does not claim perfect anonymity.
    """

    active_policy = policy or PrivacyPolicy()
    sanitized: list[SanitizedRecord] = []
    for record in records:
        sensitivities = detect_field_sensitivities(record)
        redacted = redact_record(record, sensitivities, active_policy)
        sanitized.append(generalize_record(redacted, sensitivities, active_policy))

    groups: Counter[tuple[tuple[str, Any], ...]] = Counter()
    for record in sanitized:
        group_fields = {
            key: value
            for key, value in record.fields.items()
            if not str(value).startswith("[REDACTED_") and key not in {"diagnosis", "medication", "private_note", "debt", "bank_balance"}
        }
        groups[tuple(sorted(group_fields.items()))] += 1

    result: list[SanitizedRecord] = []
    for index, (items, count) in enumerate(sorted(groups.items(), key=lambda item: (item[0], item[1])), start=1):
        fields = dict(items)
        fields["record_count"] = count
        result.append(
            SanitizedRecord(
                record_id=f"synthetic_aggregate_{index}",
                fields=fields,
                transformations=[{"action": "aggregate_synthetic", "source_records": count}],
                raw_private_data_removed=True,
                synthetic=True,
                metadata={
                    "limitations": [
                        "proof_only_aggregate",
                        "not_statistically_equivalent",
                        "not_perfect_anonymity",
                    ]
                },
            )
        )
    return result

