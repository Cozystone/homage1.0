from __future__ import annotations

from typing import Any

from .detectors import sensitivity_map
from .models import FieldSensitivity, PrivacyPolicy, SanitizedRecord, TabularRecord


PLACEHOLDERS = {
    "email": "[REDACTED_EMAIL]",
    "phone": "[REDACTED_PHONE]",
    "name": "[REDACTED_NAME]",
    "full_name": "[REDACTED_NAME]",
    "address": "[REDACTED_ADDRESS]",
    "ssn": "[REDACTED_DIRECT_IDENTIFIER]",
    "resident_id": "[REDACTED_DIRECT_IDENTIFIER]",
    "passport": "[REDACTED_DIRECT_IDENTIFIER]",
    "account_number": "[REDACTED_DIRECT_IDENTIFIER]",
    "card_number": "[REDACTED_DIRECT_IDENTIFIER]",
    "exact_user_id": "[REDACTED_DIRECT_IDENTIFIER]",
}


def _key(field_name: str) -> str:
    return field_name.strip().lower().replace("-", "_").replace(" ", "_")


def redact_record(
    record: TabularRecord,
    sensitivities: list[FieldSensitivity],
    policy: PrivacyPolicy | None = None,
) -> SanitizedRecord:
    """Redact direct identifiers while preserving the field names."""

    active_policy = policy or PrivacyPolicy()
    by_field = sensitivity_map(sensitivities)
    fields: dict[str, Any] = dict(record.fields)
    transformations: list[dict[str, Any]] = []
    raw_removed = True

    for field_name, sensitivity in by_field.items():
        if sensitivity.sensitivity_type != "direct_identifier":
            continue
        if active_policy.allow_direct_identifiers or not active_policy.redact_direct_identifiers:
            raw_removed = False
            transformations.append({"field": field_name, "action": "kept_direct_identifier"})
            continue
        placeholder = PLACEHOLDERS.get(_key(field_name), "[REDACTED_DIRECT_IDENTIFIER]")
        fields[field_name] = placeholder
        transformations.append({"field": field_name, "action": "redacted", "placeholder": placeholder})

    return SanitizedRecord(
        record_id=record.record_id,
        fields=fields,
        transformations=transformations,
        raw_private_data_removed=raw_removed,
        synthetic=False,
        metadata={"source_label": record.source_label, "is_private": record.is_private},
    )

