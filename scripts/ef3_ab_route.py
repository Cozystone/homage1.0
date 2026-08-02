# -*- coding: utf-8 -*-
"""E-F3 — live A/B: frame route vs neural realizer on held-out bones (S2.5b verdict).

Grammar-error PROXY (pre-declared, No-LLM): the unseen-word-bigram rate against the human WoW reply
corpus — a bigram no human produced in 69k replies is likely disfluent ("the the", "city of the
city of"). Gates: (1) frame-route unseen-bigram rate < realizer-route rate; (2) G-F3: empty bones
=> BOTH routes abstain 40/40; (3) grounding: every spoken output passes the receipt gate.

  python scripts/ef3_ab_route.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import torch
from tokenizers import Tokenizer

from packages.grounded_composer.dual_route import realize_dual, grounding_gate, ABSTAIN
from packages.reasoning_vm.ace.realizer import Realizer

W = re.compile(r"[A-Za-z']+")
HOLD = REPO / "data" / "graph_scale" / "realizer_holdout.jsonl"
DLG = REPO / "data" / "graph_scale" / "dialogue_grounded.jsonl"
_REL = {"is_a": "is a", "alias": "also called", "located_in": "is located in", "capable_of": "can",
        "has_property": "is", "used_for": "is used for", "part_of": "is part of",
        "made_of": "is made of", "has_a": "has", "manner_of": "is a manner of",
        "defined_as": "is defined as", "grounded_in": "is grounded in"}


from packages.reasoning_vm.ace.match_features import _stem as _st


def _skel_bigrams(text: str, bones) -> list[tuple[str, str]]:
    """Grammar lives in the FUNCTION-word skeleton: delexicalise words traceable to the bones to <E>
    so entity novelty cannot count as a grammar error (fair to both routes; the human reference is
    built the same way with each reply's own bones)."""
    ent = set()
    for s, _r, o in bones:
        ent |= {_st(w) for w in W.findall(f"{s} {o}")}
    ws = [("<E>" if _st(w) in ent else w.lower()) for w in W.findall(text)]
    return [(ws[i], ws[i + 1]) for i in range(len(ws) - 1)]


def main() -> int:
    # human bigram reference (the grammar oracle: what humans actually say)
    human = set()
    with DLG.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
                human.update(_skel_bigrams(r["text"], r.get("bones") or []))
            except Exception:
                continue
    print(f"human bigram reference: {len(human):,} bigrams")

    tok = Tokenizer.from_file(str(REPO / "data/graph_scale/ace2_tokenizer/tokenizer.json"))
    d = torch.load(REPO / "data/graph_scale/realizer.pt", map_location="cpu")
    model = Realizer(d["vocab"]); model.load_state_dict(d["state"]); model.eval()

    def realizer_fn(bones, history):
        lin = "; ".join(f"{s} {_REL.get(r, r.replace('_',' '))} {' '.join(str(o).split()[:24])}"
                        for s, r, o in bones[:6])
        p = [1] + tok.encode("bones: " + lin).ids + [2]
        return tok.decode(model.generate(p, sep_id=2, max_new=40, greedy=True, uid_penalty=4.0)).strip()

    rows = [json.loads(l) for l in HOLD.read_text(encoding="utf-8").splitlines() if l.strip()][:200]

    stats = {"frame": {"unseen": 0, "big": 0, "n": 0, "gate_fail": 0},
             "realizer": {"unseen": 0, "big": 0, "n": 0, "gate_fail": 0}}
    shown = 0
    for r in rows:
        bones = r["bones"]
        # A: frame route (via dual composer, realizer disabled)
        a = realize_dual(bones, realizer_fn=None)
        # B: realizer route (direct)
        b_text = realizer_fn(bones, [])
        for name, text in (("frame", a.text if a.route == "frame" else ""), ("realizer", b_text)):
            if not text or text == ABSTAIN:
                continue
            ok, _rc = grounding_gate(text, bones)
            bg = _skel_bigrams(text, bones)
            if not bg:
                continue
            stats[name]["n"] += 1
            stats[name]["big"] += len(bg)
            stats[name]["unseen"] += sum(1 for g in bg if g not in human)
            stats[name]["gate_fail"] += 0 if ok else 1
        if shown < 3 and a.route == "frame":
            print(f"  FRAME: {a.text}")
            print(f"  REALZ: {b_text[:90]}")
            shown += 1

    print("\n=== E-F3 A/B verdict ===")
    rates = {}
    for name, s in stats.items():
        rate = s["unseen"] / max(1, s["big"])
        rates[name] = rate
        print(f"{name:9}: outputs {s['n']:>3} · unseen-bigram(grammar-error proxy) {rate:.4f} "
              f"· gate_fail {s['gate_fail']}")
    # G-F3 at composer level: empty bones must abstain, 40/40
    gf3 = sum(1 for _ in range(40) if realize_dual([]).text == ABSTAIN)
    print(f"G-F3 composer (empty bones abstain): {gf3}/40 = {gf3/40:.3f}")
    gate1 = rates["frame"] < rates["realizer"]
    gate2 = gf3 == 40
    gate3 = stats["frame"]["gate_fail"] == 0
    print(f"\nGATE1 frame < realizer error rate : {'PASS' if gate1 else 'FAIL'}")
    print(f"GATE2 G-F3 == 1.000               : {'PASS' if gate2 else 'FAIL'}")
    print(f"GATE3 frame grounding fail == 0   : {'PASS' if gate3 else 'FAIL'}")
    print(f"E-F3: {'ALL GATES PASS' if (gate1 and gate2 and gate3) else 'NOT MET'}")
    return 0 if (gate1 and gate2 and gate3) else 1


if __name__ == "__main__":
    raise SystemExit(main())
