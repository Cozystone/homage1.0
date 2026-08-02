from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .detectors import sensitivity_map
from .models import FieldSensitivity, PrivacyPolicy, SanitizedRecord


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _generalize_age(value: Any) -> str:
    age = _as_int(value)
    if age is None or age < 0:
        return "unknown_age"
    lower = (age // 10) * 10
    upper = lower + 9
    return f"{lower}-{upper}"


def _generalize_year(value: Any) -> str:
    year = _as_int(value)
    if year is None:
        return "unknown_decade"
    decade = (year // 10) * 10
    return f"{decade}s"


def _generalize_zipcode(value: Any) -> str:
    text = str(value)
    return text[:3] + "**" if len(text) >= 3 else "zip_region"


def _generalize_date(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return f"{value.year:04d}-{value.month:02d}"
    text = str(value)
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]
    return "date_bucket"


def _generalize_income(value: Any) -> str:
    amount = _as_int(value)
    if amount is None:
        return "income_bucket_unknown"
    if amount < 30000:
        return "income_under_30k"
    if amount < 70000:
        return "income_30k_70k"
    if amount < 150000:
        return "income_70k_150k"
    return "income_150k_plus"


def _normalize(field_name: str) -> str:
    return field_name.strip().lower().replace("-", "_").replace(" ", "_")


def _generalize_field(field_name: str, value: Any) -> Any:
    normalized = _normalize(field_name)
    if normalized == "age":
        return _generalize_age(value)
    if normalized == "birth_year":
        return _generalize_year(value)
    if normalized in {"birthday", "birthdate"}:
        return _generalize_date(value)
    if normalized in {"zipcode", "zip_code"}:
        return _generalize_zipcode(value)
    if normalized == "income":
        return _generalize_income(value)
    if normalized in {"region", "location"}:
        text = str(value).split(",")[0].strip()
        return text if text else "broad_region"
    if normalized in {"workplace", "school", "job_title"}:
        return f"generalized_{normalized}"
    if normalized == "rare_category":
        return "other"
    return "generalized_value"


def generalize_record(
    record: SanitizedRecord,
    sensitivities: list[FieldSensitivity],
    policy: PrivacyPolicy | None = None,
) -> SanitizedRecord:
    """Generalize quasi-identifiers deterministically."""

    active_policy = policy or PrivacyPolicy()
    by_field = sensitivity_map(sensitivities)
    fields = dict(record.fields)
    transformations = list(record.transformations)

    if not active_policy.generalize_quasi_identifiers:
        return record

    for field_name, sensitivity in by_field.items():
        if sensitivity.sensitivity_type == "quasi_identifier" and field_name in fields:
            before = fields[field_name]
            fields[field_name] = _generalize_field(field_name, before)
            transformations.append({"field": field_name, "action": "generalized", "from_type": type(before).__name__})
        if sensitivity.sensitivity_type == "sensitive_attribute" and _normalize(field_name) == "income" and field_name in fields:
            before = fields[field_name]
            fields[field_name] = _generalize_income(before)
            transformations.append({"field": field_name, "action": "generalized_sensitive_income", "from_type": type(before).__name__})

    return SanitizedRecord(
        record_id=record.record_id,
        fields=fields,
        transformations=transformations,
        raw_private_data_removed=record.raw_private_data_removed,
        synthetic=record.synthetic,
        metadata=dict(record.metadata),
    )

