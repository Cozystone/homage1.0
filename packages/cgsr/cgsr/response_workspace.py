# -*- coding: utf-8 -*-
"""Response workspace — the ONE model's answer selection, by grounding competition, not order.

Owner's standing question (2026-07-20, repeated): "다중턴 참여엔진이 따로 필요한가? 다중턴을 실행할
때만 저 엔진을 켜는 건 규칙기반이랑 다를 게 없지 않나? 결국 하나의 '모델' 개념으로 통합돼야 하지 않나?"

He is right, and the honest audit found the residue of exactly what he warned about: the answer path
had grown a chain of ORDERED early-returns (self-causal reasoning, then discussion, then anaphora,
...), where the FIRST lane to match short-circuits the rest. First-match-wins by ORDER is a
mode-switch in disguise — the order, not the understanding, decides who speaks. Worse, two lanes had
begun re-parsing the discussion INDEPENDENTLY (the direct lane with the seat/declaration fix, the
engagement lane without it), so they had already diverged.

This is the same problem the Living Loop's Global Workspace already solved for THOUGHT: many concerns
compete, the best-supported one is broadcast — a single stream, chosen by fit, not by a switch. Here
that principle is applied to RESPONSE: every capability reads the ONE shared perception (the
Understanding, parsed once) and offers a candidate contribution with a GROUNDING score; the
best-grounded candidate wins. A capability with nothing to say returns None and competes for nothing
— so no engine is ever "switched on"; they are all always present, and understanding (grounding),
not order, decides. That is what makes it one model rather than a rule table.

No-LLM, hallucination-0 preserved: each candidate composer already grounds or abstains; the workspace
only chooses among grounded offers. It does not invent; it arbitrates.
"""
from __future__ import annotations

import re
from collections import namedtuple
from dataclasses import dataclass
from typing import Any, Callable

from .relevance_gate import _terms


@dataclass
class Candidate:
    answer: str
    answer_kind: str
    grounding: float          # how well THIS capability's offer is supported (0..1); the bid
    engine_name: str
    # OPTIONAL fluency-surface metadata (M-B1, CO L3 surfacing). `bones` = the grounded triples this
    # answer realizes from; only a bones-carrying, free-form, multi-fact winner is eligible for the
    # fluency surface pass. `reshapeable`: None -> inferred from answer_kind; False -> a FIXED honest
    # form (abstention boilerplate, a verified certificate) that must NEVER be reshaped. NEITHER field
    # participates in winner SELECTION (that stays grounding + engine_name only) — so carrying them can
    # never change WHO wins; they only decide whether the winner's SURFACE may be made more natural.
    bones: list | None = None
    reshapeable: bool | None = None


def _self_causal_candidate(raw_question: str) -> Candidate | None:
    try:
        from packages.self_model.self_causal_reasoner import answer_self_causal
        sc = answer_self_causal(raw_question)
    except Exception:
        return None
    if not sc:
        return None
    return Candidate(sc["answer"], sc["answer_kind"], float(sc.get("confidence", 0.7)),
                     "ATANOR Self-Causal Reasoner")


def _hypothesis_candidate(raw_question: str) -> Candidate | None:
    """A Black-Relay-class deduction (stated candidate set + clearances) -> eliminate to the
    survivor, with proof. Grounded high only when it DETERMINES a single answer; under-determined
    and inconsistent still speak (honestly), at lower grounding, rather than let a guess win."""
    try:
        from packages.situation_model.hypothesis import from_text
        v = from_text(raw_question)
    except Exception:
        return None
    if v is None:
        return None
    grounding = 0.88 if v.determined else 0.5    # a proven single answer outranks ordinary lanes
    return Candidate(v.reply, "hypothesis_elimination", grounding, "ATANOR Deduction")


def _discourse_candidate(understanding: Any) -> Candidate | None:
    """Reuses the discussion ALREADY parsed on the shared Understanding (with the seat/declaration
    perception) — so there is no second, divergent parse. This is the anti-fork guarantee."""
    disc = getattr(understanding, "discussion", None)
    if not disc:
        return None
    try:
        from .discourse_participation import contribute
        contrib = contribute(disc, turn_index=len(disc.get("prior_turns", [])))
    except Exception:
        return None
    if not contrib:
        return None
    # a declaration is a firmer act than an ongoing turn; both are well-grounded in observed turns
    grounding = 0.62 if disc.get("already_declared") else 0.6
    return Candidate(contrib, "discourse_participation", grounding, "ATANOR Discourse")


# a fully-verified multi-hop chain is the strongest grounded contribution the workspace can receive:
# every executed hop carried a real organ certificate and the final answer is a mechanical
# substitution of verified step answers only. It outranks ordinary lanes, but is never 1.0 — the
# deliberation is only as certain as its stated situation grounding.
_DELIBERATION_GROUNDING = 0.9


