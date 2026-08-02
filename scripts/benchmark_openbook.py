# -*- coding: utf-8 -*-
"""CLOSED-BOOK public benchmark harness (KMMLU) — the world pack's report card.

Naming corrected (owner, 2026-07-15): the world pack is LEARNED, internalized knowledge — the
graph IS the model, so consulting it at test time is exactly what an LLM does with its weights:
**closed-book**. "Open-book" would mean external retrieval (web/search) at test time, which this
harness never does. (The file keeps its legacy name because benchmark_gpqa imports it.)

Strategy: ATANOR's claim is GROUNDED answering from its own learned graph: spreading activation
lights the subgraph around the question's anchors, and each choice is scored by how much stored
evidence supports it. No web, no LLM, deterministic.

Honest scoring (BINDING: MMLU-style accuracy cannot measure hallucination — a guess and a
grounded answer look identical when right):
  - coverage       : fraction of questions where the graph held ANY usable evidence
  - answered_acc   : accuracy on those answered (the quality of grounded answers)
  - strict_acc     : accuracy over ALL questions with abstentions counted WRONG (the number a
                     leaderboard would print)
  - guess_baseline : 0.25 (4 choices) — answered_acc must clear this to mean anything

Questions are cached to data/benchmarks/kmmlu/ on first run, so the post-worldpack rerun scores
the IDENTICAL items — the delta is the world pack's measured contribution.

  python scripts/benchmark_openbook.py [n_per_subject]
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")   # safer than reassigning stdout (survives backgrounding)
except Exception:
    pass
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
for _d in sorted((REPO / "packages").iterdir(), reverse=True):
    if (_d / "pyproject.toml").exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from packages.reasoning_vm.discrimination import discriminate   # noqa: E402  C3 verify-gated MCQ

CACHE = REPO / "data" / "benchmarks" / "kmmlu"
REPORTS = REPO / "reports" / "benchmarks"
# knowledge-leaning subjects (world-pack-sensitive); reasoning-heavy ones (math/law-application)
# are the arithmetic/deduction VM's exam, not the world pack's — kept out of THIS report card.
SUBJECTS = ["Biology", "Chemistry", "Ecology", "Health", "Economics",
            "Political-Science-and-Sociology", "Psychology", "Food-Processing"]
_HDR = {"User-Agent": "ATANOR-bench (research; blueyjkim@gmail.com)"}
_TOKEN = re.compile(r"[가-힣]{2,}|[A-Za-z]{3,}")
_JOSA_TAIL = re.compile(r"(으로서|으로써|에서의|이라는|라는|에서|에게|으로|로서|처럼|보다|이란|란|은|는|이|가|을|를|의|에|와|과|도|만)$")


def _fetch_subject(subject: str) -> list[dict]:
    """Load a subject's test rows — from cache first (identical items across reruns)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    fp = CACHE / f"{subject}-test.csv"
    if not fp.exists():
        url = f"https://huggingface.co/datasets/HAERAE-HUB/KMMLU/resolve/main/data/{subject}-test.csv"
        fp.write_bytes(urllib.request.urlopen(
            urllib.request.Request(url, headers=_HDR), timeout=30).read())
    rows = list(csv.DictReader(fp.open(encoding="utf-8")))
    return rows


MMLU_PRO_CACHE = REPO / "data" / "benchmarks" / "mmlu_pro"
MMLU_PRO_CATS = ["biology", "chemistry", "physics", "history", "economics",
                 "psychology", "health", "law"]


