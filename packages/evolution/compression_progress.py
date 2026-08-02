# -*- coding: utf-8 -*-
"""Compression-progress drive — a principled interestingness / learning-progress signal
(owner 2026-07-23, X1 of the redirected explosion engine; see
docs/ATANOR_intelligence_explosion_research.md).

WHY THIS FILE REPLACES THE COMPETENCE/NOVELTY HEURISTIC
-------------------------------------------------------
`auto_curriculum.py` paces its own curriculum with a crude self-pacing heuristic (competence =
solve-rate, novelty = fraction-new) and picks targets by blind composition; `structural-curiosity`
elsewhere approximated "interesting" as schema-completion. Tonight's research verdict: the CORE
driver of open-ended self-acceleration is Schmidhuber's COMPRESSION-PROGRESS / LEARNING-PROGRESS
signal — pursue structure that is **learnable-but-not-yet-learned** (maximise the *rate* of
compression improvement), NOT novelty, NOT competence, NOT a neural recogniser.

THE SIGNAL (Schmidhuber, operationalised with our own MDL machinery — No-LLM, information-theoretic)
--------------------------------------------------------------------------------------------------
For a candidate target `t`, estimate the EXPECTED COMPRESSION PROGRESS of learning it: how much
learning `t` (and abstracting from it) would reduce the future description-length / expected
solve-cost, USING THE CURRENT LIBRARY + ABSTRACTION SET AS THE COMPRESSOR. The estimator is a
product of two MDL-anchored factors, each in [0, 1], so BOTH must hold — this is exactly
"learnable-but-not-yet-learned":

    progress(t) = novelty_under_compressor(t)  x  learnable_abstraction(t)

  * novelty_under_compressor(t) = mdl_cost(t | library, abstractions) / raw_len(t)
        The fraction of t's raw description that the CURRENT compressor CANNOT already collapse to a
        reference. ~0 when t is already cheaply expressible (a known block, or a one-op recombination
        of known blocks) — this REJECTS TRIVIAL targets (already-solved => ~0 progress). ~1 when t is
        genuinely new structure.

  * learnable_abstraction(t) = max over library block b of param_value(anti_unify(t, b))
        The value of the best GENUINELY PARAMETERISED abstraction (>=1 hole, non-trivial shared body)
        that anti-unifying t against a known block unlocks — i.e. reusable structure t shares with
        what we already know, expressed as the fraction of t recoverable through that abstraction.
        ~0 when t shares no compressible motif with anything known — this REJECTS NOISE / UNLEARNABLE
        targets (no compressible structure => ~0 progress; also an exact duplicate anti-unifies to
        ZERO holes => not a parameterised abstraction => 0). > 0 only when there is real reusable
        structure to be named.

The MID-FRONTIER (novel AND structurally reachable from the library) is where the product PEAKS —
the learnable-but-not-yet-learned band. Trivial (novelty~0) and noise (learnable~0) both fall to ~0.
The two rejections come from DIFFERENT factors, which is why a single scalar cannot be gamed by
either degenerate extreme.

THIS IS THE SAME SIGNAL AS THE CONSCIOUS ORCHESTRATOR'S VALUE / FELT / INTERESTINGNESS SIGNAL.
`interestingness(candidate, state)` is exposed as the reusable API the CO calls to decide what is
worth attending to / valuable / interesting. Schmidhuber's compression-progress = "what to learn"
(explosion target selection) = "what is interesting / felt-valuable" (the orchestrator's subjective
value signal): one organ, two call-sites (see docs/ATANOR_intelligence_explosion_research.md sec 3).

HONEST SCOPE. This is an APPROXIMATION of the true Schmidhuber signal. The exact signal integrates
the compressor's improvement over the real future data stream; we approximate the future target
distribution by (a) the family's current library as the compressor state and (b) the candidate's
structural neighbourhood (anti-unification against known blocks) as the reachable-abstraction proxy.
It is a *propose*-quality drive (fast, structural), not a verified claim about the future — consistent
with propose-verify: it steers search, it does not promote anything.

SAFETY / No-LLM. Pure structural computation over the whitelisted tuple-tree grammar via
`abstraction.py` (anti_unify / match / size / compression_gain). Nothing is evaluated, exec'd, or
learned from a corpus; no neural component. Total and side-effect-free.
"""
from __future__ import annotations

from typing import Any

from packages.evolution import abstraction as _ab

# ---------------------------------------------------------------------------
# Tree helpers (grammar-agnostic: the same tuple-tree used by code_evolver / open_domain).
# ---------------------------------------------------------------------------


def _is_node(t: Any) -> bool:
    return isinstance(t, (tuple, list)) and len(t) > 0


def raw_len(t: Any) -> int:
    """Plain MDL codelength = node count under the EMPTY compressor (nothing known). This is the
    description length before any library reference is available; `_ab.size` counts non-recursed
    leaves as 1 and each node as 1 (holes count as 1)."""
    return _ab.size(t)