def _deliberation_grounding(understanding: Any) -> dict | None:
    """The deliberator's input contract is passage/situation-scoped grounding (facts stated in THIS
    context, never smuggled world facts). It rides on the shared Understanding: an upstream organ or a
    situation-bearing client attaches it as ``deliberation_grounding``. Absent it, the deliberator has
    nothing to reason over and bids None — so it is contextual, never a keyword-triggered second
    engine."""
    g = getattr(understanding, "deliberation_grounding", None)
    if g is None and isinstance(understanding, dict):
        g = understanding.get("deliberation_grounding")
    return g if isinstance(g, dict) and g else None


def _deliberation_candidate(understanding: Any, raw_question: str) -> Candidate | None:
    """DELIBERATOR (System-2) as a grounded workspace BIDDER — the multi-hop reasoner competing on
    grounding, never toggled by a keyword.

    It bids ONLY a VERIFIED composite answer: the structural decomposer recognizes the question's
    composite shape (or the caller supplies a declared structural plan), the propose/verify/compose
    chain runs, and a Candidate is offered only when every executed hop grounded with a real
    certificate and the answer composed from verified steps alone. If the shape is unrecognized, no
    grounding is present, or any required hop cannot be grounded, it returns None — the workspace then
    abstains honestly rather than emit an unverified guess (작화 0)."""
    g = _deliberation_grounding(understanding)
    if not g:
        return None                                   # no situation grounding -> nothing to deliberate
    try:
        from packages.deliberator.controller import Deliberation, deliberate
        from packages.deliberator.steps import decompose, SubGoal
    except Exception:
        return None
    try:
        plan = decompose(raw_question, g)             # structural recognition of a known composite shape
    except Exception:
        plan = None
    if plan is None:
        declared = g.get("plan")                      # or a caller-declared structural plan (still no generation)
        if isinstance(declared, list) and declared and all(isinstance(s, SubGoal) for s in declared):
            plan = declared
    if not plan:
        return None
    try:
        res = deliberate(Deliberation(goal=str(raw_question), plan=plan, compose=g.get("compose")))
    except Exception:
        return None
    if res.abstained or not res.answer or not str(res.answer).strip():
        return None                                   # honest abstain — never a fabricated bridge
    guarantees = (res.certificate or {}).get("guarantees", {})
    if not (guarantees.get("every_executed_step_verified")
            and guarantees.get("composed_only_from_verified_steps")
            and not guarantees.get("fabricated_facts", False)):
        return None                                   # defensive: only a fully verified chain may bid
    return Candidate(str(res.answer), "deliberation", _DELIBERATION_GROUNDING, "ATANOR Deliberator")


# ── TEMPORAL (block-universe) BIDDER — V2.1 ─────────────────────────────────────────────────────────
# The learned block-universe view (packages/temporal_reasoning/block_universe.py) wired as a
# LOW-grounding, ALWAYS-hypothesis-tagged workspace bidder. It walks the LEARNED precedence field
# forward (project_forward) or backward (infer_backward) to answer genuinely temporal questions — what
# canonically comes next, what typically led up to an event — and surfaces the result ONLY as a hedged
# projection in block_universe.render_human's own "not a certainty" voice, enforced by epistemic_tier.
# It is strictly ADDITIVE and safe:
#   • it bids ONLY when the question's SHAPE is temporal (an inference-request framing over a
#     forward/backward ordering construction with a substantive anchor); a non-temporal question yields
#     None -> contextual, never a mode-switch (understanding decides, not a keyword firing);
#   • it is FAIL-CLOSED on knowledge: if the learned field has no coverage for the anchor tokens, or the
#     order-confidence is too weak, block_universe returns [] / the step is dropped and the bidder
#     ABSTAINS (None) — it NEVER invents a projection;
#   • its grounding is capped LOW (_TEMPORAL_GROUNDING), strictly below every verified lane, so a
#     projection can never override a grounded answer — it only surfaces when all other lanes abstained.
_TEMPORAL_GROUNDING = 0.45          # strictly below discourse 0.6 < self-causal 0.7 < deliberation 0.9
_MIN_ORDER_CONFIDENCE = 0.6         # a surfaced step must clear this learned-order confidence, else drop

# Closed-class temporal-ordering CONSTRUCTION markers (LAD surface layer: grammar, not world knowledge
# — relevance_gate._FUNCTION already classes before/after/then as function words). These recognize the
# temporal FRAME only; the content ANCHOR comes from the question's focus and ALL order knowledge comes
# from the learned field — never from a content whitelist. Single-word markers match on whole words;
# multi-word markers match as phrases.
_FWD_WORDS = frozenset({"after", "afterward", "afterwards", "next", "following", "follows", "follow",
                        "subsequently", "thereafter", "ensue", "ensues", "ensuing"})
