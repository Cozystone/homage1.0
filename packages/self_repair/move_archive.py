# -*- coding: utf-8 -*-
"""A DIVERGENT archive of moves — diverse stepping stones instead of one winner.

    from packages.self_repair.move_archive import admit, elites, diversity

WHY, AND THE MEASUREMENT THAT FORCED IT. Composition was measured at zero: 18 pairs, no emergent
unlock, no superadditive total, and in live behaviour the loop took its escape (`min_fire` 15 -> 7)
and plateaued on the very next cycle. I reported that I had no mechanism for it.

I was wrong, and the mechanism was written down a week earlier. `docs/ATANOR_intelligence_explosion_
research.md` (2026-07-23) lists four measured deficits behind self-acceleration, and the second is
exactly this: **reuse is ADDITIVE (a constant level-shift), not multiplicative.** Its prescription is
a divergent archive plus babble-grade abstraction. And `packages/evolution/qd_archive.py` states the
cause in its own words, of a different search space:

    a CONVERGENT archive keeps one elite per behaviour, so two structurally different things that do
    the same job collapse to one, and any alternative SPELLING of an already-reachable capability is
    discarded as a duplicate. Abstractions mined from such a library are re-spellings of what is
    already reachable -- search noise, no leverage. Multiplicative reuse needs a DIVERGENT archive of
    diverse stepping stones.

`search_parameters` is a convergent archive. It sorts wins by enablement and `as_moves` takes the best
per key, so two knob values that unlock DIFFERENT things collapse to whichever scores higher. **There
were no diverse stepping stones to compose FROM.** That is why pairs did not compose -- not because
composition is hard here, but because everything but one winner had already been thrown away.

THE NICHE, following qd_archive's three axes translated to this space rather than borrowed as code
(that module walks tuple-tree programs and cannot take a knob):

    d0  WHAT IT UNLOCKS   the exact set of newly-possible (cue, relation) pairs. Exact, not binned,
                          so no capability is ever lost to a bucket collision -- the archive is a
                          strict superset of the convergent one.
    d1  WHERE IT ACTS     the organ and knob touched. The "how it is built" axis: two knobs that
                          unlock the same thing by different routes stay distinct, which is precisely
                          what the convergent archive was destroying.
    d2  HOW FAR           the direction and coarse magnitude of the change. A gentle loosening and a
                          drastic one are different stepping stones even when they open the same door.

ELITE PER NICHE = the SMALLEST change (parsimony), tie-broken deterministically by key, exactly as
qd_archive keeps the smallest program. Diversity lives ACROSS niches; within one, the cleanest
representative.

HONESTY. This does not claim composition now works. It removes the reason composition COULD not work,
and the same 18-pair measurement re-run over the archive is what says whether it did.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ARCHIVE = REPO / "data" / "self_repair" / "move_archive.json"


def _magnitude(frm, to) -> str:
    """d2 — direction and coarse size of the change, as a bin."""
    try:
        a, b = float(frm), float(to)
    except (TypeError, ValueError):
        return "?"
    if a == 0:
        return "up" if b > 0 else "down"
    r = b / a
    d = "up" if r > 1 else "down"
    far = "far" if (r >= 2 or r <= 0.5) else "near"
    return f"{d}-{far}"


def _opened(win: dict) -> list:
    """Everything a move opens — survivor pairs AND newly nameable relations.

    Keying on survivors alone reported an empty unlock set for every win whose enablement came from a
    relation, so a search that had just found three wins offered the archive nothing to admit. A niche
    keyed on half of what a move does is keyed on noise."""
    return [list(x) for x in (win.get("newly_possible") or [])] + \
           [list(x) for x in (win.get("relations_newly_nameable") or [])]


def descriptor(win: dict) -> tuple:
    """The three niche coordinates of one move."""
    unlocks = tuple(sorted(tuple(x) for x in _opened(win)))
    where = str(win.get("key") or "")
    return (unlocks, where, _magnitude(win.get("from"), win.get("to")))


def key_of(desc: tuple) -> str:
    unlocks, where, mag = desc
    return "‖".join(["|".join(f"{c}>{r}" for c, r in unlocks), where, mag])


def _load() -> dict:
    if not ARCHIVE.exists():
        return {}
    try:
        return json.loads(ARCHIVE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(arch: dict) -> None:
    try:
        ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVE.write_text(json.dumps(arch, indent=1, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def admit(wins: list) -> dict:
    """Put every win in its niche, keeping the smallest change per niche.

    Every win, not only the best: a move that unlocks less is still a different stepping stone if it
    unlocks something ELSE, and that difference is the whole point."""
    arch = _load()
    added = replaced = 0
    for w in wins or []:
        if not _opened(w):
            continue                       # a move that opens nothing is not a stepping stone
        k = key_of(descriptor(w))
        cur = arch.get(k)
        cand = {"key": w.get("key"), "from": w.get("from"), "to": w.get("to"),
                "enablement": w.get("enablement"), "unlocks": _opened(w),
                "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if cur is None:
            arch[k] = cand
            added += 1
        else:
            # parsimony within the niche: the gentler change, tie-broken deterministically
            def _size(x):
                try:
                    return abs(float(x["to"]) - float(x["from"]))
                except (TypeError, ValueError, KeyError):
                    return float("inf")
            if (_size(cand), str(cand["key"])) < (_size(cur), str(cur["key"])):
                arch[k] = cand
                replaced += 1
    _save(arch)
    return {"niches": len(arch), "added": added, "replaced_by_parsimony": replaced}


def elites() -> list:
    """One move per niche — what there is to compose FROM."""
    return list(_load().values())


def diversity() -> dict:
    """Both numbers, so an A/B can show the archive did not collapse to one winner.

    `niches` counts stepping stones; `distinct_unlocks` counts genuinely distinct capabilities. The
    second can never be inflated by structural variants, which is what keeps the first honest."""
    arch = _load()
    unlocks = {json.dumps(v.get("unlocks"), sort_keys=True) for v in arch.values()}
    keys = {str(v.get("key")) for v in arch.values()}
    return {"niches": len(arch), "distinct_unlocks": len(unlocks), "distinct_knobs": len(keys),
            "reading": ("niches are a superset of capabilities: structural variants raise the first "
                        "and never the second. A convergent archive would show niches == "
                        "distinct_unlocks, which is the collapse this exists to prevent")}
