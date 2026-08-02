# -*- coding: utf-8 -*-
"""SQuAD 2.0 — reading comprehension WITH unanswerable questions. ATANOR's honest home benchmark.

Why this is our battlefield (owner 2026-07-15): SQuAD 2.0 mixes ~50% questions whose answer is NOT in
the passage. An LLM hallucinates a plausible span and loses points; our INTEGRITY GATE answers only when
the passage genuinely supports a span, else abstains (predicts no-answer). We score the OFFICIAL metric
(EM/F1 with no-answer handling) and — the honest receipt — split it into:
  • HasAns  : span-extraction quality on answerable questions
  • NoAns   : did we correctly ABSTAIN on the unanswerable ones (our anti-hallucination strength)

No-LLM, deterministic: wh-type detection → best-matching sentence → type-constrained span, with an
answerability gate. No trained reader; heuristic span extraction — HasAns EM will be modest and that is
reported honestly, while NoAns is where the architecture genuinely shines.

  python scripts/benchmark_squad.py [n_questions]
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEV = REPO / "data" / "benchmarks" / "squad2" / "dev-v2.0.json"

_SENT = re.compile(r"(?<=[.!?])\s+")
_TOK = re.compile(r"[A-Za-z0-9]+")
_ARTICLES = {"a", "an", "the"}
_STOP = {"is", "are", "was", "were", "of", "in", "on", "at", "to", "for", "and", "or", "which",
         "what", "who", "whom", "whose", "when", "where", "why", "how", "did", "does", "do", "that",
         "this", "with", "by", "as", "from", "be", "been", "has", "have", "had", "it", "its", "their",
         "many", "much", "name", "following", "there", "these", "those", "than", "then", "also"}
_YEAR = re.compile(r"\b\d{3,4}s?\b|\b\d{1,2}(?:st|nd|rd|th)\s+century\b", re.I)
_NUM = re.compile(r"\b\d[\d,\.]*\b")
_PROPER = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b")


# ── official SQuAD normalization / metrics ───────────────────────────────────────────────────────
def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(w for w in s.split() if w not in _ARTICLES)


def _f1(pred: str, gold: str) -> float:
    p, g = _norm(pred).split(), _norm(gold).split()
    if not p or not g:
        return float(p == g)                       # both empty → 1, one empty → 0
    common = Counter(p) & Counter(g)
    n = sum(common.values())
    if n == 0:
        return 0.0
    prec, rec = n / len(p), n / len(g)
    return 2 * prec * rec / (prec + rec)


def _em(pred: str, gold: str) -> float:
    return float(_norm(pred) == _norm(gold))


def _best(metric, pred: str, golds: list[str]) -> float:
    return max((metric(pred, g) for g in golds), default=metric(pred, ""))


# ── the answerer (No-LLM extractive reader + abstain gate) ───────────────────────────────────────
def _qtype(q: str) -> str:
    ql = q.lower()
    if "when" in ql or "what year" in ql or "which year" in ql:
        return "when"
    if "how many" in ql or "how much" in ql:
        return "num"
    if ql.startswith("who") or "whom" in ql:
        return "who"
    if "where" in ql:
        return "where"
    return "what"


def answer(context: str, question: str) -> str:
    """Return an answer span, or '' to abstain (predict unanswerable)."""
    qkeys = [w for w in (_TOK.findall(question.lower())) if w not in _STOP and len(w) > 1]
    if not qkeys:
        return ""
    qset = set(qkeys)
    sents = _SENT.split(context)
    best_s, best_ov = "", 0.0
    for s in sents:
        stoks = set(_TOK.findall(s.lower()))
        ov = len(qset & stoks) / len(qset)
        if ov > best_ov:
            best_ov, best_s = ov, s
    # ANSWERABILITY GATE (integrity): the passage must genuinely cover the question AND actually contain
    # an answer-TYPE-appropriate span. SQuAD's unanswerable questions ARE topically covered but the
    # specific fact is absent — so overlap alone is not enough; the type-span must be PRESENT, else we
    # abstain rather than hallucinate. This is the honest anti-hallucination profile.
    if best_ov < 0.6 or not best_s:
        return ""
    qt = _qtype(question)
    if qt == "when":                                       # a date must exist in the sentence, else no-answer
        m = _YEAR.search(best_s)
        return m.group(0) if m else ""
    if qt == "num":
        m = _NUM.search(best_s)
        return m.group(0) if m else ""
    # who / where / what → a proper-noun phrase NOT in the question. No such entity → abstain (no word-dump).
    cands = [p for p in _PROPER.findall(best_s) if p.lower() not in question.lower()
             and not any(w in qset for w in p.lower().split())]
    if cands and best_ov >= 0.6:
        return max(cands, key=len)
    return ""


def main() -> int:
    if not DEV.exists():
        print("dev-v2.0.json not found — download it to data/benchmarks/squad2/")
        return 1
    n_max = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    data = json.loads(DEV.read_text(encoding="utf-8"))["data"]
    rows = []
    for art in data:
        for para in art["paragraphs"]:
            ctx = para["context"]
            for qa in para["qas"]:
                golds = [a["text"] for a in qa["answers"]] or [""]
                rows.append((ctx, qa["question"], golds, bool(qa.get("is_impossible"))))
    rows = rows[:n_max]

    t0 = time.time()
    em = f1 = 0.0
    has = has_em = has_f1 = 0
    no = no_correct = 0
    for ctx, q, golds, impossible in rows:
        pred = answer(ctx, q)
        if impossible:
            no += 1
            no_correct += int(pred == "")          # correct abstain
            em += int(pred == "")
            f1 += int(pred == "")
        else:
            has += 1
            e, f = _best(_em, pred, golds), _best(_f1, pred, golds)
            has_em += e
            has_f1 += f
            em += e
            f1 += f
    n = len(rows)
    rep = {
        "n": n, "elapsed_s": round(time.time() - t0, 1),
        "overall_EM": round(100 * em / n, 1), "overall_F1": round(100 * f1 / n, 1),
        "HasAns_n": has, "HasAns_EM": round(100 * has_em / max(1, has), 1),
        "HasAns_F1": round(100 * has_f1 / max(1, has), 1),
        "NoAns_n": no, "NoAns_abstain_acc": round(100 * no_correct / max(1, no), 1),
    }
    print(json.dumps(rep, indent=2))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"squad2_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