_FWD_PHRASES = ("comes next", "come next", "happens next", "happen next", "what follows",
                "comes after", "come after", "happens after", "happen after")
_BWD_WORDS = frozenset({"before", "precede", "precedes", "preceded", "preceding", "beforehand",
                        "antecedent", "antecedents"})
_BWD_PHRASES = ("led to", "leading to", "leading up to", "lead up to", "gave rise to", "give rise to",
                "caused by", "what caused", "cause of", "prior to", "comes before", "come before",
                "result of", "came before", "brought about", "what brought")
# inference-request framing: an interrogative head, or a predictive imperative anywhere in the text
_INFER_HEADS = frozenset({"what", "which", "who", "when", "how", "why"})
_INFER_VERBS = frozenset({"predict", "forecast", "project", "anticipate", "reconstruct", "trace",
                          "expect", "simulate", "foresee", "extrapolate"})

_TemporalAsk = namedtuple("_TemporalAsk", ["mode", "anchor"])   # mode: 'forward'|'backward'; anchor: focus set


def _is_inference_request(q: str) -> bool:
    """Is this a request for temporal INFERENCE (a question or a predictive imperative), rather than a
    bare declarative that merely happens to contain a temporal word? This is the shape requirement that
    keeps 'I saw her before lunch' or 'add your next contribution' from firing the bidder."""
    ql = (q or "").strip().lower()
    if not ql:
        return False
    if ql.endswith("?"):
        return True
    words = re.findall(r"[a-z']+", ql)
    if words and words[0] in _INFER_HEADS:
        return True
    return any(w in _INFER_VERBS for w in words)


def _temporal_mode(q: str) -> str | None:
    """Recognize the temporal-ordering CONSTRUCTION and its direction from the question's grammar.
    'backward' (trace antecedents) / 'forward' (project successors) / None (no temporal frame)."""
    ql = (q or "").lower()
    words = set(re.findall(r"[a-z']+", ql))
    fwd = bool(_FWD_WORDS & words) or any(p in ql for p in _FWD_PHRASES)
    bwd = bool(_BWD_WORDS & words) or any(p in ql for p in _BWD_PHRASES)
    if bwd and not fwd:
        return "backward"
    if fwd:
        return "forward"          # forward, or ambiguous both -> project (low cap + hedge keep it safe)
    return None


def _temporal_ask(understanding: Any, raw_question: str) -> _TemporalAsk | None:
    """Read the SHARED perception (Understanding.focus) + the question's grammar to decide whether this
    is a genuinely temporal question. Returns a typed ask or None (contextual). Never a keyword whitelist
    over content: the frame is closed-class grammar, the anchor is the perception's content focus, and
    the order knowledge lives entirely in the learned field consulted downstream."""
    q = raw_question or getattr(understanding, "question", "") or ""
    if not _is_inference_request(q):
        return None
    mode = _temporal_mode(q)
    if mode is None:
        return None
    focus = getattr(understanding, "focus", None) or _terms(q)
    if not focus:                                  # no content anchor for the field to walk
        return None
    return _TemporalAsk(mode=mode, anchor=set(focus))


def _shared_block_universe(raw_question: str):
    """Build the block-universe view for THIS query: the shared LEARNED field (canonical order — the
    knowledge) anchored on a question-scoped timeline, so a forward projection anchors on the question's
    own event rather than on unrelated prior turns. Returns None if the substrate is unavailable. This
    is the seam tests override to inject a covered/uncovered toy field."""
    try:
        from packages.temporal_reasoning.unified_timeline import Timeline
        from packages.temporal_reasoning.block_universe import BlockUniverse
    except Exception:
        return None
    try:
        tl = Timeline()
        tl.record("utterance", raw_question or "", who="user")
        return BlockUniverse.over(tl)
    except Exception:
        return None


def _observe_world4d_shadow(ask: _TemporalAsk, raw_question: str) -> bool:
    """Run the sibling World4D observer without entering answer arbitration."""

    import os

    if os.environ.get("ATANOR_WORLD4D_SHADOW", "0") != "1":
        return False
    try:
        from packages.world4d.shadow import submit_temporal_query_shadow

        return submit_temporal_query_shadow(
            question=raw_question,
            direction="forward" if ask.mode == "forward" else "backward",
            anchor_terms=tuple(sorted(ask.anchor)),
        )
    except Exception:
        return False


