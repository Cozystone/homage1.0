# -*- coding: utf-8 -*-
"""Situation-fact extractor — the grounded bridge from raw NL to the DELIBERATOR's typed grounding.

The gap this closes (measured, V1 seed): the deliberator (packages/deliberator, System-2, verified
multi-hop) is a live workspace bidder, but it only ever fires when an upstream client hand-attaches
``understanding.deliberation_grounding``. On a real free-text question NOTHING populates that shape,
so the deliberator bids None in production. This module reads the user's question/passage and, WHEN
(and only when) it can GROUND every fact a supported reasoning SHAPE needs to a SPAN of the input,
emits exactly the typed grounding dict ``packages.deliberator.steps.decompose`` consumes. Otherwise
it emits nothing and the deliberator stays silent — contextual, never keyword-toggled.

Scope, honestly bounded: ALL THREE shapes the decomposer recognizes, each read end-to-end from raw
NL into its EXISTING typed contract (no new reasoning shape is invented — this is a reader):
  * reach-in-time  "… reach/arrive/deliver … in time?"  -> [mechanism(blocked path) ->
                   relational(detour magnitude) -> arithmetic(magnitude vs. budget)]      (extract)
  * more-than-enough "… more/greater/larger/higher/faster than … enough/minimum?" ->
                   [relational(attr A) -> relational(threshold B) -> arithmetic(A > B)]
                   (extract_more_than_enough)
  * belief-chain   "Will <agent> find/get/search … <entity>?"  -> [belief(where the agent looks) ->
                   mechanism|relational(a property of THAT place)]        (extract_will_find)
extract_grounding tries each in turn; the first that fully grounds (span-traced) wins, else None.
The belief in the belief-chain is COMPUTED by the StateTracker organ from witnessed placements (it
abstains when the agent was never co-present) — a grounded fact, never an inferred one.

BINDING anti-fabrication contract (every guarantee is enforced below, not asserted):
  1. GROUNDED-ONLY. Every FACT placed in the grounding traces to a verbatim SPAN of the input text —
     the blocked-path sentence, the detour entity, the detour magnitude number, the budget number.
     Each is recorded in ``_provenance`` with its (start,end) offset so a caller can re-verify that
     span[start:end] == the stored value. Relation LABELS ("length") are LAD surface-layer relation
     names (the same class as base_brain.relational_lookup.RELATION_VOCAB / mechanism's condition
     cues), NOT world facts — they carry no subject commitment and are the only non-span tokens.
  2. ABSENCE -> ABSTAIN, NEVER INVENT. If any fact the shape needs is not literally in the text, the
     extractor returns None (no grounding) OR emits grounding whose detour edge is NOT a length
     (so the relational hop abstains mid-chain). A missing budget number, a missing blocked-path
     statement, or a detour magnitude that is only referential ("as long as the Nile" — a world
     fact we refuse to smuggle) all yield an honest non-answer. No number is ever guessed.
  3. ONE MODEL, NOT A KEYWORD SWITCH. The shape gate is the decomposer's OWN regex (imported, so it
     can never drift from what decompose() recognizes); a non-reasoning input matches nothing and
     gets no grounding. The reader runs inside the single comprehension pass (perceive), producing
     grounding for reasoning inputs and None for the rest — understanding decides, not a trigger word.
  4. PLAUSIBLE BINDING, ELSE ABSTAIN. A measured magnitude is used as THE DETOUR only when the measured
     entity's own noun phrase carries a detour/alternate surface cue (detour, bypass, alternate, ring
     road, loop, reroute, other route/road/path — LAD span tokens, the same class as _MEASURE_WORD,
     never world facts). A DISTRACTOR measurement of some unrelated entity ("the river is 100 km long")
     is therefore never mis-bound as the detour; and if TWO distinct detour-linked magnitudes are
     stated, the detour is genuinely ambiguous and the extractor abstains rather than pick one. A
     mis-binding is worse than an honest abstain: this guard only ever ABSTAINS MORE than the bare
     reader — it accepts nothing new and adds no fabrication surface.

Neuro-budget: 0 new fact source, 0 learned params. It reuses two already-proved organs verbatim —
mechanism.read_conditions (the blocked-path condition reader) and the deliberator's shape regex —
plus surface regex for the stated magnitude/budget. The facts come only from the passage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# reuse the ORGAN's own blocked-path condition reader — the extractor's notion of "blocked" is
# EXACTLY the mechanism organ's, so a block we extract is a block the mechanism law will fire on.
from packages.situation_model.mechanism import read_conditions, answer_mechanism
# the belief-chain shape (SHAPE 3) runs the SAME theory-of-mind organ the deliberator's belief hop
# runs — so a belief we can extract is a belief that organ actually grounds (or abstains on).
from packages.situation_model.state_tracker import StateTracker

# the shape gate is the decomposer's OWN pattern (imported, never re-declared) so the extractor can
# only ever target a shape decompose() actually recognizes. Fallback keeps perceive total if the
# private name ever moves.
try:                                                       # pragma: no cover - import shim
    from packages.deliberator.steps import _REACH_IN_TIME
except Exception:                                          # pragma: no cover
    _REACH_IN_TIME = re.compile(
        r"\b(reach|arrive|arrives?|get|deliver|make it)\b.*\b(in time|on time|within|"
        r"before the deadline)\b", re.IGNORECASE)


# ── surface cues (LAD layer: measurement units + measure words, NOT world facts) ─────────────────
_DIST_UNIT = (r"(?:km|kilomet(?:er|re)s?|miles?|mi|met(?:er|re)s?|minutes?|mins?|hours?|hrs?|"
              r"blocks?|feet|ft|yards?|yds?)")
_MEASURE_WORD = re.compile(r"\b(?:long|away|far)\b|\bin\s+(?:length|distance|duration)\b", re.I)

# subject NP (1–3 words) + a measure verb + a NUMBER (+ optional unit): "the ring road is 12 km long"
_MEASURE_NUM = re.compile(
    r"\b(?P<subj>[a-z][a-z]*(?:\s+[a-z]+){0,2}?)\s+"
    r"(?:is|was|are|were|measures?|runs?|spans?|stretches?|covers?)\s+"
    r"(?:about\s+|around\s+|roughly\s+|approximately\s+|only\s+|just\s+|some\s+)?"
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>" + _DIST_UNIT + r")?\b", re.I)

# "the length of X is N …" / "the distance of X is N"
_LENGTH_OF = re.compile(
    r"\b(?:length|distance|duration)\s+of\s+(?:the\s+)?"
    r"(?P<subj>[a-z][a-z]*(?:\s+[a-z]+){0,2}?)\s+(?:is|was)\s+(?:about\s+)?(?P<num>\d+(?:\.\d+)?)",
    re.I)

# subject + copula + … + measure word but NO number: a referential/qualitative extent
# ("the detour is as long as the Nile", "the ring road is quite long"). We capture the ENTITY but
# refuse to invent a magnitude — the object edge is deliberately NOT a length, so the hop abstains.
_MEASURE_FRAME = re.compile(
    r"\b(?P<subj>[a-z][a-z]*(?:\s+[a-z]+){0,2}?)\s+(?:is|was|are|were)\s+"
    r"(?P<qual>[a-z][^.?!]*?(?:\blong\b|\baway\b|\bfar\b|\bin\s+length\b))", re.I)

# budget: an operator cue + a NUMBER ("within 20 km", "at most 30 minutes", "under 15")
_BUDGET_OP = re.compile(
    r"\b(?P<cue>at\s+most|no\s+more\s+than|not\s+more\s+than|within|up\s+to|under|less\s+than|"
    r"below|fewer\s+than|no\s+longer\s+than)\s+(?:about\s+|around\s+)?(?P<num>\d+(?:\.\d+)?)", re.I)
# budget stated as a bound NOUN ("the deadline is 30 minutes", "a limit of 25 km")
_BUDGET_NOUN = re.compile(
    r"\b(?:deadline|time\s+limit|limit|budget|maximum|max|cap|allowance)\b"
    r"[^.?!\d]{0,18}?(?P<num>\d+(?:\.\d+)?)", re.I)
_STRICT_CUES = {"under", "less than", "below", "fewer than"}

_ARTICLES = {"the", "a", "an", "this", "that", "these", "those", "his", "her", "its",
             "their", "our", "my", "your", "some", "any", "another", "one"}
_STOP_ENTITY = {"", "it", "this", "that", "these", "those", "them", "there", "here", "you",
                "me", "us", "him", "her", "everything", "anything", "something", "way", "route"}
# ^ 'route'/'way' bare are too generic to be a clean lookup entity; "alternate route" (>=2 words)
#   is fine and passes because the guard only rejects the BARE head.


@dataclass
class Extraction:
    """The extractor's full result: the grounding decompose() consumes (or None), plus the
    span provenance for every fact and a human-readable note on WHY it abstained."""
    grounding: dict[str, Any] | None
    provenance: dict[str, dict] = field(default_factory=dict)
    shape: str | None = None
    note: str = ""


def _span(text: str, sub: str) -> dict | None:
    """Locate ``sub`` as a verbatim (case-insensitive) substring of ``text`` and return its span.
    Returns None if it is not literally present — the caller then treats the fact as ungrounded."""
    if not sub:
        return None
    i = text.lower().find(sub.lower())
    if i < 0:
        return None
    return {"span": text[i:i + len(sub)], "start": i, "end": i + len(sub)}


def _clean_entity(subj: str) -> str:
    toks = [t for t in re.findall(r"[a-z]+", str(subj or "").lower())]
    while toks and toks[0] in _ARTICLES:
        toks = toks[1:]
    return " ".join(toks).strip()


def _num(raw: str) -> Any:
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


# ── detour linkage (LAD surface cues) ────────────────────────────────────────────────────────────
# An entity's measured magnitude is trusted as THE DETOUR only if the entity's OWN noun phrase marks
# it as an alternate/detour. These are span-present surface tokens (the same LAD class as _MEASURE_WORD
# and mechanism's condition cues), NOT world facts — they carry no subject commitment. Requiring an
# INTRINSIC cue (never merely co-present elsewhere in the text) is what stops a distractor measurement
# from borrowing a detour cue that belongs to a different entity.
_DETOUR_CUE = re.compile(
    r"\b(?:detour|by-?pass|alternate|alternative|ring\s+road|loop|re-?route|long\s+way|"
    r"go(?:ing|es)?\s+around|reroute|other\s+(?:route|road|path|way))\b", re.I)


def _is_detour_linked(entity: str) -> bool:
    """True iff the measured entity's own name carries a detour/alternate surface cue. Deliberately
    narrow: linkage must be intrinsic to the entity NP, so a distractor ("the river is 100 km long")
    can never be mis-read as the detour just because a detour word appears elsewhere in the passage."""
    return bool(entity) and _DETOUR_CUE.search(entity) is not None


def _find_detour(text: str, block_place: str) -> tuple[dict | None, str]:
    """Find the detour entity and (if stated) its magnitude, using ONLY entities whose own name marks
    them as a detour/alternate (``_is_detour_linked``). Returns ``(detour, note)`` where ``detour`` is
    {entity, value|None, value_raw|None[, qual]} or None. When ``detour`` is None the note says WHY:

      * a magnitude was measured but of a NON-detour entity  -> distractor -> abstain (never mis-bind);
      * TWO OR MORE distinct detour-linked magnitudes stated -> ambiguous  -> abstain (never guess);
      * nothing measured or framed at all                    -> no magnitude/extent stated.

    A detour-linked measure FRAME with no number yields value=None (entity known, magnitude not given)
    so the relational hop abstains mid-chain — no number is ever invented. This is strictly TIGHTER
    than the bare reader: the set of inputs it grounds is a subset (linked ⊆ any), so it can only ever
    abstain MORE, never less."""
    linked_num: list[dict] = []            # detour-linked numeric magnitudes, deduped by (entity,value)
    any_measured = False                   # SOME entity was measured (possibly only a distractor)
    seen: set[tuple[str, Any]] = set()
    for rx in (_MEASURE_NUM, _LENGTH_OF):
        for m in rx.finditer(text):
            # a bare number needs a measurement CONTEXT (a unit here, or a measure word in the clause)
            unit = m.groupdict().get("unit")
            if rx is _MEASURE_NUM and not unit:
                tail = text[m.start(): m.end() + 12]
                if not _MEASURE_WORD.search(tail):
                    continue
            entity = _clean_entity(m.group("subj"))
            if not _valid_entity(entity) or entity == block_place:
                continue
            any_measured = True
            if not _is_detour_linked(entity):              # a DISTRACTOR measurement -> never bind it
                continue
            val = _num(m.group("num"))
            if (entity, val) in seen:
                continue
            seen.add((entity, val))
            linked_num.append({"entity": entity, "value": val, "value_raw": m.group("num")})
    if len(linked_num) == 1:                               # exactly one detour-linked magnitude -> use it
        return linked_num[0], ""
    if len(linked_num) >= 2:                               # genuine ambiguity -> abstain, do not pick one
        return None, ("detour magnitude ambiguous: two or more distinct detour-linked measurements are "
                      "stated -> abstain rather than pick one")
    # no numeric detour magnitude — is there a detour-linked measure FRAME (entity known, no number)?
    any_framed = False
    for m in _MEASURE_FRAME.finditer(text):
        entity = _clean_entity(m.group("subj"))
        if not _valid_entity(entity) or entity == block_place:
            continue
        any_framed = True
        if _is_detour_linked(entity):
            return ({"entity": entity, "value": None, "value_raw": None,
                     "qual": m.group("qual").strip()}, "")
    if any_measured or any_framed:                         # something was said, but not of a DETOUR
        return None, ("detour magnitude not linked to a detour: the measured entity is not marked as a "
                      "detour/alternate route -> abstain (a distractor binding would be worse)")
    return None, "no detour magnitude/extent stated in the text"


def _valid_entity(entity: str) -> bool:
    if not entity or any(ch.isdigit() for ch in entity):
        return False
    if entity in _STOP_ENTITY:
        return False
    return len(entity) >= 3


def _find_budget(text: str) -> dict | None:
    """Find the time/distance budget: an operator cue + number, or a bound-noun + number. Returns
    {op, threshold, threshold_raw, cue} or None. The operator DIRECTION is read from the cue word
    (a span), so the comparison is grounded, not assumed."""
    m = _BUDGET_OP.search(text)
    if m:
        cue = re.sub(r"\s+", " ", m.group("cue").strip().lower())
        op = "<" if cue in _STRICT_CUES else "<="
        return {"op": op, "threshold": _num(m.group("num")), "threshold_raw": m.group("num"),
                "cue": m.group(0)}
    m = _BUDGET_NOUN.search(text)
    if m:
        return {"op": "<=", "threshold": _num(m.group("num")), "threshold_raw": m.group("num"),
                "cue": m.group(0)}
    return None


def _compose(bindings: dict[str, Any]) -> str:
    """Fixed template over the VERIFIED arithmetic verdict — a mechanical render of ``in_time``,
    never a generated sentence. (Module-level so it is a stable, inspectable callable.)"""
    return "arrives in time" if bindings.get("in_time") else "does not arrive in time"


def extract(text: str) -> Extraction:
    """Read raw NL into the deliberator's reach-in-time grounding, or abstain. Total, never raises."""
    t = text or ""
    if not _REACH_IN_TIME.search(t):
        return Extraction(None, note="not a reach/arrive-in-time reasoning shape")

    cond = read_conditions(t)
    if not cond.blocked:
        return Extraction(None, note="no blocked-path condition stated in the text")
    place = next(iter(cond.blocked))                       # blocked entity (a span; mechanism's _np)
    block_text = cond.blocked[place]                       # the verbatim blocking sentence (a span)

    det, det_note = _find_detour(t, place)
    if det is None:
        return Extraction(None, note=det_note or "no detour magnitude/extent stated in the text")

    bud = _find_budget(t)
    if bud is None:
        return Extraction(None, note="no time/distance budget stated in the text")

    entity = det["entity"]
    # provenance: every FACT -> a verbatim span of the input (relation labels are surface-layer)
    prov: dict[str, dict] = {}
    for role, sub in (("blocked_path", block_text), ("detour_entity", entity),
                      ("budget_threshold", str(bud["threshold_raw"])), ("budget_cue", bud["cue"])):
        s = _span(t, sub)
        if s is None:
            return Extraction(None, note=f"internal: '{role}' did not map to a span")   # never emit an ungrounded fact
        prov[role] = s

    if det["value"] is None:
        # magnitude not given numerically: keep the entity but attach a NON-length edge (the stated
        # qualitative extent) so the length lookup finds no edge and the hop abstains mid-chain —
        # NO number is invented. Situation-scoped (a real row) so no world-store fallback can fire.
        qual = det.get("qual") or "unspecified extent"
        qs = _span(t, qual)
        prov["detour_extent_note"] = qs or {"span": qual, "start": -1, "end": -1}
        detour_facts = [(entity, "length_note", qual)]
    else:
        vs = _span(t, str(det["value_raw"]))
        if vs is None:
            return Extraction(None, note="internal: detour magnitude did not map to a span")
        prov["detour_length"] = vs
        detour_facts = [(entity, "length", det["value"])]

    grounding: dict[str, Any] = {
        "cross_question": f"Can it cross the {place}?",
        "block_text": block_text,
        "detour_query": f"what is the length of the {entity}?",
        "detour_facts": detour_facts,
        "budget_expr": "{detour_len} " + f"{bud['op']} {bud['threshold']}",
        "compose": _compose,
        # private metadata (ignored by decompose(); carried for audit / gate verification)
        "_provenance": prov,
        "_source_text": t,
        "_shape": "reach_in_time",
        "_grounded": det["value"] is not None,             # False => a required magnitude was absent
    }
    return Extraction(grounding, provenance=prov, shape="reach_in_time",
                      note=("complete" if det["value"] is not None
                            else "detour magnitude absent -> relational hop will abstain"))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SHAPE 2 — TWO-ATTRIBUTE COMPARISON ("… more/greater/larger/higher/faster than … enough/minimum?")
# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The decomposer's ``_MORE_THAN_ENOUGH`` recognizes this shape and consumes {attr_a, attr_b,
# compare_expr}, emitting [relational(attr_a) -> relational(attr_b) -> arithmetic(compare_expr)].
# We fill it span-traceably: A is the ONE measured entity whose RELATION_VOCAB attribute carries a
# NUMBER in the text; B is the stated THRESHOLD (minimum/requirement/…) number over the SAME
# comparison dimension. The comparison operator is the LAD-surface comparison word — every first-group
# word (more/greater/larger/bigger/higher/faster) is a strict ">", so the operator is read off the
# surface, never assumed. Same anti-fabrication discipline as reach-in-time: every FACT (the compared
# entity, its magnitude, the threshold noun, the threshold magnitude) is a verbatim SPAN; the relation
# LABEL is LAD-surface (a RELATION_VOCAB name — no subject commitment). Absence -> abstain; two
# measured entities -> ambiguous -> abstain (never mis-bind a distractor); no number is ever invented.

try:                                                       # pragma: no cover - import shim
    from packages.deliberator.steps import _MORE_THAN_ENOUGH
except Exception:                                          # pragma: no cover
    _MORE_THAN_ENOUGH = re.compile(
        r"\b(more|greater|larger|bigger|higher|faster)\b.*\bthan\b.*\b(enough|exceed|meets?|threshold|"
        r"charter|minimum|requirement)\b", re.IGNORECASE)

