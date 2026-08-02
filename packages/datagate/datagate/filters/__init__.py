"""DataGate filter chain.

``default_filters`` builds the canonical, ordered fail-fast chain:
min_length -> duplicate_hash -> special_char_ratio -> link_density.
"""

from __future__ import annotations

from ..config import DataGateConfig
from .base import BaseFilter
from .duplicate_hash import DuplicateHashFilter
from .link_density import LinkDensityFilter
from .min_length import MinLengthFilter
from .special_char_ratio import SpecialCharRatioFilter


def default_filters(config: DataGateConfig) -> list[BaseFilter]:
    """Return the canonical ordered filter chain for a run."""
    return [
        MinLengthFilter(config),
        DuplicateHashFilter(),
        SpecialCharRatioFilter(config),
        LinkDensityFilter(config),
    ]


__all__ = [
    "BaseFilter",
    "MinLengthFilter",
    "DuplicateHashFilter",
    "SpecialCharRatioFilter",
    "LinkDensityFilter",
    "default_filters",
]