def _pick_backward_anchor(anchor_terms: set[str], bu: Any) -> str | None:
    """Choose the content token to trace back FROM: the causally-latest (max-phase) focus token the
    field actually knows with real evidence (seen>=3). None -> the field cannot ground any anchor."""
    field = getattr(bu, "field", None)
    if field is None:
        return None
    known = [t for t in anchor_terms if t in field.phase and field.seen.get(t, 0) >= 3]
    if not known:
        return None
    return max(known, key=lambda t: field.phase[t])


def _temporal_candidate(understanding: Any, raw_question: str) -> Candidate | None:
    """The block-universe temporal reasoner as a grounded workspace BIDDER (V2.1).

    Bids ONLY for a genuinely temporal question shape, walks the LEARNED precedence field forward or
    backward, and surfaces the result ONLY as an epistemic-tier-tagged HYPOTHESIS (hedged in
    block_universe's own voice). FAIL-CLOSED: no field coverage or weak order-confidence -> None (never
    a fabricated projection). Grounding is capped LOW so a projection can never override a verified lane
    — it only speaks when everyone else abstained."""
    ask = _temporal_ask(understanding, raw_question)
    if ask is None:
        return None                                # not a temporal question -> contextual, not a mode-switch
    _observe_world4d_shadow(ask, raw_question)      # sibling observer; output is deliberately ignored
    bu = _shared_block_universe(raw_question)
    if bu is None or getattr(bu, "field", None) is None:
        return None                                # no learned substrate -> abstain
    try:
        from packages.temporal_reasoning.block_universe import BlockUniverse
        from packages.temporal_reasoning.unified_timeline import Timeline
        from packages.temporal_reasoning import epistemic_tier as et
    except Exception:
        return None

    render = BlockUniverse(Timeline(), None)       # empty-timeline renderer -> only the hedged lines

    if ask.mode == "forward":
        proj = [p for p in bu.project_forward(horizon=3)
                if p.get("confidence") is not None and p["confidence"] >= _MIN_ORDER_CONFIDENCE]
        if not proj:
            return None                            # fail-closed: field cannot ground a confident next step
        surface = render.render_human(projections=proj)
        tier, kind, conf = et.Tier.PROJECTED, "temporal_projection", proj[0]["confidence"]
    else:  # backward
        anchor = _pick_backward_anchor(ask.anchor, bu)
        if anchor is None:
            return None                            # fail-closed: no known anchor to trace back from
        back = [b for b in bu.infer_backward(anchor, k=3)
                if b.get("confidence") is not None and b["confidence"] >= _MIN_ORDER_CONFIDENCE]
        if not back:
            return None
        surface = render.render_human(backward=back)
        tier, kind, conf = et.Tier.RETRODICTED, "temporal_retrodiction", back[0]["confidence"]

    surface = (surface or "").strip()
    if not surface:
        return None
    try:
        claim = et.enforce(et.tag(surface, tier, conf))   # a projection voiced as bare fact is refused here
    except et.EpistemicViolation:
        return None                                # never surface an unmarked projection (작화 0)
    return Candidate(claim.text, kind, _TEMPORAL_GROUNDING, "ATANOR Block-Universe")


# ── FLUENCY SURFACE PASS — M-B1 (CO L3 tier-preserving surfacing) ───────────────────────────────────
# The fluency realizer (packages/fluency: delex + copy + register, faithfulness proved 1.0 in its own
# tests) wired as an OPTIONAL surface pass over the WINNING workspace answer. It reuses the fluency
# package VERBATIM (no new fact source, no new weights) and it NEVER changes who wins or the grounded
# content — it only re-surfaces a free-form, MULTI-FACT winner in a more natural register, and adopts
# that surface ONLY when fluency's OWN gates all pass:
#   • FAITHFULNESS 1.0  — every content token traces to the winner's bones (fluency_v1.faithfulness),
#     no fabricated token, AND slot-copy 1.0 (every grounded entity placed -> nothing dropped): this is
#     the "identical fact set" gate (no added / removed / changed fact reaches the surface).
#   • FACT-SET == LITERAL — the reshape introduces or drops NO grounded value versus the literal answer.
#   • TIER PRESERVED    — if the literal carries an epistemic hedge (a PROJECTED / RETRODICTED marker),
#     the realized surface MUST still carry it, PROVEN by re-running epistemic_tier.enforce; a
#     realization that dropped the marker is rejected (a projection can never be voiced as bare fact).
#   • FLUENCY UP        — fluency's own proxy (fluency_v1.fluency_proxy) must STRICTLY increase, else the
#     reshape earns nothing and the literal stands.
# ANY failure -> keep the LITERAL answer. This is honesty-first: a fluency output that alters meaning,
# drops a fact, or loses a hedge NEVER reaches output (작화 0 preserved). It is CONTEXTUAL, not always-on:
# a fixed honest form (abstention boilerplate, a verified deliberation certificate, a short determinate
# proof) has no bones or a fixed-form kind and is passed through untouched.

