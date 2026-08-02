from __future__ import annotations

from packages.spark_chamber.strange_loop import probe_strange_loop


def test_strange_loop_stops_before_infinite_recursion() -> None:
    payload: dict[str, object] = {}
    payload["self_reference"] = payload
    result = probe_strange_loop(payload, max_depth=3)
    assert result["recursion_depth"] <= 3
    assert 0.0 <= result["loop_complexity_score"] <= 1.0
    assert result["consciousness_claim"] is False