def _hole_nodes(t: Any) -> int:
    """Number of ("hole", i) NODES in a template (a repeated parameter counts each occurrence) — for
    body-size math: body = size(template) - hole_nodes(template)."""
    if not _is_node(t):
        return 0
    if t[0] == _ab._HOLE:
        return 1
    return sum(_hole_nodes(c) for c in t[1:] if _is_node(c))


def _freeze(t: Any) -> Any:
    """Canonical hashable form (JSON round-trips tuples to lists; the grammar uses tuples)."""
    if isinstance(t, list):
        return tuple(_freeze(x) for x in t)
    if isinstance(t, tuple):
        return tuple(_freeze(x) for x in t)
    return t


# ---------------------------------------------------------------------------
# Factor 1 — novelty under the current compressor (MDL codelength ratio).
# ---------------------------------------------------------------------------


def mdl_cost(t: Any, blockset: frozenset, templates: tuple = ()) -> float:
    """Description length of `t` given the current compressor = (library blocks, abstraction
    templates). A subtree that EQUALS a known library block, or is an INSTANCE of a known abstraction
    template, collapses to a single reference token (cost 1 + the cost of any template arguments).
    Everything else pays one token per node plus the cost of its children. This is the honest
    "how expensive is t to express with what I already know" — the compressed codelength.

    Known things are cheap (1), unknown structure is dear (per node): the exact MDL notion the rest
    of the stack uses (schema_induction.mdl_gain = without - (schema + via); abstraction.compression_
    gain = (body-1)*occ)."""
    if not _is_node(t):
        return 1.0
    key = _freeze(t)
    if key in blockset:
        return 1.0                                            # reference a solved block
    best = 1.0 + sum(mdl_cost(c, blockset, templates) for c in t[1:] if _is_node(c))
    for tmpl in templates:
        binds = _ab.match(tmpl, t, {})
        if binds is not None:                                # an instance of a named abstraction
            cand = 1.0 + sum(mdl_cost(arg, blockset, templates) for arg in binds.values())
            if cand < best:
                best = cand
    return best


def novelty_under_compressor(t: Any, blockset: frozenset, templates: tuple = ()) -> float:
    """Fraction of t's raw description the compressor CANNOT already collapse: mdl_cost / raw_len,
    in (0, 1]. ~0 => already cheaply expressible (TRIVIAL: a known block, or known blocks glued by one
    op). ~1 => genuinely new structure. The "not-yet-learned" half of the drive."""
    raw = raw_len(t)
    if raw <= 0:
        return 0.0
    return mdl_cost(t, blockset, templates) / raw


# ---------------------------------------------------------------------------
# Factor 2 — learnable abstraction unlocked (anti-unification against the library).
# ---------------------------------------------------------------------------


def _param_value(tmpl: Any, raw_t: int) -> float:
    """Value of an anti-unified template as a REUSABLE, PARAMETERISED abstraction, as a fraction of t.
    Requires >=1 hole (a genuine parameter — an exact duplicate anti-unifies to ZERO holes and scores
    0) and a non-trivial shared body (>=2 shared nodes). The shared body minus one reference token is
    the number of t's nodes recoverable through the abstraction; divided by (raw_t - 1) it is the
    fraction of t that is reusable structure adapted from a known block. In [0, 1]."""
    holes = _ab.holes_in(tmpl)
    body = _ab.size(tmpl) - _hole_nodes(tmpl)                # shared non-hole structure
    if holes < 1 or body < 2:
        return 0.0
    denom = max(1, raw_t - 1)
    return min(1.0, (body - 1) / denom)


def learnable_abstraction(t: Any, blocks: list, templates: tuple = ()) -> float:
    """How much genuinely reusable, parameterised structure learning t would make nameable — the
    "learnable" half of the drive. For every library block b, anti-unify t against b and value the
    resulting parameterised abstraction; take the best. ~0 when t shares no compressible motif with
    anything known (NOISE / unlearnable, or an exact duplicate => zero holes). > 0 only when there is
    real reusable structure. In [0, 1]."""
    raw_t = raw_len(t)
    best = 0.0
    for b in blocks:
        tmpl = _ab.canonical(_ab.anti_unify(t, b))
        v = _param_value(tmpl, raw_t)
        if v > best:
            best = v
    return best


def _distributional_gain(t: Any, blocks: list) -> int:
    """CORROBORATION (reported, not part of the ranking score): the extra compression that adding t to
    the library unlocks over the DISTRIBUTION already present — the best parameterised motif t shares
    with a block, scored by how many library subtrees it also matches (abstraction.compression_gain).
    A distributional read of "does learning t compress the family", complementary to the pairwise
    anti-unification value. 0 for noise (no recurring motif) and for an exact duplicate (0 holes)."""
    best = 0
    for b in blocks:
        tmpl = _ab.canonical(_ab.anti_unify(t, b))
        if _ab.holes_in(tmpl) < 1 or _ab.size(tmpl) - _hole_nodes(tmpl) < 2:
            continue
        g = _ab.compression_gain(list(blocks) + [t], tmpl)
        if g > best:
            best = g
    return best


# ---------------------------------------------------------------------------
# The drive — expected compression progress = novelty x learnable.
# ---------------------------------------------------------------------------


