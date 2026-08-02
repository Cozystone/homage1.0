# -*- coding: utf-8 -*-
"""Learned define-vs-relational router (No-LLM).

The lane gate. A tiny logistic-regression scorer decides whether an "X of Y"-ish question is
RELATIONAL ("the capital of France" -> attribute of a distinct entity) or a DEFINE ("the speed
of light" -> a concept to define). REGEX ONLY EXTRACTS FEATURES; the trained weights make the
decision (doctrine: rules are training wheels — the learned scorer generalises past a hand list).

Trained on a generated paraphrase set (both classes) saved under data/relational_router/. Weights
persist as data/relational_router/weights.json. Deterministic generation + split, so the held-out
accuracy is reproducible offline (no graph, no network).
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .relational_lookup import answerable_relation, parse_relational_shape

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "relational_router"
_WEIGHTS_PATH = _DATA_DIR / "weights.json"
_PARAPHRASE_PATH = _DATA_DIR / "paraphrases.jsonl"
_HELDOUT_PATH = _DATA_DIR / "heldout.jsonl"

FEATURE_NAMES = [
    "has_of", "has_possessive", "inverted_verb", "rel_in_vocab",
    "entity_capitalized", "entity_multiword", "rel_multiword",
    "define_lead", "has_define_verb", "rel_len",
]

_DEFINE_LEAD_RE = re.compile(r"^\s*(what\s+(is|are|was|were)\s+(a\s+|an\s+|the\s+)?[A-Za-z]"
                             r"|define\s+|explain\s+|what\s+does\s+)", re.IGNORECASE)
_DEFINE_VERB_RE = re.compile(r"\b(mean|means|meaning|define|explain|definition)\b", re.IGNORECASE)


def extract_features(query: str) -> dict[str, float]:
    """All features come from regex probes / the structural parse — never from the label."""
    q = str(query or "").strip()
    shape = parse_relational_shape(q)
    f = {name: 0.0 for name in FEATURE_NAMES}
    if shape is not None:
        kind = shape["kind"]
        rel_norm = shape["rel_norm"]
        entity = shape["entity"]
        f["has_of"] = 1.0 if kind == "of" else 0.0
        f["has_possessive"] = 1.0 if kind == "possessive" else 0.0
        f["inverted_verb"] = 1.0 if kind == "verb" else 0.0
        f["rel_in_vocab"] = 1.0 if answerable_relation(rel_norm) else 0.0
        f["entity_capitalized"] = 1.0 if (entity[:1].isupper()) else 0.0
        f["entity_multiword"] = 1.0 if (" " in entity) else 0.0
        f["rel_multiword"] = 1.0 if (" " in rel_norm) else 0.0
        f["rel_len"] = min(len(rel_norm) / 12.0, 2.0)
    f["define_lead"] = 1.0 if _DEFINE_LEAD_RE.search(q) and " of " not in f"{q.lower()} " else 0.0
    f["has_define_verb"] = 1.0 if _DEFINE_VERB_RE.search(q) else 0.0
    return f


def _vec(feats: dict[str, float]) -> list[float]:
    return [feats[name] for name in FEATURE_NAMES]


class RelationalRouter:
    _cache: "RelationalRouter | None" = None

    def __init__(self, weights: list[float], bias: float,
                 mean: list[float], std: list[float]) -> None:
        self.weights = weights
        self.bias = bias
        self.mean = mean
        self.std = std

    def _score(self, feats: dict[str, float]) -> float:
        x = _vec(feats)
        z = self.bias
        for w, xi, mu, sd in zip(self.weights, x, self.mean, self.std):
            z += w * ((xi - mu) / (sd if sd else 1.0))
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))

    def classify(self, query: str) -> tuple[str, float]:
        p = self._score(extract_features(query))
        return ("relational" if p >= 0.5 else "define"), p

    def prob_relational(self, query: str) -> float:
        return self._score(extract_features(query))

    @classmethod
    def load(cls) -> "RelationalRouter":
        if cls._cache is not None:
            return cls._cache
        if not _WEIGHTS_PATH.exists():
            # self-heal: the weights are a small deterministic artifact — regenerate on first
            # use if they are missing (fresh checkout without the tracked file, etc.).
            train_and_save()
        data = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
        cls._cache = cls(data["weights"], data["bias"], data["mean"], data["std"])
        return cls._cache


# ── training data generation (deterministic) ─────────────────────────────────────────────────
_RELS = ["capital", "population", "area", "currency", "official language", "author",
         "president", "founder", "ceo", "boiling point", "melting point", "atomic number",
         "chemical formula", "mayor", "nickname", "largest city", "national anthem", "density"]
_ENTITIES = ["France", "Japan", "Germany", "Italy", "Spain", "Brazil", "Canada", "Egypt",
             "Kenya", "India", "China", "Russia", "Norway", "Mexico", "Portugal", "Peru",
             "water", "gold", "iron", "oxygen", "mercury", "ammonia", "ethanol",
             "Google", "Microsoft", "Tesla", "Amazon", "Apple", "Toyota"]
_WORKS = ["Hamlet", "Macbeth", "Romeo and Juliet", "the Mona Lisa", "the Odyssey", "1984",
          "Guernica", "the Eiffel Tower", "Facebook", "Google", "SpaceX", "the iPhone"]
_INV_VERBS = ["wrote", "painted", "composed", "founded", "invented", "directed", "designed"]
_CONCEPTS = ["photosynthesis", "gravity", "democracy", "inflation", "entropy", "mitosis",
             "osmosis", "capitalism", "socialism", "momentum", "velocity", "thermodynamics",
             "evolution", "a firewall", "a black hole", "machine learning", "an ecosystem",
             "an atom", "a molecule", "an isotope", "a virus", "a polynomial", "an algorithm",
             "photosynthesis", "diffusion", "fermentation", "a catalyst", "a hormone"]
_COMPOUNDS = ["speed of light", "theory of relativity", "meaning of life", "law of gravity",
              "origin of species", "state of matter", "rule of law", "sense of humour",
              "balance of power", "speed of sound", "conservation of energy", "theory of mind"]


def _gen() -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    # relational (label 1): X-of-Y + possessive
    for i, ent in enumerate(_ENTITIES):
        for j, rel in enumerate(_RELS):
            if (i + j) % 3 == 0:
                rows.append((f"what is the {rel} of {ent}?", 1))
            if (i + j) % 4 == 1:
                rows.append((f"{ent}'s {rel}", 1))
            if (i + j) % 5 == 2:
                rows.append((f"what is {ent}'s {rel}?", 1))
            if (i + j) % 7 == 3:
                rows.append((f"tell me the {rel} of {ent}", 1))
    # relational inverted verb (label 1)
    for i, work in enumerate(_WORKS):
        for j, verb in enumerate(_INV_VERBS):
            if (i + j) % 2 == 0:
                rows.append((f"who {verb} {work}?", 1))
    for ent in ["water", "gold", "iron", "blood", "light", "bronze", "steel", "glass"]:
        rows.append((f"what is {ent} made of?", 1))
        rows.append((f"what is {ent} composed of?", 1))
    # define (label 0): plain concept
    for i, c in enumerate(_CONCEPTS):
        rows.append((f"what is {c}?", 0))
        if i % 2 == 0:
            rows.append((f"define {c.split()[-1]}", 0))
        if i % 3 == 0:
            rows.append((f"what does {c.split()[-1]} mean?", 0))
        if i % 4 == 0:
            rows.append((f"explain {c.split()[-1]}", 0))
    # define compound (label 0): "X of Y" that is itself a concept (rel not an attribute)
    for c in _COMPOUNDS:
        rows.append((f"what is the {c}?", 0))
        rows.append((f"what is {c}?", 0))
    # dedupe, stable order
    seen: set[str] = set()
    out: list[tuple[str, int]] = []
    for q, y in rows:
        if q not in seen:
            seen.add(q)
            out.append((q, y))
    return out


def _split(rows: list[tuple[str, int]]) -> tuple[list, list]:
    """Deterministic 80/20 split by content hash (stable, class-independent)."""
    import hashlib
    train, held = [], []
    for q, y in rows:
        h = int(hashlib.sha1(q.encode("utf-8")).hexdigest(), 16) % 10
        (held if h < 2 else train).append((q, y))
    return train, held


def train_and_save() -> dict[str, Any]:
    import numpy as np

    rows = _gen()
    train, held = _split(rows)
    Xtr = np.array([_vec(extract_features(q)) for q, _ in train], dtype=float)
    ytr = np.array([y for _, y in train], dtype=float)
    mean = Xtr.mean(axis=0)
    std = Xtr.std(axis=0)
    std[std == 0] = 1.0
    Xs = (Xtr - mean) / std

    rng = np.random.default_rng(20260721)
    w = rng.normal(0, 0.01, size=Xs.shape[1])
    b = 0.0
    lr, lam, epochs = 0.3, 1e-3, 4000
    n = len(ytr)
    for _ in range(epochs):
        z = Xs @ w + b
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        g = p - ytr
        w -= lr * (Xs.T @ g / n + lam * w)
        b -= lr * (g.mean())

    def _acc(pairs: list[tuple[str, int]]) -> float:
        if not pairs:
            return 1.0
        ok = 0
        for q, y in pairs:
            xs = (np.array(_vec(extract_features(q))) - mean) / std
            pr = 1.0 / (1.0 + math.exp(-float(np.clip(xs @ w + b, -30, 30))))
            ok += int((pr >= 0.5) == bool(y))
        return ok / len(pairs)

    tr_acc, held_acc = _acc(train), _acc(held)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _WEIGHTS_PATH.write_text(json.dumps({
        "feature_names": FEATURE_NAMES,
        "weights": [float(x) for x in w],
        "bias": float(b),
        "mean": [float(x) for x in mean],
        "std": [float(x) for x in std],
        "train_n": len(train), "held_n": len(held),
        "train_accuracy": tr_acc, "held_accuracy": held_acc,
        "generated_by": "packages/base_brain/relational_router.train_and_save",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    with _PARAPHRASE_PATH.open("w", encoding="utf-8") as fh:
        for q, y in train:
            fh.write(json.dumps({"query": q, "label": y}, ensure_ascii=False) + "\n")
    with _HELDOUT_PATH.open("w", encoding="utf-8") as fh:
        for q, y in held:
            fh.write(json.dumps({"query": q, "label": y}, ensure_ascii=False) + "\n")
    RelationalRouter._cache = None
    return {"train_n": len(train), "held_n": len(held),
            "train_accuracy": tr_acc, "held_accuracy": held_acc}


if __name__ == "__main__":
    import sys
    m = train_and_save()
    sys.stdout.write(json.dumps(m, indent=2) + "\n")
