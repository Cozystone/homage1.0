from __future__ import annotations

from packages.spark_chamber.contradiction import detect_contradictions


def test_contradiction_pressure_bounded() -> None:
    result = detect_contradictions({"contradictions": [{"claim": "A", "negates": "A"}]})
    assert 0.0 <= result["pressure"] <= 1.0
    assert result["factuality_claim"] is False
    assert result["contradictions"]
