from __future__ import annotations

from packages.tabularis_privacy.detectors import detect_field_sensitivities
from packages.tabularis_privacy.models import PrivacyPolicy, TabularRecord
from packages.tabularis_privacy.redaction import redact_record


def test_redaction_removes_raw_identifiers() -> None:
    record = TabularRecord("r", {"name": "Ada", "email": "ada@example.test", "phone": "555-0101"})
    sanitized = redact_record(record, detect_field_sensitivities(record), PrivacyPolicy())
    assert "Ada" not in sanitized.fields.values()
    assert "ada@example.test" not in sanitized.fields.values()
    assert "555-0101" not in sanitized.fields.values()
    assert sanitized.fields["email"] == "[REDACTED_EMAIL]"
    assert sanitized.raw_private_data_removed is True


def test_policy_can_mark_raw_remaining_when_allowed() -> None:
    record = TabularRecord("r", {"email": "ada@example.test"})
    sanitized = redact_record(record, detect_field_sensitivities(record), PrivacyPolicy(allow_direct_identifiers=True))
    assert sanitized.raw_private_data_removed is False

