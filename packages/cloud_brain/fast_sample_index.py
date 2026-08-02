from __future__ import annotations

from pathlib import Path
from typing import Any

from .read_model import build_cloud_read_model, load_fast_graph_sample
from .status_cache import DEFAULT_CLOUD_ROOT


def load_fast_sample_index(
    root: str | Path = DEFAULT_CLOUD_ROOT,
    *,
    limit_nodes: int = 1200,
    limit_edges: int = 2400,
) -> dict[str, Any]:
    return load_fast_graph_sample(root, limit_nodes=limit_nodes, limit_edges=limit_edges)


def rebuild_fast_sample_index(
    root: str | Path = DEFAULT_CLOUD_ROOT,
    *,
    limit_nodes: int = 1200,
    limit_edges: int = 2400,
) -> dict[str, Any]:
    return build_cloud_read_model(root, limit_nodes=limit_nodes, limit_edges=limit_edges)