def _fetch_mmlu_pro(n_per_cat: int) -> list[dict]:
    """MMLU-Pro test slice, stratified by category, cached as jsonl (identical across reruns).
    Row shape: {question, choices: {A..J}, gold, category}."""
    MMLU_PRO_CACHE.mkdir(parents=True, exist_ok=True)
    fp = MMLU_PRO_CACHE / f"slice_{n_per_cat}.jsonl"
    if not fp.exists():
        import pandas as pd
        url = ("https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro/resolve/main/"
               "data/test-00000-of-00001.parquet")
        raw = MMLU_PRO_CACHE / "test.parquet"
        if not raw.exists():
            raw.write_bytes(urllib.request.urlopen(
                urllib.request.Request(url, headers=_HDR), timeout=120).read())
        df = pd.read_parquet(raw)
        out = []
        letters = "ABCDEFGHIJ"
        for cat in MMLU_PRO_CATS:
            sub = df[df["category"].str.lower() == cat].head(n_per_cat)
            for _i, r in sub.iterrows():
                opts = list(r["options"])
                out.append({"question": str(r["question"]),
                            "choices": {letters[j]: str(o) for j, o in enumerate(opts)},
                            "gold": str(r["answer"]).strip().upper(),
                            "category": cat})
        fp.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out),
                      encoding="utf-8")
    return [json.loads(ln) for ln in fp.read_text(encoding="utf-8").splitlines()]


MMLU_CACHE = REPO / "data" / "benchmarks" / "mmlu"
# knowledge-leaning MMLU subjects, chosen to mirror the KMMLU slice (biology/chem/physics/health/
# econ/psych/sociology/geography) — 4 options, guess baseline 0.25 (apples-to-apples with KMMLU).
MMLU_SUBJECTS = ["high_school_biology", "college_chemistry", "conceptual_physics", "nutrition",
                 "high_school_psychology", "sociology", "high_school_macroeconomics",
                 "high_school_geography"]


def _fetch_mmlu(n_per: int) -> list[dict]:
    """Standard MMLU (English) test slice, stratified by subject, cached as jsonl (identical across
    reruns). Row shape mirrors mmlu-pro: {question, choices{A..D}, gold, category}."""
    MMLU_CACHE.mkdir(parents=True, exist_ok=True)
    fp = MMLU_CACHE / f"slice_{n_per}.jsonl"
    if not fp.exists():
        import pandas as pd
        url = ("https://huggingface.co/datasets/cais/mmlu/resolve/main/all/"
               "test-00000-of-00001.parquet")
        raw = MMLU_CACHE / "test.parquet"
        if not raw.exists():
            raw.write_bytes(urllib.request.urlopen(
                urllib.request.Request(url, headers=_HDR), timeout=120).read())
        df = pd.read_parquet(raw)
        out, letters = [], "ABCD"
        for subj in MMLU_SUBJECTS:
            sub = df[df["subject"] == subj].head(n_per)
            for _i, r in sub.iterrows():
                ch = list(r["choices"])
                if len(ch) != 4:
                    continue
                out.append({"question": str(r["question"]),
                            "choices": {letters[j]: str(o) for j, o in enumerate(ch)},
                            "gold": letters[int(r["answer"])], "category": subj})
        fp.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out), encoding="utf-8")
    return [json.loads(ln) for ln in fp.read_text(encoding="utf-8").splitlines()]


def _strip_josa(tok: str) -> str:
    m = _JOSA_TAIL.search(tok)
    return tok[: m.start()] if m and m.start() >= 2 else tok


def _tokens(text: str) -> set[str]:
    return {_strip_josa(t) for t in _TOKEN.findall(str(text or ""))} - {""}


_QID_RE = re.compile(r"^Q\d+$")


def _resolve_qid(term: str, fa, cache: dict[str, str]) -> str:
    """World-pack schema stores objects as Q-ids ((, capital, Q90)); the readable label lives
 in a separate (Q90, qlabel, ) row. Resolve it — the SAME adapter dual_brain uses — so the
 evidence field carries '', not the untokenizable 'Q90'. kg_triples (no Q-ids) → no-op."""
    t = str(term)
    if not _QID_RE.match(t):
        return t
    if t in cache:
        return cache[t]
    lbl = t
    try:
        for _s, p, o in fa(t):
            if p == "qlabel":
                lbl = str(o)
                break
    except Exception:
        pass
    cache[t] = lbl
    return lbl


# exam-frame/function words: a 141M-triple store "knows" them all, so they hijack the anchor


