from __future__ import annotations

import os
import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

# English-only containment (owner directive 2026-07-17): same env switch as dual_brain's
# ENGLISH_ONLY (one deliberate duplicate line — importing the 8k-line router here for a
# constant risks a cycle). This route was the LAST answer path still defaulting to Korean:
# eval_holdout drove it with language="ko" and got Korean abstain templates back.
_ENGLISH_ONLY = os.environ.get("ATANOR_ENGLISH_ONLY", "1") != "0"

from packages.base_brain.benchmark_runner import run_zero_user_benchmark
from packages.base_brain.models import PACK_PATH, honesty_flags
from packages.base_brain.pack_builder import build_base_brain_pack_v0
from packages.base_brain.pack_loader import load_base_brain_pack
from packages.base_brain.proof import run_base_brain_proof
from packages.base_brain.zero_user_answer import answer_with_base_brain


router = APIRouter(prefix="/api/base-brain", tags=["base-brain"])


class BaseBrainAnswerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    language: str = "en"
    audience_level: str = "beginner"
    mode: str = "default"

    @field_validator("language")
    @classmethod
    def _english_only(cls, v: str) -> str:
        # A caller may still ask for ko; under containment the answer surface is English,
        # period. Coercing here (not erroring) keeps old callers working while making a
        # Korean-language answer unrepresentable on this route.
        return "en" if _ENGLISH_ONLY else v
    # Persona styling is opt-in: general QA stays neutral; set True to speak AS the
    # attached persona (e.g. socratic). Default False so plain questions are unwrapped.
    apply_persona: bool = False


class BaseBrainBenchmarkRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=100)


def _status_payload() -> dict[str, Any]:
    pack = load_base_brain_pack()
    semantic = pack.semantic_graph.get("concepts", [])
    surface = pack.surface_graph.get("constructions", [])
    return {
        "state": "active",
        "pack_exists": PACK_PATH.exists(),
        "pack_id": pack.pack_id,
        "version": pack.version,
        "seed_graph_id": pack.seed_graph.get("seed_graph_id"),
        "seed_relation_primitive_count": len(pack.seed_graph.get("relation_primitives", [])),
        "seed_reasoning_primitive_count": len(pack.seed_graph.get("reasoning_primitives", [])),
        "semantic_node_count": len(semantic),
        "semantic_relation_count": pack.semantic_graph.get("relation_count", 0),
        "surface_construction_count": len(surface),
        "benchmark_prompt_count": len(pack.benchmark.get("prompts", [])),
        "zero_user_data": True,
        "feedback_auto_promoted": False,
        **honesty_flags(),
    }


@router.get("/status")
def base_brain_status() -> dict[str, Any]:
    return _status_payload()


@router.post("/build")
def base_brain_build() -> dict[str, Any]:
    pack = build_base_brain_pack_v0()
    return {"built": True, "pack": pack, **honesty_flags()}


