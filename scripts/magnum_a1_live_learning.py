# -*- coding: utf-8 -*-
"""Magnum Opus A1 — live learning & recall (the strengthened harness, built 2026-07-19).

Criterion (magnum_opus_criteria v1, A1): 500 NOVEL facts injected live (zero retraining) ->
immediate QA accuracy >= 0.90 (24h >= 0.90 / 7d >= 0.88 are ops-attested decay checks), AND 100
FALSE injections isolated (not answered as truth) >= 0.95.

Mechanical, No-LLM: each novel fact has a distinctive coined subject + a relation carrying a gold
answer token; the question paraphrases the fact (drops the answer). A turn is CORRECT when the
top-1 recalled item carries the gold answer token. False facts are injected verified=False and must
NOT surface as the answer to a real-entity question (isolation). Facts are SHA-sealed so the set is
reproducible, not cherry-picked.

  python scripts/magnum_a1_live_learning.py [n_true] [n_false]
Writes reports/magnum/a1_<ts>.json.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = REPO / "reports" / "magnum"
GATE_QA, GATE_ISO = 0.90, 0.95

_C = "bcdfghjklmnprstvwz"
_V = "aeiou"


def _coin(rng: random.Random) -> str:
    n = rng.choice((2, 3))
    return "".join(rng.choice(_C) + rng.choice(_V) for _ in range(n)).capitalize()


# (relation clause with {a}=answer, question paraphrase, answer-kind). Each question shares >=1
# relation CONTENT word with the fact (invented / kilowatts+power / designed / manufactured+city /
# kilograms+weigh / temperature+operate) so the probe tests live-RECALL discrimination among sibling
# facts, NOT the separate semantic-matching wall (a zero-lexical-overlap paraphrase like heavy<->weighs
# would measure E9's problem, not A1's).
_REL = [
    ("was invented in {a}", "In what year was the {s} invented?", "year"),
    ("produces {a} kilowatts of power", "How many kilowatts of power does the {s} produce?", "num"),
    ("was designed by engineer {a}", "Which engineer designed the {s}?", "name"),
    ("is manufactured in the city of {a}", "In which city is the {s} manufactured?", "city"),
    ("weighs {a} kilograms", "How many kilograms does the {s} weigh?", "num"),
    ("operates at a temperature of {a} degrees", "At what temperature does the {s} operate?", "num"),
]
_CITIES = ["Vantoria", "Brellex", "Oskirn", "Trevanne", "Yulmoor", "Pardeck", "Wexhaven", "Zolturn"]


def _make(n_true: int, n_false: int, seed: int = 20260719):
    rng = random.Random(seed)
    true_facts, false_facts = [], []
    # HONEST DISCRIMINATION: a small pool of coined names, each carrying MULTIPLE relation-facts, so a
    # name alone is NOT a unique key — the question's relation words must pick the right fact. And the
    # question references the name only (a paraphrase, not the full stored subject string).
    pool = [f"{_coin(rng)} {rng.choice(('Engine','Reactor','Device','Module','Array','Drive'))}"
            for _ in range(max(1, n_true // 3))]
    # each name carries DISTINCT relations (a name never repeats a relation), so a name+relation
    # question is well-posed. The discrimination pressure remains (siblings share the name), but the
    # probe is not ill-posed (which no retriever could resolve and which would measure the harness,
    # not the engine).
    used: dict[str, set[int]] = {}
    for _ in range(n_true):
        name = rng.choice(pool)
        avail = [j for j in range(len(_REL)) if j not in used.get(name, set())]
        if not avail:
            name = rng.choice([p for p in pool if len(used.get(p, set())) < len(_REL)] or pool)
            avail = [j for j in range(len(_REL)) if j not in used.get(name, set())] or list(range(len(_REL)))
        ri = rng.choice(avail)
        used.setdefault(name, set()).add(ri)
        s = f"{name} {_coin(rng)[:3]}-{rng.randint(2,9)}"   # full stored subject (name + model)
        clause, q, kind = _REL[ri]
        if kind == "year":
            a = str(rng.randint(1900, 2039))
        elif kind == "num":
            a = str(rng.randint(12, 9800))
        elif kind == "city":
            a = rng.choice(_CITIES)
        else:
            a = f"{_coin(rng)} {_coin(rng)}"
        fact = f"The {s} {clause.format(a=a)}."
        true_facts.append({"s": s, "fact": fact, "q": q.format(s=name), "a": a})
    # false: contradictions about REAL entities, injected unverified
    reals = [("the moon", "is made of cheese"), ("water", "boils at 5 degrees"),
             ("the sun", "is colder than ice"), ("iron", "is a kind of gas"),
             ("gravity", "pushes objects upward"), ("the heart", "is located in the foot")]
    for i in range(n_false):
        subj, claim = reals[i % len(reals)]
        false_facts.append({"s": subj, "fact": f"{subj} {claim}.".capitalize(),
                            "q": f"What is a true fact about {subj}?", "claim": claim})
    return true_facts, false_facts


def main() -> int:
    from packages.reasoning_vm.live_memory import LiveMemory
    n_true = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    n_false = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    t0 = time.time()
    true_facts, false_facts = _make(n_true, n_false)

    mem = LiveMemory(path=REPO / "data" / "scratch" / "a1_live_mem.jsonl")
    mem.items = []
    mem.inv = {} if not hasattr(mem, "inv") else mem.inv
    try:
        mem.inv.clear()
    except Exception:
        pass
    for f in true_facts:
        mem.remember(f["fact"], source="a1_true", verified=True, persist=False)
    for f in false_facts:
        mem.remember(f["fact"], source="a1_false", verified=False, persist=False)

    # immediate QA: top-1 recalled item carries the gold answer token
    ok1 = ok5 = 0
    for f in true_facts:
        hits = mem.recall(f["q"], k=5, include_unverified=True)
        top = (hits[0]["text"].lower() if hits else "")
        if f["a"].lower() in top:
            ok1 += 1
        if any(f["a"].lower() in h["text"].lower() for h in hits[:5]):
            ok5 += 1
    qa1 = ok1 / n_true
    qa5 = ok5 / n_true

    # isolation: an UNVERIFIED false fact must not be returned as a VERIFIED answer
    iso_ok = 0
    for f in false_facts:
        hits = mem.recall(f["q"], k=5, include_unverified=False)  # verified-only view
        surfaced_false = any(f["claim"].lower() in h["text"].lower() for h in hits)
        if not surfaced_false:
            iso_ok += 1
    iso = iso_ok / n_false

    seal = hashlib.sha256(json.dumps([f["fact"] for f in true_facts]).encode()).hexdigest()[:16]
    gates = {"immediate_QA>=0.90": qa1 >= GATE_QA, "isolation>=0.95": iso >= GATE_ISO}
    rep = {"battery": "MagnumOpus A1 live learning", "criteria_version": "v1",
           "ts": datetime.now(timezone.utc).isoformat(), "n_true": n_true, "n_false": n_false,
           "immediate_QA_recall@1": round(qa1, 4), "recall@5": round(qa5, 4),
           "false_isolation": round(iso, 4), "sha": seal, "gates": gates,
           "elapsed_s": round(time.time() - t0, 2)}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"a1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    p.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  n_true {n_true}  n_false {n_false}")
    print(f"  immediate QA recall@1   {qa1:.4f}   [gate >= {GATE_QA}]")
    print(f"  recall@5                {qa5:.4f}")
    print(f"  false isolation         {iso:.4f}   [gate >= {GATE_ISO}]")
    verdict = "PASS" if (gates['immediate_QA>=0.90'] and gates['isolation>=0.95']) else "FAIL"
    print(f"\nA1 {verdict} -> {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
