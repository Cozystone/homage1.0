from __future__ import annotations

from typing import Any

from packages.surface_brain.realization_planner import plan_speech


def plan_surface_speech(query: str, semantic_context: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    return plan_speech(query, semantic_context, **kwargs)