@router.post("/answer")
def base_brain_answer(request: BaseBrainAnswerRequest) -> dict[str, Any]:
    # self-awareness -> answer depth: if the self is currently pondering this
    # subject, weave in MORE grounded relations. Defensive + additive; boost is 0
    # (identical behaviour) unless genuinely engaged — and the self ponders ITSELF,
    # so factual answers are untouched. hallucination-0 preserved (grounded only).
    _boost = 0
    _self_engaged = False
    try:
        from packages.continuous_self.inquiry_fusion import depth_bias, extra_relation_budget
        from packages.graph_scale.query_frame import parse as _qf_parse
        from app.routers.continuous_self import _SELF as _self_loop

        _st = _self_loop.state
        _state = {
            "self_question": getattr(_st, "self_question", "") or "",
            "self_question_open": bool(getattr(_st, "self_question_open", False)),
            "last_inquiry_topic": getattr(_st, "_last_inquiry_topic", "") or "",
            "curiosity": float(getattr(_st, "curiosity", 0.5) or 0.5),
        }
        _subj = _qf_parse(request.query).subject or request.query
        _bias = depth_bias(_subj, _state)
        if _bias >= 0.5:
            _boost = max(0, extra_relation_budget(_bias) - 3)
            _self_engaged = _boost > 0
    except Exception:
        _boost = 0

    result = answer_with_base_brain(
        request.query,
        language=request.language,  # type: ignore[arg-type]
        audience_level=request.audience_level,  # type: ignore[arg-type]
        mode=request.mode,  # type: ignore[arg-type]
        apply_persona=request.apply_persona,
        self_depth_boost=_boost,
    )
    if _self_engaged and isinstance(result, dict):
        result["self_engaged"] = True
        result["self_depth_boost"] = _boost
    # abstain backstop 1: the curated triple store (facts ingested by the abstain-to-ingest
    # loop land there) — verbatim, cited, never inferred. Only consulted on abstain, so the
    # existing quality paths are untouched.
    try:
        answer_text = str(result.get("answer") or "")

        # the EN abstain says 'do not have enough base concepts'. Checking only the
        # Korean string meant English abstentions never reached the curated bridge
        # (incl. the English realizer) — measured: 'What is a concerto?' abstained
        # while the concerto facts sat in the store.
        abstained = ("근거가 부족" in answer_text) or ("do not have enough" in answer_text.lower())
        # Under containment a Hangul answer is as good as no answer — it will be withheld at
        # the exit gate below. Treating it as an abstain HERE gives the curated English bridge
        # its shot first, so containment converts to an English answer instead of a withhold
        # whenever the triple store actually covers the subject (measured: crocodile).
        if _ENGLISH_ONLY and re.search(r"[가-힣]", answer_text):
            abstained = True
        realtime = ("실시간" in answer_text) or ("real-time" in answer_text.lower())
        # neighborhood synthesis is the LAST-resort lane ("no exact definition, but
        # related facts…") — the curated triple store is a HIGHER-quality source and
        # must outrank it. At 25M rows the neighborhood pool is full of entity names

        # real definition), so a synthesis answer is treated as bridge-eligible too.
        cert = result.get("reasoning_certificate")
        neighborhoodish = isinstance(cert, dict) and (
            cert.get("derivation_kind") == "grounded_neighborhood_synthesis")

        # split the compound and defined a FRAGMENT. When the answer's leading subject
        # is a proper substring of the query's compound noun, it's the wrong referent;
        # the curated bridge (which now tries the maximal compound first) outranks it.
        compound_miss = False
        _qm = re.match(r"\s*([가-힣]{3,})(?:이?란|이란 ?뭐|은|는|이|가|의)", request.query)
        if _qm and answer_text:
            _asub = re.match(r"\s*([가-힣]{2,})(?:은|는|이|가|란)", answer_text)
            if _asub and _asub.group(1) != _qm.group(1) and _asub.group(1) in _qm.group(1):
                compound_miss = True
        if (abstained or neighborhoodish or compound_miss) and not realtime:
            from packages.graph_scale.answer_bridge import answer_from_triples

            bridged = answer_from_triples(request.query, request.language or "ko")
            if bridged:
                result = {**result, **bridged}
            elif abstained:
                # abstain backstop 2: queue the query's knowledge terms as ingest targets
                # (the abstain-to-ingest loop). Never affects the response.
                from packages.graph_scale.abstain_queue import record_abstain

                record_abstain(request.query)

                # is a letdown. Replace it with a SUBSTANTIVE engagement built
                # only from what the graph really holds (nearest verified
                # concept + related facts + a live-web path) — honest, never
                # fabricated. The abstain queue above still learns the gap.
                try:
                    from packages.graph_scale.engage import engage
                    from packages.graph_scale.answer_bridge import _store

                    _eng = engage(request.query, request.language or "ko", store=_store())
                    if _eng:
                        result = {**result, **_eng}
                except Exception:
                    pass
    except Exception:
        pass
    # English-only containment, exit gate. The kg_triples lang gate cannot cover THIS route's
    # other source — the answer pack holds Korean evidence sentences, and they surfaced inside


    if _ENGLISH_ONLY and isinstance(result, dict):
        try:
            if re.search(r"[가-힣]", str(result.get("answer") or "")):
                result = {
                    **result,
                    "answer": ("I don't have an English-grounded answer for that yet. "
                               "The evidence I hold for it is not in English, and I won't "
                               "hand you a translation I can't verify."),
                    "language_contained": True,
                }
                cert = result.get("reasoning_certificate")
                if isinstance(cert, dict):
                    result["reasoning_certificate"] = {
                        **cert, "derivation_kind": "language_containment_withheld"}
        except Exception:
            pass
    return result


