from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


SensitivityType = Literal[
    "direct_identifier",
    "quasi_identifier",
    "sensitive_attribute",
    "public_attribute",
    "unknown",
]


def _unit_interval(name: str, value: float) -> float:
    numeric = float(value)
    if numeric < 0.0 or numeric > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return numeric


@dataclass(frozen=True)
class FieldSensitivity:
    field_name: str
    sensitivity_type: SensitivityType
    confidence: float
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.field_name:
            raise ValueError("field_name is required")
        object.__setattr__(self, "confidence", _unit_interval("confidence", self.confidence))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PrivacyPolicy:
    allow_direct_identifiers: bool = False
    allow_private_raw_export: bool = False
    min_k_anonymity: int = 5
    redact_direct_identifiers: bool = True
    generalize_quasi_identifiers: bool = True
    synthetic_output_only: bool = True
    max_privacy_risk: float = 0.25

    def __post_init__(self) -> None:
        if self.min_k_anonymity < 1:
            raise ValueError("min_k_anonymity must be at least 1")
        object.__setattr__(self, "max_privacy_risk", _unit_interval("max_privacy_risk", self.max_privacy_risk))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TabularRecord:
    record_id: str
    fields: dict[str, Any]
    source_label: str | None = None
    is_private: bool = True

    def __post_init__(self) -> None:
        if not self.record_id:
            raise ValueError("record_id is required")
        if not isinstance(self.fields, dict):
            raise ValueError("fields must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SanitizedRecord:
    record_id: str
    fields: dict[str, Any]
    transformations: list[dict[str, Any]]
    raw_private_data_removed: bool
    synthetic: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.record_id:
            raise ValueError("record_id is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PrivacyRiskReport:
    total_records: int
    direct_identifier_fields: list[str]
    quasi_identifier_fields: list[str]
    sensitive_fields: list[str]
    privacy_risk: float
    utility_score: float
    k_anonymity_estimate: int | None
    safe_for_atlas: bool
    safe_for_mirofish: bool
    safe_for_cloud_brain: bool
    notes: list[str]
    limitations: list[str]

    def __post_init__(self) -> None:
        if self.total_records < 0:
            raise ValueError("total_records must be non-negative")
        object.__setattr__(self, "privacy_risk", _unit_interval("privacy_risk", self.privacy_risk))
        object.__setattr__(self, "utility_score", _unit_interval("utility_score", self.utility_score))
        if self.k_anonymity_estimate is not None and self.k_anonymity_estimate < 0:
            raise ValueError("k_anonymity_estimate must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

