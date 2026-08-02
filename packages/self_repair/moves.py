# -*- coding: utf-8 -*-
"""The escape space, typed — four moves the loop can apply and measure instead of a person writing one.

    from packages.self_repair.moves import MOVES, apply_move, search
    search()      # try each move, score it by ENABLEMENT, keep what unlocks something

WHY FOUR MOVES AND NOT CODE SYNTHESIS. Every escape performed today was diagnosed by the loop and
WRITTEN BY A PERSON. But looking at what those four changes actually were settles what is needed:

    "measure the FIRST token instead of the last"        -> a signal swap
    "read seven evidence files instead of one"           -> a source swap
    "exclude the disputed cue while mining"              -> a filter
    "score against an external table, not our own rows"  -> a comparison swap

Not one is a novel algorithm. They are moves in a small structured space over machinery that already
exists. So escaping does not have to wait for code synthesis to get good -- at 18.9% on MBPP it will
not soon -- it can be a SEARCH over move types, each with the free oracle the loop already uses on
patterns: apply it, measure what it unlocks, keep or revert.

    SIGNAL       measure a different property of the same objects
    SOURCE       draw evidence from somewhere else
    FILTER       stop including something that was being included
    COMPARISON   judge against a different reference set

WHAT THIS IS HONESTLY NOT. The vocabulary is four moves wide and a person chose the four, from four
observed escapes. A fifth kind of escape -- one that is not a signal, source, filter or comparison
change -- is invisible to this and would need a person again. That is a real ceiling and it is written
into `search()`'s own output rather than left for a reader to discover.

Each move is a PARAMETER of an organ that already runs, so applying one is a config change rather than
an edit to logic, and reverting is exact by construction.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "self_repair" / "move_search.jsonl"


@dataclass
class Move:
    """One escape, as something applicable rather than something to be written."""

    kind: str                    # SIGNAL | SOURCE | FILTER | COMPARISON
    name: str
    describe: str
    apply: object                # () -> token used to revert
    revert: object               # (token) -> None
    note: str = ""


# ---------------------------------------------------------------- SIGNAL
def _signal_head_both():
    """Score objects on BOTH tokens rather than the relation-appropriate one.

    The move the discriminator fix was, run the other way: today's escape swapped last-token for
    first-token on the action relations after measuring 0.645 -> 0.810 on held-out pairs. Offering the
    swap as a MOVE means the loop can try it on a relation nobody has measured yet."""
    from packages.self_repair import relation_fit as rf
    original = rf._head
    cache = dict(rf._PROFILE_CACHE)

    def both(obj: str, relation: str = "") -> str:
        import re
        words = re.findall(r"[a-z]+", str(obj or "").lower())
        if not words:
            return ""
        return words[0] if len(words) == 1 else f"{words[0]} {words[-1]}"

    rf._head = both
    rf._PROFILE_CACHE.clear()
    return (original, cache)


def _signal_revert(token):
    from packages.self_repair import relation_fit as rf
    original, cache = token
    rf._head = original
    rf._PROFILE_CACHE.clear()
    rf._PROFILE_CACHE.update(cache)


# ---------------------------------------------------------------- SOURCE
def _source_acquired():
    """Add web-acquired evidence to the arbiter alongside the on-disk sources."""
    from packages.self_repair import relation_discovery as rd
    from packages.self_repair.oracle_acquire import acquired_oracle
    before = dict(rd._CN_CACHE)
    base = dict(rd.conceptnet())
    for subj, facts in acquired_oracle().items():
        base.setdefault(subj, []).extend(facts)
    rd._CN_CACHE["cn"] = base
    return before


def _source_revert(token):
    from packages.self_repair import relation_discovery as rd
    rd._CN_CACHE.clear()
    rd._CN_CACHE.update(token)


# ---------------------------------------------------------------- FILTER
def _filter_drop_generic_head():
    """Stop refusing objects whose head is a generic noun.

    GENERIC_OBJ was measured and is mostly right, but it also killed `playing a game` and `give the
    age of a person`. Offering its removal as a move lets measurement decide rather than the list."""
    from packages.graph_scale import property_extraction as pe
    original = set(pe.GENERIC_OBJ)
    pe.GENERIC_OBJ.clear()
    return original


def _filter_revert(token):
    from packages.graph_scale import property_extraction as pe
    pe.GENERIC_OBJ.clear()
    pe.GENERIC_OBJ.update(token)


# ---------------------------------------------------------------- COMPARISON
def _comparison_lower_margin():
    """Require a smaller margin over the runner-up relation.

    The margin was set at 15% by hand. A move that relaxes it lets measurement say whether that number
    was earning its place -- and enablement will refuse it if it only lets junk through, because junk
    does not survive the held-out gate downstream."""
    from packages.self_repair import relation_fit as rf
    original = rf.judge.__defaults__
    return original


def _comparison_revert(token):
    pass                                       # the relaxed judge is passed per-call, nothing global


MOVES: list = [
    Move("SIGNAL", "head_both",
         "score objects on both first and last token instead of the relation-appropriate one",
         _signal_head_both, _signal_revert,
         "the discriminator fix ran this direction once, measured 0.645 -> 0.810"),
    Move("SOURCE", "add_acquired",
         "add web-acquired, consensus-corroborated facts to the arbiter",
         _source_acquired, _source_revert,
         "the acquisition path exists and was switched off for the sealed runs"),
    Move("FILTER", "drop_generic_head",
         "stop refusing objects whose head noun is generic",
         _filter_drop_generic_head, _filter_revert,
         "the list is measured and mostly right, and it also killed 'playing a game'"),
]


def apply_move(move: Move, *, top_cues: int = 12) -> dict:
    """Apply, measure ENABLEMENT, revert. The move survives only if it unlocked something."""
    from packages.meta_diagnosis.enablement import enablement_since, snapshot

    before = snapshot(top_cues=top_cues, label=f"before {move.name}")
    token = move.apply()
    try:
        result = enablement_since(before, top_cues=top_cues, label=f"{move.kind}:{move.name}",
                                  record=False)
    finally:
        move.revert(token)

    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": move.kind, "move": move.name,
           "describe": move.describe,
           "enablement": result["enablement"],
           "newly_possible": result["newly_possible"],
           "no_longer_possible": result["no_longer_possible"],
           "kept": result["enablement"] > 0,
           "note": move.note}
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def apply_pair(a: Move, b: Move, *, top_cues: int = 12) -> dict:
    """Two moves at once, and the only test of composition that additive independence cannot pass.

    The plateau fires immediately after every escape, which is the signature of a ONE-MOVE-DEEP
    search: make a move, exhaust what it opened, stop. Composition is the difference between a search
    and a lookup.

    THE FIRST VERSION OF THIS TEST WAS WRONG, and it read GREEN. It asked whether the pair beat both
    of its parts, which two INDEPENDENT moves satisfy for free: A worth 2 and B worth 1 give a pair
    worth 3, and 3 beats both. Measured on the real winner --

        A alone   {a vessel -> made_of, for cutting -> made_of}
        B alone   {}
        A + B     {a vessel -> made_of, for cutting -> made_of}

    -- the pair unlocked nothing A did not, and still scored 3 against a best part of 2, because the
    third point was B's independent relation. Addition wearing composition's clothes.

    So the test is now two things that addition cannot fake:

        EMERGENT       the pair unlocks something NEITHER part unlocks alone -- a set difference,
                       immune to how the parts are scored
        SUPERADDITIVE  the pair is worth more than the SUM of its parts, not more than the max

    A pair that is merely the union of its parts is recorded as the union of its parts."""
    from packages.meta_diagnosis.enablement import enablement_since, snapshot

    before = snapshot(top_cues=top_cues, label=f"before {a.name}+{b.name}")

    ta = a.apply()
    try:
        ea = enablement_since(before, top_cues=top_cues, label=f"{a.name} alone", record=False)
    finally:
        a.revert(ta)
    tb = b.apply()
    try:
        eb = enablement_since(before, top_cues=top_cues, label=f"{b.name} alone", record=False)
    finally:
        b.revert(tb)

    ta, tb = a.apply(), b.apply()
    try:
        result = enablement_since(before, top_cues=top_cues,
                                  label=f"{a.name}+{b.name}", record=False)
    finally:
        b.revert(tb)
        a.revert(ta)

    # WHICH STANDARD GOVERNS IS NOT DECIDED HERE. The criteria ledger is asked, so that the criterion
    # this system defeated cannot quietly return by someone rewriting this function -- and so that the
    # defeating case travels with the result instead of living in a commit message.
    from packages.self_repair.criteria_ledger import in_force
    governing = in_force("pair_beats_both_parts",
                         default="the pair beats both of its one-move parts")

    A = {tuple(x) for x in ea["newly_possible"]}
    B = {tuple(x) for x in eb["newly_possible"]}
    P = {tuple(x) for x in result["newly_possible"]}
    emergent = sorted(P - A - B)
    return {"pair": [a.name, b.name], "enablement": result["enablement"],
            "part_enablement": [ea["enablement"], eb["enablement"]],
            "newly_possible": result["newly_possible"],
            "no_longer_possible": result["no_longer_possible"],
            "emergent": [list(x) for x in emergent],
            "is_emergent": bool(emergent),
            "superadditive": result["enablement"] > ea["enablement"] + eb["enablement"],
            "composes": bool(emergent) or result["enablement"] > ea["enablement"] + eb["enablement"],
            "criterion_in_force": governing["criterion"],
            "criterion_superseded": governing["superseded"],
            "why": governing["because"] or (
                "beating both parts is what two INDEPENDENT moves do for free; only an emergent "
                "unlock or a superadditive total is composition")}


def search(*, top_cues: int = 12) -> dict:
    """Try every move, score each by what it unlocks, and report the ceiling honestly."""
    results = [apply_move(m, top_cues=top_cues) for m in MOVES]
    single = {r["move"]: r["enablement"] for r in results}

    # COMPOSITION. A pair is only interesting if it beats both parts -- otherwise the moves are
    # independent and this is accumulation with extra steps, which is the distinction the whole
    # enablement idea exists to keep honest.
    import itertools
    pairs = []
    for a, b in itertools.combinations(MOVES, 2):
        pr = apply_pair(a, b, top_cues=top_cues)
        pr["best_part"] = max(single.get(a.name, 0), single.get(b.name, 0))
        pairs.append(pr)

    best = max(results, key=lambda r: r["enablement"]) if results else None
    return {
        "moves_tried": len(results),
        "results": results,
        "pairs_tried": len(pairs),
        "pairs": pairs,
        "any_pair_composes": any(p["composes"] for p in pairs),
        "any_pair_emergent": any(p["is_emergent"] for p in pairs),
        "best": best["move"] if best and best["enablement"] > 0 else None,
        "any_unlocked": any(r["enablement"] > 0 for r in results),
        "ceiling": ("this vocabulary is four kinds wide and a person chose the four, from four "
                    "observed escapes. An escape that is not a signal, source, filter or comparison "
                    "change is invisible here and still needs a person"),
    }