_ANCHOR_STOP = {"대한", "관한", "설명", "다음", "경우", "옳은", "옳지", "않은", "것은", "것을",
                "것이", "질문", "무엇", "위한", "위해", "해당", "아닌", "모두", "가장", "제대로",
                "내용", "그중", "보기", "고르", "고른", "선택"}


def _evidence_field(question: str, fa) -> tuple[set[str], list[str]]:
    """Light the graph around the question: spread from the longest content tokens that the
    store actually knows; the evidence = every activated concept label + its property prose.
    Q-id objects are resolved to their labels (world-pack schema) before tokenizing."""
    from packages.graph_scale.spreading_activation import spread
    q_toks = sorted(_tokens(question), key=len, reverse=True)
    anchors: list[str] = []
    for t in q_toks[:14]:
        if t in _ANCHOR_STOP:
            continue
        try:
            if fa(t):
                anchors.append(t)
        except Exception:
            continue
        if len(anchors) >= 4:
            break
    ev: set[str] = set()
    qc: dict[str, str] = {}                        # Q-id → label resolution cache (one per question)
    for a in anchors:
        try:
            sg = spread(a, fa, max_nodes=60)
        except Exception:
            continue
        for k in sg.activation.keys():
            ev |= _tokens(_resolve_qid(k, fa, qc))
        for s, p, o, _d in sg.edges:
            ev |= _tokens(_resolve_qid(o, fa, qc))
        for node_props in sg.properties.values():
            for _s, _p, o in node_props:
                ev |= _tokens(_resolve_qid(o, fa, qc))
    return ev, anchors


def _resolving_fa(fa):
    """A facts_about that resolves Q-id objects to labels — what discriminate() needs so a choice
 '' matches the stored target (, capital, Q64)→, not the untokenizable 'Q64'."""
    qc: dict[str, str] = {}
    return lambda subject: [(s, p, _resolve_qid(o, fa, qc)) for (s, p, o) in (fa(subject) or [])]


_PASSAGES: dict | None = None       # open-book corpus (title->lead_text), loaded in main() if present
_CONTENT_INDEX = None               # IDF content index over passages (recall past title-match)


def _answer(q: str, choices: dict[str, str], gold_letter: str, fa) -> dict:

    # (1) verify-gated factual, (2) conceptual entailment / transitive is_a, (3) graph-evidence rank,
    # (4) stable guess — always returns a pick, marking confidence (grounded|inference|guess) so a
    # guess is never asserted as a settled fact. The anti-correlated token-overlap scorer is retired.
    from packages.reasoning_vm.exam_answer import answer_exam
    r = answer_exam(q, choices, _resolving_fa(fa), passages=_PASSAGES, content_index=_CONTENT_INDEX)
    pick = r.get("choice_key")
    return {"gold": gold_letter, "pick": pick, "answered": pick is not None,
            "correct": bool(pick == gold_letter), "path": r.get("mode", "guess"),
            "q_tokens": sorted(_tokens(q), key=len, reverse=True)[:8],
            "top_score": round(float(r.get("confidence", 0.0)), 3)}


def answer_one(row: dict, fa) -> dict:
    q = str(row.get("question") or "")
    choices = {k: str(row.get(k) or "") for k in ("A", "B", "C", "D")}
    gold = str(row.get("answer") or "").strip()
    gold_letter = {"1": "A", "2": "B", "3": "C", "4": "D"}.get(gold, gold.upper()[:1])
    return _answer(q, choices, gold_letter, fa)


