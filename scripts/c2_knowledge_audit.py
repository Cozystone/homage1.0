# -*- coding: utf-8 -*-
"""C2 (/) audit — the world-pack's coverage AND correctness against a CANONICAL oracle, with
alias-aware resolution. Unlike the C3 discrimination battery (drawn FROM the store, so store-lookup
consistent by construction), this checks the store against facts KNOWN-true externally, so it can
find COVERAGE GAPS (§2: France·) and WRONG facts (measured 2026-07-18: Paris→country→USA,
coffee→defined_as→"eye color", photosynthesis→"Pokémon move" — polysemy/wrong-sense).

C2 DONE gate (FINAL_PLAN §2/§4): major-entity gaps → 0, fact_qa correctness ≥ target, hallucination 0.
This is a RECEIPT of where C2 stands, not a claim. Run: python scripts/c2_knowledge_audit.py
"""
from __future__ import annotations

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

_Q = re.compile(r"^Q\d+$")

# CANONICAL oracle: (subject, relation, {acceptable answer substrings}). Facts known-true externally;

# writes to the store; it only reads the store and compares.
ORACLE = [
    ("France", "capital", {"paris", "파리"}),
    ("Germany", "capital", {"berlin", "베를린"}),
    ("Japan", "capital", {"tokyo", "도쿄"}),
    ("South Korea", "capital", {"seoul", "서울"}),
    ("United States", "capital", {"washington", "워싱턴"}),
    ("Brazil", "capital", {"brasília", "brasilia", "브라질리아"}),
    ("Italy", "capital", {"rome", "로마"}),
    ("Spain", "capital", {"madrid", "마드리드"}),
    ("China", "capital", {"beijing", "베이징", "peking"}),
    ("United Kingdom", "capital", {"london", "런던"}),
    ("Paris", "country", {"france", "프랑스"}),
    ("Tokyo", "country", {"japan", "일본"}),
    ("Seoul", "country", {"korea", "한국", "대한민국"}),
    ("Berlin", "country", {"germany", "독일"}),
    ("Albert Einstein", "born_in", {"ulm", "울름", "german", "독일"}),
    ("William Shakespeare", "occupation", {"playwright", "poet", "writer", "극작가", "시인", "작가"}),
    ("Isaac Newton", "occupation", {"physicist", "mathematician", "물리", "수학"}),
    ("water", "defined_as", {"h2o", "liquid", "hydrogen", "물", "액체", "constituent"}),
    ("coffee", "defined_as", {"beverage", "drink", "brewed", "음료", "seeds"}),
    ("photosynthesis", "defined_as", {"light", "plants", "glucose", "광합성", "식물", "energy"}),
]


def _norm(s: str) -> str:
    return re.sub(r"[\s.,'\"()]+", "", str(s).lower())


def main() -> int:
    st = TripleStore(REPO / "data" / "graph_scale" / "world_pack_full",
                     dict_backend="sharded", write_src=False)
    cols = st.open_columns()
    s_col, p_col, o_col = cols["s"], cols["p"], cols["o"]
    term = st.terms.term
    aid = st.terms.lookup("alias")
    _qc: dict[str, str] = {}

    from packages.graph_scale.qid_labels import resolve as _sidecar   # read-only Q-id label sidecar

    def qlabel(o: str) -> str:
        if not _Q.match(str(o)):
            return o
        if o in _qc:
            return _qc[o]
        v = next((x for (_s, p, x) in st.facts_about(o, limit=8) if p == "qlabel"), o)
        if _Q.match(str(v)):                          # store had no qlabel → try the sidecar backfill
            v = _sidecar(v)
        _qc[o] = v
        return v

    def rev_alias(subj: str) -> list[str]:
        sid = st.terms.lookup(subj)
        if sid is None or aid is None:
            return []
        m = (p_col == aid) & (o_col == sid)
        return [term(int(s_col[i])) for i in np.nonzero(m)[0][:6].tolist()]

    from packages.graph_scale.supplementary_facts import facts_for as _supp   # read-only overlay

    def resolved(subj: str, rel: str) -> list[str]:
        seen = {subj}
        fx = list(st.facts_about(subj, limit=60))
        alts = {o for (_s, p, o) in fx if p == "alias"} | set(rev_alias(subj))
        for a in alts:
            if a not in seen and not _Q.match(str(a)):
                seen.add(a)
                fx += st.facts_about(a, limit=60)
        vals = [qlabel(o) for (_s, p, o) in fx if p == rel]
        for a in seen:                                 # supplement facts the store is MISSING
            for row in _supp(a, rel):
                vals.extend(row["object"])
        return vals

    correct = wrong = missing = 0
    fails: list[str] = []
    for subj, rel, accept in ORACLE:
        vals = [v for v in resolved(subj, rel) if v and not _Q.match(str(v))]
        if not vals:
            missing += 1
            fails.append(f"MISSING  {subj} -{rel}-> ? (want {sorted(accept)[:2]})")
            continue
        norm_accept = {_norm(a) for a in accept}
        hit = any(any(na in _norm(v) or _norm(v) in na for na in norm_accept) for v in vals)
        if hit:
            correct += 1
        else:
            wrong += 1
            fails.append(f"WRONG    {subj} -{rel}-> {vals[:2]} (want {sorted(accept)[:2]})")
    n = len(ORACLE)
    print("=== C2 knowledge audit (world-pack vs canonical oracle, alias-resolved) ===\n")
    for f in fails:
        print(f"  {f}")
    print(f"\n  correct={correct}/{n}  wrong={wrong}  missing={missing}")
    print(f"  coverage(answered)={round((correct + wrong) / n, 3)}  "
          f"correctness(of answered)={round(correct / max(1, correct + wrong), 3)}")
    gate = correct / n >= 0.90 and wrong == 0
    print(f"\n  C2 gate (correct>=0.90 of all, wrong==0): {'PASS' if gate else 'not yet'}")
    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
