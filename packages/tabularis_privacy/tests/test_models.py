from __future__ import annotations

import pytest

from packages.tabularis_privacy.models import FieldSensitivity, PrivacyPolicy, PrivacyRiskReport, TabularRecord


def test_model_validation() -> None:
    assert FieldSensitivity("email", "direct_identifier", 1.0).confidence == 1.0
    with pytest.raises(ValueError):
        FieldSensitivity("email", "direct_identifier", 1.5)
    with pytest.raises(ValueError):
        PrivacyPolicy(min_k_anonymity=0)
    record = TabularRecord("r1", {"email": "fixture@example.test"})
    assert record.record_id == "r1"


def test_report_bounds() -> None:
    report = PrivacyRiskReport(0, [], [], [], 0.1, 0.9, None, True, False, False, [], [])
    assert report.privacy_risk == 0.1
    with pytest.raises(ValueError):
        PrivacyRiskReport(0, [], [], [], 1.2, 0.9, None, True, False, False, [], [])

