# -*- coding: utf-8 -*-
"""OpenBookQA — No-LLM . 1326 (= ) ,
 (+) . MMLU - ( ). 0,
. 0.25. acc = No-LLM ( ). .

 python scripts/eval_obqa.py
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OBQA = REPO / "data" / "benchmarks" / "obqa"
_TOK = re.compile(r"[a-z]+")
_STOP = {"the", "a", "an", "of", "to", "in", "is", "are", "be", "and", "or", "for", "on", "at",
         "as", "by", "it", "this", "that", "with", "which", "would", "will", "can", "most",
         "these", "they", "their", "them", "what", "when", "where", "how", "why", "does", "do",
         "some", "if", "than", "then", "so", "more", "less", "not", "all", "one", "was", "has"}


def _toks(t):
    return [w for w in _TOK.findall(str(t).lower()) if w not in _STOP and len(w) > 2]


def _brain_conn(qset, oset, fa, cache):
    """ : term term (2 ).
 OpenBookQA book-fact + — ."""
    score = 0.0
    for ot in list(oset)[:4]:
        neigh = cache.get(ot)
        if neigh is None:
            neigh = set()
            try:
                for _s, _p, o in (fa(ot) or []):
                    neigh |= set(_toks(o))
            except Exception:
                pass
            cache[ot] = neigh
        score += len(neigh & qset) * 1.0
    return score


def main():
    use_brain = "--brain" in sys.argv
    fa = None
    if use_brain:
        sys.path.insert(0, str(REPO))
        from packages.graph_scale.triple_store import TripleStore
        st = TripleStore(str(REPO / "data" / "graph_scale" / "kg_triples"))
        fa = lambda t: st.facts_about(t, limit=20)
    facts = [json.loads(l) if l.startswith('"') else l.strip()
             for l in (OBQA / "facts.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    facts = [f.strip('"') for f in facts]
    rows = [json.loads(l) for l in (OBQA / "test.jsonl").read_text(encoding="utf-8").splitlines()]

    df = {}
    ftoks = [set(_toks(f)) for f in facts]
    for s in ftoks:
        for w in s:
            df[w] = df.get(w, 0) + 1
    N = len(facts)
    idf = {w: math.log(N / c) for w, c in df.items()}

    def w(t):
        return idf.get(t, math.log(N))

    correct = 0
    for r in rows:
        q = r["question"]["stem"]; choices = r["question"]["choices"]
        gold = r["answerKey"]
        qset = set(_toks(q))

        allo = set()
        for c in choices:
            allo |= set(_toks(c["text"]))
        fact_scores = []
        for i, fs in enumerate(ftoks):
            if not fs:
                continue
            sq = sum(w(t) for t in (qset & fs)); so = sum(w(t) for t in (allo & fs))
            if sq > 0 and so > 0:
                fact_scores.append((sq + so, i))
        fact_scores.sort(reverse=True)
        top_facts = [ftoks[i] for _s, i in fact_scores[:5]] or ftoks


        best_key, best_score = choices[0]["label"], -1.0
        bcache = {}
        for c in choices:
            oset = set(_toks(c["text"]))
            fsc = 0.0
            for fs in top_facts[:5]:
                so = sum(w(t) for t in (oset & fs))
                fsc = max(fsc, so)
            direct = sum(w(t) for t in (qset & oset))
            score = fsc + 0.25 * direct
            if fa is not None:
                score += 0.8 * _brain_conn(qset, oset, fa, bcache)
            if score > best_score:
                best_score, best_key = score, c["label"]
        correct += int(best_key == gold)

    acc = correct / len(rows)
    rep = {"benchmark": "OpenBookQA (No-LLM open-book, 1326-fact book)", "n": len(rows),
           "accuracy": round(acc, 4), "random": 0.25,
           "reading": "acc>0.25 = No-LLM 오픈북이 실 과학 MCQ서 작동. 작은 정밀 북이 MMLU 검색벽 우회."}
    print("RESULT eval_obqa", json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
