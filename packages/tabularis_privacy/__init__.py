"""Proof-only Tabularis privacy shield package.

This package is intentionally isolated from Cloud Brain runtime, candidate
learning, API routes, UI code, production stores, candidate stores, and Local
Brain databases.
"""

from .detectors import detect_field_sensitivities
from .generalization import generalize_record
from .models import (
    FieldSensitivity,
    PrivacyPolicy,
    PrivacyRiskReport,
    SanitizedRecord,
    TabularRecord,
)
from .redaction import redact_record
from .report import build_privacy_report
from .risk import calculate_privacy_risk
from .synthetic import create_aggregate_records

__all__ = [
    "FieldSensitivity",
    "PrivacyPolicy",
    "PrivacyRiskReport",
    "SanitizedRecord",
    "TabularRecord",
    "build_privacy_report",
    "calculate_privacy_risk",
    "create_aggregate_records",
    "detect_field_sensitivities",
    "generalize_record",
    "redact_record",
]

