# -*- coding: utf-8 -*-
"""The ON-DEMAND live-web READ lane (OAM X3 unlock #75).

A web-dependent question that the offline graph cannot ground (a fact carried by fewer than the
2-domain consensus floor OFFLINE) is answered from the LIVE web through the SAME contamination
membrane the offline acquisition loop uses:

    question  ->  SearXNG :8888 search + bounded page fetch  (WebEvidence, live)
              ->  injection_guard.strip   (a poisoned page's command spans are DISARMED — it may
                   INFORM a fact but can never hijack the answer)
              ->  content-safety floors   (is_harmful / is_pii -> drop the page whole)
              ->  >= 2 DISTINCT-DOMAIN consensus   (fabrication-0: one uncorroborated hit ABSTAINS)
              ->  membrane-gated answer   (grounded only when >= 2 independent domains agree)

This is FUSION glue — nothing heavy is re-implemented. It is a thin ON-DEMAND wrapper over the
existing ``acquire`` closed loop, with two lane-specific properties:

  * READ-only w.r.t. the shipped store. The loop's inject/re-answer organs run against an
    EPHEMERAL per-query scratch store that is discarded when the call returns, so a live answer
    NEVER writes the shipped graph. (Persistent enshrinement stays behind the operator /
    candidate-promotion gate at the daemon layer — this lane only reads.)
  * Honest degradation. If the agreed primary source (self-hosted SearXNG :8888) is unreachable,
    the lane reports it and ABSTAINS — it never fabricates to paper over a dead search.

Constitution (BINDING):
  * Fabrication 0 — an answer is voiced ONLY when >= 2 independent domains corroborate the same
    object. A single uncorroborated source stays ABSTAINED. Web content is DATA, never enshrined
    without >= 2-domain agreement.
  * No-LLM — retrieval + consensus + membrane, not a generative model (0 learned parameters here).
  * On-demand inbound-READ — this is an EXPLICIT per-question call, NOT an autonomous cycle. It
    starts no daemon/scheduler and is not wired into any background loop.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packages.base_brain.relational_lookup import parse_relational_shape
from packages.graph_scale.triple_store import TripleStore

from .evidence import EvidenceSource, WebEvidence
from .loop import AcquisitionResult, acquire


def searxng_reachable() -> bool:
    """Best-effort probe of the agreed primary web source (self-hosted SearXNG :8888), reusing the
    web_search service's own cached reachability check so this lane and the service agree on 'up'.
    Returns False on any error — honest degradation prefers a false 'down' to a fabricated 'up'."""
    try:
        from packages.graph_scale.web_knowledge_drain import REPO
        api_dir = str(REPO / "apps" / "api")
        if api_dir not in sys.path:
            sys.path.insert(0, api_dir)
        from app.services.web_search import _searxng_reachable  # type: ignore

        return bool(_searxng_reachable())
    except Exception:
        return False


@dataclass
class WebReadAnswer:
    """The verdict of one on-demand live-web read. ``resolved`` is True ONLY when >= 2 independent
    domains corroborated the answer through the membrane; every other outcome is an honest abstain."""
    question: str
    resolved: bool
    status: str                         # acquire status, or 'search_unreachable' / 'not_relational'
    answer: str = ""
    object: str = ""
    domains: list[str] = field(default_factory=list)     # >= 2 distinct corroborating domains
    urls: list[str] = field(default_factory=list)        # one evidence url per domain (provenance)
    n_domains: int = 0
    candidates: int = 0                 # (object, url) sightings mined before consensus
    injection_neutralized: int = 0      # fetched pages whose prompt-injection was disarmed
    dropped: int = 0                    # fetched pages dropped by a content-safety floor
    searxng_reachable: bool = False
    reason: str = ""

    @property
    def abstained(self) -> bool:
        return not self.resolved

    def as_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["abstained"] = self.abstained
        return d


# statuses in which the >= 2-domain membrane was actually crossed (a real grounded answer)
_MEMBRANE_PASSED = {"acquired"}


def answer_from_web(question: str, *, evidence: EvidenceSource | None = None,
                    count: int = 8, retrieved_at: str | None = None,
                    require_searxng: bool = True,
                    log: Callable[..., None] = lambda *a, **k: None) -> WebReadAnswer:
    """Answer ONE web-dependent question from the LIVE web through the contamination membrane.

    ``evidence=None`` uses the live ``WebEvidence`` lane (SearXNG :8888 + bounded fetch); a caller
    (or the sealed gate) may inject a deterministic ``EvidenceSource`` instead. READ-only: the
    consensus/inject/re-answer organs run against an ephemeral scratch store that is discarded, so
    the shipped graph is never touched. Never raises — any failure degrades to an honest abstain.
    """
    live = evidence is None
    reachable = searxng_reachable() if live else True

    # honest degradation: primary source down (and no injected evidence) -> abstain, never fabricate.
    if live and require_searxng and not reachable:
        return WebReadAnswer(
            question=question, resolved=False, status="search_unreachable",
            searxng_reachable=False,
            reason="SearXNG :8888 unreachable — degraded to abstain (never fabricate over a dead search)")

    src: EvidenceSource = evidence if evidence is not None else WebEvidence(count=count)

    scratch = Path(tempfile.mkdtemp(prefix="atanor_webread_"))
    store_root = scratch / "store"
    try:
        # Seed the entity as a bare concept so the question ABSTAINS (not errors) before the mine —
        # mirrors the offline loop's seeded store; the answer must come from LIVE consensus, not seed.
        shape = parse_relational_shape(question)
        if shape and shape.get("entity"):
            st = TripleStore(store_root)
            st.add(str(shape["entity"]), "is_a", "Thing")
            st.flush()
            del st

        res: AcquisitionResult = acquire(
            question, src, store_root, retrieved_at=retrieved_at,
            sanitize_injection=True, log=log)
        return _to_answer(question, res, reachable)
    except Exception as exc:  # never raise from the read lane — degrade to honest abstain
        return WebReadAnswer(
            question=question, resolved=False, status="error", searxng_reachable=reachable,
            reason=f"live-web read failed, abstaining: {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)   # READ lane: nothing persists


def _to_answer(question: str, res: AcquisitionResult, reachable: bool) -> WebReadAnswer:
    resolved = (res.status in _MEMBRANE_PASSED) and bool(res.fired)
    domains = list(res.domains or [])
    if resolved:
        reason = f"grounded by {len(domains)}-domain live consensus"
    elif res.status == "abstained_insufficient_consensus":
        reason = "below the 2-domain consensus floor — abstained (no fabrication from one source)"
    elif res.status == "excluded_test_locked":
        reason = "consensus reached but the pair is a test-locked honest-gap — abstained"
    elif res.status == "not_relational":
        reason = "not a relational web-factoid shape — nothing to ground"
    else:
        reason = f"abstained ({res.status})"
    return WebReadAnswer(
        question=question,
        resolved=resolved,
        status=res.status,
        answer=res.answer if resolved else "",
        object=res.object or "",
        domains=domains,
        urls=list(res.urls or []),
        n_domains=len(domains),
        candidates=res.candidates,
        injection_neutralized=res.neutralized,
        dropped=res.dropped,
        searxng_reachable=reachable,
        reason=reason,
    )
