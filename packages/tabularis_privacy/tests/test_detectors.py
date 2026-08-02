from __future__ import annotations

from packages.tabularis_privacy.detectors import detect_field_sensitivities
from packages.tabularis_privacy.models import TabularRecord


def _types(record: TabularRecord) -> dict[str, str]:
    return {item.field_name: item.sensitivity_type for item in detect_field_sensitivities(record)}


def test_direct_identifier_detection() -> None:
    types = _types(TabularRecord("r", {"email": "a@example.test", "phone": "555", "name": "Ada"}))
    assert types["email"] == "direct_identifier"
    assert types["phone"] == "direct_identifier"
    assert types["name"] == "direct_identifier"


def test_quasi_identifier_detection() -> None:
    types = _types(TabularRecord("r", {"age": 33, "zipcode": "12345", "workplace": "Lab"}))
    assert types["age"] == "quasi_identifier"
    assert types["zipcode"] == "quasi_identifier"
    assert types["workplace"] == "quasi_identifier"


def test_sensitive_and_public_detection() -> None:
    types = _types(TabularRecord("r", {"diagnosis": "fixture", "income": 10, "generic_topic": "books"}))
    assert types["diagnosis"] == "sensitive_attribute"
    assert types["income"] == "sensitive_attribute"
    assert types["generic_topic"] == "public_attribute"

