"""Deterministic quality scoring for accepted documents.

No I/O, no randomness. Same input -> same output, always.
"""

from __future__ import annotations

from .config import DataGateConfig
from .models import Document


class QualityScorer:
    def __init__(self, config: DataGateConfig) -> None:
        self.config = config

    def score(self, doc: Document, metrics: dict[str, float | int]) -> float:
        """Return a quality score in ``[0, 100]``.

        Weighted, monotonic, documented formula::

            score = 100
                    - 40 * special_char_ratio_norm   # ratio / max_ratio, capped at 1
                    - 30 * link_density_norm          # ratio / max_ratio, capped at 1
                    - length_penalty                  # 0 if >= 1000 chars,
                                                       #   linear up to 10 at min_chars

        ``metrics`` must contain ``special_char_ratio``, ``link_density`` and
        ``char_count``. Result is clamped to ``[0, 100]`` and rounded to 2
        decimals. Same input -> same output, always.
        """
        special_ratio = float(metrics["special_char_ratio"])
        link_ratio = float(metrics["link_density"])
        char_count = int(metrics["char_count"])

        max_special = self.config.max_special_char_ratio
        max_link = self.config.max_link_density

        special_norm = min(special_ratio / max_special, 1.0) if max_special else 0.0
        link_norm = min(link_ratio / max_link, 1.0) if max_link else 0.0

        min_chars = self.config.min_chars
        if char_count >= 1000:
            length_penalty = 0.0
        elif char_count <= min_chars:
            length_penalty = 10.0
        else:
            length_penalty = 10.0 * (1000 - char_count) / (1000 - min_chars)

        score = 100.0 - 40.0 * special_norm - 30.0 * link_norm - length_penalty
        return round(max(0.0, min(100.0, score)), 2)
