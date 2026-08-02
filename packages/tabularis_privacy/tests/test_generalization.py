from __future__ import annotations

from packages.tabularis_privacy.detectors import detect_field_sensitivities
from packages.tabularis_privacy.generalization import generalize_record
from packages.tabularis_privacy.models import PrivacyPolicy, TabularRecord
from packages.tabularis_privacy.redaction import redact_record


def test_generalization_preserves_schema_with_lower_specificity() -> None:
    record = TabularRecord("r", {"age": 34, "birth_year": 1984, "zipcode": "12345", "workplace": "Research Lab"})
    sensitivities = detect_field_sensitivities(record)
    sanitized = generalize_record(redact_record(record, sensitivities), sensitivities, PrivacyPolicy())
    assert set(sanitized.fields) == set(record.fields)
    assert sanitized.fields["age"] == "30-39"
    assert sanitized.fields["birth_year"] == "1980s"
    assert sanitized.fields["zipcode"] == "123**"
    assert sanitized.fields["workplace"] == "generalized_workplace"

