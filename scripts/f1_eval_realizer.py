# -*- coding: utf-8 -*-
"""Track F / F1 — evaluate the realizer: fluency (eyeball samples), FAITHFULNESS (does the output
actually express the bones?), and the ★G-F3 knowing/saying-separation probe (empty bones => it must
ABSTAIN, never fabricate a fact). A realizer that invents facts with no bones has become a knowledge
store = No-LLM violation, and this is the measured gate against it.

  python scripts/f1_eval_realizer.py
"""
from __future__ import annotations

import json
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

from packages.reasoning_vm.ace.realizer import Realizer
from packages.reasoning_vm.ace.match_features import tokenize, _stem

DEV = "cuda" if torch.cuda.is_available() else "cpu"
TOKJSON = REPO / "data" / "graph_scale" / "ace2_tokenizer" / "tokenizer.json"
CKPT = REPO / "data" / "graph_scale" / "realizer.pt"
HOLD = REPO / "data" / "graph_scale" / "realizer_holdout.jsonl"
CLS, SEP = 1, 2
_REL = {"is_a": "is a", "alias": "also called", "located_in": "is located in", "capable_of": "can",
        "has_property": "is", "used_for": "is used for", "part_of": "is part of",
        "made_of": "is made of", "has_a": "has", "manner_of": "is a manner of",
        "defined_as": "is defined as"}
_ABSTAIN_CUES = ("don't have", "do not have", "no grounded", "cannot", "not sure", "don't know")


def _lin(bones):
    return "; ".join(f"{s} {_REL.get(r, r.replace('_',' '))} {o}" for s, r, o in bones[:6])


def _content(text):
    return {_stem(w) for w in tokenize(text) if len(w) > 1}


def main() -> int:
    if not CKPT.exists():
        print(f"no realizer at {CKPT} — train first"); return 1
    ckpt = Path(sys.argv[sys.argv.index("--ckpt") + 1]) if "--ckpt" in sys.argv else CKPT
    tok = Tokenizer.from_file(str(TOKJSON))
    d = torch.load(ckpt, map_location=DEV)
    # instantiate the architecture the checkpoint was trained at (size stored on save) so larger
    # realizers load correctly; falls back to the 512/8 default for older checkpoints
    model = Realizer(d["vocab"], d_model=d.get("d_model", 512), layers=d.get("layers", 8)).to(DEV)
    if d.get("untied"):                       # S1 checkpoints carry a separate lm_head — untie first
        import torch.nn as _nn
        model.lm_head.weight = _nn.Parameter(model.tok_emb.weight.detach().clone())
    model.load_state_dict(d["state"]); model.eval()
    print(f"eval ckpt: {ckpt.name} (untied={bool(d.get('untied'))})", flush=True)

    def realize(prompt: str) -> str:
        pids = [CLS] + tok.encode(prompt).ids + [SEP]
        out = model.generate(pids, sep_id=SEP, max_new=48, greedy=True)
        return tok.decode(out).strip()

    hold = [json.loads(l) for l in HOLD.read_text(encoding="utf-8").splitlines() if l.strip()] \
        if HOLD.exists() else []

    # --- fluency + faithfulness on held-out bones ---
    print("=== F1 realizer — grounded realisation samples ===")
    faith_hits = 0
    shown = 0
    for r in hold[:200]:
        say = realize("bones: " + _lin(r["bones"]))
        objs = set()
        for _s, _rel, o in r["bones"]:
            objs |= _content(o)
        said = _content(say)
        faithful = bool(objs and (objs & said))
        faith_hits += 1 if faithful else 0
        if shown < 8:
            print(f"\n  BONES : {_lin(r['bones'])}")
            print(f"  SAY   : {say}")
            print(f"  faithful={faithful}")
            shown += 1
    n = min(200, len(hold))
    print(f"\nfaithfulness (bones expressed in output): {faith_hits}/{n} = {faith_hits/max(1,n):.3f}")

    # --- ★G-F3: empty bones must ABSTAIN (no fabricated fact) ---
    abstain = 0
    trials = 40
    for _ in range(trials):
        say = realize("bones: none")
        if any(c in say.lower() for c in _ABSTAIN_CUES) or len(say) < 3:
            abstain += 1
    print(f"\n★ G-F3 knowing/saying separation — empty-bones abstention: {abstain}/{trials} "
          f"= {abstain/trials:.3f}   [gate: high; fabrication on empty bones = No-LLM breach]")
    print("read: a realizer that stays silent/abstains with no bones has NOT absorbed knowledge into "
          "its weights; that is the neuro-symbolic contract holding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
