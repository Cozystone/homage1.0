"""Abstract base class for DataGate filters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from ..models import Document, FilterResult


class BaseFilter(ABC):
    """A single quality check in the fail-fast filter chain.

    Subclasses declare a stable ``name`` (used in metadata and rejection
    breakdowns) and implement ``apply``. ``reset`` is a no-op by default;
    stateful filters (e.g. dedup) override it so the runner can clear state at
    the start of every run.
    """

    name: ClassVar[str]

    @abstractmethod
    def apply(self, doc: Document) -> FilterResult:
        """Evaluate ``doc`` and return a :class:`FilterResult`."""

    def reset(self) -> None:
        """Clear any per-run state. Default: nothing to do."""
        return None