# answer_kinds whose surface string is a FIXED honest form — reshaping would corrupt a load-bearing
# exact wording, so they are never handed to the realizer (a contextual gate, not a keyword switch).
_FIXED_FORM_KINDS = frozenset({
    "abstention", "abstain", "honest_abstention", "no_answer",
    "deliberation",                 # a verified-step certificate composition; the exact string is the proof
    "conversation_control", "meta_instruction",
    "self_causal_reasoning",        # a specific self-model sentence, not multi-fact prose
    "hypothesis_elimination",       # a proof conclusion (a survivor name), not prose to reshape
    "discourse_participation",      # a single conversational turn
})
# NOTE: temporal_projection / temporal_retrodiction are NOT fixed here. The CURRENT temporal bidder
# carries no bones, so it is already excluded by the "no_bones" gate; but a FUTURE bidder that supplies
# the factual body's bones for a projection SHOULD be reshaped WITH its hedge preserved — that is the
# tier-preservation path (_reattach_hedge + _hedge_survives), and blocking the kind would defeat it.

# abstention/boilerplate surfaces that pass through untouched even if a bidder mis-attaches bones
_BOILERPLATE_FRAGMENTS = (
    "i can only speak english", "i don't have", "i do not have", "i'm not able", "i am not able",
    "cannot answer", "i don't know", "i do not know", "no grounded answer",
)

_RESHAPE_REGISTERS = ("neutral", "explanatory", "simple")   # candidate natural surfaces to try

_HedgeMark = namedtuple("_HedgeMark", ["tier", "marker", "confidence"])


def _reshape_eligible(winner: "Candidate") -> tuple[bool, str]:
    """A winner is eligible for the fluency surface pass ONLY if it is a free-form, multi-fact,
    bones-carrying answer that is not a fixed honest form. Returns (ok, reason)."""
    if getattr(winner, "reshapeable", None) is False:
        return False, "explicitly_fixed"
    if winner.answer_kind in _FIXED_FORM_KINDS:
        return False, "fixed_form_kind"
    bones = [b for b in (winner.bones or []) if b]
    if not bones:
        return False, "no_bones"                 # the realizer is bone-driven; no bones -> nothing to re-surface
    if len(bones) < 2:
        return False, "not_multi_fact"           # sparse content is identical by design; nothing to gain
    low = (winner.answer or "").lower()
    if any(frag in low for frag in _BOILERPLATE_FRAGMENTS):
        return False, "boilerplate"
    return True, "eligible"


def _epistemic_hedge_in(text: str, confidence: float | None = None) -> "_HedgeMark | None":
    """Detect an epistemic-tier hedge the literal already carries; returns the tier + canonical marker
    fragment to preserve, or None. Reuses epistemic_tier's OWN canonical fragments (single source of the
    'not a certainty' / 'not a record' wording), so tier-preservation stays in the narrator's voice."""
    try:
        from packages.temporal_reasoning import epistemic_tier as et
    except Exception:
        return None
    low = (text or "").lower()
    proj = et.marker_for(et.Tier.PROJECTED)
    retro = et.marker_for(et.Tier.RETRODICTED)
    if proj and proj in low:
        return _HedgeMark(et.Tier.PROJECTED, proj, confidence)
    if retro and retro in low:
        return _HedgeMark(et.Tier.RETRODICTED, retro, confidence)
    if "not a certainty" in low:                 # terse core still an explicit hedge (PROJECTED class)
        return _HedgeMark(et.Tier.PROJECTED, "not a certainty", confidence)
    if "not a record" in low:
        return _HedgeMark(et.Tier.RETRODICTED, "not a record", confidence)
    return None


def _reattach_hedge(body: str, hedge: "_HedgeMark") -> str:
    """Re-attach the canonical hedge to a realized factual body in block_universe's narrator voice
    ('... — a projection, not a certainty.') if the body does not already carry it."""
    body = (body or "").strip()
    if hedge.marker in body.lower():
        return body
    return f"{body.rstrip(' .')} — {hedge.marker}."


def _hedge_survives(surface: str, hedge: "_HedgeMark") -> bool:
    """PROVE the hedge survived by re-running epistemic_tier.enforce on the realized surface: enforce
    RAISES EpistemicViolation if a HYPOTHESIS-tier claim lacks its marker. A raise -> tier lost ->
    reject the realization (keep the literal). This is the same enforcement the temporal bidder uses."""
    try:
        from packages.temporal_reasoning import epistemic_tier as et
        et.enforce(et.tag(surface, hedge.tier, hedge.confidence))
        return True
    except Exception:
        return False


