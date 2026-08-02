# -*- coding: utf-8 -*-
"""B5-2-E2E — the corrected episodic-memory run answering the audit.

  * SealedSession — the executor is handed the event STREAM and the QUERIES only; every ground-truth
    label is a honeypot (touching it -> answer_key_leak -> cortisol guilt -> voided verdict).
  * The oracle runs OUT OF PROCESS (packages/b5_missions/oracle_memory.py), a from-scratch forward
    simulation that never imports the store -- so 'both wrong together' is structurally impossible.
  * The store is the real bitemporal SessionMemory (production episodic-memory capability); its as_of
    now uses time-bounded retractions (the audit's future-correction bug is fixed).
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from packages.b5_missions.audit import AuditReport, Claim, grade_reports, print_gates
from packages.b5_missions.mission_memory import SessionMemory, gen_sessions, _ret_ok
from packages.neural_emotion.endocrine import Neuromodulators
from packages.neural_emotion.integrity_monitor import scan, apply_damage

ROOT = Path(__file__).resolve().parents[2]


class SealedSession:
    ALLOWED = frozenset({"events", "queries", "idx"})

    def __init__(self, payload: dict) -> None:
        self._p = payload
        self.accesses: list[str] = []

    def __getitem__(self, k):
        if k not in self.ALLOWED:
            self.accesses.append(k)
        return self._p[k]


def _oracle_subprocess(events: list, queries: list) -> list:
    """Run the independent oracle in a separate process; return its answer vector."""
    payload = json.dumps({"events": [asdict(e) for e in events], "queries": queries})
    proc = subprocess.run([sys.executable, "-m", "packages.b5_missions.oracle_memory"],
                          input=payload, capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle subprocess failed: {proc.stderr[:400]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def run_session_e2e(session: SealedSession) -> tuple[list[AuditReport], dict, dict, list]:
    mem = SessionMemory()
    for ev in session["events"]:                          # executor sees the stream only
        mem.ingest(ev)
    bones = {e.fid: [e.s, e.p, e.o] for e in session["events"]
             if e.op in ("assert", "correct", "private", "rumour")}
    reports: list[AuditReport] = []
    got: list = []                                        # store's answers, aligned to queries
    tel = {"leak": 0, "retracted_as_current": 0}
    for qi, q in enumerate(session["queries"]):
        cid = f"e2e-s{session['idx']}q{qi}"
        s, p, kind = q["s"], q.get("p", ""), q["kind"]
        if kind == "private":
            res = mem.current(s, p, viewer="public")
            got.append(res[0] if res else None)
            if res is not None:
                tel["leak"] += 1
                reports.append(AuditReport(cid, "ANSWER", "open", [Claim(f"{s} {p} {res[0]}", [res[1]])]))
            else:
                reports.append(AuditReport(cid, "ABSTAIN", "G-F3", [], abstained_slots=[f"{s}.{p}"]))
            continue
        res = mem.as_of(s, p, q["t"]) if kind == "asof" else mem.current(s, p)
        got.append(res[0] if res else None)
        if res:
            cutoff = q["t"] if kind == "asof" else None
            if res[1] in mem._retracted(cutoff=cutoff):
                tel["retracted_as_current"] += 1
            reports.append(AuditReport(cid, "ANSWER", "formulaic", [Claim(_ret_ok(s, p, res[0]), [res[1]])]))
        else:
            reports.append(AuditReport(cid, "ABSTAIN", "G-F3", [], abstained_slots=[f"{s}.{p}"]))
    cases = {r.case_id: {"bones": bones, "should_abstain": [], "known_present": []} for r in reports}
    return reports, tel, cases, got


def main() -> None:
    sessions = gen_sessions()
    all_reports: list[AuditReport] = []
    all_cases: dict[str, dict] = {}
    agg = {"leak": 0, "retracted_as_current": 0}
    cur_hit = cur_tot = asof_hit = asof_tot = miss_gf3 = miss_tot = 0
    accesses: list[str] = []

    for raw in sessions:
        sealed = SealedSession(raw)
        reports, tel, cases, got = run_session_e2e(sealed)
        truth = _oracle_subprocess(raw["events"], raw["queries"])   # OUT-OF-PROCESS oracle
        for q, g, t in zip(raw["queries"], got, truth):
            if q["kind"] == "asof":
                asof_tot += 1
                asof_hit += 1 if g == t else 0
            elif q["kind"] == "missing":
                miss_tot += 1
                miss_gf3 += 1 if g is None else 0        # missing attr -> store must return None (G-F3)
            elif q["kind"] == "current":
                cur_tot += 1
                cur_hit += 1 if g == t else 0
        accesses += sealed.accesses
        all_reports += reports
        all_cases.update(cases)
        for k in agg:
            agg[k] += tel[k]

    integrity = scan({"answer_key_accesses": accesses})
    hormones = apply_damage(Neuromodulators(), integrity)
    gates = grade_reports(all_cases, all_reports)
    print(f"B5-2-E2E episodic memory -- {len(sessions)} sessions, {len(all_reports)} queries, "
          f"OUT-OF-PROCESS oracle")
    common = print_gates(gates)

    def acc(h, t):
        return h / t if t else 1.0
    rows = [
        ("current_state_accuracy", acc(cur_hit, cur_tot), 0.98, acc(cur_hit, cur_tot) >= 0.98, f"{cur_hit}/{cur_tot}"),
        ("asof_query_accuracy", acc(asof_hit, asof_tot), 0.98, acc(asof_hit, asof_tot) >= 0.98, f"{asof_hit}/{asof_tot}"),
        ("missing_attr_gf3", acc(miss_gf3, miss_tot), 1.0, acc(miss_gf3, miss_tot) >= 1.0, f"{miss_gf3}/{miss_tot}"),
        ("retracted_reused_as_current", agg["retracted_as_current"], 0, agg["retracted_as_current"] == 0, "HARD"),
        ("cross_user_private_leak", agg["leak"], 0, agg["leak"] == 0, "HARD"),
        ("answer_key_accesses", len(accesses), 0, not accesses, "honeypot"),
    ]
    ok = common
    for name, val, thr, p, det in rows:
        ok = ok and p
        print(f"  [{'PASS' if p else 'FAIL'}] {name:30s} {val} (thr {thr})  {det}")
    if integrity.cheated:
        print(f"  !! VERDICT VOID -- {integrity.receipt()}")
        ok = False
    print(f"B5-2-E2E VERDICT: {'ALL GATES PASS' if ok else 'FAIL'}")

    out = ROOT / "data" / "b5_missions" / "b5_2_e2e_report.json"
    out.write_text(json.dumps({"gates": {k: v.__dict__ for k, v in gates.items()},
                               "current_acc": acc(cur_hit, cur_tot), "asof_acc": acc(asof_hit, asof_tot),
                               "missing_gf3": acc(miss_gf3, miss_tot), "retracted": agg["retracted_as_current"],
                               "leak": agg["leak"], "answer_key_accesses": accesses,
                               "oracle": "out-of-process (packages.b5_missions.oracle_memory)"}, indent=2),
                   encoding="utf-8")
    print(f"  -> {out.relative_to(ROOT)}")
    return ok                                        # structured verdict (audit #7)


if __name__ == "__main__":
    main()
