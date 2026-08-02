from __future__ import annotations

from typing import Any

from packages.surface_brain.extraction import extract_surface_projection


def project_surface(sentence: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(sentence, str):
        return extract_surface_projection({"text": sentence})
    return extract_surface_projection(sentence)
