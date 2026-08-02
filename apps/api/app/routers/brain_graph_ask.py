from __future__ import annotations

""" — ( " ").
 (ConceptNet + is_a) EpistemicGraph :
(KNOWN)→(INHERITED)→(SCHEMA)→ (ANALOGIZED)→(GUESSED)→UNKNOWN.
 ("X"/" X"/" X "). = .
 ( ), 503 ( ). No LLM.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/brain", tags=["brain-graph"])

_brain = None
_load_error: Optional[str] = None


def _get():
    global _brain, _load_error
    if _brain is not None:
        return _brain
    try:
        from packages.reasoning_vm.brain_loader import load_real_brain
        _brain = load_real_brain()
        _load_error = None
    except Exception as exc:
        _load_error = f"{type(exc).__name__}: {exc}"
        raise HTTPException(status_code=503, detail=f"brain graph unavailable: {_load_error}")
    return _brain


class AskRequest(BaseModel):
    s: str = Field(min_length=1)
    p: str = Field(min_length=1)


class AskNLRequest(BaseModel):
    question: str = Field(min_length=1)


class VerifyRequest(BaseModel):
    s: str = Field(min_length=1)
    p: str = Field(min_length=1)
    o: str = Field(min_length=1)


class VerifyNLRequest(BaseModel):
    question: str = Field(min_length=1)


def _answer(g, s: str, p: str) -> dict:
    from packages.reasoning_vm.brain_loader import _norm
    from packages.reasoning_vm.capability_tier import annotate
    r = g.answer(_norm(s), p)
    r["confabulation"] = g.is_confabulation(r)
    r["query"] = {"s": _norm(s), "p": p}
    return annotate(r, confidence=float(r.get("confidence") or 0.0))


@router.post("/ask")
def ask(req: AskRequest):
    """ (,) → . ."""
    return _answer(_get(), req.s, req.p)


@router.post("/ask_nl")
def ask_nl(req: AskNLRequest):
    """ → (,) . ( )."""
    from packages.reasoning_vm.brain_loader import parse_question
    parsed = parse_question(req.question)
    if parsed is None:
        return {"answer": "", "epistemic_type": "UNKNOWN", "confidence": 0.0,
                "surface": "질문을 (주어, 속성)으로 이해하지 못했습니다. 'penguin|capable_of' 형식으로 주시면 답하겠습니다.",
                "parsed": None, "engaged": True}
    s, p = parsed
    out = _answer(_get(), s, p)
    out["parsed"] = {"s": s, "p": p}
    return out


@router.post("/explain")
def explain(req: AskRequest):
    """ + ' ' ( ). ."""
    from packages.reasoning_vm.brain_loader import _norm
    g = _get()
    r = g.explain(_norm(req.s), req.p)
    r["confabulation"] = g.is_confabulation(r)
    return r


@router.post("/verify")
def verify(req: VerifyRequest):
    """ (,,) → AFFIRM/REFUTE/UNCONFIRMED/UNKNOWN. : ≠( '' )."""
    from packages.reasoning_vm.brain_loader import _norm
    return _get().verify(_norm(req.s), req.p, _norm(req.o))


@router.post("/verify_nl")
def verify_nl(req: VerifyNLRequest):
    """yes/no → . 'can a penguin fly?' / ' ?' / 's|p|o'. ."""
    from packages.reasoning_vm.brain_loader import parse_verify_question
    parsed = parse_verify_question(req.question)
    if parsed is None:
        return {"verdict": "UNKNOWN", "surface": "질문을 (주어, 속성, 대상)으로 이해하지 못했습니다. "
                "'penguin|capable_of|fly' 형식으로 주시면 답하겠습니다.", "parsed": None}
    s, p, o = parsed
    out = _get().verify(s, p, o)
    out["parsed"] = {"s": s, "p": p, "o": o}
    return out


@router.get("/tier")
def tier(refresh: bool = False):
    """R1 — (LOCAL_BASE/LOCAL_EXPERT/SAGE). .
 UI · . refresh=true ."""
    from packages.reasoning_vm.capability_tier import current_tier
    return current_tier(refresh=refresh)


@router.get("/stats")
def stats():
    """ + ( )."""
    if _brain is None:
        return {"loaded": False, "load_error": _load_error}
    st = getattr(_brain, "_load_stats", {})
    return {"loaded": True, "stats": st,
            "ladder": ["KNOWN(확실)", "INHERITED(일반적)", "SCHEMA(전형적)",
                       "ANALOGIZED(유추)", "GUESSED(추측)", "UNKNOWN(모름)"],
            "note": "확신도는 별도 분류기가 아니라 답에 도달한 경로에서 계산됩니다. 작화=추측을 KNOWN으로 내는 것(구조상 불가)."}
