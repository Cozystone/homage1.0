from __future__ import annotations

from collections import Counter
from typing import Any

from .models import FieldSensitivity, PrivacyPolicy, SanitizedRecord


def _fields_by_type(sensitivities: list[FieldSensitivity], sensitivity_type: str) -> list[str]:
    return sorted({item.field_name for item in sensitivities if item.sensitivity_type == sensitivity_type})


def estimate_k_anonymity(records: list[SanitizedRecord], quasi_fields: list[str]) -> int | None:
    if not records or not quasi_fields:
        return None
    groups: Counter[tuple[Any, ...]] = Counter()
    for record in records:
        groups[tuple(record.fields.get(field) for field in quasi_fields)] += 1
    return min(groups.values()) if groups else None


def calculate_privacy_risk(
    records: list[SanitizedRecord],
    sensitivities: list[FieldSensitivity],
    policy: PrivacyPolicy | None = None,
) -> tuple[float, float, int | None]:
    """Return privacy risk, utility score, and k-anonymity estimate."""

    active_policy = policy or PrivacyPolicy()
    direct_fields = _fields_by_type(sensitivities, "direct_identifier")
    quasi_fields = _fields_by_type(sensitivities, "quasi_identifier")
    sensitive_fields = _fields_by_type(sensitivities, "sensitive_attribute")
    k_estimate = estimate_k_anonymity(records, quasi_fields)

    remaining_direct = 0
    for record in records:
        for field in direct_fields:
            value = record.fields.get(field)
            if value is not None and not str(value).startswith("[REDACTED_"):
                remaining_direct += 1

    raw_private_remaining = any(not record.raw_private_data_removed for record in records)
    synthetic_all = bool(records) and all(record.synthetic for record in records)
    risk = 0.0
    risk += min(0.45, 0.15 * remaining_direct)
    risk += min(0.25, 0.04 * len(quasi_fields))
    risk += min(0.2, 0.05 * len(sensitive_fields))
    if raw_private_remaining:
        risk += 0.2
    if k_estimate is not None and k_estimate < active_policy.min_k_anonymity:
        risk += 0.2
    if synthetic_all:
        risk -= 0.2
    privacy_risk = max(0.0, min(1.0, round(risk, 4)))

    if not records:
        return privacy_risk, 0.0, k_estimate
    total_fields = sum(len(record.fields) for record in records)
    redacted_fields = sum(1 for record in records for value in record.fields.values() if str(value).startswith("[REDACTED_"))
    utility = 0.25
    if total_fields:
        utility += 0.5 * (1.0 - (redacted_fields / total_fields))
    if all(record.raw_private_data_removed for record in records):
        utility += 0.1
    if synthetic_all:
        utility += 0.1
    utility_score = max(0.0, min(1.0, round(utility, 4)))
    return privacy_risk, utility_score, k_estimate

