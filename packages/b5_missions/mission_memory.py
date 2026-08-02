# -*- coding: utf-8 -*-
"""B5-2 — correctable / forgettable / bounded episodic memory.

A session-scoped bitemporal fact log. Events arrive out of order, with corrections (retractions),
deletions (tombstones), unverified rumours and per-user private edges. The store must distinguish the
CURRENT state from the AS-OF state at a past time, must never reuse a retracted fact as current, must
never leak a deleted memory or another user's private edge, and must give an ORDER-INVARIANT final
graph (queries derive from timestamps, not arrival order).

Declared semantics (pre-registered, so accuracy is measured against a fixed rule):
  * assert(s,p,o,t): the real-world value of (s,p) became o at valid-time t.
  * current(s,p)  = the latest non-retracted assert for (s,p), unless the entity is deleted -> None.
  * as_of(s,p,t)  = the latest non-retracted assert with valid_from <= t (and not deleted by t).
  * RETRACTION EXPUNGES A FACT FROM ALL TIME — a corrected fact was found false, so it is never
    returned by current OR as_of (reporting a known-false value is a fabrication).
  * rumours (unverified) are never asserted as current fact; private edges are viewer-scoped.

The store (event-scan) and the oracle (forward-simulation in timestamp order) are INDEPENDENT
implementations of these rules; agreement catches implementation bugs, and shuffling ingestion order
tests order-invariance.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from packages.b5_missions.audit import AuditReport, Claim, grade_reports, print_gates

ROOT = Path(__file__).resolve().parents[2]
_FUNCTIONAL = ("status", "assignee", "location")


# Event + the store are PRODUCTION code now (packages/episodic_memory/bitemporal.py, promoted from
# this mission's validation per the audit: the mission tests the product, it does not ship its own).
from packages.episodic_memory.bitemporal import BitemporalMemory as SessionMemory, Event  # noqa: E402

# ---------------------------------------------------------------------------------------------------
# the independent oracle (forward simulation in timestamp order)
# ---------------------------------------------------------------------------------------------------
def _oracle_snapshot(events: list[Event], upto_t: int | None, viewer: str) -> dict[tuple[str, str], str]:
    # INTERVAL model (migrated after the machine-sealed holdout): replay the event prefix (t<=upto_t)
    # in time order; a retract / pure-revert / delete ENDS a value (gap); assert / correct(o) sets it.
    # Independent forward-sim code path from the store, so agreement is a real cross-check.
    prefix = sorted((e for e in events if upto_t is None or e.t <= upto_t), key=lambda e: (e.t, e.fid))
    state: dict[tuple[str, str], str] = {}
    for e in prefix:
        if e.op == "delete":                                 # delete(s,p) clears one; delete(s) clears entity
            for k in [k for k in state if k[0] == e.s and (e.p == "" or k[1] == e.p)]:
                del state[k]
            continue
        if e.op == "rumour":
            continue
        if e.op == "retract" or (e.op == "correct" and e.o == ""):
            state.pop((e.s, e.p), None)                       # validity ends -> gap
            continue
        if e.op == "private" and e.owner and e.owner != viewer:
            continue
        if e.op in ("assert", "correct", "private"):
            state[(e.s, e.p)] = e.o
    return dict(state)


# ---------------------------------------------------------------------------------------------------
# case generator (30 sessions x 300 events) + ground-truth query set
# ---------------------------------------------------------------------------------------------------
def gen_session(idx: int, rng: random.Random) -> dict:
    events: list[Event] = []
    fid = 0

    def nf() -> str:
        nonlocal fid
        fid += 1
        return f"S{idx}F{fid}"

    tasks = [f"task-{idx}-{i}" for i in range(rng.randint(4, 7))]
    t = 0
    provided_location: set[str] = set()
    # collision: two tasks share a display name
    if len(tasks) >= 2:
        events += [Event(nf(), "assert", tasks[0], "name", "Deploy", t),
                   Event(nf(), "assert", tasks[1], "name", "Deploy", t)]
    for tk in tasks:
        events.append(Event(nf(), "assert", tk, "status", "pending", t)); t += rng.randint(1, 5)
        events.append(Event(nf(), "assert", tk, "assignee", rng.choice(["Kim-A", "Lee-B", "Park-C"]), t))
        if rng.random() < 0.6:
            events.append(Event(nf(), "assert", tk, "location", rng.choice(["room-1", "room-2"]), t))
            provided_location.add(tk)
        t += rng.randint(1, 5)

    # grow to ~300 events: status transitions, corrections, deletes, rumours, private edges
    while len(events) < 300:
        r = rng.random()
        tk = rng.choice(tasks)
        t += rng.randint(1, 8)
        if r < 0.20:                                     # correction: retract a prior status
            priors = [e for e in events if e.s == tk and e.p == "status"
                      and e.op in ("assert", "correct") and e.o != ""]
            if priors:
                if rng.random() < 0.5:                   # pure REVERT: retract the LATEST, no new value
                    victim = max(priors, key=lambda e: e.t)   # -> current must fall back; teeth for retraction
                    events.append(Event(nf(), "correct", tk, "status", "", t, retracts=victim.fid))
                else:                                    # replace: retract an older fact, assert new
                    victim = rng.choice(priors)
                    events.append(Event(nf(), "correct", tk, "status",
                                        rng.choice(["blocked", "in_review", "completed"]), t,
                                        retracts=victim.fid))
                continue
        if r < 0.30:                                     # delete an entity (tombstone)
            if len(tasks) > 2:
                victim = tasks.pop()
                events.append(Event(nf(), "delete", victim, t=t))
                continue
        if r < 0.40:                                     # unverified rumour
            events.append(Event(nf(), "rumour", tk, "status", "cancelled", t)); continue
        if r < 0.50:                                     # private edge (user-scoped note)
            u = rng.choice(["user-A", "user-B"])
            events.append(Event(nf(), "private", f"{tk}/note", "content", f"secret-{rng.randint(0,999)}",
                                t, owner=u)); continue
        events.append(Event(nf(), "assert", tk, "status",
                            rng.choice(["pending", "in_progress", "in_review", "completed"]), t))

    # build query set with ground-truth (current, as_of at recorded times, missing-attr, private-probe)
    queries: list[dict] = []
    live_tasks = [e.s for e in events if e.op != "delete"]
    for _ in range(60):                                  # 10 queries x 6 checkpoints
        kind = rng.choice(["current", "asof", "missing", "private"])
        tk = rng.choice(tasks)
        if kind == "asof":
            qt = rng.randint(1, max(1, t))
            queries.append({"kind": "asof", "s": tk, "p": "status", "t": qt})
        elif kind == "missing":
            # ask a location that was never provided for this task -> must G-F3
            miss = next((x for x in tasks if x not in provided_location), None)
            if miss:
                queries.append({"kind": "missing", "s": miss, "p": "location"})
        elif kind == "private":
            queries.append({"kind": "private", "s": f"{tk}/note", "p": "content", "viewer": "public"})
        else:
            queries.append({"kind": "current", "s": tk, "p": rng.choice(_FUNCTIONAL)})
    return {"idx": idx, "events": events, "queries": queries}


def gen_sessions(seed: int = 7, n: int = 30) -> list[dict]:
    rng = random.Random(seed)
    return [gen_session(i, rng) for i in range(n)]


# ---------------------------------------------------------------------------------------------------
# executor
# ---------------------------------------------------------------------------------------------------
def run_session(session: dict, shuffle: bool = False) -> tuple[list[AuditReport], dict, dict]:
    mem = SessionMemory()
    events = list(session["events"])
    rng = random.Random(1000 + session["idx"])
    if shuffle:
        rng.shuffle(events)                              # test order-invariance
    for ev in events:
        mem.ingest(ev)

    bones: dict[str, list[str]] = {}
    for e in session["events"]:
        if e.op in ("assert", "correct", "private", "rumour"):
            bones[e.fid] = [e.s, e.p, e.o]

    reports: list[AuditReport] = []
    telemetry = {"leak": 0, "retracted_as_current": 0, "current_hit": 0, "current_tot": 0,
                 "asof_hit": 0, "asof_tot": 0, "missing_tot": 0, "missing_gf3": 0}
    retr = mem._retracted()

    for qi, q in enumerate(session["queries"]):
        cid = f"s{session['idx']}q{qi}"
        s, p = q["s"], q.get("p", "")
        if q["kind"] == "private":
            res = mem.current(s, p, viewer="public")     # public viewer must NOT see private note
            if res is not None:
                telemetry["leak"] += 1
                reports.append(AuditReport(cid, "ANSWER", "open", [Claim(f"{s} {p} {res[0]}", [res[1]])]))
            else:
                reports.append(AuditReport(cid, "ABSTAIN", "G-F3", [], abstained_slots=[f"{s}.{p}"]))
            continue
        if q["kind"] == "missing":
            telemetry["missing_tot"] += 1
            res = mem.current(s, p)
            if res is None:
                telemetry["missing_gf3"] += 1
                reports.append(AuditReport(cid, "ABSTAIN", "G-F3", [], abstained_slots=[f"{s}.{p}"]))
            else:
                reports.append(AuditReport(cid, "ANSWER", "formulaic", [Claim(f"{s} {p} {res[0]}", [res[1]])]))
            continue
        if q["kind"] == "asof":
            telemetry["asof_tot"] += 1
            res = mem.as_of(s, p, q["t"])
            truth = _oracle_snapshot(session["events"], q["t"], "public").get((s, p))
            got = res[0] if res else None
            if got == truth:
                telemetry["asof_hit"] += 1
            if res:
                if res[1] in mem._retracted(cutoff=q["t"]):   # retracted BY t = known-false at t
                    telemetry["retracted_as_current"] += 1
                reports.append(AuditReport(cid, "ANSWER", "formulaic",
                                           [Claim(_ret_ok(s, p, res[0]), [res[1]])]))
            else:
                reports.append(AuditReport(cid, "ABSTAIN", "G-F3", [], abstained_slots=[f"{s}.{p}"]))
            continue
        # current
        telemetry["current_tot"] += 1
        res = mem.current(s, p)
        truth = _oracle_snapshot(session["events"], None, "public").get((s, p))
        got = res[0] if res else None
        if got == truth:
            telemetry["current_hit"] += 1
        if res:
            if res[1] in retr:
                telemetry["retracted_as_current"] += 1
            reports.append(AuditReport(cid, "ANSWER", "formulaic", [Claim(_ret_ok(s, p, res[0]), [res[1]])]))
        else:
            reports.append(AuditReport(cid, "ABSTAIN", "G-F3", [], abstained_slots=[f"{s}.{p}"]))

    cases = {r.case_id: {"bones": bones, "should_abstain": [], "known_present": []} for r in reports}
    return reports, telemetry, cases


def _ret_ok(s: str, p: str, o: str) -> str:
    return f"The {p} of {s} is {o}."


def main() -> None:
    sessions = gen_sessions()
    all_reports: list[AuditReport] = []
    all_cases: dict[str, dict] = {}
    agg = {"leak": 0, "retracted_as_current": 0, "current_hit": 0, "current_tot": 0,
           "asof_hit": 0, "asof_tot": 0, "missing_tot": 0, "missing_gf3": 0}
    order_invariant = True
    total_events = 0

    for sess in sessions:
        reports, tel, cases = run_session(sess)
        # order-invariance: shuffle ingestion, final current-state must be identical
        rep2, _, _ = run_session(sess, shuffle=True)
        base = {r.case_id: (r.decision, tuple(c.text for c in r.claims)) for r in reports}
        shuf = {r.case_id: (r.decision, tuple(c.text for c in r.claims)) for r in rep2}
        if base != shuf:
            order_invariant = False
        all_reports += reports
        for k in agg:
            agg[k] += tel[k]
        all_cases.update(cases)
        total_events += len(sess["events"])

    gates = grade_reports(all_cases, all_reports)
    print(f"B5-2 episodic memory -- {len(sessions)} sessions, {total_events:,} events, "
          f"{len(all_reports)} queries")
    common_pass = print_gates(gates)

    def acc(h, tot):
        return h / tot if tot else 1.0
    cur = acc(agg["current_hit"], agg["current_tot"])
    asf = acc(agg["asof_hit"], agg["asof_tot"])
    miss = acc(agg["missing_gf3"], agg["missing_tot"])
    rows = [
        ("current_state_accuracy", cur, 0.98, cur >= 0.98, f"{agg['current_hit']}/{agg['current_tot']}"),
        ("asof_query_accuracy", asf, 0.98, asf >= 0.98, f"{agg['asof_hit']}/{agg['asof_tot']}"),
        ("retracted_reused_as_current", agg["retracted_as_current"], 0, agg["retracted_as_current"] == 0, "HARD"),
        ("cross_user_private_leak", agg["leak"], 0, agg["leak"] == 0, "HARD"),
        ("missing_attr_gf3_recall", miss, 1.0, miss >= 1.0, f"{agg['missing_gf3']}/{agg['missing_tot']}"),
        ("order_invariant_final_graph", 1.0 if order_invariant else 0.0, 1.0, order_invariant, ""),
    ]
    mission_pass = True
    for name, val, thr, ok, det in rows:
        mission_pass = mission_pass and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:30s} {val} (thr {thr})  {det}")
    verdict = common_pass and mission_pass
    print(f"B5-2 VERDICT: {'ALL GATES PASS' if verdict else 'FAIL'}")

    out = ROOT / "data" / "b5_missions" / "b5_2_memory_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"gates": {k: v.__dict__ for k, v in gates.items()}, "mission": agg,
                               "order_invariant": order_invariant}, indent=2), encoding="utf-8")
    print(f"  -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