# The relation-label vocabulary this filter checks against. Derived from the graph so it grows on
# its own, UNION the measurable names below: the store carries `capital`/`author` as edge types but
# not `boiling point`/`atomic mass`, which it knows only as concepts. Filtering to graph predicates
# alone therefore silently dropped every numeric relation and cost the extractor its shapes.
try:
    from packages.base_brain.relational_lookup import graph_relations as _graph_relations
    _RELATION_VOCAB = frozenset(r.replace("_", " ") for r in _graph_relations())
except Exception:                                          # pragma: no cover
    _RELATION_VOCAB = frozenset()

# The MEASURABLE subset of the relation-label vocabulary: relation NAMES that take a numeric magnitude
# (the same LAD surface class as _DIST_UNIT). Kept ⊆ RELATION_VOCAB so the relational organ's
# define-vs-relational gate is FORCED deterministically (never left to a scorer), and so a label here
# can never drift into a non-vocab token the relational lane would refuse.
_NUMERIC_RELATIONS: tuple[str, ...] = (
    "population", "area", "height", "length", "width", "depth", "diameter", "radius",
    "mass", "weight", "density", "gdp", "atomic number", "atomic mass", "atomic weight",
    "boiling point", "melting point", "freezing point", "molar mass")
_ATTR_ALT = "|".join(re.escape(a) for a in sorted(_NUMERIC_RELATIONS, key=len, reverse=True))
_NP2 = r"[a-z][a-z0-9.'\-]*(?:\s+[a-z0-9.'\-]+){0,2}?"
_APPROX = (r"(?:about\s+|around\s+|roughly\s+|approximately\s+|only\s+|just\s+|some\s+|over\s+|"
           r"nearly\s+|at\s+least\s+)?")

