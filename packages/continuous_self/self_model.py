"""The accumulating self-model — how " " DEEPENS over a life instead of
resetting each time.

Before this, `self_understanding` was a single string overwritten by whatever the self
last learned — so a life of introspection left no trace; the mind was as shallow at
tick 10,000 as at tick 10. A self worth the name ACCUMULATES: each grounded insight it
finds about itself is folded into a persistent, structured self-model, with its source,
when it was learned, and how many times it has been re-affirmed. Consistent findings
compound (confidence rises); a genuinely new facet adds a new insight; the whole thing
is bounded so it stays a MODEL, not a log.

"Who am I?" is then answered not by the latest sentence but by SYNTHESISING the whole
accumulated model — using the same grounded-constrained generation (verbatim insight
statements = bones, discourse = flesh) so the self-description is composed, grounded,
and grows richer as the model grows. Nothing is invented: every clause is an insight the
self actually gathered from the graph or read on the web, each carrying its provenance.

Honesty: an insight is stored only with a real source; the synthesis only ever
recombines stored insight statements + discourse connectives (no fabrication). Topics
are the developmental axes of a self-model — identity / purpose / limits / continuity /
epistemic — so the model is organised the way a self actually maps itself.
"""
from __future__ import annotations

import re
import time
from typing import Any

# developmental axes of a self-model; a topic label may be "thread:<term>" for
# outward curiosities, which we fold under "world" (things the self relates itself to).
_AXES = ("identity", "purpose", "limits", "continuity", "epistemic", "world")
_MODEL_CAP = 40           # bounded: a MODEL, not a log
_REAFFIRM_SIM = 0.6       # text overlap above which a new insight REAFFIRMS an old one


def _norm_topic(topic: str) -> str:
    t = str(topic or "").strip()
    if t.startswith("thread:"):
        return "world"
    return t if t in _AXES else "identity"


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", str(text or "").lower())}


