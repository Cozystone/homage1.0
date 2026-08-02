from __future__ import annotations

from packages.tabularis_privacy.detectors import detect_field_sensitivities
from packages.tabularis_privacy.models import PrivacyPolicy, TabularRecord
from packages.tabularis_privacy.redaction import redact_record
from packages.tabularis_privacy.report import build_privacy_report
from packages.tabularis_privacy.risk import calculate_privacy_risk


def test_risk_and_utility_bounded() -> None:
    record = TabularRecord("r", {"email": "a@example.test", "age": 44, "diagnosis": "fixture"})
    sensitivities = detect_field_sensitivities(record)
    sanitized = redact_record(record, sensitivities)
    risk, utility, _ = calculate_privacy_risk([sanitized], sensitivities, PrivacyPolicy())
    assert 0.0 <= risk <= 1.0
    assert 0.0 <= utility <= 1.0


def test_safe_for_atlas_false_when_direct_identifier_remains() -> None:
    record = TabularRecord("r", {"email": "a@example.test"})
    sensitivities = detect_field_sensitivities(record)
    sanitized = redact_record(record, sensitivities, PrivacyPolicy(allow_direct_identifiers=True))
    report = build_privacy_report([sanitized], sensitivities, PrivacyPolicy(allow_direct_identifiers=True))
    assert report.safe_for_atlas is False


def test_safe_for_cloud_brain_false_for_raw_private_records() -> None:
    record = TabularRecord("r", {"diagnosis": "fixture"})
    sensitivities = detect_field_sensitivities(record)
    sanitized = redact_record(record, sensitivities)
    report = build_privacy_report([sanitized], sensitivities, PrivacyPolicy())
    assert sanitized.synthetic is False
    assert report.safe_for_cloud_brain is False

