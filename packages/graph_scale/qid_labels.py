# -*- coding: utf-8 -*-
"""Read-only Q-id → label sidecar (owner-approved 2026-07-18). The world-pack references ~612k
DANGLING Q-ids as objects (capital→Q99692066) that were never ingested as subjects, so their label
is lost and a fact-QA answer is an opaque Q-id. `backfill_qid_labels.py` fetches those labels from
Wikidata into data/graph_scale/qid_labels.jsonl; this module serves them at READ time.

It is a SIDECAR, not the store — nothing is written to the triple store ( respected),
exactly the isa_verdict.col / lang_gate.col discipline: delete the file and the resolution is gone,
the graph unchanged. Deletion-reversible, evidence-only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_QID = re.compile(r"^Q\d+$")
_PATH = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "qid_labels.jsonl"
_CACHE: dict[str, str] | None = None
_SIG: tuple[float, int] | None = None


def _sig() -> tuple[float, int]:
    try:
        st = _PATH.stat()
        return (st.st_mtime, st.st_size)
    except OSError:
        return (0.0, 0)


def _load() -> dict[str, str]:
    global _CACHE, _SIG
    sig = _sig()
    if _CACHE is not None and _SIG == sig:          # reload only when the sidecar file changes
        return _CACHE
    m: dict[str, str] = {}
    if _PATH.exists():
        with _PATH.open(encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                lab = r.get("en") or r.get("ko")    # prefer English (english-core), fall back to Korean
                if lab and r.get("qid"):
                    m[r["qid"]] = lab
    _CACHE, _SIG = m, sig
    return m


def resolve(value: str) -> str:
    """A Q-id → its sidecar label; anything else (already a label) is returned unchanged. Unknown
    Q-ids come back as-is, so the caller can still tell it is unresolved."""
    v = str(value)
    if not _QID.match(v):
        return v
    return _load().get(v, v)


def size() -> int:
    return len(_load())
