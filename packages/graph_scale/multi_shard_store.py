# -*- coding: utf-8 -*-
"""MultiShardStore — read a sharded-write world pack as ONE store (unions across shard TripleStores).

The sharded builder writes N independent TripleStores (shard_0 … shard_{N-1}) to sidestep the
single-writer decel. Each shard is a complete store over a slice of the dump; a subject's facts may
span shards (partitioned by dump position, not subject), so `facts_about` unions + dedups across
shards. Drop-in for the single-store read path used by answer_bridge / discrimination."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .triple_store import TripleStore


class MultiShardStore:
    def __init__(
        self,
        root: str | Path,
        *,
        dict_backend: str = "sharded",
        read_only: bool = True,
    ) -> None:
        root = Path(root)
        dirs = sorted((d for d in root.glob("shard_*") if (d / "meta.json").exists()),
                      key=lambda d: int(d.name.split("_")[1]) if d.name.split("_")[1].isdigit() else 0)
        self.shards: list[TripleStore] = [
            TripleStore(
                d,
                dict_backend=dict_backend,
                write_src=False,
                read_only=read_only,
            )
            for d in dirs
        ]
        if not self.shards:
            raise FileNotFoundError(f"no shard_* stores under {root}")

    def facts_about(self, subject: str, limit: int = 40) -> list[tuple[str, str, str]]:
        """Union of every shard's facts for `subject`, deduplicated, capped at `limit`."""
        out: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for sh in self.shards:
            try:
                rows = sh.facts_about(subject, limit=limit)
            except Exception:
                continue
            for t in rows:
                key = (str(t[0]), str(t[1]), str(t[2]))
                if key not in seen:
                    seen.add(key)
                    out.append(t)
                    if len(out) >= limit:
                        return out
        return out

    def count(self) -> int:
        """Total triples across shards (from each shard's meta.json / column length)."""
        import json as _json
        total = 0
        for sh in self.shards:
            root = getattr(sh, "root", None) or getattr(sh, "_root", None) or getattr(sh, "path", None)
            if root is None:
                continue
            root = Path(root)
            try:
                total += int(_json.loads((root / "meta.json").read_text(encoding="utf-8")).get("count", 0))
            except Exception:
                try:                                           # fallback: s.col length / 4 (int32)
                    total += (root / "s.col").stat().st_size // 4
                except Exception:
                    pass
        return total

    def meta(self) -> dict[str, Any]:
        return {"shards": len(self.shards), "triples": self.count()}

    def close(self) -> None:
        for shard in self.shards:
            shard.close()
