# -*- coding: utf-8 -*-
"""Learned support-discriminator — the escape from the hand-rule ceiling (owner 2026-07-15, BINDING).

Owner: " . ." Every token heuristic (overlap, IDF,
number, polarity, SVO) is CORRECT but SPARSE, so the aggregate never moves. This replaces ALL of them
with two LEARNED pieces — doctrine-approved " ", No external LLM:

 1. SELF-SUPERVISED English embeddings (PPMI + truncated SVD) trained on the raw passage corpus — a
 word's meaning is READ from the company it keeps, not hand-coded. (Same recipe as lexical_field.py,
 the owner already blessed it.)
 2. A DISCRIMINATOR trained on public LABELED MCQ (ARC/OpenBookQA train splits — NEVER the eval set) to
 judge "is this option supported?" from the learned embedding interaction of (question, option,
 passage). It LEARNS the pattern of a supported answer from data; it is not told by a rule.

Applied to MMLU/SQuAD at test time, it picks the option whose learned support is highest. train != test,
so this is honest transfer, not test-fitting. Everything is cached to disk.
"""
from __future__ import annotations

import pickle
import re
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
_DIR = REPO / "data" / "graph_scale" / "learned_discriminator"
_TOK = re.compile(r"[a-z]+")
_DIM = 128
_WINDOW = 5
_MIN_COUNT = 8
_MAX_VOCAB = 40000


# ── self-supervised embeddings (PPMI + SVD) ──────────────────────────────────────────────────────
class Embeddings:
    def __init__(self, terms: list[str], vecs: np.ndarray):
        self.idx = {w: i for i, w in enumerate(terms)}
        self.vecs = vecs                                   # (V, D), L2-normalized rows
        self.dim = int(vecs.shape[1])

    def embed(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        n = 0
        for w in _TOK.findall(str(text).lower()):
            i = self.idx.get(w)
            if i is not None:
                v += self.vecs[i]
                n += 1
        if n:
            v /= n
            nrm = float(np.linalg.norm(v))
            if nrm > 0:
                v /= nrm
        return v

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        np.save(path / "vecs.npy", self.vecs)
        (path / "terms.txt").write_text("\n".join(self.idx), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Embeddings | None":
        try:
            terms = (path / "terms.txt").read_text(encoding="utf-8").splitlines()
            return cls(terms, np.load(path / "vecs.npy"))
        except Exception:
            return None


def train_embeddings(passages: list[str], dim: int = _DIM, *, max_vocab: int = _MAX_VOCAB,
                     min_count: int = _MIN_COUNT) -> Embeddings:
    """PPMI + truncated SVD over a co-occurrence window — a word is known by the company it keeps.
    max_vocab/min_count are tunable so a full-enwiki corpus can train a much larger, sharper vocabulary."""
    from collections import Counter
    from scipy import sparse
    from sklearn.decomposition import TruncatedSVD

    # 1) vocab
    df = Counter()
    toks_per: list[list[int]] = []
    freq = Counter()
    for p in passages:
        ws = _TOK.findall(p.lower())
        freq.update(ws)
    vocab = [w for w, c in freq.most_common(max_vocab) if c >= min_count]
    idx = {w: i for i, w in enumerate(vocab)}
    V = len(vocab)
    if V < 50:
        raise ValueError("corpus too small to train embeddings")

    # 2) co-occurrence counts (symmetric window), accumulated in CHUNKS so a million-passage corpus
    #    never blows memory (the escape from the 50k cap → full enwiki).
    C = sparse.csr_matrix((V, V), dtype=np.float32)
    rows: list[int] = []
    cols: list[int] = []

    def _flush():
        nonlocal C, rows, cols
        if rows:
            C = C + sparse.csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)),
                                      shape=(V, V), dtype=np.float32)
            rows, cols = [], []

    for p in passages:
        seq = [idx[w] for w in _TOK.findall(p.lower()) if w in idx]
        for k, wi in enumerate(seq):
            lo, hi = max(0, k - _WINDOW), min(len(seq), k + _WINDOW + 1)
            for j in range(lo, hi):
                if j != k:
                    rows.append(wi)
                    cols.append(seq[j])
        if len(rows) > 8_000_000:
            _flush()
    _flush()
    C.sum_duplicates()

    # 3) PPMI
    total = C.sum()
    row_sum = np.asarray(C.sum(axis=1)).ravel() + 1e-9
    col_sum = np.asarray(C.sum(axis=0)).ravel() + 1e-9
    C = C.tocoo()
    pmi = np.log((C.data * total) / (row_sum[C.row] * col_sum[C.col]) + 1e-12)
    pmi[pmi < 0] = 0.0                                      # positive PMI
    P = sparse.csr_matrix((pmi.astype(np.float32), (C.row, C.col)), shape=(V, V))

    # 4) SVD → dense vectors, L2-normalized
    d = min(dim, V - 1)
    svd = TruncatedSVD(n_components=d, random_state=0)
    vecs = svd.fit_transform(P).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs /= norms
    return Embeddings(vocab, vecs)


