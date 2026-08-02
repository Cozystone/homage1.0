from __future__ import annotations

from typing import Any

from packages.surface_brain.realization_planner import realize_answer


def route_verbalization(surface_plan: dict[str, Any], semantic_context: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    return realize_answer(surface_plan, semantic_context, **kwargs)
