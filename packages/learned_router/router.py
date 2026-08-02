# -*- coding: utf-8 -*-
"""Learned intent router v0 — LEARNED understanding replacing hand-written regexes.

The macro diagnosis (2026-07-07): 7 of 8 measured chat failures were ROUTING
failures — the knowledge was in the graph, the regex lanes misread the question.
Rules generalize O(1) per fix; a learned classifier generalizes from data.

Architecture (deliberately small, inspectable, No-LLM):
  features  = hashed character 2–4-grams + word unigrams (2^15 dims, L2-normed)
  model     = multiclass logistic regression trained by SGD (pure numpy)
  training  = bootstrap synthesis from slot templates (scripts/train_router.py)
              + every real disagreement the flywheel logs becomes future gold

Precedent: this is the fastText/Watson recipe — linear models over n-grams are
within a few points of deep models for short-text intent classification, at
microsecond latency and full auditability. IBM Watson beat Jeopardy champions
with exactly this class of learned routing over retrieval — no LLM existed.

Deployment contract (soft policy, never a cliff): the regex lanes stay as
high-precision overrides; the learned router runs in SHADOW on every turn
(logged to the flywheel) and is consulted as a decider only where no regex
fires. Quality can only go up, and every disagreement is training data.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO / "data" / "learned_router"
MODEL_PATH = MODEL_DIR / "router_v0.npz"
META_PATH = MODEL_DIR / "router_v0.meta.json"

DIM = 1 << 15  # hashed feature space

_MODEL: dict[str, Any] = {"W": None, "b": None, "classes": None, "mtime": 0.0}


def _structural_tokens(text: str) -> list[str]:
    """SPEECH-ACT / structural features — the signal ngrams miss. ' 
 ?' (correction) and ' ?' (definition) share their ngrams but differ in
 STRUCTURE: a correction-of-prior vs a bare wh-definition. These weighted, learnable markers
 are what let a linear model separate meaning the surface can't. (Cheap first layer; the
 phase-space concept vector is the next.)"""
    t = str(text or "")
    toks: list[str] = []
    if re.search(r"(물어본|물은)\s*(게|거)\s*아[닌니냐녜]|그게\s*아[닌니냐녜]|그런\s*(거|게|뜻|의미)\s*(가\s*)?아[닌니냐녜]|그거\s*말고|잘못\s*(알아|이해|짚)|다시\s*(말|물)|무슨\s*소리", t):
        toks.append("STRUCT:correction")
    if re.search(r"(아니|안|못|없)[가-힣]?\b|아[닌니냐녜]", t):
        toks.append("STRUCT:negation")
    if re.search(r"뭐|무엇|뭔", t): toks.append("STRUCT:wh_what")
    if re.search(r"왜|어째서", t): toks.append("STRUCT:wh_why")
    if re.search(r"어디", t): toks.append("STRUCT:wh_where")
    if re.search(r"언제", t): toks.append("STRUCT:wh_when")
    if re.search(r"누구|누가", t): toks.append("STRUCT:wh_who")
    if re.search(r"얼마|몇|개수|수치", t): toks.append("STRUCT:wh_howmuch")
    if re.search(r"어떻게|어떡", t): toks.append("STRUCT:wh_how")
    if re.search(r"(이야?|인가|일까|맞아|맞지|니|냐)\s*\??\s*$", t): toks.append("STRUCT:yesno")
    if re.search(r"(해\s*줘|알려\s*줘|써\s*줘|지어\s*줘|만들어|추천)", t): toks.append("STRUCT:imperative")
    if re.search(r"(^|\s)(너|넌|너는|네가|니가|당신|자기)\b|스스로", t): toks.append("STRUCT:address_self")
    if re.search(r"(면|다면)", t): toks.append("STRUCT:conditional")
    if re.search(r"(어떻게\s*생각|어떻게\s*봐|네\s*생각|의견)", t): toks.append("STRUCT:opinion")
    if re.search(r"(속상|힘들|우울|슬퍼|외로|지쳐|짜증|기뻐|축하|취업했|합격)", t): toks.append("STRUCT:affect")
    if re.search(r"[가-힣]{2,}\s*(랑|이랑|와|과)\s*[가-힣]{2,}", t): toks.append("STRUCT:compare_pair")
    if len(t.strip()) <= 6: toks.append("STRUCT:very_short")
    return toks


def _hash_features(text: str) -> np.ndarray:
    """Hashed char 2-4 grams + word unigrams + structural speech-act markers, L2-normalized.
    Deterministic (FNV-1a, stable across processes)."""
    x = np.zeros(DIM, dtype=np.float32)
    t = " " + re.sub(r"\s+", " ", (text or "").strip().lower()) + " "
    feats: list[str] = []
    for n in (2, 3, 4):
        feats.extend(t[i:i + n] for i in range(len(t) - n + 1))
    feats.extend(w for w in t.split() if w)
    # structural markers get a 3x weight so the linear model can lean on meaning, not just ngrams
    for st in _structural_tokens(text):
        feats.extend([st, st, st])
    for f in feats:
        h = 2166136261
        for ch in f.encode("utf-8"):  # FNV-1a: stable across processes
            h = ((h ^ ch) * 16777619) & 0xFFFFFFFF
        x[h % DIM] += 1.0
    norm = float(np.linalg.norm(x))
    return x / norm if norm > 0 else x


def _load() -> bool:
    try:
        if not MODEL_PATH.exists():
            return False
        mtime = MODEL_PATH.stat().st_mtime
        if _MODEL["W"] is None or _MODEL["mtime"] != mtime:
            data = np.load(MODEL_PATH)
            _MODEL["W"], _MODEL["b"] = data["W"], data["b"]
            _MODEL["classes"] = json.loads(META_PATH.read_text(encoding="utf-8"))["classes"]
            _MODEL["mtime"] = mtime
        return True
    except Exception:
        return False


def router_available() -> bool:
    return _load()


def predict(text: str) -> tuple[str, float]:
    """(intent, confidence). ('', 0.0) when no model is trained yet — callers
    treat that as 'no opinion', never as an intent."""
    if not _load():
        return "", 0.0
    x = _hash_features(text)
    z = _MODEL["W"] @ x + _MODEL["b"]
    z = z - z.max()
    p = np.exp(z)
    p /= p.sum()
    i = int(p.argmax())
    return str(_MODEL["classes"][i]), float(p[i])


def train(rows: list[tuple[str, str]], epochs: int = 12, lr: float = 0.5,
          l2: float = 1e-5, seed: int = 7, out_path: Path | None = None,
          meta_path: Path | None = None) -> dict[str, Any]:
    """SGD multiclass logistic regression. `rows` = (text, label). Saves the
    model + meta. Returns train/holdout accuracy (10% holdout, honest split).
    `out_path` defaults to the PRODUCTION model — pass a separate path for
    experiments/distillation so they never clobber the live router."""
    out_path = out_path or MODEL_PATH
    meta_path = meta_path or META_PATH
    rng = np.random.default_rng(seed)
    classes = sorted({label for _t, label in rows})
    cidx = {c: i for i, c in enumerate(classes)}
    X = np.stack([_hash_features(t) for t, _l in rows])
    y = np.array([cidx[l] for _t, l in rows])
    n = len(rows)
    order = rng.permutation(n)
    cut = max(1, n // 10)
    hold, tr = order[:cut], order[cut:]
    W = np.zeros((len(classes), DIM), dtype=np.float32)
    b = np.zeros(len(classes), dtype=np.float32)

    # holding the GIL; py-spy measured it at 58% of ALL engine CPU while daemons retrained. While a
    # chat request is in flight, the trainer sleeps — a request costs ~1s, an epoch can wait.
    try:
        from packages.graph_scale.load_signal import busy as _requests_busy
    except Exception:  # pragma: no cover - standalone use
        _requests_busy = lambda: False
    import time as _time
    for _ep in range(epochs):
        while _requests_busy():
            _time.sleep(0.05)
        rng.shuffle(tr)
        for _j, i in enumerate(tr):
            if _j % 512 == 0 and _requests_busy():
                while _requests_busy():
                    _time.sleep(0.05)
            z = W @ X[i] + b
            z -= z.max()
            p = np.exp(z)
            p /= p.sum()
            p[y[i]] -= 1.0  # dL/dz for cross-entropy
            W -= lr * (np.outer(p, X[i]) + l2 * W)
            b -= lr * p
    def _acc(idx: np.ndarray) -> float:
        z = X[idx] @ W.T + b
        return float((z.argmax(axis=1) == y[idx]).mean())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_path, W=W, b=b)
    meta_path.write_text(json.dumps({"classes": classes, "n_train": int(len(tr)),
                                     "n_holdout": int(len(hold))}, ensure_ascii=False),
                         encoding="utf-8")
    if out_path == MODEL_PATH:
        _MODEL["W"] = None  # force reload only when the PRODUCTION model changed
    return {"classes": len(classes), "train_acc": _acc(tr), "holdout_acc": _acc(hold),
            "n": n}
