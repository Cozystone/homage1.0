from __future__ import annotations

"""Real-time thinking endpoint — teach a fact this turn, reason over it the next, with zero retraining.

Wraps RealTimeThinker (Layer A live buffer → priority fusion → multi-hop reader → doubt gate). The model is
LAZY-loaded on first use so it never bloats engine startup, and every failure degrades to 503 rather than
crashing the process. Hallucination-0: /think abstains when nothing is lexically relevant, and answers carry
evidence provenance + live/static origin.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/realtime", tags=["realtime"])

_thinker = None            # lazy singleton — loaded on first /learn or /think, never at import time
_load_error: Optional[str] = None


def _get():
    global _thinker, _load_error
    if _thinker is not None:
        return _thinker
    try:
        from packages.reasoning_vm.deliberator.realtime import RealTimeThinker
        _thinker = RealTimeThinker(ckpt="ace_hotpot.pt")
        _load_error = None
    except Exception as exc:                                    # torch/ckpt missing → degrade, don't crash
        _load_error = f"{type(exc).__name__}: {exc}"
        raise HTTPException(status_code=503, detail=f"real-time thinker unavailable: {_load_error}")
    return _thinker


class LearnRequest(BaseModel):
    """Untrusted public learning input.

    Verification is deliberately absent and extra fields are rejected: only a
    server-owned verifier may promote a stored item after this ingress.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    source: str = ""


class ThinkRequest(BaseModel):
    question: str = Field(min_length=1)
    static_paragraphs: list[tuple[str, str]] | None = None     # optional (title,text) from the corpus
    include_unverified: bool = True                            # surface unverified, flagged


@router.post("/learn")
def learn(req: LearnRequest):
    """HEAR — store immediately as unverified; public callers cannot promote."""
    it = _get().learn(req.text, source=req.source)
    return {"id": it["id"], "verified": it["verified"], "at": it["at"]}


@router.post("/think")
def think(req: ThinkRequest):
    """HEAR→FUSE→THINK→DOUBT — answer over the live buffer (priority) + optional static evidence, or
    abstain honestly when nothing is relevant."""
    return _get().think(req.question, static_paragraphs=req.static_paragraphs,
                        include_unverified=req.include_unverified)


@router.get("/stats")
def stats():
    """Live-buffer stats + whether the model is loaded (does not force a load)."""
    if _thinker is None:
        return {"loaded": False, "load_error": _load_error, "items": 0}
    return {"loaded": True, "hippocampus": _thinker.mem.stats(), "cortex": _thinker.cortex.stats()}


@router.post("/sleep")
def sleep(prune: bool = False):
    """D1 SLEEP — consolidate verified episodic facts hippocampus→cortex and mine the misses into a deficit
    curriculum. 'Wake up smarter': consolidated knowledge is durable and survives a buffer clear. The heavy
    TCT training the curriculum feeds runs separately behind the A/B win-gate."""
    from packages.reasoning_vm.consolidation import SleepConsolidator
    t = _get()
    sc = SleepConsolidator(hippocampus=t.mem, cortex=t.cortex, misslog=t.misslog)
    return sc.sleep_cycle(prune=prune)


@router.get("/curriculum")
def curriculum(top_k: int = 20):
    """The mined deficit curriculum — the topics the system keeps failing to ground (targets for a curiosity
    expedition and the next training cycle). Does not force a model load."""
    from packages.reasoning_vm.consolidation import MissLog, SleepConsolidator
    from packages.reasoning_vm.live_memory import LiveMemory
    if _thinker is not None:
        sc = SleepConsolidator(hippocampus=_thinker.mem, cortex=_thinker.cortex, misslog=_thinker.misslog)
    else:
        sc = SleepConsolidator(hippocampus=LiveMemory(), cortex=LiveMemory(), misslog=MissLog())
    return {"deficits": sc.mine_curriculum(top_k=top_k)}
