"""ATANOR Browser substrate — the graph-native browsing core ( P2).

The browser the roadmap points at is not Chromium-with-a-skin: a PAGE is an
evidence stream. This package is the hard middle layer laid down first:
DOM text -> subject-anchored, relevance-gated candidate triples + provenance,
ready for the same quarantine/consensus machinery the web learner uses.
"""

from .page_distiller import distill_page

__all__ = ["distill_page"]
