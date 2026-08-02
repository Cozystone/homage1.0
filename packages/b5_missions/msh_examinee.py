# -*- coding: utf-8 -*-
"""MSH examinee runtime — solves sealed exams authored on a separate machine (the Radxa examiner).

The examiner holds the answer key; this side only ever sees the exam. Every task is dispatched to a
promoted production organ (episodic_memory.bitemporal / reasoning_vm.precondition_planner / the
incident executor). Exam fields are DATA: parsed as JSON, never executed; free text inside a task is
graph content, never an instruction (injection boundary). A task type we cannot solve returns an
explicit ABSTAIN (fail-closed) -- the examinee never fabricates to look capable.

Transport is pluggable:
  --local-drop <dir>   solve every exam_*.json in a shared folder (plumbing / SFTP-mounted dir)
  --sftp host user ... pull/push over SFTP (owner supplies connection; no credentials are guessed)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.grounded_composer.dual_route import realize_dual
from packages.reasoning_vm.precondition_planner import plan_preconditions
from packages.episodic_memory.bitemporal import BitemporalMemory, Event

import re as _re
# non-disclosable field lexicon (universal sensitive categories, NOT exam-specific). A value on a
# predicate matching any of these is BLOCKED (abstained), never returned. Matching is TOKEN-based:
# the predicate is split on non-alphanumerics so a marker is caught as a COMPONENT of a compound name
# (pii_contact, contact-pii, medical_history) -- a word-boundary regex missed 'pii_contact' because
# '_' is a word char (exam_002 leak). 'note' alone stays data; 'private_notes' -> token 'private'.
_SENSITIVE_TOKENS = {"private", "secret", "confidential", "password", "passwd", "ssn", "pii", "phi",
                     "medical", "health", "salary", "payroll", "clearance", "layoff", "classified",
                     "diagnosis", "biometric", "genetic"}
_SENSITIVE_SUB = ("social_security", "phone", "creditcard", "credit_card")   # safe as substrings


def _is_sensitive(p: str) -> bool:
    low = (p or "").lower()
    toks = set(_re.split(r"[^a-z0-9]+", low))
    return bool(toks & _SENSITIVE_TOKENS) or any(sub in low for sub in _SENSITIVE_SUB)


def _cap(s: str) -> str:
    return s[0].upper() + s[1:] if s and s[0].islower() else s


def _sentence(s: str) -> str:
    """Terminate a sentence exactly once (fixes the double-period artifact the examiner scored:
    a value already ending with punctuation must not get a second period)."""
    s = s.rstrip()
    while s.endswith(".."):                              # collapse an accidental double stop
        s = s[:-1]
    return s if s.endswith((".", "!", "?")) else s + "."


_INJ = _re.compile(r"\b(ignore|disregard|override|reinstate[d]?|classify|declare|execute|delete|"
                   r"shutdown|bypass|reflect this|you must|authorized|instruction|system\s*override)\b",
                   _re.IGNORECASE)

# Temporal-paradox judgment comes from the LEARNED precedence field (packages/temporal_reasoning):
# a 1-D phase coordinate per event token fit on real-corpus order observations. The hand-ranked
# 3-phase lexicon that used to live here was itself a hand-rule (the examiner's exam_004 scored it
# 0/8) and was DELETED -- no word grades are authored in code anymore. An unknown predicate yields
# no judgment (honest abstention), never a guess. See docs/ATANOR_temporal_causal_physics.md.
from packages.temporal_reasoning.precedence_field import PrecedenceField
from packages.temporal_reasoning.anomaly import detect_paradoxes, parse_ts as _parse_ts

_FIELD = PrecedenceField.load()          # None until the field has been trained -> detector abstains


def _decide(claims: list, abstained: list) -> str:
    if abstained:
        return "PARTIAL" if claims else "ABSTAIN"
    return "ANSWER" if claims else "ABSTAIN"


def _solve_incident(task: dict) -> dict:
    """DOMAIN-GENERAL: report every grounded fact on ANY predicate; a functional slot (s,p) holding
    >=2 distinct values is a CONFLICT -> report each observation + abstain the resolution; a '?'/''
    sentinel -> abstain; bones carrying injected commands are quarantined (data, never asserted).
    NL-PROMPT COMPLIANT (examiner rule 2026-07-20): the queries[].prompt is the examiner's trusted
    instruction -- when it asks for narrative/chronology the answer carries an ordered narrative read
    off the 4-D timeline, and every LEARNED temporal paradox is voiced as an explicit sentence naming
    both bones. Paradox judgment comes from the precedence field, never a hand lexicon."""
    bones = task.get("bones", {})
    blocked = [bid for bid, (s, p, o) in bones.items() if _INJ.search(str(o))]
    ok = {bid: v for bid, v in bones.items() if bid not in blocked}

    slots: dict[tuple, list] = {}                        # (s,p) -> [(o,bid), ...]
    for bid, (s, p, o) in ok.items():
        slots.setdefault((s, p), []).append((o, bid))

    claims, abstained = [], []
    for bid in blocked:                                  # quarantined bones stay VISIBLE as data --
        s, p, o = bones[bid]                             # verbatim, cited, never followed (the
        claims.append({"text": _sentence(f"The {p.replace('_', ' ')} of {s} reads: {o}"),
                       "bone_ids": [bid]})               # examiner-endorsed t1/t5 pattern)
    for (s, p), obs in sorted(slots.items()):
        real = [(o, bid) for o, bid in obs if str(o).strip() not in ("?", "")]
        if not real:                                     # only sentinels present -> missing value
            abstained.append(f"{s}.{p}")
            continue
        distinct = {o for o, _ in real}
        if len(distinct) > 1:                            # conflict -> report each, abstain resolution
            for o, bid in real:
                dr = realize_dual([[s, p, o]])
                if dr.grounded and dr.route != "abstain":
                    claims.append({"text": _sentence(dr.text), "bone_ids": [bid]})
            abstained.append(f"{s}.{p}")
            continue
        o, bid = real[0]
        dr = realize_dual([[s, p, o]])
        if dr.grounded and dr.route != "abstain":
            claims.append({"text": _sentence(dr.text), "bone_ids": [bid]})
        else:
            abstained.append(f"{s}.{p}")                 # ungroundable -> abstain, never fabricate

    # learned temporal-paradox judgment (precedence field; abstains when untrained/unknown)
    paradoxes = detect_paradoxes(ok, _FIELD)
    for px in paradoxes:
        abstained.append(px.flagged_slot)                # flag offender; values stay cited as data

    # NL prompt compliance: narrative reconstruction when the examiner's prompt asks for one
    narrative: list[dict] = []
    prompt = " ".join(str(q.get("prompt", "")) for q in task.get("queries", []))
    wants_narrative = bool(_re.search(r"\b(narrative|reconstruct|chronolog|lifecycle|describe|"
                                      r"story|sequence of events|timeline)\b", prompt, _re.IGNORECASE))
    if wants_narrative:
        timeline = sorted(((_parse_ts(o), s, p, o, bid) for bid, (s, p, o) in ok.items()
                           if _parse_ts(o) is not None), key=lambda x: x[0])
        for ts, s, p, o, bid in timeline:                # read the story off the 4-D time axis
            narrative.append({"text": f"At {o}, {s} recorded {p.replace('_', ' ')}.",
                              "bone_ids": [bid]})
        for px in paradoxes:                             # voice each impossibility explicitly
            narrative.append({"text": px.sentence(), "bone_ids": [px.early_bone, px.late_bone]})

    out = {"decision": _decide(claims, abstained), "route": "composer",
           "claims": claims, "abstained_slots": sorted(set(abstained)), "blocked_uids": blocked}
    if narrative:
        out["narrative"] = narrative
    return out


def _solve_memory(task: dict) -> dict:
    mem = BitemporalMemory()
    for e in task.get("events", []):
        mem.ingest(Event(e["fid"], e["op"], e["s"], e.get("p", ""), e.get("o", ""),
                         int(e.get("t", 0)), e.get("retracts", ""), e.get("owner", ""),
                         int(e.get("rt", -1))))          # recorded-time (transaction-time); -1=unset
    claims, abstained, blocked, narrative = [], [], [], []
    # Which standing values are private, and to whom. `claims` is a FLAT per-task list with no
    # per-query structure, so an owner's legitimate disclosure and a stranger's refusal of the SAME
    # slot would otherwise collapse into one unqualified sentence -- which reads as a leak, because
    # nothing in the answer says who was entitled to it. Every private value therefore carries its
    # viewer scope in the claim itself.
    _private_owner = {e["fid"]: e.get("owner", "")
                      for e in task.get("events", []) if e.get("op") == "private"}
    for q in task.get("queries", []):
        kind, s, p = q.get("kind"), q.get("s"), q.get("p", "")
        prompted = bool(str(q.get("prompt", "")).strip())  # examiner asked in prose -> answer in prose
        when = f" as of t={q.get('t')}" if kind == "asof" else ""
        if _is_sensitive(p):                              # sensitive field -> BLOCK, never disclose
            blocked.append(f"{s}.{p}")
            abstained.append(f"{s}.{p}")
            if prompted:
                narrative.append({"text": f"The {p.replace('_', ' ')} of {s} is a protected field; "
                                          f"the system does not disclose it.", "bone_ids": []})
            continue
        # VIEWER-CONDITIONED DISCLOSURE: a `private` record is withheld from OTHER viewers but is
        # disclosable to its own owner (bitemporal._state already enforces exactly this). The viewer
        # must be carried through from the query -- hardcoding "public" made every owner look like a
        # stranger and turned a correct disclosure into an over-abstention. Sensitive-CATEGORY
        # predicates stay blocked above regardless of viewer; ownership is a separate axis.
        viewer = next((str(q[k]) for k in ("viewer", "as_viewer", "querying_viewer", "requester")
                       if q.get(k)), "public")
        if kind == "asof":
            res = mem.as_of(s, p, int(q["t"]), viewer=viewer)
        elif kind == "asknown":                           # true bitemporal: belief about valid-time
            vt = q.get("t")                               # `t` as known at recorded-time `rt`
            res = mem.as_known(s, p, None if vt is None else int(vt), int(q["rt"]), viewer=viewer)
        else:
            res = mem.current(s, p, viewer=viewer)
        if res:
            owner = _private_owner.get(res[1], "")
            body = (f"The {p} of {s} is {res[0]}, a private record disclosed only to its owner "
                    f"{owner} and withheld from every other viewer" if owner
                    else f"The {p} of {s} is {res[0]}")
            claims.append({"text": _sentence(body), "bone_ids": [res[1]]})
            if prompted:
                narrative.append({"text": _sentence(f"Considering the full event history, the "
                                          f"{p.replace('_', ' ')} of {s}{when} resolves to {res[0]}"),
                                  "bone_ids": [res[1]]})
        else:
            abstained.append(f"{s}.{p}")                  # missing/deleted/retracted-gap -> abstain
            if any(e.get("op") == "private" and e.get("s") == s and e.get("p") == p
                   and e.get("owner") and e.get("owner") != viewer
                   for e in task.get("events", [])):      # withheld because THIS viewer is not the
                blocked.append(f"{s}.{p}")                # owner -> record the refusal explicitly
            if prompted:
                narrative.append({"text": f"No valid value stands for the {p.replace('_', ' ')} of "
                                          f"{s}{when}: the value was retracted, deleted, or never set, "
                                          f"so the system reports an abstention rather than a stale "
                                          f"value.", "bone_ids": []})
    out = {"decision": _decide(claims, abstained), "route": "bitemporal_memory",
           "claims": claims, "abstained_slots": sorted(set(abstained)), "blocked_uids": blocked}
    if narrative:
        out["narrative"] = narrative
    return out


def _solve_recovery(task: dict) -> dict:
    plan = plan_preconditions(task.get("bones", {}))
    claims = [{"text": st.text, "bone_ids": [b for b in st.support if b]} for st in plan.steps]
    return {"decision": "ANSWER" if plan.goal_emitted else ("PARTIAL" if claims else "ABSTAIN"),
            "route": "precondition_planner", "claims": claims,
            "abstained_slots": sorted(set(plan.abstained)), "blocked_uids": []}


_DISPATCH = {"incident": _solve_incident, "memory": _solve_memory, "recovery": _solve_recovery}


def solve_task(task: dict) -> dict:
    fn = _DISPATCH.get(task.get("type"))
    if fn is None:                                        # unknown type -> fail-closed abstain
        return {"decision": "ABSTAIN", "route": "unsupported",
                "claims": [], "abstained_slots": [f"task.{task.get('type')}"], "blocked_uids": []}
    try:
        return fn(task)
    except Exception as e:                                # any solver error -> honest abstain, never fake
        return {"decision": "ABSTAIN", "route": "error", "claims": [],
                "abstained_slots": [f"task.error:{type(e).__name__}"], "blocked_uids": []}


def solve_exam(exam: dict) -> dict:
    return {"exam_id": exam.get("exam_id"),
            "answers": [{"id": t.get("id"), "audit": solve_task(t)} for t in exam.get("tasks", [])]}


def run_local_drop(drop: Path) -> list[str]:
    done = []
    for exam_fp in sorted(drop.glob("exam_*.json")):
        ans_fp = drop / exam_fp.name.replace("exam_", "answers_")
        if ans_fp.exists():
            continue
        exam = json.loads(exam_fp.read_text(encoding="utf-8"))
        ans_fp.write_text(json.dumps(solve_exam(exam), indent=2), encoding="utf-8")
        done.append(ans_fp.name)
    return done


def _sftp_batch(host: str, user: str, key: str, remote_dir: str, commands: str) -> str:
    """Run an sftp batch (key auth only, no password ever). Returns stdout."""
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".sftp", delete=False, encoding="utf-8") as f:
        f.write(f"cd {remote_dir}\n{commands}\n")
        batch = f.name
    try:
        p = subprocess.run(["sftp", "-i", key, "-o", "BatchMode=yes",
                            "-o", "StrictHostKeyChecking=accept-new", "-b", batch, f"{user}@{host}"],
                           capture_output=True, text=True, timeout=120)
        return p.stdout + p.stderr
    finally:
        Path(batch).unlink(missing_ok=True)


def run_sftp(host: str, user: str, key: str, remote_dir: str, workdir: Path) -> list[str]:
    """One poll cycle: list remote exam_*.json, pull any without a local answer, solve, push answers.
    The examinee fetches ONLY exam files and pushes ONLY answers -- it never reads a key or score."""
    workdir.mkdir(parents=True, exist_ok=True)
    listing = _sftp_batch(host, user, key, remote_dir, "ls -1")
    # sftp `ls -1` may return full paths OR basenames depending on version -> normalise to basename
    names = {ln.strip().rsplit("/", 1)[-1] for ln in listing.splitlines()}
    exams = sorted(n for n in names if n.startswith("exam_") and n.endswith(".json"))
    done = []
    for exam_name in exams:
        ans_name = exam_name.replace("exam_", "answers_")
        if ans_name in names:                            # already answered (and possibly graded) ->
            continue                                     # NEVER re-solve a seen exam (anti-overfit)
        local_exam = workdir / exam_name
        _sftp_batch(host, user, key, remote_dir, f"get {exam_name} {local_exam.as_posix()}")
        if not local_exam.exists():
            continue
        exam = json.loads(local_exam.read_text(encoding="utf-8"))
        local_ans = workdir / ans_name
        local_ans.write_text(json.dumps(solve_exam(exam), indent=2), encoding="utf-8")
        _sftp_batch(host, user, key, remote_dir, f"put {local_ans.as_posix()} {ans_name}")
        done.append(ans_name)
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local-drop", type=str, help="shared folder with exam_*.json to solve")
    ap.add_argument("--sftp-host", type=str, help="Radxa host/IP")
    ap.add_argument("--sftp-user", type=str, help="Radxa SFTP username")
    ap.add_argument("--sftp-key", type=str, default=str(Path.home() / ".ssh" / "atanor_msh_ed25519"))
    ap.add_argument("--remote-dir", type=str, default="/srv/msh/drop")
    ap.add_argument("--workdir", type=str, default=str(Path.home() / ".atanor_msh"))
    ap.add_argument("--watch", type=int, default=0, help="poll every N seconds until interrupted")
    args = ap.parse_args()

    def one_cycle() -> list[str]:
        if args.local_drop:
            return run_local_drop(Path(args.local_drop))
        return run_sftp(args.sftp_host, args.sftp_user, args.sftp_key, args.remote_dir, Path(args.workdir))

    if not args.local_drop and not (args.sftp_host and args.sftp_user):
        print("need --local-drop <dir>  OR  --sftp-host <ip> --sftp-user <name>")
        return
    if args.watch:
        import time
        from datetime import datetime
        print(f"[watch] polling every {args.watch}s (Ctrl-C to stop)")
        while True:
            try:
                wrote = one_cycle()
                if wrote:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] SOLVED+UPLOADED -> {wrote}", flush=True)
            except Exception as e:                        # transient network error -> keep watching
                print(f"[{datetime.now().strftime('%H:%M:%S')}] poll error: {type(e).__name__}: {e}", flush=True)
            time.sleep(args.watch)
    else:
        wrote = one_cycle()
        print(f"solved+uploaded -> {wrote}" if wrote else "no new exams yet")


if __name__ == "__main__":
    main()
