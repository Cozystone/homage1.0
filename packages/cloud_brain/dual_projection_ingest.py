from __future__ import annotations

from typing import Any

from packages.surface_brain.dual_projection import ingest_source_sentence_dual_projection


def ingest_dual_projection(sentence: str | dict[str, Any]) -> dict[str, Any]:
    return ingest_source_sentence_dual_projection(sentence)
