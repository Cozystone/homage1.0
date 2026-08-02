# -*- coding: utf-8 -*-
"""Lexical field — self-supervised word meaning LEARNED from raw text, so hand-written lists die.

Owner (2026-07-10): " . ." — the emotion/placeholder/pronoun sets
were O(N) (a rule per word, forever). This is the O(1) escape: ONE mechanism trained on the
Korean text the system already holds, from which a word's meaning (valence, similarity, type) is
READ, not hand-coded. Add a new word to the corpus and it is covered for free — no new list entry.

Method (No-LLM, deterministic, CPU): the classic distributional recipe — count how words co-occur
in a window (a word is known by the company it keeps), turn counts into PPMI, factor with truncated
SVD into dense vectors. Valence then GENERALISES: a word's charge = its similarity to a TINY innate
seed (= / = — the handful of primitives evolution wires in) minus the opposite seed.
// — never in any list — get a charge because they keep the company of the seeds.

Retrains from the corpus (bigger corpus = better coverage), cached to disk. If untrained/unavailable,
callers fall back to their seed lists, so nothing breaks — the lists become the floor, not the ceiling.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
_DIR = REPO / "data" / "graph_scale" / "lexical_field"
_WINDOW = 4
_MIN_COUNT = 3
_MAX_VOCAB = 6000
_DIM = 96

_S: dict[str, Any] = {"loaded": False, "vec": None, "idx": {}, "terms": []}


# ── corpus gathering (the raw text the system already has) ──────────────────────────────────
def _ko_strings(o: Any, out: list[str]) -> None:
    if isinstance(o, str):
        s = o.strip()
        if 12 <= len(s) <= 600 and sum(1 for c in s if "가" <= c <= "힣") >= 6:
            out.append(s)
    elif isinstance(o, dict):
        for v in o.values():
            _ko_strings(v, out)
    elif isinstance(o, list):
        for v in o:
            _ko_strings(v, out)


def gather_corpus(limit: int = 200_000) -> list[str]:
    """Every Korean sentence the engine already holds — evidence store, base-brain pack, narrative
    corpus, ingested pages. This is the abundant raw text the sparse graph never exposed."""
    import glob
    sents: list[str] = []
    files = (glob.glob(str(REPO / "data/brain_link/**/evidence.jsonl"), recursive=True)
             + glob.glob(str(REPO / "data/base_brain/packs/atanor_base_brain_v0.json"))
             + glob.glob(str(REPO / "data/surface_brain/narrative_corpus.jsonl"))
             + glob.glob(str(REPO / "data/autonomy/expedition_journal.jsonl"))
             + glob.glob(str(REPO / "data/*/semantic_packs/**/*.json"), recursive=True))
    for f in files:
        try:
            if f.endswith(".jsonl"):
                for line in open(f, encoding="utf-8"):
                    try:
                        _ko_strings(json.loads(line), sents)
                    except Exception:
                        continue
            else:
                _ko_strings(json.load(open(f, encoding="utf-8")), sents)
        except Exception:
            continue
        if len(sents) >= limit:
            break
    # de-dup while preserving order
    seen: set[str] = set()
    uniq = [s for s in sents if not (s in seen or seen.add(s))]
    return uniq[:limit]


def _tokenize(sent: str) -> list[str]:
    """Content morphemes (Kiwi): nouns + verb/adjective STEMS + roots. Stems (not surfaces) so
 // all map to the one lemma — the affect signal concentrates instead of scattering."""
    try:
        from packages.base_brain.neighborhood import _kiwi
        kw = _kiwi()
        if kw is None:
            return []
        return [t.form for t in kw.tokenize(sent)
                if t.tag in ("NNG", "NNP", "VV", "VA", "VV-I", "VA-I", "XR", "SL")]
    except Exception:
        return []


