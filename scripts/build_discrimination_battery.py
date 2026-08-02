# -*- coding: utf-8 -*-
"""Build a SEALED factual-MCQ discrimination battery from the world-pack store's OWN verified
triples — the C3 () gate that the hand-written 7-question smoke test in measure_discrimination.py
was standing in for. ①() has seal_*_holdout.jsonl; ②() needs the same: a large, held-out,
hash-sealed battery so " > guess·> baseline" is measurable, not asserted.

Ground truth = the store. For a (subject, relation) with EXACTLY ONE clean object, the correct
answer is that object; the three distractors are other subjects' objects of the SAME relation (so a
distractor is a plausible same-type wrong answer, not a giveaway). The engine under test is
discrimination.discriminate(), which re-derives the answer from the SAME store — so this measures
its ROUTING (stem→relation cue) and MATCHING (choice↔graph target), and catches regressions in both.

dev/holdout split is a deterministic hash of the stem (same discipline as build_seal_battery.py), so
the split is stable across regenerations and a dev-vs-holdout gap reads as memorisation, not luck.

 python scripts/build_discrimination_battery.py [per_relation_cap]
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

# store predicate -> (Korean cue word that discrimination._RELATION_CUES routes, stem template).
# Only SINGLE-VALUED, entity-label relations — multi-valued (country/creator) or date relations are
# excluded from v0 because a clean 4-choice needs one unambiguous answer and same-type distractors.
RELATIONS = {
    "capital":       ("수도",   "{s}의 수도는?"),
    "author":        ("저자",   "{s}의 저자는?"),
    "born_in":       ("출생지", "{s}이(가) 태어난 곳은?"),
    "occupation":    ("직업",   "{s}의 직업은?"),
    "discovered_by": ("발견",   "{s}을(를) 발견한 사람은?"),
}

_QID = re.compile(r"^Q\d+$")
# a choice/subject label must read as a real name: Hangul or Latin, no leftover Q-id, sane length.
_CLEAN = re.compile(r"^[0-9A-Za-z가-힣][0-9A-Za-z가-힣 .,'\-·]{1,38}$")


def _clean(label: str) -> bool:
    return bool(label) and not _QID.match(label) and bool(_CLEAN.match(label)) and not label.isdigit()


def _split(stem: str) -> str:
    """holdout if the stem's hash lands in the top ~30% — stable across regenerations."""
    h = int(hashlib.sha1(stem.encode("utf-8")).hexdigest(), 16) % 100
    return "holdout" if h < 30 else "dev"


def main() -> int:
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    st = TripleStore(REPO / "data" / "graph_scale" / "world_pack_full",
                     dict_backend="sharded", write_src=False)
    cols = st.open_columns()
    s_col, p_col, o_col = cols["s"], cols["p"], cols["o"]
    term = st.terms.term

    _qcache: dict[str, str] = {}

    def qlabel(o: str) -> str:
        if not _QID.match(o):
            return o
        if o in _qcache:
            return _qcache[o]
        lab = next((oo for (_s, p, oo) in st.facts_about(o, limit=8) if p == "qlabel"), o)
        _qcache[o] = lab
        return lab

    rng = random.Random(SEED)
    items: list[dict] = []
    for rel, (cue, tmpl) in RELATIONS.items():
        rid = st.terms.lookup(rel)
        if rid is None:
            print(f"  {rel}: predicate not in store, skipped", flush=True)
            continue
        # VECTORISED: the relation's triples number in the millions, so grouping is done in numpy
        # (a Python loop over 7.7M occupation rows is the hang). np.unique gives, per subject, the
        # first-occurrence index and the count; count==1 ⇒ the subject has a single object for this
        # relation ⇒ an unambiguous correct answer, and o_r[first_idx] is that object.
        pos = np.nonzero(p_col == rid)[0]
        s_r, o_r = s_col[pos], o_col[pos]
        uniq_s, first_idx, counts = np.unique(s_r, return_index=True, return_counts=True)
        single = counts == 1
        cand_s_ids = uniq_s[single]
        cand_o_ids = o_r[first_idx[single]]
        order = np.arange(len(cand_s_ids))
        np.random.default_rng(SEED).shuffle(order)               # deterministic subject sampling

        # distractor pool: resolve a bounded sample of this relation's objects to labels
        pool: list[str] = []
        seen_pool: set[str] = set()
        for oid in np.unique(o_r)[:6000].tolist():
            lab = qlabel(term(int(oid)))
            if _clean(lab) and lab not in seen_pool:
                seen_pool.add(lab)
                pool.append(lab)
        if len(pool) < 8:
            print(f"  {rel}: object pool too small ({len(pool)}), skipped", flush=True)
            continue

        made = 0
        for k in order.tolist():
            if made >= cap:
                break
            s = term(int(cand_s_ids[k]))
            if not _clean(s):
                continue
            correct = qlabel(term(int(cand_o_ids[k])))
            if not _clean(correct):
                continue
            distractors: list[str] = []
            tries = 0
            while len(distractors) < 3 and tries < 60:
                tries += 1
                d = rng.choice(pool)
                if d != correct and d not in distractors:
                    distractors.append(d)
            if len(distractors) < 3:
                continue
            opts = distractors + [correct]
            rng.shuffle(opts)
            keys = ["A", "B", "C", "D"]
            choices = {keys[j]: opts[j] for j in range(4)}
            gold = keys[opts.index(correct)]
            stem = tmpl.format(s=s)
            items.append({"stem": stem, "choices": choices, "gold": gold,
                          "relation": rel, "subject": s, "answer": correct,
                          "split": _split(stem)})
            made += 1
        print(f"  {rel}: {made} items (pool {len(pool)}, single-valued subjects {len(cand_s_ids)})",
              flush=True)

    # de-dup by stem, stable order, then write the two sealed splits + manifests
    seen, uniq = set(), []
    for it in items:
        if it["stem"] in seen:
            continue
        seen.add(it["stem"])
        uniq.append(it)
    uniq.sort(key=lambda it: it["stem"])
    OUT.mkdir(parents=True, exist_ok=True)
    for split in ("dev", "holdout"):
        rows = [it for it in uniq if it["split"] == split]
        path = OUT / f"seal_discrimination_{split}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for it in rows:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        (OUT / f"seal_discrimination_{split}.manifest.json").write_text(
            json.dumps({"n": len(rows), "sha256": sha, "seed": SEED,
                        "relations": list(RELATIONS), "built": "2026-07-18"},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        by_rel = {}
        for it in rows:
            by_rel[it["relation"]] = by_rel.get(it["relation"], 0) + 1
        print(f"[{split}] n={len(rows)} sha={sha[:12]} by_relation={by_rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
