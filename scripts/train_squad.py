# -*- coding: utf-8 -*-
"""SQuAD 2.0 v2 — the NORTH STAR. Learned reader with linguistic (LAD) candidate structure.

v1 post-mortem (measured F1 11.1 vs hand-heuristic 35.9): naive embedding features lost to structural
priors. The fix is NOT to abandon learning — it is to give the learner the right signal:
  • sentence selection by IDF-weighted overlap (embeddings alone dilute),
  • TYPE-CONSTRAINED candidates (when→dates, how-many→numbers, who/where→proper nouns) — this is
    surface grammar (LAD), doctrine-legal; the DECISION among candidates stays 100% learned,
  • rich span features: span-adjacent context vs question, sentence coverage, type match, lengths,
  • two learned heads: SPAN RANKER (which span) + ANSWERABILITY (abstain gate) fed by ranker outputs,
  • batched predictions (v1 predicted one row at a time — 1.2M single-row calls).

Trained on SQuAD-train, evaluated on SQuAD-dev (official EM/F1, HasAns/NoAns split). No external LLM.

  python scripts/train_squad.py [n_train_q] [threshold]
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from packages.reasoning_vm import learned_discriminator as LD          # noqa: E402

SQ = REPO / "data" / "benchmarks" / "squad2"
_SENT = re.compile(r"(?<=[.!?])\s+")
_TOK = re.compile(r"[A-Za-z0-9]+")
_ART = {"a", "an", "the"}
_QSTOP = {"what", "which", "who", "whom", "whose", "when", "where", "why", "how", "is", "are", "was",
          "were", "did", "does", "do", "the", "a", "an", "of", "in", "on", "to", "for", "and", "or",
          "many", "much", "name", "that", "this", "with", "by", "as", "from", "it", "its", "be",
          "been", "has", "have", "had", "not", "但"}
_PROPER = re.compile(r"[A-Z][\w'-]*(?:\s+(?:of|the|and|de|von|la|le)\s+)?(?:\s?[A-Z][\w'-]*)*")
_DATE = re.compile(r"(?:\d{1,2}\s+)?(?:January|February|March|April|May|June|July|August|September|"
                   r"October|November|December)\s+\d{1,4}|\d{3,4}s?\b|\d{1,2}(?:st|nd|rd|th)\s+century")
_NUM = re.compile(r"\d[\d,\.]*(?:\s?(?:%|percent|million|billion|thousand|km|miles|feet|meters))?")


# ── official metric ──────────────────────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return " ".join(w for w in s.split() if w not in _ART)


def _f1(pred: str, gold: str) -> float:
    p, g = _norm(pred).split(), _norm(gold).split()
    if not p or not g:
        return float(p == g)
    common = sum((Counter(p) & Counter(g)).values())
    if not common:
        return 0.0
    pr, rc = common / len(p), common / len(g)
    return 2 * pr * rc / (pr + rc)


def _em(a: str, b: str) -> float:
    return float(_norm(a) == _norm(b))


def _best(pred, golds, m):
    return max((m(pred, g) for g in golds), default=m(pred, ""))


# ── LAD surface structure (candidates), decisions stay learned ──────────────────────────────────
def _qtype(q: str) -> str:
    ql = q.lower()
    if "when" in ql or "what year" in ql or "which year" in ql or "what date" in ql:
        return "when"
    if "how many" in ql or "how much" in ql or "what percentage" in ql:
        return "num"
    if ql.startswith(("who", "whom")) or " who " in ql:
        return "who"
    if "where" in ql:
        return "where"
    return "what"


def _qcontent(q: str) -> list[str]:
    return [w for w in _TOK.findall(q.lower()) if w not in _QSTOP and len(w) > 1]


class IDF:
    def __init__(self, contexts: list[str]):
        df = Counter()
        for c in contexts:
            df.update(set(_TOK.findall(c.lower())))
        self.n = len(contexts)
        self.df = df

    def w(self, t: str) -> float:
        return math.log(self.n / (1 + self.df.get(t, 0))) + 1.0


def _pick_sents(ctx: str, qc: list[str], idf: IDF, k: int = 3) -> list[str]:
    sents = [s for s in _SENT.split(ctx) if s.strip()] or [ctx]
    scored = []
    for s in sents:
        st = set(_TOK.findall(s.lower()))
        scored.append((sum(idf.w(t) for t in qc if t in st), s))
    scored.sort(key=lambda x: -x[0])
    return [s for _v, s in scored[:k]]


def _cands(sent: str, qt: str, qset: set[str]) -> list[str]:
    """Candidate spans from one sentence. Type priors (dates/numbers/proper nouns) give PRECISION; the
    noun-phrase n-grams give RECALL for every question type (measured: proper-noun-only floored where/
    num recall at ~47%). LAD surface structure only — the learned ranker decides among them."""
    out: dict[str, None] = {}                             # ordered: typed/proper priors first (priority)
    if qt == "when":
        for m in _DATE.finditer(sent):
            out.setdefault(m.group(0).strip())
        for m in re.finditer(r"\b\d{3,4}\b", sent):
            out.setdefault(m.group(0))
    if qt == "num":
        for m in _NUM.finditer(sent):
            out.setdefault(m.group(0).strip())
    for m in _PROPER.finditer(sent):                      # proper nouns: who/where/what/when alike
        t = m.group(0).strip()
        if 1 <= len(t.split()) <= 6:
            out.setdefault(t)
    toks = _TOK.findall(sent)                             # noun-ish n-grams for ALL types (recall)
    for n in (1, 2, 3, 4):
        for i in range(len(toks) - n + 1):
            w = toks[i:i + n]
            if w[0].lower() in _QSTOP or w[-1].lower() in _QSTOP:
                continue
            if all(x.lower() in qset for x in w):         # span made purely of question words — no
                continue
            out.setdefault(" ".join(w))
    return [c for c in out if 1 <= len(c) <= 50]


# ── features: span-in-context alignment (rich, learnable) ───────────────────────────────────────
def _span_feats(emb, qv, q: str, qc: list[str], qt: str, sent: str, span: str, idf: IDF,
                sent_cov: float) -> np.ndarray:
    sv, ov = emb.embed(sent), emb.embed(span)
    stoks = _TOK.findall(sent.lower())
    sptoks = [t.lower() for t in _TOK.findall(span)]
    # context words adjacent to the span inside the sentence vs question content (alignment signal)
    try:
        pos = sent.lower().find(span.lower())
    except Exception:
        pos = -1
    left = sent[:pos] if pos >= 0 else ""
    right = sent[pos + len(span):] if pos >= 0 else ""
    lw = set(_TOK.findall(left.lower()))
    rw = set(_TOK.findall(right.lower()))
    ctx_hit = sum(idf.w(t) for t in qc if t in lw or t in rw)
    span_q_overlap = sum(1 for t in sptoks if t in qc) / max(1, len(sptoks))
    tmatch = 1.0 if ((qt == "when" and _DATE.search(span)) or (qt == "num" and _NUM.search(span))
                     or (qt in ("who", "where") and span[:1].isupper())) else 0.0
    return np.concatenate([
        ov * sv, ov * qv,
        [float(ov @ sv), float(ov @ qv), float(sv @ qv),
         ctx_hit, span_q_overlap, sent_cov, tmatch,
         float(len(sptoks)), float(pos >= 0), float(len(stoks))],
    ]).astype(np.float32)


_SP = 10   # scalar tail length of _span_feats (the interpretable alignment signals)


def _featurize_question(emb, idf, ctx: str, q: str):
    """→ (spans, X, passage) — type-constrained candidates + a passage-level answerability vector.

    `passage` carries signals a threshold on ranker-probability CANNOT: the absolute best sentence↔
    question alignment and whole-passage content coverage. For an unanswerable question these stay low
    even though the ranker still ranks *some* type-matching span first — that gap is the abstain signal."""
    qv = emb.embed(q)
    qc = _qcontent(q)
    qt = _qtype(q)
    qset = set(qc)
    qw = max(1e-9, sum(idf.w(t) for t in qc))
    rows, spans, seen = [], [], set()
    max_sent_sim = 0.0
    for sent in _pick_sents(ctx, qc, idf, k=3):
        sv = emb.embed(sent)
        max_sent_sim = max(max_sent_sim, float(sv @ qv))
        st = set(_TOK.findall(sent.lower()))
        cov = sum(idf.w(t) for t in qc if t in st) / qw
        for c in _cands(sent, qt, qset):
            key = c.lower()
            if key in seen:
                continue                                  # de-dup across the picked sentences
            seen.add(key)
            rows.append(_span_feats(emb, qv, q, qc, qt, sent, c, idf, cov))
            spans.append(c)
            if len(spans) >= 90:                          # bound cost; priors are enumerated first
                break
        if len(spans) >= 90:
            break
    whole = set(_TOK.findall(ctx.lower()))
    whole_cov = sum(idf.w(t) for t in qc if t in whole) / qw
    passage = np.array([max_sent_sim, whole_cov, float(len(qc)), float(len(spans))], np.float32)
    if not rows:
        return [], np.zeros((0, 1), np.float32), passage
    return spans, np.vstack(rows), passage


def _ans_feats(X: np.ndarray, p: np.ndarray, passage: np.ndarray) -> np.ndarray:
    """Answerability features = the BEST span's alignment scalars (absolute quality, not the ranker's
    squashed prob) ⊕ passage-level coverage ⊕ a 3-number summary of the ranker distribution."""
    if len(p) == 0:
        return np.concatenate([np.zeros(_SP, np.float32), passage, np.zeros(3, np.float32)]).astype(np.float32)
    i = int(np.argmax(p))
    order = np.sort(p)[::-1]
    top1 = float(order[0])
    top3 = float(order[:3].mean() if len(order) >= 3 else order.mean())
    margin = float(order[0] - (order[1] if len(order) > 1 else 0.0))
    return np.concatenate([X[i, -_SP:], passage, [top1, top3, margin]]).astype(np.float32)


def main() -> int:
    t0 = time.time()
    nq = int(sys.argv[1]) if len(sys.argv) > 1 else 30000
    thr = float(sys.argv[2]) if len(sys.argv) > 2 else 0.30
    train = json.loads((SQ / "train-v2.0.json").read_text(encoding="utf-8"))["data"]
    dev = json.loads((SQ / "dev-v2.0.json").read_text(encoding="utf-8"))["data"]

    def _flat(data):
        rows = []
        for art in data:
            for para in art["paragraphs"]:
                for qa in para["qas"]:
                    rows.append((para["context"], qa["question"],
                                 [a["text"] for a in qa["answers"]], bool(qa.get("is_impossible"))))
        return rows

    tr, dv = _flat(train), _flat(dev)
    ctxs = list({c for c, _q, _g, _i in tr})
    idf = IDF(ctxs)
    print(f"loaded {len(tr)} train / {len(dv)} dev; contexts {len(ctxs)}", flush=True)
    emb = LD.train_embeddings(ctxs, dim=LD._DIM)
    print(f"  embeddings vocab {len(emb.idx)}  ({round(time.time()-t0,1)}s)", flush=True)

    import random
    rng = random.Random(0)
    rng.shuffle(tr)
    tr = tr[:nq]

    # ── train SPAN RANKER (answerable questions; gold vs in-context negatives) ──
    Xs, ys = [], []
    for ctx, q, golds, imp in tr:
        if imp or not golds:
            continue
        spans, X, _passage = _featurize_question(emb, idf, ctx, q)
        if not spans:
            continue
        gold_norm = {_norm(g) for g in golds}
        labs = np.array([1 if _norm(s) in gold_norm else 0 for s in spans])
        if labs.sum() == 0:
            continue                                       # gold not among candidates — skip (recall gap)
        neg_idx = np.where(labs == 0)[0]
        # IN-QUESTION negatives: the gold's actual competitors (near-duplicate n-grams) are the hard
        # negatives that teach fine boundary discrimination — far more informative than random spans.
        keep = np.concatenate([np.where(labs == 1)[0],
                               neg_idx[rng.sample(range(len(neg_idx)), min(30, len(neg_idx)))]
                               if len(neg_idx) else neg_idx])
        Xs.append(X[keep])
        ys.append(labs[keep])
    Xs, ys = np.vstack(Xs), np.concatenate(ys)
    ranker = LD.make_clf("gbm:0.1")
    ranker.fit(Xs, ys)
    print(f"  span ranker: {len(ys)} spans ({round(time.time()-t0,1)}s)", flush=True)

    # ── train ANSWERABILITY on rich best-span-quality + passage features (BOTH answerable & impossible) ──
    Xa, ya = [], []
    for ctx, q, golds, imp in tr:
        spans, X, passage = _featurize_question(emb, idf, ctx, q)
        p = ranker.predict_proba(X)[:, 1] if spans else np.array([])
        Xa.append(_ans_feats(X, p, passage))
        ya.append(0 if imp else 1)
    ansclf = LD.make_clf("gbm:0.1")
    ansclf.fit(np.array(Xa, np.float32), np.array(ya))
    print(f"  answerability: {len(ya)} questions ({round(time.time()-t0,1)}s)", flush=True)

    # dump feature matrices for the ceiling prober (oracle-gap analysis, RIF M0) — offline consumers
    dump = REPO / "data" / "graph_scale" / "rif_probe"
    dump.mkdir(parents=True, exist_ok=True)
    np.save(dump / "gate_X.npy", np.array(Xa, np.float32))
    np.save(dump / "gate_y.npy", np.array(ya, np.int8))
    np.save(dump / "ranker_X.npy", Xs[:200_000].astype(np.float32))
    np.save(dump / "ranker_y.npy", ys[:200_000].astype(np.int8))

    # ── choose the operating threshold on a TRAIN-held-out slice (never dev): maximize overall score.
    #    The abstain/answer trade-off is a dial; v2 measured that a fixed 0.30 collapses abstention.
    def _predict(ctx, q):
        spans, X, passage = _featurize_question(emb, idf, ctx, q)
        if not spans:
            a = ansclf.predict_proba(_ans_feats(X, np.array([]), passage)[None, :])[0, 1]
            return None, float(a)
        p = ranker.predict_proba(X)[:, 1]
        a = ansclf.predict_proba(_ans_feats(X, p, passage)[None, :])[0, 1]
        return spans[int(np.argmax(p))], float(a)

    # held-out TRAIN questions (beyond nq under the same shuffle), REBALANCED to SQuAD 2.0's ~50/50
    # answerable ratio — the task design is public, so calibrating the operating point to it is honest
    # (dev is never touched). A ratio-matched slice is what keeps the sweep out of the abstain-all corner.
    pool = _flat(train)
    random.Random(0).shuffle(pool)
    pool = pool[nq:]
    pos = [r for r in pool if not r[3]]
    neg = [r for r in pool if r[3]]
    m = min(len(pos), len(neg), 2500)
    val = pos[:m] + neg[:m]
    random.Random(3).shuffle(val)
    cache = []
    for ctx, q, golds, imp in val:
        best_span, a = _predict(ctx, q)
        cache.append((best_span, a, golds, imp))
    best_thr, best_score = thr, -1.0
    for t_ in [i / 40 for i in range(1, 40)]:
        sc = sum((int(bs is None or bs == "" or a < t_) if imp
                  else (_best(bs, golds, _f1) if (bs and a >= t_) else 0.0))
                 for bs, a, golds, imp in cache) / max(1, len(cache))
        if sc > best_score:
            best_score, best_thr = sc, t_
    thr = best_thr
    # report the val operating split so a degenerate abstain-all corner is visible, not hidden
    vh = [(bs, a, g) for bs, a, g, im in cache if not im]
    vn = [a for bs, a, g, im in cache if im]
    v_ans = sum(1 for bs, a, g in vh if bs and a >= thr) / max(1, len(vh))
    v_abst = sum(1 for a in vn if a < thr) / max(1, len(vn))
    print(f"  threshold swept on balanced train-held-out ({len(val)}): thr={thr} "
          f"(val_F1 {round(100*best_score,1)}; HasAns answered {round(100*v_ans,1)}%, "
          f"NoAns abstained {round(100*v_abst,1)}%)", flush=True)

    # ── eval on dev ──
    em = f1 = 0.0
    has = has_em = has_f1 = no = no_ok = 0
    ranker_f1 = 0.0            # HasAns_F1 if we ALWAYS answer (pure ranker/extraction quality)
    perfect_overall = 0.0      # overall F1 with a PERFECT gate (answer answerable, abstain impossible)
    for ctx, q, golds, imp in dv:
        best_span, a = _predict(ctx, q)
        pred = best_span if (best_span and a >= thr) else ""
        if imp:
            no += 1
            ok = int(pred == "")
            no_ok += ok
            em += ok
            f1 += ok
            perfect_overall += 1.0                          # perfect gate abstains → F1 1.0
        else:
            has += 1
            e, f = _best(pred, golds, _em), _best(pred, golds, _f1)
            has_em += e
            has_f1 += f
            em += e
            f1 += f
            rf = _best(best_span or "", golds, _f1)          # answer-all: ranker's own F1
            ranker_f1 += rf
            perfect_overall += rf                            # perfect gate answers → ranker F1
    n = len(dv)
    rep = {"dev_n": n, "EM": round(100 * em / n, 1), "F1": round(100 * f1 / n, 1),
           "HasAns_EM": round(100 * has_em / max(1, has), 1),
           "HasAns_F1": round(100 * has_f1 / max(1, has), 1),
           "NoAns_abstain": round(100 * no_ok / max(1, no), 1),
           "ranker_HasAns_F1_answerall": round(100 * ranker_f1 / max(1, has), 1),
           "perfect_gate_overall_F1": round(100 * perfect_overall / n, 1),
           "abstain_all_baseline_F1": round(100 * no / n, 1),
           "threshold": thr, "train_q": len(tr), "vocab": len(emb.idx),
           "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT", json.dumps(rep))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"squad2_learned_{time.strftime('%Y%m%d_%H%M')}.json"
     ).write_text(json.dumps(rep, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