# "the <attr> of (the) <entity> is <num>"
_ATTR_OF_NUM = re.compile(
    r"\bthe\s+(?P<attr>" + (_ATTR_ALT or r"(?!x)x") + r")\s+of\s+(?:the\s+)?(?P<subj>" + _NP2 + r")\s+"
    r"(?:is|was|equals?|comes?\s+to|:)\s+" + _APPROX + r"(?P<num>\d+(?:\.\d+)?)", re.I)
# "<entity> has a/an <attr> of <num>"
_HAS_ATTR_NUM = re.compile(
    r"\b(?P<subj>" + _NP2 + r")\s+(?:has|have|had|holds?|carries|boasts?)\s+"
    r"(?:an?\s+)?(?P<attr>" + (_ATTR_ALT or r"(?!x)x") + r")\s+of\s+" + _APPROX + r"(?P<num>\d+(?:\.\d+)?)",
    re.I)
# "<entity>'s <attr> is <num>"
_POSS_ATTR_NUM = re.compile(
    r"\b(?P<subj>" + _NP2 + r")'s\s+(?P<attr>" + (_ATTR_ALT or r"(?!x)x") + r")\s+"
    r"(?:is|was|equals?|:)\s+" + _APPROX + r"(?P<num>\d+(?:\.\d+)?)", re.I)
