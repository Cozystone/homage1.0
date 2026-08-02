"""Configuration for the DataGate quality pipeline.

All thresholds and input/output paths live here so the pipeline stays
deterministic and free of magic numbers. No FastAPI or web imports.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DataGateConfig(BaseModel):
    """Thresholds and filesystem paths for a DataGate run.

    Paths default to the repo-relative ``data/*`` layout described in the
    handoff, but tests (and the API) may override them with absolute paths.
    """

    input_dir: str = "data/raw"
    cleaned_dir: str = "data/cleaned"
    rejected_dir: str = "data/rejected"
    metadata_dir: str = "data/metadata"

    min_chars: int = Field(default=200, ge=0)
    max_special_char_ratio: float = Field(default=0.30, ge=0.0, le=1.0)
    max_link_density: float = Field(default=0.40, ge=0.0, le=1.0)
