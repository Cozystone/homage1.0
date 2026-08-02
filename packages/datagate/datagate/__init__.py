"""DataGate: deterministic rule-based quality gate for ATANOR.

Pure library ??no FastAPI or web framework imports. ``apps/api`` wraps it.
"""

from __future__ import annotations

from .config import DataGateConfig
from .filters import (
    BaseFilter,
    DuplicateHashFilter,
    LinkDensityFilter,
    MinLengthFilter,
    SpecialCharRatioFilter,
    default_filters,
)
from .hashing import content_hash, doc_id_for, normalize_text
from .io import discover_files, load_document, write_outputs
from .models import Document, DocumentMetadata, FilterResult, RunReport
from .runner import PipelineRunner
from .scoring import QualityScorer

__version__ = "0.1.0"

__all__ = [
    "DataGateConfig",
    "Document",
    "DocumentMetadata",
    "FilterResult",
    "RunReport",
    "QualityScorer",
    "PipelineRunner",
    "BaseFilter",
    "MinLengthFilter",
    "DuplicateHashFilter",
    "SpecialCharRatioFilter",
    "LinkDensityFilter",
    "default_filters",
    "normalize_text",
    "content_hash",
    "doc_id_for",
    "discover_files",
    "load_document",
    "write_outputs",
    "__version__",
]