# a stated QUALITATIVE attribute with NO number ("has a vast area"): entity+attr known, magnitude
# absent -> we attach a NON-numeric note edge so the relational hop abstains mid-chain (no # invented)
_HAS_ATTR_QUAL = re.compile(
    r"\b(?P<subj>" + _NP2 + r")\s+(?:has|have|had)\s+(?:an?\s+)?(?P<qual>[a-z]+)\s+"
    r"(?P<attr>" + (_ATTR_ALT or r"(?!x)x") + r")\b", re.I)

# threshold nouns (LAD surface layer — closed-class comparison-anchor words, the same class as the
# decomposer's own second regex group). A threshold VALUE is a number stated within a short window of
# one of these words.
_THRESHOLD_WORDS = (r"minimum|requirement|threshold|charter|maximum|limit|cap|quota|standard|"
                    r"baseline|allowance|floor|ceiling")
_THRESHOLD_NUM = re.compile(
    r"\b(?P<noun>" + _THRESHOLD_WORDS + r")\b[^.?!\d]{0,20}?(?P<num>\d+(?:\.\d+)?)", re.I)
_THRESHOLD_ANY = re.compile(r"\b(?:" + _THRESHOLD_WORDS + r")\b", re.I)


def _compose_more_than(bindings: dict[str, Any]) -> str:
    """Mechanical render of the VERIFIED comparison verdict (bind name 'verdict'); never generated."""
    return "meets the requirement" if bindings.get("verdict") else "falls short of the requirement"


