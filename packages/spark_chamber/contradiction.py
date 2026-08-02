from __future__ import annotations

from typing import Any


def detect_contradictions(fixture: dict[str, Any]) -> dict[str, Any]:
    """Detect symbolic contradiction markers in a fixture only."""

    contradictions = list(fixture.get("contradictions", []))
    pairs = []
    for item in contradictions:
        if isinstance(item, dict) and item.get("claim") == item.get("negates"):
            pairs.append(item)
    pressure = min(1.0, 0.25 * len(pairs) + 0.1 * len(contradictions))
    return {"contradictions": pairs, "pressure": pressure, "factuality_claim": False}