def compression_progress(t: Any, blocks: list, templates: tuple = ()) -> float:
    """Expected compression progress of learning t, in [0, 1]: the product of the two MDL-anchored
    factors. BOTH must be non-trivial (learnable-but-not-yet-learned) — this is the whole point:
      * TRIVIAL   (already cheaply solvable)  => novelty ~ 0 => progress ~ 0
      * NOISE     (no compressible structure) => learnable ~ 0 => progress ~ 0
      * MID-FRONTIER (novel AND reachable)    => both > 0     => progress PEAKS
    The two rejections come from different factors, so neither degenerate extreme can inflate it."""
    blockset = frozenset(_freeze(b) for b in blocks)
    nov = novelty_under_compressor(t, blockset, templates)
    lrn = learnable_abstraction(t, blocks, templates)
    return nov * lrn


def progress_breakdown(t: Any, blocks: list, templates: tuple = ()) -> dict[str, Any]:
    """The score with its components exposed — for logging, the CO's "why is this interesting",
    and the sealed-gate assertions. Transparent, no hidden state."""
    blockset = frozenset(_freeze(b) for b in blocks)
    nov = novelty_under_compressor(t, blockset, templates)
    lrn = learnable_abstraction(t, blocks, templates)
    return {
        "progress": nov * lrn,
        "novelty_under_compressor": nov,
        "learnable_abstraction": lrn,
        "mdl_cost": mdl_cost(t, blockset, templates),
        "raw_len": raw_len(t),
        "distributional_gain": _distributional_gain(t, blocks),
    }


# ---------------------------------------------------------------------------
# Reusable API — the Conscious Orchestrator's value / felt / interestingness signal.
# ---------------------------------------------------------------------------


def _resolve(candidate: Any, state: Any) -> tuple[Any, list, tuple]:
    """Normalise (candidate, state) into (tree, blocks, templates) so the same signal serves the
    curriculum, a bare tree + explicit compressor, or a Conscious-Orchestrator call.

    candidate may be:
      * a tree (tuple/list)                         — the thing to score
      * {"tree": <tree>, "family": <str>}           — carries its family for a multi-family state
    state may be:
      * a curriculum state {"libraries": {...}, "abstractions": {...}} (+ optional family on candidate
        or state["family"])                         — pull that family's blocks/templates
      * a lightweight compressor {"library"/"blocks": [...], "abstractions"/"templates": [...]} — used
        directly (no family needed) — the general CO form.
    """
    tree = candidate
    family = None
    if isinstance(candidate, dict):
        tree = candidate.get("tree", candidate.get("candidate"))
        family = candidate.get("family")
    state = state or {}
    if family is None:
        family = state.get("family")

    # multi-family curriculum state
    if "libraries" in state:
        libs = state.get("libraries", {})
        absns = state.get("abstractions", {})
        if family is None:
            # single-family convenience: if exactly one family is populated, use it
            populated = [f for f, v in libs.items() if v]
            family = populated[0] if len(populated) == 1 else next(iter(libs), None)
        blocks = list(libs.get(family, []))
        templates = tuple(_template_of(a) for a in absns.get(family, []))
        return tree, blocks, templates

    # lightweight compressor form
    blocks = list(state.get("library", state.get("blocks", [])))
    raw_templates = state.get("abstractions", state.get("templates", []))
    templates = tuple(_template_of(a) for a in raw_templates)
    return tree, blocks, templates


def _template_of(a: Any) -> Any:
    """Accept an abstraction as a bare template tree or a {"template": ...} record."""
    if isinstance(a, dict):
        return a.get("template")
    return a


def interestingness(candidate: Any, state: Any) -> float:
    """THE REUSABLE SIGNAL. Expected compression progress of `candidate` given the compressor in
    `state`, in [0, 1]. Higher = more interesting = more worth learning / attending to.

    This is the SAME organ as the Conscious Orchestrator's value / felt / interestingness signal
    (docs/ATANOR_intelligence_explosion_research.md sec 3): "what is worth learning" (explosion target
    selection) and "what is interesting / subjectively valuable" (the orchestrator's felt value) are
    one and the same compression-progress signal. The CO calls this to decide where to turn attention
    and resources; the curriculum calls it to decide which target to pose next. Standalone-callable
    and deterministic — the same (candidate, state) always yields the same score."""
    tree, blocks, templates = _resolve(candidate, state)
    if tree is None:
        return 0.0
    return compression_progress(tree, blocks, templates)


def rank(candidates: list, state: Any) -> list[tuple[float, Any]]:
    """Score and sort candidates by interestingness (descending). Convenience for target selection and
    for the CO to pick the most valuable option from a set. Ties keep input order (stable sort)."""
    scored = [(interestingness(c, state), c) for c in candidates]
    scored.sort(key=lambda x: -x[0])
    return scored


def most_interesting(candidates: list, state: Any) -> Any:
    """The single argmax-interestingness candidate (or None). The one-line target selector / CO pick."""
    scored = rank(candidates, state)
    return scored[0][1] if scored else None