def _measured_triples(text: str) -> list[dict]:
    """All (entity, attr, value) triples where attr ∈ the numeric relation vocabulary and a NUMBER is
    stated — each entity and value a verbatim span. A threshold-word entity is excluded (that side is
    the threshold, not the compared entity). Deduped by (entity, attr, value)."""
    out: list[dict] = []
    seen: set[tuple[str, str, Any]] = set()
    for rx in (_ATTR_OF_NUM, _HAS_ATTR_NUM, _POSS_ATTR_NUM):
        for m in rx.finditer(text):
            ent = _clean_entity(m.group("subj"))
            attr = re.sub(r"\s+", " ", m.group("attr").strip().lower())
            if not _valid_entity(ent) or _THRESHOLD_ANY.search(ent):
                continue
            val = _num(m.group("num"))
            key = (ent, attr, val)
            if key in seen:
                continue
            seen.add(key)
            out.append({"entity": ent, "attr": attr, "value": val, "value_raw": m.group("num")})
    return out


def extract_more_than_enough(text: str) -> Extraction:
    """Read raw NL into the deliberator's more/greater-than-enough grounding, or abstain. Total."""
    t = text or ""
    if not _MORE_THAN_ENOUGH.search(t):
        return Extraction(None, note="not a more/greater-than-enough comparison shape")
    if not _ATTR_ALT:                                      # no numeric relation vocabulary loaded
        return Extraction(None, note="internal: no numeric relation vocabulary available")

    triples = _measured_triples(t)
    if len(triples) >= 2:                                  # two measured entities -> genuinely ambiguous
        return Extraction(None, note=("more-than comparison ambiguous: two or more measured attributes "
                                      "are stated -> abstain rather than pick one (distractor guard)"))

    # threshold value B: required, and a single distinct value (two distinct thresholds -> ambiguous)
    thr_vals: list[Any] = []
    thr_seen: set[Any] = set()
    thr_noun: str | None = None
    thr_num_raw: str | None = None
    for m in _THRESHOLD_NUM.finditer(t):
        v = _num(m.group("num"))
        if v in thr_seen:
            continue
        thr_seen.add(v)
        thr_vals.append(v)
        if thr_noun is None:
            thr_noun = re.sub(r"\s+", " ", m.group("noun").strip().lower())
            thr_num_raw = m.group("num")
    if len(thr_vals) >= 2:
        return Extraction(None, note=("threshold ambiguous: two or more distinct threshold values are "
                                      "stated -> abstain"))
    if not thr_vals:
        return Extraction(None, note="no threshold value stated in the text")

    if triples:
        a = triples[0]
        a_facts = [(a["entity"], a["attr"], a["value"])]
        a_value_present = True
        a_qual = None
    else:
        # A's magnitude is absent. If the entity+attr is NAMED qualitatively, attach a note edge so the
        # relational hop abstains mid-chain (never invent a number); else there is nothing to compare.
        a = None
        a_qual = None
        for m in _HAS_ATTR_QUAL.finditer(t):
            ent = _clean_entity(m.group("subj"))
            if _valid_entity(ent) and not _THRESHOLD_ANY.search(ent):
                a_qual = {"entity": ent,
                          "attr": re.sub(r"\s+", " ", m.group("attr").strip().lower()),
                          "qual": m.group("qual").strip().lower()}
                break
        if a_qual is None:
            return Extraction(None, note="no measured attribute for the compared entity stated in the text")
        a = a_qual
        a_facts = [(a_qual["entity"], a_qual["attr"] + "_note", a_qual["qual"])]
        a_value_present = False

    attr = a["attr"]
    entity = a["entity"]
    thr_entity = thr_noun or "threshold"
    b_facts = [(thr_entity, attr, thr_vals[0])]            # threshold over the SAME dimension (LAD label)

    # provenance: every FACT -> a verbatim span; relation labels are LAD-surface (exempt)
    prov: dict[str, dict] = {}
    items = [("compared_entity", entity), ("threshold_noun", thr_entity),
             ("threshold_value", str(thr_num_raw))]
    if a_value_present:
        items.append(("compared_value", str(a["value_raw"])))
    for role, sub in items:
        s = _span(t, sub)
        if s is None:
            return Extraction(None, note=f"internal: '{role}' did not map to a span")
        prov[role] = s
    if not a_value_present:
        qs = _span(t, a_qual["qual"])
        prov["compared_extent_note"] = qs or {"span": a_qual["qual"], "start": -1, "end": -1}

    grounding: dict[str, Any] = {
        "attr_a": {"query": f"what is the {attr} of the {entity}?", "facts": a_facts},
        "attr_b": {"query": f"what is the {attr} of the {thr_entity}?", "facts": b_facts},
        "compare_expr": "{a} > {b}",
        "compose": _compose_more_than,
        "_provenance": prov,
        "_source_text": t,
        "_shape": "more_than_enough",
        "_grounded": a_value_present,
    }
    return Extraction(grounding, provenance=prov, shape="more_than_enough",
                      note=("complete" if a_value_present
                            else "compared magnitude absent -> relational hop A will abstain"))


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# SHAPE 3 — BELIEF-CHAIN ("Will <agent> find/get/search/open … <entity>?")
# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The decomposer's ``_WILL_FIND`` recognizes this shape and consumes {belief, second}, emitting
# [belief(where the agent looks) -> mechanism|relational(a property of THAT place)]. We fill it
# span-traceably. The belief is NOT inferred: it is COMPUTED by the already-proved StateTracker organ
# from WITNESSED placements in the passage (it returns a place only when the agent was co-present with
# the placement, else it abstains). So the belief hop's inputs are the passage sentences (spans) plus
# the agent/entity named in the question (spans) — no belief is fabricated. The SECOND hop is grounded
# only when the passage states a property OF the believed place: a locked/blocked condition (mechanism)
# or a "made of X" material (relational). Both are verbatim spans; the believed place FLOWS into the
# second hop through the {place} placeholder. If the belief organ abstains, or no span-traced property
# of the believed place is stated, the extractor returns None — the chain never invents the outcome.

