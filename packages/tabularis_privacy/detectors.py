from __future__ import annotations

from .models import FieldSensitivity, TabularRecord


DIRECT_IDENTIFIER_FIELDS = {
    "name",
    "full_name",
    "email",
    "phone",
    "address",
    "ssn",
    "resident_id",
    "passport",
    "account_number",
    "card_number",
    "exact_user_id",
}

QUASI_IDENTIFIER_FIELDS = {
    "age",
    "birth_year",
    "birthday",
    "birthdate",
    "zipcode",
    "zip_code",
    "region",
    "workplace",
    "school",
    "job_title",
    "gender",
    "rare_category",
    "location",
}

SENSITIVE_ATTRIBUTE_FIELDS = {
    "health",
    "diagnosis",
    "medication",
    "income",
    "debt",
    "bank_balance",
    "political_view",
    "religion",
    "biometric",
    "private_note",
}

PUBLIC_ATTRIBUTE_FIELDS = {
    "product_category",
    "generic_topic",
    "public_count",
    "aggregate_label",
}


def _normalize(field_name: str) -> str:
    return field_name.strip().lower().replace("-", "_").replace(" ", "_")


def detect_field_sensitivities(record: TabularRecord) -> list[FieldSensitivity]:
    """Classify fields with deterministic local constants only."""

    result: list[FieldSensitivity] = []
    for field_name in sorted(record.fields):
        normalized = _normalize(field_name)
        if normalized in DIRECT_IDENTIFIER_FIELDS:
            result.append(FieldSensitivity(field_name, "direct_identifier", 0.99, ["field_name:direct_identifier"]))
        elif normalized in QUASI_IDENTIFIER_FIELDS:
            result.append(FieldSensitivity(field_name, "quasi_identifier", 0.85, ["field_name:quasi_identifier"]))
        elif normalized in SENSITIVE_ATTRIBUTE_FIELDS:
            result.append(FieldSensitivity(field_name, "sensitive_attribute", 0.9, ["field_name:sensitive_attribute"]))
        elif normalized in PUBLIC_ATTRIBUTE_FIELDS:
            result.append(FieldSensitivity(field_name, "public_attribute", 0.8, ["field_name:public_attribute"]))
        else:
            result.append(FieldSensitivity(field_name, "unknown", 0.25, ["field_name:unknown"]))
    return result


def sensitivity_map(sensitivities: list[FieldSensitivity]) -> dict[str, FieldSensitivity]:
    return {item.field_name: item for item in sensitivities}

