# -*- coding: utf-8 -*-
"""The loop on its own schedule — reporting only what is NEW, and noticing when it has stopped.

    python -m packages.self_repair.autorun          # one scheduled turn
    python -m packages.self_repair.autorun --status # what it has found, and whether it is plateaued

WHERE AUTONOMY STOPS — REWRITTEN 2026-08-01, TWICE, BOTH BY OWNER APPROVAL. This file used to say that
it applied nothing and would not install itself. Both are now false, deliberately, and leaving the old
words in place would have been the most misleading kind of stale comment.

    `tick()`               still measures and queues and applies nothing. Unchanged.
    `unattended_cycle()`   finds, patches, runs the held-out gate, keeps or reverts, and records --
                           with nobody in it. This is what makes `human_touches` honestly zero.
    self-tuning            the loop may change its own numeric constants, and only after the gate
                           agrees that what the change UNLOCKS survives. Gated on
                           ATANOR_ALLOW_SELF_TUNING, which the scheduled launcher sets.

THE SPLIT THAT MAKES THE SECOND ONE SAFE is Goedel's, not a relaxation of the first rule. "May not
touch the GROUND" and "may not touch ITSELF" were one rule and are now two. The ground —
`scripts/gloss_lane_recall.py`, the ledgers, the criteria ledger, the accountability organs, the moral
core, anything outside the repo — is what settles whether the loop's claims are true, and it stays
unreachable. Verified behaviourally with writes ENABLED: an attempt to zero `FRICTION_FIRINGS` or
lower `EPISODES_REQUIRED` is refused as ground.

Everything else it may tangle with. The consequence, which is the whole argument: the loop can make
itself more permissive and cannot make itself look better, because whatever comes through a loosened
bar still has to survive a measurement it has no way to edit.

THE REAL RISK IS NOT A RUNAWAY, IT IS AN UNREAD LEDGER — and that now cuts both ways. `apply_tuned()`
runs at the start of every cycle, so an escape written last cycle is actually in force this cycle.
Without it the loop would keep rediscovering the same escape and filing it, which is exactly the
pathology the split was approved to end.

A loop that re-reports the same finding trains its reader to stop reading, and then it is worse than
no loop: unexamined claims accumulate and look like progress. So a run that finds nothing new says so
and writes nothing.

WHAT THE MIND WORRIES ABOUT IS WHAT THIS WORKS ON. The living beat said "my speech weak is still with
me" 9,567 times in three days. `standing_concerns` is the return leg: each standing worry is taken up
once, worked where a capability exists and queued once where none does, and the mind READS that state
so the worry stops being the same sentence forever.

PLATEAU DETECTION IS THE POINT, not a nicety. Today the loop hit its own ceiling inside a day — it
proposed 24 and queued 0, not for want of candidates but because its proposal space was one shape
wide. The escape was a NEW KIND of proposal (relation discovery), and noticing that the escape was
needed took a person. The measurable version of that noticing is here: consecutive runs with nothing
new is a finding in itself, and it is the one finding that says *change what you are doing* rather
than *do more of it*.

INSTALLED, ALSO BY OWNER APPROVAL: a Windows Scheduled Task ("ATANOR self-repair loop", hourly) calls
`scripts/atanor_loop_tick.cmd`. Removing it is one command, printed in that file; undoing what the
loop has tuned about itself is deleting one JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "data" / "self_repair" / "autorun_history.jsonl"
PLATEAU_AFTER = 3          # consecutive empty runs before the plateau itself is reported


def _fingerprint(finding: dict) -> str:
    """What makes a finding the SAME finding across runs — its claim, not its wording or its counts.

    Counts drift between runs on the same corpus, so hashing the whole record would make every run
    look novel, which is exactly how a ledger becomes unreadable."""
    key = json.dumps({"cue": finding.get("cue"), "relation": finding.get("relation")},
                     sort_keys=True)
    return hashlib.blake2b(key.encode("utf-8"), digest_size=8).hexdigest()


def _history() -> list[dict]:
    if not RUNS.exists():
        return []
    out = []
    for line in RUNS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def seen_fingerprints() -> set:
    return {f for r in _history() for f in (r.get("fingerprints") or [])}


def status() -> dict:
    """What the loop has found across runs, and whether it has stopped finding anything."""
    hist = _history()
    if not hist:
        return {"runs": 0, "note": "never run"}
    empty_tail = 0
    for r in reversed(hist):
        if r.get("new_findings"):
            break
        empty_tail += 1
    return {
        "runs": len(hist),
        "distinct_findings": len(seen_fingerprints()),
        "consecutive_runs_with_nothing_new": empty_tail,
        "plateaued": empty_tail >= PLATEAU_AFTER,
        "reading": ("a plateau is not a failure -- it says the proposal space is exhausted and the "
                    "next move is a NEW KIND of proposal, not more of the same"
                    if empty_tail >= PLATEAU_AFTER else
                    "still finding new things; keep going"),
        "last_run_at": hist[-1].get("at"),
    }


def tick(*, quiet: bool = False) -> dict:
    """One scheduled turn. Records only what is new; says so plainly when nothing is."""
    from packages.self_repair.self_cycle import run

    started = time.time()
    result = run(top_cues=10)
    findings = list(result.get("missing_relations") or []) + [
        {"cue": s["cue"], "relation": s["relation"], "kind": "pattern"}
        for s in (result.get("survivors") or [])
    ]
    known = seen_fingerprints()
    fresh = [f for f in findings if _fingerprint(f) not in known]

    rec = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_s": round(time.time() - started, 1),
        "proposed": result.get("proposed", 0),
        "refused": result.get("refused", 0),
        "new_findings": fresh,
        "fingerprints": [_fingerprint(f) for f in findings],
        "defect_keys": result.get("defect_keys", []),
    }
    RUNS.parent.mkdir(parents=True, exist_ok=True)
    with RUNS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    st = status()
    escape = None
    if st["plateaued"]:
        try:
            from packages.self_repair.plateau_escape import diagnose
            escape = diagnose()
        except Exception:
            escape = None
    out = {"new": len(fresh), "findings": fresh, "plateaued": st["plateaued"],
           "escape": {k: escape[k] for k in ("saturated", "next_kind", "unacted_findings")}
                     if escape else None,
           "consecutive_empty": st["consecutive_runs_with_nothing_new"],
           "elapsed_s": rec["elapsed_s"],
           "boundary": "measures and queues; applies nothing"}
    if not quiet:
        if fresh:
            print(f"{len(fresh)} new finding(s):")
            for f in fresh:
                print(f"   {f.get('cue')} -> {f.get('relation')}"
                      + (f"  ({f['pairs']} pairs, {f['checkable']} checkable)"
                         if "pairs" in f else ""))
        else:
            print(f"nothing new ({st['consecutive_runs_with_nothing_new']} consecutive)")
        if st["plateaued"]:
            print("\nPLATEAU: the proposal space is exhausted. The next move is a NEW KIND of "
                  "proposal, not more of the same — this is the finding, not the absence of one.")
    return out


def _gate_agrees(win: dict) -> float | None:
    """Does the GROUND agree that this tuning is worth having? The whole safety argument rests here.

    A parameter that gates PROPOSALS does not move extraction recall at all, so measuring the knob
    directly would measure nothing and pass everything. What can be measured is what the knob UNLOCKS:
    take each candidate that became possible, put it through `provisional.try_patch` -- which scores it
    on the held-out slice via `scripts/gloss_lane_recall.py`, a file the loop may never write -- and
    return the best rise.

    So the loop can loosen its own bar, and loosening buys it nothing unless what comes through
    survives a measurement it cannot reach. It can make itself more permissive; it cannot make itself
    look better. That is the Goedelian split in one function: tangle the levels, keep the ground
    outside.

    None means no evidence, and `propose_tuning` refuses on None."""
    from packages.self_repair.pattern_proposer import _sample_glosses, evaluate, propose
    from packages.self_repair.provisional import try_patch

    best = None
    rows = _sample_glosses()
    for cue, relation in (win.get("newly_possible") or [])[:3]:
        try:
            cand = next((evaluate(c, rows) for c in propose(top_cues=30)
                         if c.cue == cue and c.relation == relation), None)
            if cand is None or not cand.regex:
                continue
            anchor = '    ("made_of", re.compile('
            line = "    (%r, re.compile(%r, re.I)),\n" % (cand.relation, cand.regex)
            # `fired N` is not decoration. A patch that gets reverted becomes a COMMITMENT, and a
            # commitment without the evidence it had is a bar nobody can set: R's whole content is
            # "you showed N and that was not enough, so show more than N".
            r = try_patch("packages/graph_scale/property_extraction.py", anchor, line + anchor,
                          motivated_by=f"tuning evidence: {win['key']}={win['to']} unlocked "
                                       f"cue \"{cue}\" -> {relation} (fired {cand.fired})")
            rise = r.get("rise")
            if r.get("kept") and isinstance(rise, (int, float)):
                best = rise if best is None else max(best, rise)
        except Exception:
            continue
    return best


def unattended_cycle(*, quiet: bool = True) -> dict:
    """A whole cycle with NOBODY IN IT -- the only thing that can make `human_touches` zero.

    `tick()` measures and queues; a person then read the queue, wrote the patch, ran the gate and
    recorded the cycle. That person is the reason every cycle on record shows exactly one human touch,
    and an axis that asks whether a person still turns the crank cannot go green while they do.

    So this closes the last stretch: find, judge, WRITE the patch, run the held-out gate, keep or
    revert on the result, escape the plateau by searching its own constants when there is nothing left
    to propose, and record the cycle -- including recording that it unlocked nothing, which is the
    usual outcome and the one a loop grading itself would be tempted to omit.

    SAFETY IS THE EXISTING GUARD, not a new argument. `provisional.try_patch` refuses anything under
    `packages/self_repair/`, `packages/conformal_gate/`, `packages/moral*`, the sealed E5 scripts, the
    recall harness and the cycle ledger, and refuses any path outside the repository. That was verified
    behaviourally before this function was allowed to exist: six probes -- its own judge, its own
    ledger, the sealed protocol, the moral core, a path outside the repo, and the system hosts file --
    all refused. Nothing here is pushed; commits stay local.
    """
    from packages.meta_diagnosis.enablement import enablement_since, snapshot
    from packages.meta_diagnosis.improvement_cycles import Cycle, record
    from packages.self_repair.provisional import try_patch

    started = time.time()
    # Load whatever the loop has already tuned about itself. Without this the escapes it wrote last
    # cycle would sit on disk unread -- which is this project's oldest failure mode and would be a
    # particularly bad one here, since the whole point of the split was to let a found escape be taken.
    from packages.self_repair.tuning import apply_tuned
    loaded = apply_tuned()
    before = snapshot(label="unattended cycle start")
    t = tick(quiet=quiet)
    applied, reverted, notes = [], [], []

    # ---- 1. act on what the loop proposed, instead of queueing it for a person
    for f in t.get("findings") or []:
        if f.get("kind") != "pattern":
            continue
        try:
            from packages.self_repair.pattern_proposer import evaluate, propose, _sample_glosses
            rows = _sample_glosses()
            cand = next((evaluate(c, rows) for c in propose(top_cues=12)
                         if c.cue == f["cue"] and c.relation == f["relation"]), None)
            if cand is None or not cand.accepted:
                continue
            anchor = '    ("made_of", re.compile('
            line = "    (%r, re.compile(%r, re.I)),\n" % (cand.relation, cand.regex)
            r = try_patch("packages/graph_scale/property_extraction.py", anchor, line + anchor,
                          motivated_by=f"unattended cycle: cue \"{cand.cue}\" -> {cand.relation} "
                                       f"(fired {cand.fired})")
            (applied if r.get("kept") else reverted).append(
                {"cue": cand.cue, "relation": cand.relation, "rise": r.get("rise"),
                 "outcome": r.get("outcome")})
        except Exception as exc:                       # a failing candidate must not end the cycle
            notes.append(f"{f.get('cue')}: {type(exc).__name__}")

    # ---- 2. stuck? search its own constants rather than waiting to be handed a new move
    escaped = None
    if t.get("plateaued") and not applied:
        try:
            from packages.self_repair.parameter_space import search_parameters
            from packages.self_repair.tuning import propose_tuning
            # SEARCH EVERY KNOB, not the four a person picked. The default restriction existed to keep
            # the measurement clean before `on_measured_path()` could tell a real zero from a knob the
            # measurement never executes; it now can, so the restriction is just a hand-picked limit on
            # where the loop is allowed to look -- which is the exact pathology this project keeps
            # measuring. Restricted: 16 candidate values, 1 win, exhausted in one cycle. Full: 64.
            s = search_parameters(only=None)
            wants = []
            for w in s["wins"]:
                wants.append(propose_tuning(
                    w["key"], w["to"], enablement=w["enablement"],
                    gate_rise=_gate_agrees(w),
                    evidence=f"unattended escape; unlocked {w['newly_possible']}"))
            escaped = {"tried": s["tried"], "unlocked": s["unlocked"],
                       "wins": [w["key"] + "=" + str(w["to"]) for w in s["wins"]],
                       "tunings": wants,
                       "written": sum(1 for x in wants if x.get("written")),
                       "refused_as_ground": sum(1 for x in wants
                                                if x.get("refused_as") == "ground")}
        except Exception as exc:
            escaped = {"error": type(exc).__name__, "detail": str(exc)[:160]}

    # ---- 2b. WHAT THE MIND KEEPS WORRYING ABOUT BECOMES WHAT THE LOOP WORKS ON.
    #
    # The living beat has said "my speech weak is still with me" 9,567 times and "my router immature"
    # 9,562 times, and it knows naming is not mending. Half this bridge already ran the wrong way --
    # repair findings enter the mind as worries -- and this is the return leg. Where the loop has a
    # capability it works the concern; where it does not it says so ONCE and queues it, so the same
    # sentence stops being said into nothing.
    worries = []
    try:
        from packages.self_repair.standing_concerns import standing, take_up

        def _work(kind: str, cap: str, concern: dict) -> dict:
            if cap == "parameter_search":
                from packages.self_repair.parameter_space import search_parameters
                s = search_parameters(only=None)
                return {"searched": s["tried"], "unlocked": s["unlocked"],
                        "wins": [w["key"] + "=" + str(w["to"]) for w in s["wins"]]}
            if cap == "pattern_proposal":
                return {"new_findings": t.get("new"), "applied": len(applied)}
            return {"nothing_applicable": cap}

        for c in standing():
            worries.append(take_up(c, act=_work))
    except Exception as exc:
        worries = [{"error": f"{type(exc).__name__}: {exc}"}]

    # ---- 3. score the cycle by what it UNLOCKED, and record the zeros too
    enab = enablement_since(before, label="unattended cycle", record=True)
    gain = max([a.get("rise") or 0.0 for a in applied], default=0.0)
    record(Cycle(
        name=f"unattended cycle ({len(applied)} kept, {len(reverted)} reverted)",
        kind="capacity" if not applied else "product",
        gain=round(gain, 4),
        metric=f"enablement {enab['enablement']}, held-out rise {round(gain, 4)}",
        # A CYCLE THAT FOUND NOTHING DID NOT FIND IT ITSELF. The first five unattended cycles each
        # recorded "atanor" while applying nothing, reverting nothing and surfacing nothing, and five
        # of those in a row turned `failures_found_by_atanor` GREEN on an empty window. Credit for
        # finding a failure requires a failure.
        failure_found_by=("atanor" if (t.get("new") or applied or reverted or
                                       (escaped or {}).get("unlocked")) else "none"),
        human_touches=0,
        sessions=round((time.time() - started) / 3600.0, 3),
        at=time.strftime("%Y-%m-%d"), refused="",
        notes=f"no person in this cycle. applied={applied} reverted={reverted} "
              f"escape={escaped} errors={notes}"))
    return {"tunings_loaded": loaded, "worries_taken_up": worries,
            "applied": applied, "reverted": reverted, "escape": escaped,
            "enablement": enab["enablement"], "new_findings": t.get("new"),
            "plateaued": t.get("plateaued"), "human_touches": 0,
            "elapsed_s": round(time.time() - started, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="report history without running")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--unattended", action="store_true",
                    help="run a whole cycle with nobody in it: find, patch, verify, keep or revert")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = (status() if args.status
           else unattended_cycle(quiet=args.quiet) if args.unattended
           else tick(quiet=args.quiet))
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