try:                                                       # pragma: no cover - import shim
    from packages.deliberator.steps import _WILL_FIND
except Exception:                                          # pragma: no cover
    _WILL_FIND = re.compile(r"\bwill\s+\w+\s+(find|look|search|open|reach|get)\b", re.IGNORECASE)

# the agent (a proper name) directly after "will"; the sought ENTITY is the object of a
# find/get/search/look(-for)/locate verb ANYWHERE in the question (so "open the box and GET the marble"
# still names the marble as the sought entity, not the box).
_WILL_AGENT = re.compile(r"\bwill\s+(?P<agent>[A-Z][a-z']+)\b", re.I)
_SOUGHT = re.compile(
    r"\b(?:find|get|retrieve|recover|fetch|locate|search\s+for|look\s+for)\s+(?:the\s+|her\s+|his\s+|"
    r"their\s+|its\s+|a\s+|an\s+)?(?P<obj>[a-z][a-z']*(?:\s+[a-z']+){0,2}?)\b", re.I)


def _compose_will_find_material(bindings: dict[str, Any]) -> str:
    """Mechanical render: where the agent looks (verified belief) + that place's verified material."""
    return f"will look in the {bindings.get('place')}, which is made of {bindings.get('outcome')}"


def _compose_will_find_mechanism(bindings: dict[str, Any]) -> str:
    """Mechanical render: where the agent looks + the verified mechanism outcome for that place."""
    out = str(bindings.get("outcome")).strip().lower()
    verdict = "cannot open it (locked, key inside)" if out in ("no", "false") else str(bindings.get("outcome"))
    return f"will look in the {bindings.get('place')}, but {verdict}"


def _lock_sentence(text: str, place: str) -> str | None:
    """The verbatim passage sentence stating the believed place is locked (a span). read_conditions
    stores ``locked[place]=True`` (a flag, not the sentence), so we recover the sentence here for
    provenance — the exact text the mechanism law reads its 'locked' condition from."""
    for raw in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        s = raw.strip()
        low = s.lower()
        if place in low and re.search(r"\block(?:ed|s)?\b", low):
            return s
    return None


def _will_find_sentences(text: str) -> list[str]:
    """Narrative sentences (spans) fed to the belief organ — every sentence of the passage EXCEPT the
    question itself (so 'Will <agent> …' never registers a spurious agent/placement)."""
    out: list[str] = []
    for raw in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        s = raw.strip()
        if s and not _WILL_FIND.search(s):
            out.append(s)
    return out