def _fact_values_present(text: str, bones: list) -> frozenset:
    """The set of grounded bone content-values (subjects/objects) that appear on `text`, using the
    fluency package's OWN value-presence test (handles plural/case morphology). This concrete 'fact set'
    is compared literal-vs-realized so a reshape can neither add nor drop a fact."""
    try:
        from packages.fluency.fluency_v1 import _value_present
    except Exception:
        return frozenset()
    low = (text or "").lower()
    vals: set[str] = set()
    for triple in bones:
        s, r, o = (list(triple) + ["", "", ""])[:3]
        for cell in (s, o):
            c = str(cell).strip().lower()
            if c and _value_present(c, low):
                vals.add(c)
    return frozenset(vals)


# ── NO-DROP SAFETY GATE (CO keystone, 2026-07-22) ───────────────────────────────────────────────────
# The faithfulness gate proves every token in the REALIZED surface traces to the bones (surface -> bones,
# no fabrication). It does NOT prove the reverse: that no fact in the LITERAL was DROPPED. A bones-driven
# reshape of a base-brain answer that leads with a curated PROSE definition ("Kubernetes deploys, scales,
# and operates containers across machines. It is a kind of ...") realizes only the RELATION bones and
# silently drops the definition sentence — a real degradation that still scores faithfulness 1.0, slot 1.0,
# and a HIGHER fluency proxy (measured on the live base pack). This gate closes that hole: a reshape may be
# adopted ONLY if it drops no CONTENT token the literal carried. It only ever REJECTS (keeps the literal),
# so it can never introduce a new adoption — the pure-bone winners the fluency tests exercise (whose literal
# IS the bone realization, nothing extra to drop) are unaffected; a base-brain prose literal with an
# un-bone-able definition is preserved verbatim.

# Function words + the closed set of relation SURFACE words both realizers emit (is-a "kind", "used for",
# "manages", "requires", ...). Excluding them keeps the gate focused on CONTENT values (nouns the reshape
# would drop), and avoids a false reject when the two realizers phrase the same relation slightly
# differently ("is a kind of X" vs "is a X").
_NODROP_STOP = frozenset({
    "the", "a", "an", "this", "that", "these", "those", "some", "any", "each", "every", "all", "both",
    "its", "their", "his", "her", "our", "your", "my",
    "of", "in", "on", "at", "to", "for", "with", "and", "or", "but", "as", "by", "from", "into", "than",
    "then", "so", "across", "over", "under", "between", "among", "per", "via", "up", "out", "off", "also",
    "only", "not", "no", "such", "more", "most", "very",
    "it", "they", "he", "she", "we", "you", "i", "them", "him", "her", "us", "who", "which", "what",
    "whose", "itself", "one", "ones", "there", "here",
    "is", "are", "was", "were", "be", "been", "being", "am", "has", "have", "had", "can", "could", "will",
    "would", "may", "might", "do", "does", "did", "should", "must", "shall",
    # relation surface words (closed function-like set — the predicate lexicon of both realizers)
    "kind", "part", "property", "used", "use", "uses", "using", "manage", "manages", "managed", "enable",
    "enables", "enabled", "require", "requires", "required", "depend", "depends", "contrast", "contrasts",
    "produce", "produces", "produced", "support", "supports", "contain", "contains", "similar", "cause",
    "causes", "example", "related", "relate", "turn", "instance", "consist", "consists", "include",
    "includes", "refers", "refer", "describe", "describes", "means", "mean", "represent", "represents",
})


def _nodrop_content_tokens(text: str) -> frozenset:
    """Content tokens of `text`: alphanumerics >= 3 chars, minus function/relation words, with a light
    plural normalization so 'systems'/'system' and 'containers'/'container' compare equal."""
    out: set[str] = set()
    for tok in re.findall(r"[a-z0-9']+", (text or "").lower()):
        if len(tok) < 3 or tok in _NODROP_STOP:
            continue
        out.add(tok[:-1] if (tok.endswith("s") and len(tok) > 3) else tok)
    return frozenset(out)


def _reshape_drops_content(literal: str, surface: str) -> bool:
    """True when the realized `surface` DROPS a content value the `literal` carried — i.e. the literal
    held facts (a prose definition) the bones could not reconstruct. The subject and every grounded
    object are copy-placed by slot-copy 1.0, so the only tokens that can go missing are literal-only
    content the reshape cannot carry: dropping them is a degradation, so the caller keeps the literal."""
    return bool(_nodrop_content_tokens(literal) - _nodrop_content_tokens(surface))


