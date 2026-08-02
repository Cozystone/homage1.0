from __future__ import annotations

from typing import Any


def probe_strange_loop(payload: dict[str, Any], max_depth: int = 4) -> dict[str, Any]:
    """Measure bounded self-reference without claiming consciousness."""

    depth = 0
    cursor: Any = payload
    seen: set[int] = set()
    while isinstance(cursor, dict) and "self_reference" in cursor and depth < max_depth:
        marker = id(cursor)
        if marker in seen:
            break
        seen.add(marker)
        depth += 1
        cursor = cursor.get("self_reference")
    stopped = depth >= max_depth or not (isinstance(cursor, dict) and "self_reference" in cursor)
    return {
        "recursion_depth": depth,
        "stopped": stopped,
        "loop_complexity_score": min(1.0, depth / max_depth if max_depth else 1.0),
        "consciousness_claim": False,
    }