# ── the learned discriminator ────────────────────────────────────────────────────────────────────
_SENT = re.compile(r"(?<=[.!?])\s+")


class Discriminator:
    """Predicts which option is SUPPORTED by the passage, from the LEARNED embedding relationship of
    (question, option, passage). No hand rule decides the answer — the classifier is trained on labels.

    Feature design (topological alignment, not bag-of-words):
      • the passage is reduced to the SENTENCE best aligned to the option (max embedding cosine) — the
        signal isn't diluted across 700 chars.
      • NLI-style interaction: option⊙sent, |option−sent| (contradiction), option⊙question, and sims.
      • MCQ-RELATIVE: each option's features are augmented with (feature − field mean), so the model
        judges which option STANDS OUT against the others — the discriminative act itself.
    """

    def __init__(self, emb: Embeddings, clf):
        self.emb = emb
        self.clf = clf

    def _mcq_matrix(self, question: str, options: dict, passage: str) -> tuple[list, np.ndarray]:
        e = self.emb
        q = e.embed(question)
        sents = [s for s in _SENT.split(str(passage)) if s.strip()] or [str(passage)]
        svecs = np.array([e.embed(s) for s in sents], dtype=np.float32)     # (S, D), embedded once
        keys, raw = list(options), []
        for k in keys:
            o = e.embed(options[k])
            p = svecs[int(np.argmax(svecs @ o))] if len(svecs) else np.zeros(e.dim, dtype=np.float32)
            raw.append(np.concatenate([
                o * p, np.abs(o - p), o * q,
                [float(o @ p), float(o @ q), float(p @ q), float(np.linalg.norm(o - p))],
            ]).astype(np.float32))
        R = np.array(raw, dtype=np.float32)
        rel = R - R.mean(axis=0, keepdims=True)                            # relative-to-field
        return keys, np.concatenate([R, rel], axis=1)

    def score_mcq(self, question: str, options: dict, passage: str) -> dict:
        keys, X = self._mcq_matrix(question, options, passage)
        try:
            s = self.clf.predict_proba(X)[:, 1]
        except Exception:
            s = self.clf.decision_function(X)
        return {k: float(s[i]) for i, k in enumerate(keys)}

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.emb.save(path)
        with open(path / "clf.pkl", "wb") as f:
            pickle.dump(self.clf, f)

    @classmethod
    def load(cls, path: Path = _DIR) -> "Discriminator | None":
        emb = Embeddings.load(path)
        if emb is None:
            return None
        try:
            with open(path / "clf.pkl", "rb") as f:
                return cls(emb, pickle.load(f))
        except Exception:
            return None


def make_clf(spec: str):
    """spec like 'mlp:160,64' / 'gbm:0.1' / 'lr:1.0' → an UNFITTED sklearn estimator. Named specs let the
    validation selector sweep model AND hyperparameters uniformly."""
    kind, _, arg = spec.partition(":")
    if kind == "gbm":
        from sklearn.ensemble import HistGradientBoostingClassifier
        return HistGradientBoostingClassifier(max_iter=300, learning_rate=float(arg or 0.1), random_state=0)
    if kind == "lr":
        from sklearn.linear_model import LogisticRegression
        return LogisticRegression(max_iter=1000, C=float(arg or 1.0), class_weight="balanced")
    from sklearn.neural_network import MLPClassifier
    hidden = tuple(int(x) for x in (arg or "160,64").split(",") if x)
    return MLPClassifier(hidden_layer_sizes=hidden, max_iter=400, early_stopping=True,
                         alpha=1e-4, random_state=0)


def featurize(emb: Embeddings, examples: list[dict]) -> list[tuple[int, np.ndarray]]:
    """(gold_index, per-option feature matrix) per MCQ — computed ONCE so K-fold CV never re-embeds."""
    disc = Discriminator(emb, None)
    out = []
    for ex in examples:
        keys, X = disc._mcq_matrix(ex["question"], ex["options"], ex.get("passage", ""))
        if ex["gold_key"] in keys:
            out.append((keys.index(ex["gold_key"]), X))
    return out


def train_discriminator(emb: Embeddings, examples: list[dict], model: str = "mlp") -> Discriminator:
    """Train the discriminator on labeled MCQ. `model` = a make_clf spec (default 'mlp')."""
    feats = featurize(emb, examples)
    X = np.concatenate([f[1] for f in feats], axis=0)
    y = np.concatenate([[1 if i == g else 0 for i in range(len(m))] for g, m in feats])
    if len(set(y.tolist())) < 2:
        raise ValueError("need both positive and negative examples")
    clf = make_clf(model)
    clf.fit(X, y)
    return Discriminator(emb, clf)


def answer_mcq(question: str, options: dict, passage: str, disc: "Discriminator") -> str | None:
    """Pick the option with the highest LEARNED support (MCQ-relative). Returns the option key, or None."""
    if not options:
        return None
    scored = disc.score_mcq(question, options, passage)
    return max(scored, key=scored.get) if scored else None