def _fluency_surface(winner: "Candidate", understanding: Any, raw_question: str) -> tuple[str, dict[str, Any]]:
    """Re-surface the WINNER through the fluency realizer, adopting the natural surface ONLY if every
    fluency gate (faithfulness 1.0 + slot-copy 1.0 + identical fact set + no dropped literal content +
    tier preserved + proxy up) passes; otherwise return the LITERAL answer. Returns
    (surface_text, honest_audit_meta)."""
    literal = winner.answer
    meta: dict[str, Any] = {"attempted": False, "adopted": False, "reason": "not_eligible"}
    ok, why = _reshape_eligible(winner)
    if not ok:
        meta["reason"] = why
        return literal, meta                     # fixed form / no bones -> literal stands (common live case)
    bones = [b for b in winner.bones if b]
    meta.update(attempted=True, reason="attempted", n_bones=len(bones))
    try:
        from packages.fluency import realizer as _R
        from packages.fluency.delex import Grounding
        from packages.fluency.fluency_v1 import (
            faithfulness as _faith, fluency_proxy as _proxy, slot_copy_accuracy as _slot,
        )
        from packages.fluency.register import load_registers, select_register
    except Exception:
        meta["reason"] = "fluency_unavailable"
        return literal, meta

    hedge = _epistemic_hedge_in(literal, winner.grounding)
    grounding = Grounding.from_bones(bones)
    ctx = {"query": raw_question} if raw_question else {}
    try:
        ctx_reg = select_register(ctx, load_registers())
    except Exception:
        ctx_reg = "neutral"
    order = [ctx_reg] + [r for r in _RESHAPE_REGISTERS if r != ctx_reg]

    p_lit, _ = _proxy(literal)
    lit_facts = _fact_values_present(literal, bones)
    tried: list[tuple[str, Any]] = []
    best: tuple[float, str, str, float] | None = None      # (proxy, register, surface, faithfulness)
    content_dropped = False                                # a reshape was rejected for dropping literal content
    for reg in order:
        try:
            body = (_R.realize(bones, register=reg, context=ctx) or "").strip()
        except Exception:
            continue
        if not body:
            continue
        faith, fabricated = _faith(body, grounding)
        slot = _slot(bones, body)
        if faith < 1.0 or fabricated or slot < 1.0:
            tried.append((reg, "faithfulness_or_slotcopy_lt_1"))
            continue                             # an altered or dropped fact -> never surface it
        surface = _reattach_hedge(body, hedge) if hedge else body
        if hedge is not None and not _hedge_survives(surface, hedge):
            tried.append((reg, "tier_marker_lost"))
            continue                             # a projection/inference MUST keep its hedge
        if _fact_values_present(surface, bones) != lit_facts:
            tried.append((reg, "fact_set_changed"))
            continue                             # identical fact set as the literal, or reject
        if _reshape_drops_content(literal, surface):
            tried.append((reg, "literal_content_dropped"))
            content_dropped = True
            continue                             # the bones can't carry the literal's prose def -> keep literal
        p_new, _ = _proxy(surface)
        tried.append((reg, round(p_new, 4)))
        if best is None or p_new > best[0]:
            best = (p_new, reg, surface, faith)
    meta.update(registers_tried=tried, proxy_literal=round(p_lit, 4),
                hedge_tier=(hedge.tier.value if hedge else None))
    if best is None:
        meta["reason"] = "literal_content_dropped" if content_dropped else "no_faithful_surface"
        return literal, meta
    p_new, reg, surface, faith = best
    meta.update(register=reg, proxy_realized=round(p_new, 4), faithfulness=round(faith, 4))
    try:                                          # transparency only (NOT a gate): the learned verifier's read
        from packages.fluency.verifier import score as _vscore
        meta.update(verifier_literal=round(_vscore(literal), 4), verifier_realized=round(_vscore(surface), 4))
    except Exception:
        pass
    if p_new <= p_lit:
        meta["reason"] = "no_fluency_gain"       # the reshape earned nothing -> keep literal
        return literal, meta
    meta.update(adopted=True, reason="adopted", tier_preserved=(hedge is not None))
    return surface, meta


