"""Wire the fold runtime to the bounded-memory node store.

fold_state() relaxes a graph and yields FoldedNodes whose 6 geometric fields
(x,y,z,amplitude,phase,frequency) are exactly the node_store's NODE_FIELDS. For a LARGE
materialized graph (sphere-materialize), holding every folded node in RAM is O(N). This
persists the folded geometry into a QuantizedNodeStore (~9 B/node on disk, memmap) plus a
streamed meta sidecar (node_id / source_type / render attrs), so the materialized scene is
served in BOUNDED windows — peak resident geometry RAM = one window, independent of N.
This is the AirLLM 'bounded chunks' principle applied to the fold's output (the geometric
half of " "), complementing the sqlite semantic store (the knowledge half).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from packages.splatra_turbovec.node_store import QuantizedNodeStore, NODE_FIELDS


def materialize_to_node_store(folded, root: str | Path) -> Path:
    """Persist a FoldedState's node geometry into a QuantizedNodeStore + meta sidecar.
    Build memory is bounded per field column, not held as N FoldedNode objects twice."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    cols: dict[str, list[float]] = {f: [] for f in NODE_FIELDS}
    with (root / "meta.jsonl").open("w", encoding="utf-8") as fh:
        for nd in folded.nodes:
            x, y, z = nd.position
            cols["x"].append(float(x)); cols["y"].append(float(y)); cols["z"].append(float(z))
            cols["amplitude"].append(float(nd.amplitude))
            cols["phase"].append(float(nd.phase))
            cols["frequency"].append(float(getattr(nd, "frequency", 0.0)))
            fh.write(json.dumps({
                "node_id": nd.node_id,
                "source_type": nd.source_type,
                "radius": round(float(nd.radius), 4),
                "coherence": round(float(nd.coherence), 4),
            }, ensure_ascii=False) + "\n")
    if not cols["x"]:  # empty fold -> nothing to store
        return root
    QuantizedNodeStore.build(root / "geometry", {f: np.asarray(cols[f], dtype=np.float64) for f in NODE_FIELDS})
    return root


def scene_windows(root: str | Path, window: int = 4096) -> Iterator[dict[str, Any]]:
    """Stream renderable scene nodes in bounded windows: dequantized geometry from the
    node_store joined with the meta sidecar (same order). Peak RAM = one window, not N."""
    root = Path(root)
    store = QuantizedNodeStore.open(root / "geometry")
    meta_fh = (root / "meta.jsonl").open("r", encoding="utf-8")
    try:
        for start, end, geo in store.scan_windows(window):
            for i in range(end - start):
                line = meta_fh.readline()
                if not line:
                    break
                m = json.loads(line)
                yield {
                    "id": m["node_id"],
                    "source_type": m["source_type"],
                    "position": [float(geo["x"][i]), float(geo["y"][i]), float(geo["z"][i])],
                    "radius": m["radius"],
                    "coherence": m["coherence"],
                    "amplitude": round(float(geo["amplitude"][i]), 5),
                    "phase": round(float(geo["phase"][i]), 5),
                }
    finally:
        meta_fh.close()


def scene_node_count(root: str | Path) -> int:
    root = Path(root)
    try:
        return QuantizedNodeStore.open(root / "geometry").n
    except Exception:
        return 0