def _load_store(*, read_only: bool = False) -> tuple[object, dict]:
    """Load the knowledge base the benchmark reads. Prefer the world pack (the real learned graph:
    world_pack_sharded via MultiShardStore, else world_pack_full) when present — WORLD_PACK_STORE
    overrides the name; fall back to answer_bridge's kg_triples. Returns (store, meta_for_report)."""
    base = REPO / "data" / "graph_scale"
    name = os.environ.get("WORLD_PACK_STORE", "")
    candidates = [name] if name else ["world_pack_sharded", "world_pack_full"]
    for cand in candidates:
        d = base / cand
        if not d.exists():
            continue
        if list(d.glob("shard_*")):                       # sharded → MultiShardStore
            if not (d / "_COMPLETE.json").exists():        # crashed/partial build → skip, try next
                continue
            from packages.graph_scale.multi_shard_store import MultiShardStore
            st = MultiShardStore(d, read_only=read_only)
            return st, {"store": cand, "kind": "multi_shard", "shards": len(st.shards),
                        "triples": st.count()}
        from packages.graph_scale.triple_store import TripleStore
        st = TripleStore(
            d,
            dict_backend="sharded",
            write_src=False,
            read_only=read_only,
        )
        return st, {"store": cand, "kind": "triple_store"}
    from packages.graph_scale import answer_bridge as AB   # legacy fallback: curated kg_triples
    return AB._store(), {"store": "kg_triples", "kind": "triple_store"}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n_per = int(args[0]) if args else 25
    bench = ("mmlu-pro" if "--bench=mmlu-pro" in sys.argv or "mmlu-pro" in sys.argv
             else "mmlu" if "--bench=mmlu" in sys.argv or "mmlu" in sys.argv else "kmmlu")
    kg, store_info = _load_store()
    # UNION the harvested Wikipedia knowledge (wiki_kg) if present — the knowledge lever. facts_about
    # then sees both the world pack AND the harvested propositions, so answer_exam can verify more.
    _wiki = None
    _wdir = REPO / "data" / "graph_scale" / "wiki_kg"
    if (_wdir / "_COMPLETE.json").exists() or (_wdir / "s.col").exists():
        try:
            from packages.graph_scale.triple_store import TripleStore
            _wiki = TripleStore(_wdir, dict_backend="sharded", write_src=False)
            store_info = {**store_info, "wiki_kg": True}
        except Exception:
            _wiki = None

    # OPEN-BOOK corpus (title->lead_text). Closed-book graph lookup is at chance on propositional MCQ;
    # retrieving the entity's real passage and scoring options against it is the honest lever.
    global _PASSAGES, _CONTENT_INDEX
    _pfile = Path(os.environ.get("PASSAGES_TSV")) if os.environ.get("PASSAGES_TSV") \
        else REPO / "data" / "graph_scale" / "wiki_passages" / "passages.tsv"
    if _pfile.exists():
        try:
            from packages.reasoning_vm.openbook import load_passages, ContentIndex
            _PASSAGES = load_passages(str(_pfile))
            # ContentIndex (retrieval fallback) measured net-flat → default OFF (baseline). The L1 PMI /
            # option-conditioned levers (2026-07-16) need it; enable together via OPENBOOK_CONTENT_INDEX=1
            # + ATANOR_PMI / ATANOR_OC. Kept OFF by default so the shipped path == measured baseline.
            if os.environ.get("OPENBOOK_CONTENT_INDEX") == "1" and _PASSAGES:
                _CONTENT_INDEX = ContentIndex(_PASSAGES)
            # E6b (2026-07-18): ATANOR Index disk BM25 as the retrieval backend. The in-RAM
            # ContentIndex cannot span the 7.0M English corpus, so the English lane had title-match
            # only (E6a: fire-rate 0.295 vs the Korean lane's 0.490) — this is the coverage lever.
            # Separate flag from OPENBOOK_CONTENT_INDEX so the two backends are never conflated in a
            # measurement; disk wins if both are set, since it is the one that scales.
            if os.environ.get("OPENBOOK_DISK_INDEX") == "1":
                from packages.reasoning_vm.openbook import load_disk_index
                _di = load_disk_index()
                if _di is not None:
                    _CONTENT_INDEX = _di
                    store_info = {**store_info, "disk_index": _di.dir}
            store_info = {**store_info, "openbook_passages": len(_PASSAGES),
                          "content_index": type(_CONTENT_INDEX).__name__ if _CONTENT_INDEX else False}
        except Exception:
            _PASSAGES = None

    def fa(t):
        rows = list(kg.facts_about(t, limit=24) or [])
        if _wiki is not None:
            try:
                rows += list(_wiki.facts_about(t, limit=24) or [])
            except Exception:
                pass
        return rows
    print(f"  store: {store_info}")

    per_subject: dict[str, dict] = {}
    # per-item records for the miss-curriculum miner: TOPIC TOKENS ONLY — never the question
    # text, choices, or gold (no-training-on-test guard; see docs/BENCHMARK_NORTH_STAR.md).
    items: list[dict] = []
    total = answered = correct_answered = correct_total = 0
    by_path: dict[str, dict[str, int]] = {}   # path → {answered, correct} (discrimination attribution)
    t0 = time.time()

    if bench in ("mmlu-pro", "mmlu"):
        groups: dict[str, list[dict]] = {}
        for row in (_fetch_mmlu_pro(n_per) if bench == "mmlu-pro" else _fetch_mmlu(n_per)):
            groups.setdefault(row["category"], []).append(row)
        work = [(cat, rows) for cat, rows in groups.items()]
    else:
        work = []
        for subj in SUBJECTS:
            try:
                work.append((subj, _fetch_subject(subj)[:n_per]))
            except Exception as exc:
                per_subject[subj] = {"error": str(exc)[:90]}

    for subj, rows in work:
        s_tot = s_ans = s_cor = 0
        for row in rows:
            if bench in ("mmlu-pro", "mmlu"):
                r = _answer(row["question"], row["choices"], row["gold"], fa)
            else:
                r = answer_one(row, fa)
            items.append({"subject": subj, "q_tokens": r["q_tokens"],
                          "answered": r["answered"], "correct": r["correct"],
                          "path": r.get("path", "overlap")})
            s_tot += 1
            total += 1
            if r["answered"]:
                s_ans += 1
                answered += 1
                p = by_path.setdefault(r.get("path", "overlap"), {"answered": 0, "correct": 0})
                p["answered"] += 1
                if r["correct"]:
                    s_cor += 1
                    correct_answered += 1
                    correct_total += 1
                    p["correct"] += 1
        per_subject[subj] = {"n": s_tot, "answered": s_ans, "correct": s_cor,
                             "coverage": round(s_ans / max(1, s_tot), 3),
                             "answered_acc": round(s_cor / max(1, s_ans), 3) if s_ans else None}
        print(f"  {subj:38} n={s_tot:3}  coverage={per_subject[subj]['coverage']:.2f}  "
              f"answered_acc={per_subject[subj]['answered_acc']}")

    by_path_acc = {k: {**v, "acc": round(v["correct"] / max(1, v["answered"]), 4)}
                   for k, v in by_path.items()}
    report = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "store_meta": store_info,
        "benchmark": f"{bench}(closed-book)",
        "subjects": (MMLU_PRO_CATS if bench == "mmlu-pro" else MMLU_SUBJECTS if bench == "mmlu"
                     else SUBJECTS), "n_per_subject": n_per,
        "items": items,
        "total": total, "answered": answered, "coverage": round(answered / max(1, total), 4),
        "answered_acc": round(correct_answered / max(1, answered), 4) if answered else None,
        "strict_acc": round(correct_total / max(1, total), 4),
        "by_path": by_path_acc,   # discrimination vs overlap contribution (verify-gated vs heuristic)
        "guess_baseline": 0.25, "per_subject": per_subject,
        "elapsed_s": round(time.time() - t0, 1),
        "honest_note": "strict_acc counts abstentions as wrong; MMLU-style accuracy cannot "
                       "measure hallucination — coverage+answered_acc are the grounded metrics.",
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{bench.replace('-', '_')}_closedbook_{time.strftime('%Y%m%d_%H%M')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nTOTAL n={total}  coverage={report['coverage']:.3f}  "
          f"answered_acc={report['answered_acc']}  strict_acc={report['strict_acc']:.3f}  "
          f"(guess=0.25)")
    for pth, v in by_path_acc.items():
        print(f"  path[{pth:12}] answered={v['answered']:3}  correct={v['correct']:3}  acc={v['acc']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