def compose_response(understanding: Any, raw_question: str,
                     extra: list[Callable[[], Candidate | None]] | None = None) -> dict[str, Any] | None:
    """Gather every capability's grounded offer for THIS perception and return the best, or None if
    no capability has a grounded contribution (then the normal answer pipeline stands). Selection is
    by grounding, never by order: reordering the candidate list cannot change the winner.

    `extra` lets more capabilities register without touching this function — the workspace is open,
    the arbitration is fixed."""
    builders: list[Callable[[], Candidate | None]] = [
        lambda: _self_causal_candidate(raw_question),
        lambda: _hypothesis_candidate(raw_question),
        lambda: _discourse_candidate(understanding),
        lambda: _deliberation_candidate(understanding, raw_question),
        lambda: _temporal_candidate(understanding, raw_question),
    ] + list(extra or [])

    candidates: list[Candidate] = []
    for build in builders:
        try:
            c = build()
        except Exception:
            c = None
        if c and c.answer and c.answer.strip():
            candidates.append(c)
    if not candidates:
        return None
    # ties broken deterministically by engine name so the winner never depends on evaluation order
    winner = max(candidates, key=lambda c: (c.grounding, c.engine_name))
    # M-B1: the fluency realizer as an OPTIONAL, faithfulness-gated, tier-preserving surface pass over
    # the WINNER. It never changes who won or the grounded content — it only re-surfaces a free-form
    # multi-fact winner more naturally when every fluency gate passes, else the LITERAL stands.
    surfaced, fluency_meta = _fluency_surface(winner, understanding, raw_question)
    return {
        "answer": surfaced, "answer_kind": winner.answer_kind,
        "confidence": winner.grounding, "engine_name": winner.engine_name,
        "considered": [(c.engine_name, round(c.grounding, 2)) for c in candidates],
        "fluency": fluency_meta,
    }


# ── CO-CENTRAL ROUTING (the keystone) ────────────────────────────────────────────────────────────────
MAIN_ENGINE_NAME = "ATANOR Main"
# The main knowledge answer bids its own honest confidence, capped strictly BELOW the verified reasoning
# lanes so a genuine determined deduction (hypothesis 0.88) or a verified multi-hop deliberation (0.9)
# still wins on ITS shape, while every LOW lane — temporal projection 0.45, discourse 0.6/0.62,
# self-causal 0.7, an under-determined deduction 0.5 — is strictly out-ranked by a solid knowledge answer
# and can never hijack a definitional question. (A named base-brain answer scores 0.85..0.91; the cap
# pins it to 0.85 < 0.88 < 0.9.)
MAIN_GROUNDING_CEILING = 0.85


def route_knowledge_answer(answer: str, answer_kind: str, confidence: float, understanding: Any,
                           raw_question: str, *, bones: list | None = None,
                           ceiling: float = MAIN_GROUNDING_CEILING) -> dict[str, Any]:
    """CO keystone: enter the FINALIZED main knowledge answer into the response workspace as a
    first-class '`MAIN_ENGINE_NAME`' bidder (grounding = min(confidence, ceiling), carrying its grounded
    `bones`) and let the workspace arbitrate it against every specialist bidder — so compose_response
    governs real knowledge traffic instead of being bypassed by it.

    Returns an honest audit ``{answer, answer_kind, confidence, engine_name, won_by, changed, fluency,
    considered}``:
      • ``won_by == 'main'`` — the ordinary case. The knowledge answer won on grounding. ``answer`` is the
        workspace surface, which the fluency no-drop gate keeps IDENTICAL to the literal for a
        curated-prose answer (never degraded); a bone-derived answer may be a faithful (1.0) fluency
        improvement.
      • ``won_by == 'specialist'`` — a specialist genuinely out-grounded the knowledge answer on its own
        shape (deliberation 0.9, determined deduction 0.88); ``answer``/kind/confidence switch to it.
    Never raises: on any failure it returns the input answer unchanged, won_by 'main'."""
    literal = str(answer or "")
    fallback = {"answer": literal, "answer_kind": answer_kind, "confidence": confidence,
                "engine_name": MAIN_ENGINE_NAME, "won_by": "main", "changed": False,
                "fluency": {"attempted": False, "adopted": False, "reason": "routing_unavailable"},
                "considered": []}
    if not literal.strip():
        return fallback
    try:
        capped = min(float(confidence or 0.0), float(ceiling))
        clean_bones = [b for b in (bones or []) if b] or None
        main_bidder = (lambda: Candidate(literal, answer_kind, capped, MAIN_ENGINE_NAME, bones=clean_bones))
        rw = compose_response(understanding, raw_question, extra=[main_bidder])
    except Exception:  # pragma: no cover - routing must never break the answer path
        return fallback
    if not rw:  # main always bids a non-empty answer, so this is a defensive guard only
        return fallback
    won_by = "main" if rw.get("engine_name") == MAIN_ENGINE_NAME else "specialist"
    return {
        "answer": rw["answer"], "answer_kind": rw["answer_kind"], "confidence": rw["confidence"],
        "engine_name": rw["engine_name"], "won_by": won_by,
        "changed": (rw["answer"] != literal) or (won_by == "specialist"),
        "fluency": rw.get("fluency", {}), "considered": rw.get("considered", []),
    }