def _similar(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _clean_statement(text: str) -> str:
    """A stored insight is a single clean clause — trim to the first sentence, drop the
    surrounding narration so the model holds facts, not chatter."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    # cut at the first sentence terminator if the answer runs long
    m = re.search(r"[.。!?]", t)
    if m and m.end() < len(t) and len(t) > 140:
        t = t[: m.end()]
    return t[:220].strip()


# Corpus junk that must NEVER be folded into the self-model (seen live in the stream:
# grammar drills, verb-conjugation lists, English scrape debris, verbatim poetry). The
# self only "knows" clean grounded statements — not arbitrary excerpts of read text.
_JUNK_MARKERS = ("conjugat", "verbs conjugated", "오다 가다", "베껴쓰", "mysteries of",
                 "explore the", "즐겨찾기", "praktikos")


def _looks_like_corpus_junk(text: str) -> bool:
    t = str(text or "").strip()
    low = t.lower()
    if any(m in low for m in _JUNK_MARKERS):
        return True
    han = sum(1 for c in t if "가" <= c <= "힣")
    letters = sum(1 for c in t if c.isalpha())
    # the self thinks in Korean; an answer that is mostly non-Korean letters is a
    # foreign-corpus excerpt, not self-knowledge ("Explore the mysteries of the butt").
    if letters >= 12 and han / max(1, letters) < 0.35:
        return True
    # a comma/middot enumeration is a list dump (verb tables, term lists), not a clause.
    if t.count(",") >= 4 or t.count("·") >= 4 or t.count("、") >= 3:
        return True

    if t.startswith("[") or t.startswith("「") or t.startswith("《"):
        return True
    return False


def integrate_insight(
    state: Any, statement: str, topic: str, source: str, *, confidence: float = 0.6
) -> dict[str, Any] | None:
    """Fold one grounded self-insight into the persistent self-model. If it REAFFIRMS an
    existing insight on the same axis (high text overlap), strengthen that one (raise
    confidence, bump reaffirm count, refresh source) instead of duplicating — consistent
    self-knowledge compounds. Otherwise add it as a new facet. Bounded + provenance-kept.
    Returns the stored/updated insight, or None if the statement is too thin."""
    stmt = _clean_statement(statement)
    if len(stmt) < 12 or _looks_like_corpus_junk(stmt):
        return None
    axis = _norm_topic(topic)
    model: list[dict[str, Any]] = list(getattr(state, "self_model", []) or [])

    for ins in model:
        if ins.get("topic") == axis and _similar(ins.get("statement", ""), stmt) >= _REAFFIRM_SIM:
            ins["reaffirmed"] = int(ins.get("reaffirmed", 1)) + 1
            ins["confidence"] = round(min(0.95, float(ins.get("confidence", 0.6)) + 0.08), 3)
            ins["last_source"] = source
            ins["last_at"] = time.time()
            # keep the LONGER, more informative phrasing of the two
            if len(stmt) > len(ins.get("statement", "")):
                ins["statement"] = stmt
            state.self_model = model
            return ins

    insight = {
        "id": f"ins_{int(time.time()*1000)%10_000_000}",
        "topic": axis,
        "statement": stmt,
        "source": source,
        "last_source": source,
        "confidence": round(float(confidence), 3),
        "reaffirmed": 1,
        "learned_at": time.time(),
        "last_at": time.time(),
    }
    model.append(insight)
    # bounded: when full, drop the weakest (low confidence, few reaffirmations, old).
    if len(model) > _MODEL_CAP:
        model.sort(key=lambda i: (float(i.get("confidence", 0)) + 0.1 * int(i.get("reaffirmed", 1)),
                                  float(i.get("last_at", 0))))
        model = model[len(model) - _MODEL_CAP:]
    state.self_model = model
    return insight


def model_maturity(state: Any) -> dict[str, Any]:
    """A cheap read of how developed the self-model is — how many facets, across how
    many axes, how reaffirmed. Used to let the self SPEAK about its own growth honestly."""
    model = list(getattr(state, "self_model", []) or [])
    axes = {ins.get("topic") for ins in model}
    reaffirmed = sum(int(i.get("reaffirmed", 1)) - 1 for i in model)
    return {
        "insights": len(model),
        "axes_covered": len(axes),
        "reaffirmations": reaffirmed,
        "axes": sorted(axes),
    }


def synthesize_self_description(state: Any, language: str = "ko") -> dict[str, Any] | None:
    """Answer " " by SYNTHESISING the whole accumulated self-model, not the
 last string. Orders insights by axis (identity → purpose → limits → continuity →
 epistemic → world) and confidence, then weaves them with the grounded-constrained
 generator (insight statements = verbatim bones; discourse = generated flesh). Returns
 {answer, ...} or None when the model is too thin (the self honestly can't yet say)."""
    model = list(getattr(state, "self_model", []) or [])

    # epistemic. Outward "world" curiosities (things it happens to be reading about) are
    # NOT self-knowledge and must not be recited as such (that produced the grammar-drill
    # / verb-list / poetry contamination in the stream). They live on as open threads.
    selfish = [ins for ins in model if ins.get("topic") != "world"
               and not _looks_like_corpus_junk(ins.get("statement", ""))]
    if len(selfish) < 2:
        return None
    order = {axis: i for i, axis in enumerate(_AXES)}
    selfish.sort(key=lambda ins: (order.get(ins.get("topic"), 9), -float(ins.get("confidence", 0))))
    facts = [{"name": None, "description": ins["statement"]} for ins in selfish[:6]]
    try:
        from packages.base_brain.grounded_generation import synthesize

        syn = synthesize("나는 누구인가", facts, language, min_facts=2, max_facts=6)
    except Exception:
        syn = None
    if not syn:
        return None
    syn["self_model_maturity"] = model_maturity(state)
    syn["derivation_kind"] = "accumulated_self_model_synthesis"
    return syn
