"""Provider and sink protocols for the World4D shadow adapter."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from packages.world4d.contracts import (
    World4DProviderDescriptor,
    World4DProviderResult,
    World4DRequest,
    World4DShadowReceipt,
)


@runtime_checkable
class World4DProvider(Protocol):
    descriptor: World4DProviderDescriptor

    def propose(
        self,
        request: World4DRequest,
        payload: object,
    ) -> World4DProviderResult:
        """Return hypotheses or abstain.

        This protocol states the intended contract but does not isolate or
        attest provider side effects. Live bindings require separate source
        review or a future process boundary.
        """


@runtime_checkable
class ReceiptSink(Protocol):
    def append(self, receipt: World4DShadowReceipt) -> object:
        """Persist one bounded observer receipt."""