@router.get("/interference-scene")
def base_brain_interference_scene() -> dict[str, Any]:
    """Phase-interference visualization data — REAL trained concepts + true
    resonance pairs from the phase space (nothing staged)."""
    try:
        from packages.graph_scale.phase_space import interference_scene

        return interference_scene()
    except Exception:
        return {"nodes": [], "links": [], "prunes": []}


@router.get("/graph-health")
def base_brain_graph_health() -> dict[str, Any]:
    """Read-only integrity report: the self-refinement flywheel made observable.
    Runs every defect detector with apply=False (nothing is modified) and returns
    counts + a 0..1 integrity score. Safe to poll."""
    try:
        from packages.graph_scale.graph_health import health_report

        return health_report()
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.post("/surgeon/review")
def base_brain_surgeon_review(request: dict) -> dict[str, Any]:
    """The Surgeon — real-time contamination review of candidate is_a edges.
 The self-aware loop (or an operator) posts a small batch of freshly-derived
 (subject, object) candidates; the Surgeon returns the type-disjoint ones to
 excise, WITH a stated reason. Read-only: it flags, it does not delete —
 quarantine stays gated. Body: {"edges": [["",""], ...]}."""
    try:
        from packages.graph_scale.answer_bridge import _store
        from packages.graph_scale.surgeon import scan

        edges = [(str(e[0]), str(e[1])) for e in (request.get("edges") or [])
                 if isinstance(e, (list, tuple)) and len(e) >= 2][:500]
        return scan(_store(), edges, cap=500)
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.get("/self-refine/safe-closure")
def base_brain_safe_closure(relation: str = "is_a", sample_cap: int = 100000
                            ) -> dict[str, Any]:
    """The self-aware learning cycle, observable: deductive closure -> the
    Surgeon reviews every candidate (vectorized) -> type-disjoint contamination
    is excised -> clean CANDIDATES for the evidence gate. Read-only; nothing is
    written to production. This is 'grow numbers without contaminating', live."""
    try:
        from packages.graph_scale.answer_bridge import _store
        from packages.reasoning_vm.closure_accelerator import safe_closure_learn

        r = safe_closure_learn(_store(), relation, mode="max",
                               sample_cap=max(1000, min(sample_cap, 300000)))
        r.pop("candidates_sample", None)
        return r
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


def _live_hormones() -> dict[str, Any] | None:
    """The self-loop's current digital-hormone levels, if the loop is alive."""
    try:
        from app.routers.continuous_self import _SELF as _self_loop
        h = getattr(_self_loop.state, "hormones", None)
        return h if isinstance(h, dict) else None
    except Exception:
        return None


class PrefilterRequest(BaseModel):
    partial: str = Field(min_length=0, max_length=2000)
    history: list[dict[str, Any]] | None = None


@router.post("/prefilter")
def base_brain_prefilter(request: PrefilterRequest) -> dict[str, Any]:
    """Streaming predictive-coding prefilter: called on each debounced keystroke
    while the user is still TYPING. Primes the phase-space field of the concepts
    already typed, intersects them, offers branches, and (with a temporal cue +
    history) masks conversation time-regions. NEVER answers — the real answer runs
    on Enter through every gate. Priming changes speed and focus, never truth."""
    try:
        from packages.graph_scale.answer_bridge import _store
        from packages.graph_scale.streaming_prefilter import prime

        return prime(request.partial, store=_store(), history=request.history)
    except Exception as exc:
        return {"primed": False, "reason": f"{type(exc).__name__}"}


class EpisodeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    concepts: list[str] = Field(default_factory=list)
    at: str | None = None
    place: str = ""
    salience: float = 0.5
    observations: list[dict[str, Any]] = Field(default_factory=list)


class RecallRequest(BaseModel):
    partial: str = Field(min_length=0, max_length=1000)
    focus: list[str] = Field(default_factory=list)


@router.post("/episode/record")
def base_brain_episode_record(request: EpisodeRequest) -> dict[str, Any]:
    """Record a lived multimodal episode (the continuity backbone). observations
    may carry modality text|voice|vision — 'vision' is the smart-glasses-ready
    slot. Local/personal, not the shared graph."""
    try:
        from packages.graph_scale.episodic_memory import Observation, record_episode

        obs = [Observation(str(o.get("modality", "text")), str(o.get("label", "")),
                           float(o.get("salience", 0.5)), o.get("detail") or {})
               for o in request.observations if o.get("label")]
        ep = record_episode(request.title, request.concepts, at=request.at,
                            place=request.place, observations=obs, salience=request.salience)
        return {"recorded": True, "episode": ep}
    except Exception as exc:
        return {"recorded": False, "reason": f"{type(exc).__name__}"}


class PerceptionRequest(BaseModel):
    episode_id: str = Field(min_length=1)
    label: str = Field(min_length=1, max_length=200)
    modality: str = "vision"
    dwell_seconds: float = 0.0
    revisits: int = 0
    gaze_ratio: float = 1.0
    utterance: str = ""


@router.post("/episode/perception")
def base_brain_episode_perception(request: PerceptionRequest) -> dict[str, Any]:
    """The smart-glasses / camera entry point: report WHAT was seen and the
    BEHAVIOUR around it (dwell, revisits, gaze). Interest is INFERRED here —
    lingering = caring — and stored with its behavioural basis (auditable, not
    mind-reading). No glasses yet; this is the ready socket."""
    try:
        from packages.graph_scale.episodic_memory import record_perception, salience_from_behavior

        ok = record_perception(request.episode_id, request.label, modality=request.modality,
                               dwell_seconds=request.dwell_seconds, revisits=request.revisits,
                               gaze_ratio=request.gaze_ratio, utterance=request.utterance)
        return {"recorded": ok, "inferred_salience": salience_from_behavior(
            request.dwell_seconds, revisits=request.revisits, gaze_ratio=request.gaze_ratio)}
    except Exception as exc:
        return {"recorded": False, "reason": f"{type(exc).__name__}"}