def extract_will_find(text: str) -> Extraction:
    """Read raw NL into the deliberator's belief-chain grounding, or abstain. Total, never raises."""
    t = text or ""
    if not _WILL_FIND.search(t):
        return Extraction(None, note="not a will-find belief-chain shape")

    am = _WILL_AGENT.search(t)
    sm = _SOUGHT.search(t)
    if not am or not sm:
        return Extraction(None, note="could not name the agent and the sought entity as spans")
    agent = am.group("agent").strip()
    entity = _clean_entity(sm.group("obj"))
    if not _valid_entity(entity):
        return Extraction(None, note="the sought entity is not a clean lookup entity")

    sentences = _will_find_sentences(t)
    if not sentences:
        return Extraction(None, note="no narrative sentences to establish the belief")

    # RUN the belief organ (the same one the deliberator will run) to find WHERE the agent looks. This
    # is grounding, not inference: the organ returns a place only from a witnessed placement, else None.
    tracker = StateTracker()
    for i, s in enumerate(sentences):
        tracker.ingest(s, i)
    bel = tracker.believes(agent, entity)
    if bel is None:
        return Extraction(None, note=(f"belief ungrounded: {agent} was never co-present with a stated "
                                      f"placement of the {entity} -> abstain"))
    place, bel_ev = bel                                    # place is _np'd (lowercase, no article)

    # SECOND HOP — a property OF the believed place, span-traced. Prefer a mechanism condition
    # (locked+key / blocked), else a stated material. If neither is stated -> abstain.
    cond = read_conditions(t)
    second: dict[str, Any] | None = None
    second_prov_span: str | None = None
    second_compose = None
    if place in cond.locked and cond.key_inside:
        # verify the law actually fires on the believed place (never assume it)
        probe = answer_mechanism(f"Can {agent} open the {place}?", t)
        lock_sent = _lock_sentence(t, place)
        if probe and probe.get("supported") and lock_sent is not None:
            second = {"organ": "mechanism",
                      "description": f"Can {agent} open the {{place}}?",
                      "payload": {"question": f"Can {agent} open the {{place}}?", "text": t}}
            second_prov_span = lock_sent                    # the verbatim locking sentence (a span)
            second_compose = _compose_will_find_mechanism
    if second is None:
        mat_rx = re.compile(r"\b" + re.escape(place) + r"\b\s+(?:is|was)\s+made\s+of\s+"
                            r"(?:the\s+)?(?P<mat>[a-z][a-z]*)", re.I)
        mm = mat_rx.search(t)
        if mm:
            material = mm.group("mat").strip().lower()
            second = {"organ": "relational",
                      "description": "what is the {place} made of?",
                      "payload": {"query": "what is the {place} made of?",
                                  "facts": [(place, "made_of", material)]}}
            second_prov_span = mm.group(0)
            second_compose = _compose_will_find_material
    if second is None:
        return Extraction(None, note=(f"no span-traced property of the believed place ('{place}') is "
                                      f"stated (no locked/blocked condition, no material) -> abstain"))

    # provenance: agent, entity, the belief-supporting sentence, and the second-hop sentence are spans
    prov: dict[str, dict] = {}
    prov_items = [("agent", agent), ("sought_entity", entity), ("believed_place", place),
                  ("belief_evidence", bel_ev), ("second_hop_fact", second_prov_span)]
    for role, sub in prov_items:
        s = _span(t, sub) if sub else None
        if s is None:
            return Extraction(None, note=f"internal: '{role}' did not map to a span")
        prov[role] = s

    grounding: dict[str, Any] = {
        "belief": {"description": f"where does {agent} think the {entity} is?",
                   "payload": {"sentences": sentences, "kind": "believes",
                               "agent": agent, "entity": entity}},
        "second": second,
        "compose": second_compose,
        "_provenance": prov,
        "_source_text": t,
        "_shape": "will_find",
        "_grounded": True,
    }
    return Extraction(grounding, provenance=prov, shape="will_find", note="complete")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# DISPATCH — try each supported reasoning shape in turn; the first that grounds wins (else None).
# ══════════════════════════════════════════════════════════════════════════════════════════════════

_SHAPE_EXTRACTORS = (extract, extract_more_than_enough, extract_will_find)


def extract_grounding(text: str) -> dict | None:
    """Return the typed grounding for whichever supported reasoning shape THIS text fully grounds
    (span-traced), else None. Each shape gate is the decomposer's OWN regex, so the reader can only
    ever target a shape decompose() recognizes; a non-reasoning input grounds nothing."""
    try:
        for fn in _SHAPE_EXTRACTORS:
            g = fn(text).grounding
            if g is not None:
                return g
        return None
    except Exception:
        return None
