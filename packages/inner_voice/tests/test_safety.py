from __future__ import annotations

from packages.inner_voice.safety import has_forbidden_claim, sanitize_monologue_text


def test_private_payload_redacted() -> None:
    text = sanitize_monologue_text("token: sk-secretsecretsecret payload-vault://abc")

    assert "sk-secret" not in text
    assert "payload-vault://" not in text
    assert "[redacted]" in text


def test_forbidden_claim_detected_and_rewritten() -> None:
    assert has_forbidden_claim("real consciousness")
    assert "real consciousness" not in sanitize_monologue_text("real consciousness")