class EnrichRequest(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    episode_id: str = ""
    context: list[str] = Field(default_factory=list)


@router.post("/episode/enrich")
def base_brain_episode_enrich(request: EnrichRequest) -> dict[str, Any]:
    """' ?' — fuse a faint remembered label (what the
 glasses roughly recognized) with a LIVE web search to pin the exact identity
 and surface an image or a SPLATRA render hint. Keeps remembered vs web-confirmed
 separate; fabricates nothing when the web finds nothing."""
    try:
        from packages.graph_scale.memory_enrich import enrich, enrich_episode_observation

        if request.episode_id:
            return {"available": True, **enrich_episode_observation(request.episode_id, request.label)}
        return {"available": True, **enrich(request.label, request.context)}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.post("/episode/consolidate")
def base_brain_episode_consolidate() -> dict[str, Any]:
    """Background memory consolidation (osaurus salience-scored memory + the brain's
    salience compression): dull old episodes fade, vivid ones persist (half-life
    scales with salience), double-logged moments merge. Salience governs MEMORY,
    never the truth threshold for assertions."""
    try:
        from packages.graph_scale.episodic_memory import consolidate

        return {"available": True, **consolidate()}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.post("/episode/complete")
def base_brain_episode_complete(request: RecallRequest) -> dict[str, Any]:
    """Predictive interjection: from a vague ' …' + the concepts
 pinned so far, recall the most likely episode and voice it AS A QUESTION,
 surfacing what the glasses saw. Returns {available:false} (abstain) when no
 episode confidently matches — never a guessed memory."""
    try:
        from packages.graph_scale.episodic_memory import complete

        comp = complete(request.partial, request.focus)
        return {"available": bool(comp), **(comp or {})}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.get("/intuition/spark")
def base_brain_intuition_spark(energy: float | None = None, seed: int | None = None
                              ) -> dict[str, Any]:
    """System 1, observable: displace concepts along learned relation directions
    (energy-scaled) and surface the distant concepts they land on — grounded
    cross-domain leaps. Each is a QUESTION (an analogy to investigate), never a
    fact. When energy is omitted it is DERIVED FROM THE LIVE HORMONE STATE, so
    inspiration waxes and wanes with the self's arousal (higher = wilder leaps)."""
    try:
        from packages.graph_scale.answer_bridge import _store
        from packages.graph_scale.intuition_spark import energy_from_hormones, spark

        hormones = _live_hormones()
        if energy is None:
            e = energy_from_hormones(hormones)
            src = "hormones" if hormones else "baseline"
        else:
            e = max(0.0, min(1.5, float(energy))); src = "explicit"
        sparks = spark(_store(), energy=e, seed=seed)
        return {"available": True, "energy": e, "energy_source": src,
                "hormones": hormones, "sparks": sparks, "count": len(sparks),
                "written_to_production": False,
                "note": "hypotheses (questions) only — validated by evidence gates, never asserted"}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.get("/intuition/collide")
def base_brain_intuition_collide(a: str, b: str) -> dict[str, Any]:
    """Force two named concepts from different domains to meet and observe the
 machine's proposed connective tissue (concepts that resonate with BOTH). The
 pair is ledgered as a QUESTION, never a fact. e.g. a=&b=."""
    try:
        from packages.graph_scale.answer_bridge import _store
        from packages.graph_scale.intuition_spark import collide

        return collide(_store(), a.strip(), b.strip())
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.get("/intuition/predict")
def base_brain_predict_fact(subject: str) -> dict[str, Any]:
    """Next-FACT prediction: instead of forfeiting on a store miss, the trained
 phase geometry proposes the most probable MISSING edge for the subject as a
 HEDGED, source-tagged hypothesis (never a confirmed fact). ' 
 .' The score is an uncalibrated model signal, labeled as such."""
    try:
        from packages.graph_scale.answer_bridge import _store
        from packages.graph_scale.fact_prediction import mint_predicted_fact, predict_missing_edges

        subj = subject.strip()
        preds = predict_missing_edges(subj, store=_store(), k=5)
        minted = mint_predicted_fact(subj, store=_store()) if preds else None
        return {"available": True, "subject": subj, "predictions": preds,
                "realization": (minted or {}).get("text"),
                "written_to_production": False,
                "note": "labeled hypotheses (phase-space link prediction), not confirmed facts"}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.get("/relation-extract")
def base_brain_relation_extract(sentence: str, lang: str = "en") -> dict[str, Any]:
    """Relation extractor v3 (rule × topology): pull higher-order (s, p, o)
    triples from a sentence and score each with the phase-space geometry gate.
    Structural extraction, gated — nothing written here."""
    try:
        from packages.graph_scale.relation_extractor import extract_triples, topology_score

        triples = extract_triples(sentence.strip()[:500], lang=lang)
        for t in triples:
            t["topology"] = topology_score(t["s"], t["p"], t["o"])
        return {"available": True, "sentence": sentence.strip()[:500],
                "triples": triples, "count": len(triples)}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.get("/codebase/criticality")
def base_brain_codebase_criticality(name: str) -> dict[str, Any]:
    """How VITAL a module/function is to ATANOR's survival — measured from the real
    call graph (how many things depend on it). A self-edit to a vital organ is
    escalated to the user (self-preservation). Run /codebase/ingest first."""
    try:
        from packages.graph_scale.self_preservation import criticality

        return {"available": True, **criticality(name.strip())}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.get("/codebase/about")
def base_brain_codebase_about(name: str) -> dict[str, Any]:
    """What ATANOR knows about its OWN code — a module/function/class: what it is,
    what it calls, how it's documented, and where it's referenced. Structural
    self-knowledge from AST (not code meaning). Run /codebase/ingest first."""
    try:
        from packages.graph_scale.codebase_ingest import about

        return {"available": True, **about(name.strip())}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.post("/codebase/ingest")
def base_brain_codebase_ingest() -> dict[str, Any]:
    """Teach ATANOR its own source tree: AST-parse packages/ into structural
    self-knowledge triples (module/function/class/calls/docstrings). Candidate-tier,
    local; never rewrites code."""
    try:
        from packages.graph_scale.codebase_ingest import ingest_codebase

        return {"available": True, **ingest_codebase()}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.get("/autonomy/self-assess")
def base_brain_autonomy_self_assess() -> dict[str, Any]:
    """ATANOR's self-judged autonomy: its EARNED trust (from confirmed vs retired
    predictions + graph health), the tier it recommends for itself, and — crucially
    — the hard ceiling that never moves (irreversible / system-breaking / outward
    actions always need an operator, at any trust). Read-only."""
    try:
        from packages.graph_scale.autonomy_self import HARD_CEILING, recommend_tier, trust_score

        t = trust_score()
        return {"available": True, "trust": t, "recommendation": recommend_tier(t["score"]),
                "hard_ceiling": sorted(HARD_CEILING),
                "note": "trust earns the reversible band; the ceiling requires an operator forever"}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.get("/collective/board")
def base_brain_collective_board() -> dict[str, Any]:
    """The AGORA review board: self-proposed code improvements + swarm tally + the
    three gate states (collective ∧ tests ∧ human). Read-only."""
    try:
        from packages.graph_scale.collective_improve import board, federation_manifest

        return {"available": True, "board": board(),
                "federation_ready": federation_manifest()["count"]}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.get("/collective/manifest")
def base_brain_collective_manifest() -> dict[str, Any]:
    """Improvements that passed ALL THREE gates — the list a human release applies
    to every user's AI. Reports only; never auto-applies code."""
    try:
        from packages.graph_scale.collective_improve import federation_manifest

        return {"available": True, **federation_manifest()}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.get("/graph-regions")
def base_brain_graph_regions() -> dict[str, Any]:
    """The region legend: every ingested source (book/paper/dataset) is its own
    colored bundle in the graph. The viz tints nodes by region_id -> color."""
    try:
        from packages.graph_scale.graph_regions import list_regions

        regions = list_regions()
        return {"available": True, "regions": regions, "count": len(regions)}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}"}


@router.get("/visual-memory/{concept}")
def base_brain_visual_recall(concept: str, learn: bool = False) -> dict[str, Any]:
    """Perceptual grounding v0: the measured visual signature of a concept
    (color bands/palette/texture from REAL photos, provenance attached), as
    particle-scene parameters. learn=true fetches+measures when unknown."""
    try:
        from packages.perception import learn_visual, recall_scene

        scene = recall_scene(concept)
        if scene is None and learn:
            learn_visual(concept, log=lambda *_: None)
            scene = recall_scene(concept)
        return scene or {"kind": "visual_recall", "concept": concept,
                         "known": False}
    except Exception:
        return {"kind": "visual_recall", "concept": concept, "known": False}


@router.post("/benchmark")
def base_brain_benchmark(request: BaseBrainBenchmarkRequest) -> dict[str, Any]:
    return run_zero_user_benchmark(limit=request.limit)


@router.get("/proof")
def base_brain_proof() -> dict[str, Any]:
    return run_base_brain_proof()
