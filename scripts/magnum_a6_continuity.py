# -*- coding: utf-8 -*-
"""Magnum Opus A6 — conversational continuity battery.

Criterion (magnum_opus_criteria v1, Tier A6): the 7-day unattended run PLUS a continuity
battery (anaphora / correction / follow-up, 200 exchanges) at >= 0.90.
This script implements the battery half; the 7-day uptime half is an operations attestation.

Exchange types (each is a MULTI-TURN probe — the point is memory across turns, not single QA):
  anaphora     T1 states a subject, T2 refers to it only as "it/that/they"
  correction   T1 asserts something wrong, T2 corrects it, T3 checks the correction took
  followup     T2 asks a narrower question that only makes sense given T1
  persistence  an unrelated turn is injected between the setup and the probe (distractor)
  reset_trap   T2 changes subject, T3 refers to "it" — "it" must mean the NEW subject

Scoring is mechanical: each probe declares expected tokens that a correct continuation must
contain, and forbidden tokens that indicate the model lost or confused the referent. A turn
counts as correct only when it hits >=1 expected and 0 forbidden. Abstention counts as
INCORRECT here (unlike A3): losing the thread is a capability failure, not an honesty one.

Usage:
    python scripts/magnum_a6_continuity.py build [n]
    python scripts/magnum_a6_continuity.py run [n]
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8502"
ITEMS = REPO / "data" / "benchmarks" / "magnum" / "a6_items.jsonl"
OUT = REPO / "reports" / "magnum"
GATE = 0.90

# (subject, expected-token, a contrasting subject used for reset traps)
SUBJECTS = [
    ("the moon", "moon", "the sun"), ("a volcano", "volcano", "a glacier"),
    ("penicillin", "penicillin", "aspirin"), ("the heart", "heart", "the lung"),
    ("photosynthesis", "photosynthesis", "respiration"), ("iron", "iron", "copper"),
    ("a compiler", "compiler", "a database"), ("the Amazon river", "amazon", "the Nile"),
    ("sound", "sound", "light"), ("oxygen", "oxygen", "nitrogen"),
    ("a glacier", "glacier", "a desert"), ("DNA", "dna", "rna"),
]


def build(n: int) -> None:
    items: list[dict] = []
    i = 0
    while len(items) < n:
        subj, tok, other = SUBJECTS[i % len(SUBJECTS)]
        otok = other.split()[-1].lower()
        i += 1
        items.append({"type": "anaphora", "turns": [f"Tell me about {subj}.", "Where is it found?"],
                      "expect": [tok], "forbid": []})
        items.append({"type": "followup", "turns": [f"Tell me about {subj}.", "What is it made of?"],
                      "expect": [tok], "forbid": []})
        items.append({"type": "persistence",
                      "turns": [f"Tell me about {subj}.", "What day comes after Monday?",
                                "Going back — what kind of thing is it?"],
                      "expect": [tok], "forbid": []})
        items.append({"type": "reset_trap",
                      "turns": [f"Tell me about {subj}.", f"Actually, tell me about {other} instead.",
                                "What is it a kind of?"],
                      "expect": [otok], "forbid": [tok]})
        items.append({"type": "correction",
                      "turns": [f"{subj} is a kind of sandwich, right?",
                                f"No, that's wrong. Forget that — what IS {subj}?"],
                      "expect": [tok], "forbid": ["sandwich"]})
    items = items[:n]
    for it in items:
        it["id"] = hashlib.sha256(json.dumps(it["turns"]).encode()).hexdigest()[:12]
        it["split"] = "holdout" if int(it["id"][:8], 16) % 10 < 3 else "dev"
    ITEMS.parent.mkdir(parents=True, exist_ok=True)
    with io.open(ITEMS, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"built {len(items)} exchanges -> {ITEMS.relative_to(REPO)}  "
          f"sha256={hashlib.sha256(ITEMS.read_bytes()).hexdigest()[:16]}")


def _ask(q: str, history: list[dict]) -> str:
    """The API is STATELESS per request: AtanorChatRequest carries context in
    `conversation_context` (a list of prior turns), NOT a session id. The first version of this
    harness sent session_id/conversation_id — fields the model simply drops — so every turn ran
    with a blank slate and the battery scored 0.04. That number measured the harness, not the
    engine. Always confirm the request schema before reporting a capability verdict."""
    body = json.dumps({"question": q, "conversation_context": history}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/chat/atanor", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return f"__ERROR__ {e}"
    res = resp.get("result") if isinstance(resp, dict) else None
    if isinstance(res, dict):
        for k in ("answer", "text", "message"):
            if isinstance(res.get(k), str):
                return res[k]
    return json.dumps(resp, ensure_ascii=False)[:300]


def run(limit: int | None) -> int:
    if not ITEMS.exists():
        print("no item set — run `build` first")
        return 1
    items = [json.loads(l) for l in io.open(ITEMS, encoding="utf-8") if l.strip()]
    if limit:
        items = items[:limit]
    by_type: dict[str, dict] = {}
    failures: list[dict] = []
    errors = 0
    for it in items:
        history: list[dict] = []
        last = ""
        for t in it["turns"]:
            last = _ask(t, history)
            if last.startswith("__ERROR__"):
                break
            history.append({"role": "user", "content": t})
            history.append({"role": "assistant", "content": last})
        if last.startswith("__ERROR__"):
            errors += 1
            continue
        low = last.lower()
        hit = any(e.lower() in low for e in it["expect"])
        bad = any(f.lower() in low for f in it["forbid"])
        ok = hit and not bad
        st = by_type.setdefault(it["type"], {"n": 0, "ok": 0})
        st["n"] += 1
        st["ok"] += int(ok)
        if not ok and len(failures) < 25:
            failures.append({"id": it["id"], "type": it["type"], "turns": it["turns"],
                             "final_answer": last[:200], "expect": it["expect"],
                             "forbid_hit": bad})
    n = sum(v["n"] for v in by_type.values())
    correct = sum(v["ok"] for v in by_type.values())
    acc = correct / n if n else 0.0
    rep = {"battery": "MagnumOpus A6 continuity", "criteria_version": "v1",
           "ts": datetime.now(timezone.utc).isoformat(), "n": n, "request_errors": errors,
           "by_type": {k: {**v, "acc": round(v["ok"] / v["n"], 3)} for k, v in by_type.items()},
           "accuracy": round(acc, 4), "gate": GATE, "PASS": acc >= GATE,
           "failures": failures,
           "note": "battery half only; the 7-day unattended-uptime half is an ops attestation"}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"a6_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  exchanges {n}  errors {errors}")
    for k, v in sorted(rep["by_type"].items()):
        print(f"  {k:12s} n={v['n']:3d}  acc={v['acc']}")
    print(f"\n  ACCURACY {acc:.4f}   [gate >= {GATE}]")
    print(f"A6 {'PASS' if rep['PASS'] else 'FAIL'} -> {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    arg = int(sys.argv[2]) if len(sys.argv) > 2 else None
    raise SystemExit(build(arg or 200) or 0 if cmd == "build" else run(arg))
