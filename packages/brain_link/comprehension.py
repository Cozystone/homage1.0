# -*- coding: utf-8 -*-
"""comprehension — a lightweight, No-LLM COMPREHENSION + SALIENCE scorer that decides, per turn,
*how much to drill vs infer-the-gist-and-continue*, as a CONTINUOUS MIXTURE of discourse modes.

Owner's correction (2026-07-24, the whole point): the place->position->thing "what is X?" regress must
NOT be blocked by a hardcoded generic-word stoplist. It must DISAPPEAR as an EMERGENT consequence of
contextual salience + comprehension — "there is a time to DRILL DOWN and a time to INFER THE GIST AND
CONTINUE." Coordinator refinement: make the mode-fork a CONTINUOUS softmax mixture over four modes with
a MOMENTUM-carrying conversational state vector (leaky integrator + homeostasis), so the mix shifts
SMOOTHLY across turns instead of jerking between boolean branches.

Two layers, both cheap and honest (no model, no store read, no web — pure structure over strings + the
agent's own known-set + its rolling discourse context):

  F1  PER-CONCEPT SALIENCE  salience(c) = centrality(c) x forward_value(c)
        * centrality      subject/genus (central) vs oblique explanatory word (peripheral)
        * forward_value   generic_factor x novelty x (1 - grasp_discount)
            - generic     a SOFT prior over near-empty shell nouns (place/thing/way/kind...). This is
                          ONE weak feature, NOT a stoplist: it only lowers salience, never hard-blocks,
                          and it is deliberately NON-LOAD-BEARING — empty GENERIC_SHELL and the regress
                          still dies (the depth budget + novelty carry it). Proven in the tests.
            - novelty     NEW discourse territory (high) vs a RE-ABSTRACTION of what's already been said
                          (low = the regress signature: a generic word explaining a generic word).
            - grasp       ADJACENT-GROUNDING: if the neighbours already let ATANOR infer the gist, the
                          drill-need drops (you don't pin every word when you already follow the point).

  F2  CONTINUOUS MODE MIXTURE (softmax) over {DRILL, INFER, CONTRIBUTE, REDIRECT}, biased by a
      CONVERSATIONAL STATE VECTOR S = [depth_pressure, breadth_pressure, gravity, momentum] that carries
      MOMENTUM/INERTIA across turns via a leaky integrator with homeostatic decay+bounds — the SAME
      pattern as packages/continuous_self/homeostasis.py (a continuous vector, decayed toward a
      baseline each tick, nudged only by real turn-evidence, clamped, and used to BIAS behaviour, never
      to fabricate content). As the thread accumulates weight, the precision-DRILL proportion rises
      SMOOTHLY (owner: "대화가 무거워지면 정밀 파고들기 비중이 부드럽게 올라감"); as it over-drills, a
      homeostatic REDIRECT release rises and pulls it back — a bounded dynamical system, no thrash.

Honesty (BINDING): this makes the conversational FLOW continuous and natural (a real win). It does NOT
manufacture substance — the ceiling on what ATANOR can *say* is still its graph content. On an empty
topic, CONTRIBUTE has nothing to offer, so the mixture leans INFER (grasp the gist, ask a genuine
forward question) — it never invents a fact to fill the gap.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# F1 — per-concept salience
# ─────────────────────────────────────────────────────────────────────────────────────────────────

# GENERIC shell nouns — a SOFT prior, not a stoplist (see the module docstring). These are the
# semantically near-empty "placeholder" nouns that carry almost no forward value on their own
# (place/thing/way/kind/aspect...). Membership only LOWERS a concept's forward_value and marks a
# generic-explaining-generic re-abstraction; it never removes a word from candidacy, and the anti-
# regress does not depend on this set (empty it and the depth budget + novelty still kill the regress).
# Kept to the UNAMBIGUOUS shells — words with a live drillable sense ('state', 'object', 'concept',
# 'context', 'idea', 'situation') are deliberately EXCLUDED so a real philosophy thread can still drill.
GENERIC_SHELL = frozenset({
    "place", "places", "position", "positions", "thing", "things", "aspect", "aspects",
    "way", "ways", "kind", "kinds", "part", "parts", "case", "cases", "form", "forms",
    "sort", "sorts", "matter", "side", "sides", "point", "points", "area", "areas",
    "manner", "respect", "regard", "notion", "element", "elements", "factor", "factors",
    "feature", "features", "stuff", "bit", "bits", "piece", "pieces", "portion", "section",
})

# abstract-noun morphology (weight/seriousness of a thread) — Latinate abstractions read as "heavy".
_ABSTRACT_SUFFIX = ("tion", "sion", "ness", "ity", "ism", "ment", "ology", "osophy", "ance",
                    "ence", "ancy", "ency", "hood", "ship", "dom", "ude")

_TOKEN = re.compile(r"[A-Za-z][A-Za-z-]*")
# oblique / prepositional heads: a candidate right after one of these sits in an explanatory backdrop
# slot (peripheral), not the claim's subject/genus. Copula+article heads (is/are a/an/the, means,
# refers to, kind of...) mark the GENUS (central). Closed-class surface syntax — the LAD exception.
_OBLIQUE = {"of", "in", "on", "at", "among", "amongst", "between", "within", "where", "through",
            "by", "with", "for", "from", "into", "about", "across", "relative", "beyond", "around",
            "against", "toward", "towards", "upon", "onto", "than", "as"}
_GENUS_LEAD = {"is", "are", "was", "were", "means", "be", "become", "becomes", "a", "an", "the"}


def is_generic(concept: str) -> bool:
    """SOFT generic-shell membership (a weak feature, never a hard gate). See module docstring."""
    return (concept or "").strip().lower() in GENERIC_SHELL


def is_abstract(concept: str) -> bool:
    """A cheap 'weight/seriousness' signal: a generic shell, an abstract-suffix noun, or a long
    Latinate word reads as heavy. Drives the S-vector 'gravity' component (heavy thread -> precision)."""
    c = (concept or "").strip().lower()
    if not c:
        return False
    if c in GENERIC_SHELL:
        return True
    if any(c.endswith(sfx) and len(c) >= len(sfx) + 3 for sfx in _ABSTRACT_SUFFIX):
        return True
    return len(c) >= 10


def abstractness(concepts) -> float:
    """Fraction of the concepts in play that read as abstract/heavy — the thread's 'gravity' evidence.
    coffee/beans/bird -> ~0 (concrete); consciousness/meaning/existence -> ~1 (heavy)."""
    cs = [c for c in (concepts or []) if str(c).strip()]
    if not cs:
        return 0.0
    return sum(1 for c in cs if is_abstract(c)) / len(cs)


def centrality(concept: str, gloss: str) -> float:
    """How central is `concept` to the peer's claim? GENUS/head (central, ~0.9) vs an OBLIQUE
    explanatory word (peripheral, ~0.35) vs mid (~0.6). Surface syntax only (copula/article/preposition
    heads = closed-class), no parser, no model. 0.6 when the concept is not located in the gloss."""
    if not gloss:
        return 0.6
    toks = [t.lower() for t in _TOKEN.findall(gloss)]
    cl = (concept or "").strip().lower()
    if cl not in toks:
        return 0.6
    idx = toks.index(cl)
    prev = toks[idx - 1] if idx > 0 else ""
    if prev in _OBLIQUE:                                   # "... depends on PLACE" -> backdrop
        return 0.35
    # GENUS: the head noun of a copular predicate — the last content token of the clause, reached
    # through a copula/article lead (allowing intervening adjectives: "is a large human SETTLEMENT").
    tail = toks[idx + 1:]
    is_clause_head = not tail or all(t in _OBLIQUE or t in _GENUS_LEAD for t in tail[:2]) or idx == len(toks) - 1
    lead_window = toks[max(0, idx - 3):idx]
    if is_clause_head and any(w in _GENUS_LEAD for w in lead_window):
        return 0.9
    if any(w in _GENUS_LEAD for w in lead_window):         # post-copular but not the final head
        return 0.7
    return 0.6


def generic_density(recent) -> float:
    """Fraction of the recent discourse that is generic shells — when the last few turns were about
    place/position/thing, the thread is already circling the abstract, so a further generic candidate
    is a re-abstraction rather than new territory."""
    r = [x for x in (recent or []) if str(x).strip()]
    if not r:
        return 0.0
    return sum(1 for x in r if is_generic(x)) / len(r)


def novelty(concept: str, subject: str, recent) -> float:
    """Is drilling `concept` NEW discourse territory (high) or a RE-ABSTRACTION of what's already been
    said (low)? The regress signature is a generic word offered to explain a generic word
    (place -> position -> thing), and re-surfacing a term the discourse already holds. Both read LOW —
    THIS is the emergent regress killer (independent of the generic word LIST: it fires on the PATTERN
    'generic explains generic' and on discourse recurrence, not on any specific word's identity)."""
    c = (concept or "").strip().lower()
    seen = {str(x).strip().lower() for x in (recent or [])}
    if c in seen:                                          # already circulating -> not new
        return 0.2
    if is_generic(concept) and is_generic(subject):        # generic explaining generic = the regress
        return 0.2
    if is_generic(concept) and generic_density(recent) >= 0.5:   # generic amid an abstract circle
        return 0.35
    return 1.0


def adjacent_grounding(instruments, known) -> float:
    """ADJACENT-GROUNDING: fraction of the peer's explanatory words ATANOR already holds. High means the
    gist is inferable from neighbours (low drill-need — you don't pin every word when you follow the
    point). `known(c) -> bool`."""
    ins = [c for c in (instruments or []) if str(c).strip()]
    if not ins:
        return 0.0
    return sum(1 for c in ins if known(c)) / len(ins)


# forward-value factor floors (soft penalties, never zero — a penalised concept can still be drilled
# if it is genuinely central and novel; the mixture, not a gate, decides).
_GENERIC_FLOOR = 0.35
_GRASP_MAX_DISCOUNT = 0.5


def concept_salience(concept: str, subject: str, gloss: str, instruments, known, recent):
    """salience = centrality x forward_value, with forward_value = generic x novelty x (1 - grasp
    discount). Returns a Salience record (score + the factors, for the honest trace)."""
    cen = centrality(concept, gloss)
    gen = _GENERIC_FLOOR if is_generic(concept) else 1.0
    nov = novelty(concept, subject, recent)
    grasp = adjacent_grounding(instruments, known)
    fwd = gen * nov * (1.0 - _GRASP_MAX_DISCOUNT * grasp)
    return Salience(concept=concept, centrality=round(cen, 4), generic=round(gen, 4),
                    novelty=round(nov, 4), grasp=round(grasp, 4),
                    forward_value=round(fwd, 4), score=round(cen * fwd, 4))


@dataclass
class Salience:
    concept: str
    centrality: float
    generic: float
    novelty: float
    grasp: float
    forward_value: float
    score: float


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# F2 — the conversational state vector S (leaky integrator + homeostasis; the hormone-dynamics pattern)
# ─────────────────────────────────────────────────────────────────────────────────────────────────

# S components, all in [0,1]:
#   depth_pressure    — how deep into "what is X?" drilling the thread has gone (rises on DRILL)
#   breadth_pressure  — how much the thread has been widening (rises on CONTRIBUTE / INFER-continue)
#   gravity           — the weight/seriousness of the topic (rises on abstract/heavy exchanges)
#   momentum          — conversational inertia: how DECISIVE the recent mixture has been
_S_COMPONENTS = ("depth_pressure", "breadth_pressure", "gravity", "momentum")
_S_BASELINE = {"depth_pressure": 0.0, "breadth_pressure": 0.0, "gravity": 0.10, "momentum": 0.0}

LAMBDA = 0.60           # leaky-integrator inertia (lambda in S_t = lambda*S_{t-1} + (1-lambda)*evidence)
HOMEO = 0.12            # extra homeostatic pull toward baseline each tick (anti-saturation guard)
_S_CEIL = 0.97          # hard ceiling — S can never fully saturate a mode (anti-runaway guard)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


@dataclass
class ConversationState:
    """The momentum-carrying S vector. Persists on the Agent across turns; updated by a leaky
    integrator with homeostatic decay+bounds — the packages/continuous_self/homeostasis.py pattern
    (a felt STATE, not a stack of dials): nudged only by real turn-evidence, always decaying home,
    always clamped. It BIASES the mode mixture; it never writes answer content."""
    depth_pressure: float = 0.0
    breadth_pressure: float = 0.0
    gravity: float = 0.10
    momentum: float = 0.0

    def as_dict(self) -> dict:
        return {k: round(float(getattr(self, k)), 4) for k in _S_COMPONENTS}

    def update(self, evidence: dict) -> None:
        """One leaky-integrator tick: S_t = lambda*S_{t-1} + (1-lambda)*evidence, then a gentle
        homeostatic pull toward baseline (so an idle component decays home and nothing sticks), then
        clamp under the ceiling. Evidence values are bounded in [0,1], so S is a bounded dynamical
        system — it cannot run away or lock a single mode on."""
        for k in _S_COMPONENTS:
            ev = _clamp01(evidence.get(k, 0.0))
            cur = float(getattr(self, k))
            nxt = LAMBDA * cur + (1.0 - LAMBDA) * ev             # leaky integrator (momentum/inertia)
            nxt = nxt + HOMEO * (_S_BASELINE[k] - nxt)           # homeostatic recovery toward baseline
            setattr(self, k, max(0.0, min(_S_CEIL, nxt)))


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# F2 — mode logits, S-bias, softmax mixture
# ─────────────────────────────────────────────────────────────────────────────────────────────────

DEPTH_BUDGET = 3        # consecutive drills before a homeostatic REDIRECT is forced (the hard bound)
_THETA_INFER = 0.35     # INFER is the gentle default when nothing else is strong

# S-bias coefficients. gravity/depth act as a multiplicative GAIN on the GROUNDED drill-salience
# (amplify a real, salient drill on a heavy thread — owner's "heavy -> precision"), so they can never
# MINT a drill out of a near-zero placeholder salience (that would resurrect the regress). redirect,
# contribute and infer take additive bias (they don't depend on a candidate concept).
_B_GRAVITY_GAIN = 0.90      # heavy topic amplifies a real drill's weight (smoothly)
_B_DEPTH_GAIN = 0.30        # already-deep thread mildly amplifies a real drill...
_B_DEPTH_REDIR = 0.45       # ...but feeds REDIRECT more (homeostatic release > reinforcement); kept
#                             modest so a SINGLE drill does not over-fire "step back" — the streak/budget
#                             term (calibrated to DEPTH_BUDGET) plus the hard bound do the main bounding.
_B_BREADTH_CONTRIB = 0.60   # been widening -> keep contributing
_B_BREADTH_INFER = 0.25     # ...and lean infer-continue
_TAU_BASE = 0.55            # softmax temperature (decisiveness); lowered by momentum (inertia)
_TAU_MIN = 0.35


@dataclass
class ModeMix:
    weights: dict            # {DRILL, INFER, CONTRIBUTE, REDIRECT} summing to 1
    dominant: str
    concept: str             # the salient concept to pin (DRILL/COMPOSITE) or the declined one (INFER)
    composite: bool          # True -> realize as gist-ack + one pinned drill (a real in-turn mixture)
    logits: dict
    saliences: list
    state: dict              # S snapshot (for the honest trace)
    reason: str

    def weight(self, mode: str) -> float:
        return float(self.weights.get(mode, 0.0))


def _softmax(logits: dict, tau: float) -> dict:
    tau = max(1e-3, float(tau))
    items = list(logits.items())
    mx = max(v for _, v in items)
    exps = {k: math.exp((v - mx) / tau) for k, v in items}
    z = sum(exps.values()) or 1.0
    return {k: v / z for k, v in exps.items()}


def decide(subject: str, gloss: str, instruments, *, known, asked, recent, state: ConversationState,
           drill_streak: int, share_due: bool = False, has_known_instrument: bool = False) -> ModeMix:
    """The continuous mode decision. Scores four mode logits from F1 salience, biases them by the
    momentum-carrying S vector, and returns the softmax MIXTURE + the realization hint (dominant /
    composite / declined concept). Does NOT mutate S — the caller updates S with the realized turn's
    evidence (so this stays a pure decision and the trace is reproducible).

      subject               the concept the peer's turn is ABOUT (its claimed subject)
      gloss                 the peer's utterance (for centrality's surface syntax)
      instruments           the content words in the gloss (candidate drill targets)
      known(c)->bool        does ATANOR hold c?          asked                already-asked (lowercased set)
      recent                rolling discourse context    state                the S vector (read-only here)
      drill_streak          consecutive prior drills     share_due            is a CONTRIBUTE (share) ready?
      has_known_instrument  did a CONNECT path already have a target? (kept as-is upstream)
    """
    askable = [c for c in (instruments or [])
               if not known(c) and c.strip().lower() not in {a.lower() for a in (asked or set())}]
    sals = [concept_salience(c, subject, gloss, instruments, known, recent) for c in askable]
    best = max(sals, key=lambda s: s.score) if sals else None
    grasp = adjacent_grounding(instruments, known)

    # ── base logits from F1 ──
    s_drill = best.score if best else 0.0
    s_infer = _THETA_INFER + 0.30 * grasp - 0.20 * s_drill
    s_contrib = 0.50 if share_due else (0.30 if has_known_instrument else 0.12)
    # REDIRECT rises with ACCUMULATED depth — the thread must have actually regressed (we have been
    # drilling) before "let me step back" is honest. A generic SUBJECT only adds once a chain exists
    # (drill_streak >= 1); on the FIRST generic mention the mixture leans INFER (grasp-and-continue),
    # not a premature REDIRECT ("we've been unpacking a while" when we have not).
    subj_generic = is_generic(subject)
    s_redirect = (0.70 * min(1.0, drill_streak / DEPTH_BUDGET)
                  + 0.30 * generic_density(recent)
                  + (0.35 if (subj_generic and drill_streak >= 1) else 0.0))

    # ── S-bias (gravity/depth AMPLIFY a real drill; redirect/contribute/infer take additive bias) ──
    drill_gain = 1.0 + _B_GRAVITY_GAIN * state.gravity + _B_DEPTH_GAIN * state.depth_pressure
    s_drill = s_drill * drill_gain
    s_redirect = s_redirect + _B_DEPTH_REDIR * state.depth_pressure
    s_contrib = s_contrib + _B_BREADTH_CONTRIB * state.breadth_pressure
    s_infer = s_infer + _B_BREADTH_INFER * state.breadth_pressure

    # ── hard homeostatic bound: at/after the depth budget, force the REDIRECT release regardless of
    # salience. This is the LOAD-BEARING, word-list-independent regress bound — even with GENERIC_SHELL
    # emptied, a drill chain cannot exceed DEPTH_BUDGET before the thread is pulled back. ──
    if drill_streak >= DEPTH_BUDGET:
        s_drill *= 0.20
        s_redirect += 1.00

    logits = {"DRILL": max(0.0, s_drill), "INFER": max(0.0, s_infer),
              "CONTRIBUTE": max(0.0, s_contrib), "REDIRECT": max(0.0, s_redirect)}
    tau = max(_TAU_MIN, _TAU_BASE * (1.0 - 0.50 * state.momentum))   # momentum -> more decisive
    weights = _softmax(logits, tau)
    dominant = max(weights, key=weights.get)

    # ── realization hint: a genuinely mixed DRILL+INFER turn -> COMPOSITE (gist-ack + one pinned drill,
    # a real in-turn mixture); otherwise the dominant mode, its minority weight colouring the surface. ──
    ranked = sorted(weights, key=weights.get, reverse=True)
    composite = (best is not None and {ranked[0], ranked[1]} == {"DRILL", "INFER"}
                 and weights[ranked[1]] >= 0.28 and weights["DRILL"] >= 0.28)
    concept = best.concept if best else ""
    reason = (f"dom={dominant} w={{" + ", ".join(f"{k}:{weights[k]:.2f}" for k in
              ('DRILL', 'INFER', 'CONTRIBUTE', 'REDIRECT')) + "}"
              + (f" composite pin={concept}" if composite else ""))
    return ModeMix(weights={k: round(v, 4) for k, v in weights.items()}, dominant=dominant,
                   concept=concept, composite=composite,
                   logits={k: round(v, 4) for k, v in logits.items()}, saliences=sals,
                   state=state.as_dict(), reason=reason)


def turn_evidence(mix: ModeMix, realized_mode: str, concepts_in_play) -> dict:
    """The bounded [0,1] evidence THIS realized turn contributes to S (fed to state.update next).
    Derived from the mixture WEIGHTS (so S evolves smoothly from the actual mix, not a hard label) plus
    the topic's abstractness. A DRILL/COMPOSITE deepens; CONTRIBUTE/INFER widen; abstract concepts add
    gravity; a decisive mixture (peaky weights) adds momentum."""
    w = mix.weights
    drill_w = w.get("DRILL", 0.0) + (0.5 if realized_mode == "COMPOSITE" else 0.0)
    # a REDIRECT/INFER/CONTRIBUTE widens the thread (and lets depth_pressure decay); a DRILL/COMPOSITE
    # deepens it. Derived from the mixture WEIGHTS so S evolves smoothly from the actual mix.
    breadth_w = w.get("CONTRIBUTE", 0.0) + 0.5 * w.get("INFER", 0.0) + 0.5 * w.get("REDIRECT", 0.0)
    return {
        "depth_pressure": min(1.0, drill_w),
        "breadth_pressure": min(1.0, breadth_w),
        "gravity": abstractness(concepts_in_play),
        "momentum": max(w.values()) if w else 0.0,        # peakiness = decisiveness of this turn
    }
