from __future__ import annotations

from .models import FieldSensitivity, PrivacyPolicy, PrivacyRiskReport, SanitizedRecord
from .risk import calculate_privacy_risk


def _fields_by_type(sensitivities: list[FieldSensitivity], sensitivity_type: str) -> list[str]:
    return sorted({item.field_name for item in sensitivities if item.sensitivity_type == sensitivity_type})


def build_privacy_report(
    records: list[SanitizedRecord],
    sensitivities: list[FieldSensitivity],
    policy: PrivacyPolicy | None = None,
) -> PrivacyRiskReport:
    """Build a reviewable proof-only privacy report."""

    active_policy = policy or PrivacyPolicy()
    direct_fields = _fields_by_type(sensitivities, "direct_identifier")
    quasi_fields = _fields_by_type(sensitivities, "quasi_identifier")
    sensitive_fields = _fields_by_type(sensitivities, "sensitive_attribute")
    privacy_risk, utility_score, k_estimate = calculate_privacy_risk(records, sensitivities, active_policy)
    remaining_direct = any(
        record.fields.get(field) is not None and not str(record.fields.get(field)).startswith("[REDACTED_")
        for record in records
        for field in direct_fields
    )
    raw_removed = all(record.raw_private_data_removed for record in records)
    synthetic_all = bool(records) and all(record.synthetic for record in records)
    small_group = k_estimate is not None and k_estimate < active_policy.min_k_anonymity

    safe_for_atlas = not remaining_direct and raw_removed and privacy_risk <= active_policy.max_privacy_risk and not small_group
    safe_for_mirofish = safe_for_atlas and (not sensitive_fields or synthetic_all)
    safe_for_cloud_brain = synthetic_all and safe_for_atlas and not remaining_direct

    notes: list[str] = []
    if sensitive_fields:
        notes.append("Sensitive attributes require caution; aggregate-only handling is recommended.")
    if small_group:
        notes.append("K-anonymity estimate is below policy threshold.")
    if synthetic_all:
        notes.append("Output is proof-only aggregate/synthetic data.")
    if not remaining_direct:
        notes.append("No raw direct identifiers remain in sanitized output.")

    limitations = [
        "Proof-only privacy shield, not a production privacy guarantee.",
        "Does not claim perfect anonymity.",
        "Synthetic output is deterministic aggregate proof data, not statistically rigorous synthetic data.",
    ]
    return PrivacyRiskReport(
        total_records=len(records),
        direct_identifier_fields=direct_fields,
        quasi_identifier_fields=quasi_fields,
        sensitive_fields=sensitive_fields,
        privacy_risk=privacy_risk,
        utility_score=utility_score,
        k_anonymity_estimate=k_estimate,
        safe_for_atlas=safe_for_atlas,
        safe_for_mirofish=safe_for_mirofish,
        safe_for_cloud_brain=safe_for_cloud_brain,
        notes=notes,
        limitations=limitations,
    )