# ── training (PPMI + truncated SVD) ─────────────────────────────────────────────────────────
def train(corpus: list[str] | None = None, *, save: bool = True) -> dict[str, Any]:
    """Learn dense word vectors from co-occurrence. Deterministic; no gradient, no LLM."""
    corpus = corpus if corpus is not None else gather_corpus()
    toks_per = [_tokenize(s) for s in corpus]
    freq: dict[str, int] = {}
    for toks in toks_per:
        for t in toks:
            freq[t] = freq.get(t, 0) + 1
    vocab = [w for w, c in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
             if c >= _MIN_COUNT][:_MAX_VOCAB]
    idx = {w: i for i, w in enumerate(vocab)}
    V = len(vocab)
    if V < 50:
        return {"ok": False, "reason": "corpus_too_small", "vocab": V, "sentences": len(corpus)}
    # symmetric window co-occurrence
    from collections import defaultdict
    cooc: dict[tuple[int, int], float] = defaultdict(float)
    wcount = np.zeros(V, dtype=np.float64)
    for toks in toks_per:
        ids = [idx[t] for t in toks if t in idx]
        for p, i in enumerate(ids):
            wcount[i] += 1
            lo, hi = max(0, p - _WINDOW), min(len(ids), p + _WINDOW + 1)
            for q in range(lo, hi):
                if q == p:
                    continue
                j = ids[q]
                cooc[(i, j)] += 1.0
    total = wcount.sum()
    # PPMI sparse matrix
    from scipy.sparse import csr_matrix
    from scipy.sparse.linalg import svds
    rows, cols, vals = [], [], []
    for (i, j), c in cooc.items():
        pmi = math.log((c * total) / (wcount[i] * wcount[j]) + 1e-12)
        if pmi > 0:
            rows.append(i); cols.append(j); vals.append(pmi)
    M = csr_matrix((vals, (rows, cols)), shape=(V, V))
    dim = min(_DIM, V - 1)
    U, Sig, _Vt = svds(M, k=dim)
    vec = U * np.sqrt(np.maximum(Sig, 0))           # word vectors
    norms = np.linalg.norm(vec, axis=1, keepdims=True)
    vec = vec / np.clip(norms, 1e-9, None)          # unit-normalize → cosine = dot
    _S.update(loaded=True, vec=vec.astype(np.float32), idx=idx, terms=vocab)
    if save:
        _DIR.mkdir(parents=True, exist_ok=True)
        np.save(_DIR / "vectors.npy", _S["vec"])
        (_DIR / "terms.json").write_text(json.dumps(vocab, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "vocab": V, "sentences": len(corpus), "dim": dim}


def maybe_retrain(min_growth: float = 1.25) -> dict[str, Any]:
    """Self-maintaining: retrain ONLY when the corpus has grown enough since the last train, so the
    learned meaning (and the affect/type coverage read from it) improves on its own as the engine
    reads more — no manual retrain step. This is the O(1) promise made good over time."""
    try:
        meta = _DIR / "meta.json"
        prev = int(json.loads(meta.read_text(encoding="utf-8")).get("sentences", 0)) if meta.exists() else 0
        cur = len(gather_corpus())
        if cur >= 200 and cur >= max(prev * min_growth, prev + 300):
            r = train()
            _DIR.mkdir(parents=True, exist_ok=True)
            meta.write_text(json.dumps({"sentences": cur}), encoding="utf-8")
            return {"retrained": True, **r}
        return {"retrained": False, "sentences": cur, "prev": prev}
    except Exception as e:
        return {"retrained": False, "error": str(e)}


def _load() -> bool:
    if _S["loaded"]:
        return True
    try:
        vec = np.load(_DIR / "vectors.npy")
        terms = json.loads((_DIR / "terms.json").read_text(encoding="utf-8"))
        _S.update(loaded=True, vec=vec, terms=terms, idx={w: i for i, w in enumerate(terms)})
        return True
    except Exception:
        return False


# ── read the learned meaning ────────────────────────────────────────────────────────────────
def available() -> bool:
    return _load()


def vector(word: str) -> np.ndarray | None:
    if not _load():
        return None
    i = _S["idx"].get(word)
    return None if i is None else _S["vec"][i]


def similarity(a: str, b: str) -> float | None:
    va, vb = vector(a), vector(b)
    if va is None or vb is None:
        return None
    return float(np.dot(va, vb))


def valence(word: str, pos_seeds: tuple[str, ...], neg_seeds: tuple[str, ...]) -> float | None:
    """A word's LEARNED valence: how much it keeps the company of the positive seeds vs the negative
    ones, in the text-trained space. Returns None only when the word never appeared in the corpus."""
    v = vector(word)
    if v is None:
        return None
    def _m(seeds: tuple[str, ...]) -> float:
        sims = [float(np.dot(v, sv)) for s in seeds if (sv := vector(s)) is not None]
        return sum(sims) / len(sims) if sims else 0.0
    return round(_m(pos_seeds) - _m(neg_seeds), 4)
