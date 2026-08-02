"""Canonical default-off seam for ATANOR's unfinished 4D world-core research."""
from packages.world4d.block_universe_provider import (
    BlockUniverseQuery,
    BlockUniverseShadowProvider,
)
from packages.world4d.contracts import (
    CheckScope,
    CheckVerdict,
    Direction,
    ProviderResultStatus,
    World4DCheck,
    World4DProviderDescriptor,
    World4DProviderResult,
    World4DRequest,
    World4DShadowReceipt,
    World4DStep,
    World4DTrajectory,
)
from packages.world4d.provider import ReceiptSink, World4DProvider
from packages.world4d.shadow import (
    JsonlReceiptSink,
    World4DShadowAdapter,
    World4DShadowDispatcher,
    submit_temporal_query_shadow,
    wait_for_temporal_shadow_idle,
)

__all__ = [
    "BlockUniverseQuery",
    "BlockUniverseShadowProvider",
    "CheckScope",
    "CheckVerdict",
    "Direction",
    "JsonlReceiptSink",
    "ProviderResultStatus",
    "ReceiptSink",
    "World4DCheck",
    "World4DProvider",
    "World4DProviderDescriptor",
    "World4DProviderResult",
    "World4DRequest",
    "World4DShadowAdapter",
    "World4DShadowDispatcher",
    "World4DShadowReceipt",
    "World4DStep",
    "World4DTrajectory",
    "submit_temporal_query_shadow",
    "wait_for_temporal_shadow_idle",
]
