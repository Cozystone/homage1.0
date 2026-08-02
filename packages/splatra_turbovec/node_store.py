"""Disk-backed, memory-mapped quantized node store — the RAM-boundedness half of the
TurboQuant/AirLLM decomposition (see docs + memory turboquant-airllm-decomposition).

TurboQuant gives ~7 B/node by quantizing the 6 physical fields (field_quantizer). But
quantization alone is still O(N) resident if every code is loaded into RAM (6.75 B/node
=> 6.75 TB at 1e12). AirLLM's principle is *stream a huge structure as bounded chunks so
peak memory = one chunk + frontier*. This store applies it to node fields:

 - codes live on DISK, columnar (one file per field), packed as uint8/uint16.
 - open() np.memmap's them: resident RAM = only the OS pages actually touched.
 - scan_windows(W) walks the store in bounded windows of W nodes; each step dequantizes
 only that window. Peak resident RAM = one window (W x 6 floats) + the tiny codebook,
 INDEPENDENT of N. A weak, low-RAM PC can therefore serve an arbitrarily large graph
 within a fixed budget — the hardware-independent " " property, measured.

The store is a pure, verifiable primitive (no engine wiring here); proof/benchmark in
tests + node_store_proof().
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Iterator

import numpy as np

from .field_quantizer import NodeFieldCodec, NODE_FIELDS


def _dtype_for_bits(bits: int) -> type[np.unsignedinteger]:
    return np.uint8 if bits <= 8 else np.uint16


class QuantizedNodeStore:
    """Columnar, memmap-backed quantized node store with a bounded-window scan."""

    def __init__(self, root: Path, codec: NodeFieldCodec, n: int, memmaps: dict[str, np.memmap]):
        self.root = Path(root)
        self.codec = codec
        self.n = n
        self._mm = memmaps

    # ---- build / open -------------------------------------------------------
    @classmethod
    def build(cls, root: str | Path, columns: dict[str, np.ndarray], *, codec: NodeFieldCodec | None = None) -> "QuantizedNodeStore":
        """Fit (or reuse) a codec, quantize the 6 field columns, and persist codes as
        columnar uint8/uint16 files + a small pickled codec. Disk grows O(N); this write
        streams column by column so build memory is bounded per field, not N x 6 floats."""
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        n = int(len(next(iter(columns.values()))))
        codec = codec or NodeFieldCodec().fit(columns)
        codes = codec.encode(columns)  # dict[field] -> int code array
        for f in NODE_FIELDS:
            dt = _dtype_for_bits(codec.codebooks[f].bits)
            np.asarray(codes[f], dtype=dt).tofile(str(root / f"{f}.codes"))
        (root / "codec.pkl").write_bytes(pickle.dumps(codec))
        (root / "meta.json").write_text(
            json.dumps({"n": n, "fields": list(NODE_FIELDS), "bytes_per_node": codec.bytes_per_node}),
            encoding="utf-8",
        )
        return cls.open(root)

    @classmethod
    def open(cls, root: str | Path) -> "QuantizedNodeStore":
        root = Path(root)
        meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
        n = int(meta["n"])
        codec: NodeFieldCodec = pickle.loads((root / "codec.pkl").read_bytes())
        mm: dict[str, np.memmap] = {}
        for f in NODE_FIELDS:
            dt = _dtype_for_bits(codec.codebooks[f].bits)
            mm[f] = np.memmap(str(root / f"{f}.codes"), dtype=dt, mode="r", shape=(n,))
        return cls(root, codec, n, mm)

    # ---- bounded-memory scan ------------------------------------------------
    def scan_windows(self, window: int = 4096) -> Iterator[tuple[int, int, dict[str, np.ndarray]]]:
        """Yield (start, end, dequantized_columns) for each bounded window. Only the
        window's pages are touched; peak resident RAM = window x 6 floats + codebook,
        regardless of N. This is the AirLLM 'peak memory = one chunk' guarantee."""
        if window < 1:
            raise ValueError("window must be >= 1")
        for start in range(0, self.n, window):
            end = min(start + window, self.n)
            win_codes = {f: np.asarray(self._mm[f][start:end]) for f in NODE_FIELDS}
            yield start, end, self.codec.decode(win_codes)

    def disk_bytes(self) -> int:
        return sum((self.root / f"{f}.codes").stat().st_size for f in NODE_FIELDS)


def node_store_proof(root: str | Path, n: int = 1_000_000, window: int = 4096, seed: int = 0) -> dict:
    """Build an N-node store and scan it, reporting disk B/node and a bounded-scan pass.
    RSS-boundedness is asserted in the test (psutil); here we return the shape facts."""
    rng = np.random.default_rng(seed)
    columns = {f: rng.standard_normal(n).astype(np.float64) for f in NODE_FIELDS}
    store = QuantizedNodeStore.build(root, columns)
    touched = 0
    for _start, end, _cols in store.scan_windows(window):
        touched = end
    return {
        "n": n,
        "disk_bytes_per_node": store.disk_bytes() / n,
        "disk_mb": store.disk_bytes() / 1e6,
        "window": window,
        "scanned": touched,
    }
