# -*- coding: utf-8 -*-
"""SEALED 2-HOP discrimination battery — the composition (backward-chaining) gate. Single-hop is a
store-lookup consistency test; this measures whether discriminate() can COMPOSE two graph hops:
subject -R1-> bridge -R2-> answer ("{} ?" = author then born_in).

Generated from world_pack_full: keep chains where BOTH hops are single-valued (one bridge, one
answer), so the correct answer is unambiguous; distractors are other R2-objects (same type as the
answer). Writes seal_discrimination_mh_{dev,holdout}.jsonl + manifests, deterministic seed, stem
hash split — same discipline as build_discrimination_battery.py.

 python scripts/build_multihop_battery.py [per_chain_cap]
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np                                                     # noqa: E402
from packages.graph_scale.triple_store import TripleStore             # noqa: E402

OUT = REPO / "data" / "eval"
SEED = 20260718

# (relations, stem template) — the template MUST contain every relation's cue IN ORDER so

# chain answers only when EVERY hop is single-valued, so 3-hop yields fewer but clean items.
CHAINS = [
    (["author", "born_in"], "{s}의 저자가 태어난 곳은?"),
    (["author", "occupation"], "{s}의 저자의 직업은?"),
    (["discovered_by", "born_in"], "{s}을(를) 발견한 사람이 태어난 곳은?"),
    (["author", "born_in", "country"], "{s}의 저자가 태어난 곳의 국가는?"),
]

_QID = re.compile(r"^Q\d+$")
_CLEAN = re.compile(r"^[0-9A-Za-z가-힣][0-9A-Za-z가-힣 .,'\-·]{1,38}$")


def _clean(label: str) -> bool:
    return bool(label) and not _QID.match(label) and bool(_CLEAN.match(label)) and not label.isdigit()


def _split(stem: str) -> str:
    return "holdout" if int(hashlib.sha1(stem.encode("utf-8")).hexdigest(), 16) % 100 < 30 else "dev"


def main() -> int:
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    st = TripleStore(REPO / "data" / "graph_scale" / "world_pack_full",
                     dict_backend="sharded", write_src=False)
    cols = st.open_columns()
    s_col, p_col, o_col = cols["s"], cols["p"], cols["o"]
    term = st.terms.term
    _qc: dict[str, str] = {}

    def qlabel(o: str) -> str:
        if not _QID.match(o):
            return o
        if o in _qc:
            return _qc[o]
        lab = next((oo for (_s, p, oo) in st.facts_about(o, limit=8) if p == "qlabel"), o)
        _qc[o] = lab
        return lab

    def single_target(subj: str, rel: str) -> str | None:
        vals = {qlabel(o) for (_s, p, o) in st.facts_about(subj, limit=40) if p == rel}
        vals = {v for v in vals if _clean(v)}
        return next(iter(vals)) if len(vals) == 1 else None

    rng = random.Random(SEED)
    items: list[dict] = []
    for rels, tmpl in CHAINS:
        cid = "->".join(rels)
        rids = [st.terms.lookup(r) for r in rels]
        if any(r is None for r in rids):
            print(f"  {cid}: relation missing, skipped", flush=True)
            continue
        r_first, r_final = rels[0], rels[-1]
        pos = np.nonzero(p_col == rids[0])[0]
        s_r = s_col[pos]
        uniq_s, first_idx, counts = np.unique(s_r, return_index=True, return_counts=True)
        single = counts == 1                                   # subjects with ONE hop-1 bridge
        cand_s_ids = uniq_s[single]
        order = np.arange(len(cand_s_ids))
        np.random.default_rng(SEED).shuffle(order)

        # distractor pool: FINAL-relation objects (same type as the answer), bounded resolved sample
        pos_f = np.nonzero(p_col == rids[-1])[0]
        pool: list[str] = []
        seen: set[str] = set()
        for oid in np.unique(o_col[pos_f])[:6000].tolist():
            lab = qlabel(term(int(oid)))
            if _clean(lab) and lab not in seen:
                seen.add(lab)
                pool.append(lab)
        if len(pool) < 8:
            print(f"  {cid}: final-relation pool too small ({len(pool)}), skipped", flush=True)
            continue

        made = 0
        for k in order.tolist():
            if made >= cap:
                break
            s = term(int(cand_s_ids[k]))
            if not _clean(s):
                continue
            # walk every hop; each must be single-valued or the chain is dropped
            cur = s
            bridge = None
            ok = True
            for r in rels[:-1]:
                cur = single_target(cur, r)
                if cur is None:
                    ok = False
                    break
                bridge = cur
            if not ok:
                continue
            answer = single_target(cur, r_final)               # final hop: one answer
            if answer is None:
                continue
            distractors: list[str] = []
            tries = 0
            while len(distractors) < 3 and tries < 60:
                tries += 1
                d = rng.choice(pool)
                if d != answer and d not in distractors:
                    distractors.append(d)
            if len(distractors) < 3:
                continue
            opts = distractors + [answer]
            rng.shuffle(opts)
            keys = ["A", "B", "C", "D"]
            choices = {keys[j]: opts[j] for j in range(4)}
            gold = keys[opts.index(answer)]
            stem = tmpl.format(s=s)
            items.append({"stem": stem, "choices": choices, "gold": gold,
                          "chain": cid, "subject": s, "bridge": bridge,
                          "answer": answer, "split": _split(stem)})
            made += 1
        print(f"  {cid}: {made} items (final pool {len(pool)})", flush=True)

    seen_stem, uniq = set(), []
    for it in items:
        if it["stem"] in seen_stem:
            continue
        seen_stem.add(it["stem"])
        uniq.append(it)
    uniq.sort(key=lambda it: it["stem"])
    OUT.mkdir(parents=True, exist_ok=True)
    for split in ("dev", "holdout"):
        rows = [it for it in uniq if it["split"] == split]
        path = OUT / f"seal_discrimination_mh_{split}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for it in rows:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        (OUT / f"seal_discrimination_mh_{split}.manifest.json").write_text(
            json.dumps({"n": len(rows), "sha256": sha, "seed": SEED,
                        "chains": ["->".join(rels) for rels, _ in CHAINS], "built": "2026-07-18"},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        by = {}
        for it in rows:
            by[it["chain"]] = by.get(it["chain"], 0) + 1
        print(f"[{split}] n={len(rows)} sha={sha[:12]} by_chain={by}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
