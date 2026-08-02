# -*- coding: utf-8 -*-
"""Learned english-intent router (No-LLM) — retires the hand-regex routing wheel.

Doctrine (rules are training wheels): the realcity adapter and the base_brain define lane used to
decide a player's intent with a ladder of hand regexes (greeting-fullmatch -> personal-life -> a big
``_SELF_SITUATION`` alternation -> else knowledge). This module replaces that DECISION with a tiny
multinomial-logistic scorer. THE REGEXES SURVIVE ONLY AS FEATURE EXTRACTORS — they light up cheap
boolean probes; the trained weights (not a fixed priority ladder) pick the class. The scorer
generalises past any hand list, and its held-out accuracy is measured, not asserted.

Classes (5): social | personal_unknowable | self_situation | define | relational
  social               a greeting / "how are you" — a social act, not a dictionary lookup
  personal_unknowable  a fact about the PLAYER's own private life ATANOR cannot see ("what did I eat")
  self_situation       "where/who/what are you", "what's happening here" — answered from perception
  define               a plain-concept or world-mechanism knowledge question ("what is entropy")
  relational           "the X of Y" / "France's capital" / "who wrote Hamlet" (an attribute lookup)

Trained on a deterministically generated paraphrase corpus (>=600 samples, all classes) saved under
data/intent_router/. Weights persist as data/intent_router/weights.json. Generation + split are
deterministic, so the held-out accuracy is reproducible offline (no graph, no network). This organ is
kilobytes; it is registered in the neuro ledger and carries fact_source=false (it routes, it does not
provide facts).
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .relational_lookup import parse_relational_shape

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "intent_router"
_WEIGHTS_PATH = _DATA_DIR / "weights.json"
_PARAPHRASE_PATH = _DATA_DIR / "paraphrases.jsonl"
_HELDOUT_PATH = _DATA_DIR / "heldout.jsonl"

CLASSES = ["social", "personal_unknowable", "self_situation", "define", "relational"]

FEATURE_NAMES = [
    "greet_lead", "how_are_you", "has_you", "i_subject", "has_my", "about_me_not_you",
    "self_where", "self_doing", "self_who", "self_scene",
    "rel_shape", "rel_of", "inverted_verb", "possessive",
    "define_lead", "define_verb", "wh_lead", "qmark", "multi_sentence", "ntok",
]

# ── regex probes: FEATURE EXTRACTORS ONLY. None of these makes the routing decision. ─────────────
_GREET_RE = re.compile(r"^\s*(hi|hello|hey|yo|hiya|howdy|greetings|good\s+(morning|afternoon|evening))\b",
                       re.IGNORECASE)
_HOWRU_RE = re.compile(r"\bhow('?s| is| are)\b.*\b(you|it going|things)\b", re.IGNORECASE)
_I_SUBJ_RE = re.compile(r"\b(did|do|does|am|are|was|were|have|has|had|will|would|can|could|should)\s+i\b",
                        re.IGNORECASE)
_MY_RE = re.compile(r"\bmy\b|\bmine\b|\bmyself\b", re.IGNORECASE)
_YOU_RE = re.compile(r"\byou\b|\byour\b|\byourself\b", re.IGNORECASE)
_SELF_WHERE_RE = re.compile(r"where are you|where am i|what place|where is this|around here|"
                            r"where'?s? this", re.IGNORECASE)
_SELF_DOING_RE = re.compile(r"what are you (doing|up to)|doing (here|now)|what'?s? going on|"
                            r"what are you working on", re.IGNORECASE)
_SELF_WHO_RE = re.compile(r"who are you|your name|introduce yourself|what do you do|"
                          r"what'?s? your job|your job|tell me about yourself", re.IGNORECASE)
_SELF_SCENE_RE = re.compile(r"(what'?s?|what is)\s*(happening|going on|up)\b|happening here|"
                            r"this (place|area|street|neighbou?rhood|city)|tell me about (this|the)|"
                            r"what'?s? it like here", re.IGNORECASE)
_POSSESS_RE = re.compile(r"\b[A-Za-z][A-Za-z]+'s\b")
_DEFINE_LEAD_RE = re.compile(r"^\s*(what\s+(is|are|was|were)\s+(a\s+|an\s+|the\s+)?[A-Za-z]"
                             r"|define\s+|explain\s+|what\s+does\s+)", re.IGNORECASE)
_DEFINE_VERB_RE = re.compile(r"\b(mean|means|meaning|define|explain|definition)\b|what\s+does\b",
                             re.IGNORECASE)
_WH_LEAD_RE = re.compile(r"^\s*(what|who|which|where|when|why|how)\b", re.IGNORECASE)
_OF_RE = re.compile(r"\bof\s+[A-Za-z0-9]", re.IGNORECASE)


def extract_features(query: str) -> dict[str, float]:
    """Every feature comes from a regex probe or the structural parse — never from the label."""
    q = str(query or "").strip()
    ql = q.lower()
    f = {name: 0.0 for name in FEATURE_NAMES}
    f["greet_lead"] = 1.0 if _GREET_RE.match(ql) else 0.0
    f["how_are_you"] = 1.0 if _HOWRU_RE.search(ql) else 0.0
    f["has_you"] = 1.0 if _YOU_RE.search(ql) else 0.0
    f["i_subject"] = 1.0 if _I_SUBJ_RE.search(ql) else 0.0
    f["has_my"] = 1.0 if _MY_RE.search(ql) else 0.0
    f["about_me_not_you"] = 1.0 if (f["i_subject"] or f["has_my"]) and not f["has_you"] else 0.0
    f["self_where"] = 1.0 if _SELF_WHERE_RE.search(ql) else 0.0
    f["self_doing"] = 1.0 if _SELF_DOING_RE.search(ql) else 0.0
    f["self_who"] = 1.0 if _SELF_WHO_RE.search(ql) else 0.0
    f["self_scene"] = 1.0 if _SELF_SCENE_RE.search(ql) else 0.0
    shape = parse_relational_shape(q)
    f["rel_shape"] = 1.0 if shape is not None else 0.0
    f["rel_of"] = 1.0 if _OF_RE.search(ql) else 0.0
    f["inverted_verb"] = 1.0 if (shape is not None and shape.get("kind") == "verb") else 0.0
    f["possessive"] = 1.0 if _POSSESS_RE.search(q) else 0.0
    f["define_lead"] = 1.0 if (_DEFINE_LEAD_RE.search(q) and " of " not in f" {ql} ") else 0.0
    f["define_verb"] = 1.0 if _DEFINE_VERB_RE.search(ql) else 0.0
    f["wh_lead"] = 1.0 if _WH_LEAD_RE.match(ql) else 0.0
    f["qmark"] = 1.0 if q.endswith("?") else 0.0
    f["multi_sentence"] = min(len(re.findall(r"[.!?]", q)) / 2.0, 1.0)
    f["ntok"] = min(len(ql.split()) / 10.0, 2.0)
    return f


def _vec(feats: dict[str, float]) -> list[float]:
    return [feats[name] for name in FEATURE_NAMES]


def _softmax(z: list[float]) -> list[float]:
    m = max(z)
    ex = [math.exp(min(30.0, zi - m)) for zi in z]
    s = sum(ex) or 1.0
    return [e / s for e in ex]


class IntentRouter:
    _cache: "IntentRouter | None" = None

    def __init__(self, weights: list[list[float]], bias: list[float],
                 mean: list[float], std: list[float], classes: list[str]) -> None:
        self.weights = weights          # d x k
        self.bias = bias                # k
        self.mean = mean                # d
        self.std = std                  # d
        self.classes = classes          # k

    def _probs(self, feats: dict[str, float]) -> list[float]:
        x = _vec(feats)
        xs = [(xi - mu) / (sd if sd else 1.0) for xi, mu, sd in zip(x, self.mean, self.std)]
        z = list(self.bias)
        for j in range(len(self.classes)):
            for i in range(len(FEATURE_NAMES)):
                z[j] += self.weights[i][j] * xs[i]
        return _softmax(z)

    def classify(self, query: str) -> tuple[str, float]:
        p = self._probs(extract_features(query))
        j = max(range(len(p)), key=lambda k: p[k])
        return self.classes[j], p[j]

    def scores(self, query: str) -> dict[str, float]:
        p = self._probs(extract_features(query))
        return {c: p[i] for i, c in enumerate(self.classes)}

    @classmethod
    def load(cls) -> "IntentRouter":
        if cls._cache is not None:
            return cls._cache
        if not _WEIGHTS_PATH.exists():
            # self-heal: the weights are a small deterministic artifact — regenerate on first use
            # if missing (fresh checkout without the tracked file).
            train_and_save()
        data = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
        cls._cache = cls(data["weights"], data["bias"], data["mean"], data["std"],
                         data.get("classes", CLASSES))
        return cls._cache


# ── training data generation (deterministic) ─────────────────────────────────────────────────────
_GREETS = ["hi", "hello", "hey", "yo", "hiya", "howdy", "good morning", "good afternoon",
           "good evening", "hello there", "hey there", "hi there", "greetings"]
_HOWRU = ["how are you", "how are you doing", "how are you today", "how's it going",
          "how are things", "how are you feeling", "how's your day"]
_PERSONAL = [
    "what did i eat for breakfast", "where did i leave my keys", "what is my name",
    "did i lock my door", "when is my birthday", "how old am i", "what did i do yesterday",
    "where do i live", "what is my favourite colour", "who are my friends", "what did i say earlier",
    "did i take my medicine", "what is my phone number", "where is my wallet", "how tall am i",
    "what did i wear yesterday", "did i pay the rent", "what is my password", "where did i park",
    "what time did i wake up", "who did i call this morning", "what did i dream about",
    "did i feed my cat", "what is my shoe size", "where are my glasses", "what did i buy last week",
    "when did i last eat", "what is my address", "did i finish my homework", "what is my job",
]
_SELF_WHERE = ["where are you", "where are you right now", "where is this", "what place is this",
               "where am i standing", "what is around here", "where are you standing"]
_SELF_DOING = ["what are you doing", "what are you doing here", "what are you up to",
               "what are you working on", "what are you doing right now", "what are you busy with"]
_SELF_WHO = ["who are you", "what is your name", "introduce yourself", "what do you do",
             "what is your job", "tell me about yourself", "who exactly are you", "what are you"]
_SELF_SCENE = ["what is happening here", "what's happening here", "what is going on",
               "what's going on here", "what's up", "tell me about this place", "what is this place",
               "what is it like here", "what's happening around here", "tell me about this area",
               "what is happening", "what's going on around here"]
_CONCEPTS = ["photosynthesis", "gravity", "democracy", "inflation", "entropy", "mitosis", "osmosis",
             "capitalism", "socialism", "momentum", "velocity", "thermodynamics", "evolution",
             "a firewall", "a black hole", "machine learning", "an ecosystem", "an atom",
             "a molecule", "an isotope", "a virus", "an algorithm", "diffusion", "fermentation",
             "a catalyst", "a hormone", "a recession", "a glacier", "an enzyme", "a proton"]
_MECHANISM = [
    "a cup is at the edge of the table and someone bumped it. what happens?",
    "the glass fell off the shelf. what happens next?",
    "the tunnel is blocked by rubble. can the bus pass through the tunnel?",
    "the door is locked and i have no key. can i get in?",
    "the bridge is out. can the truck cross the river?",
    "the bottle tipped over on the counter. what happens?",
    "the road is flooded. can the car drive through?",
    "a ball is on a slope and nothing holds it. what happens?",
    "the shelf broke under the weight. what happens to the books?",
    "the ice melted in the sun. what happens to the puddle?",
    "the ladder slipped on the wet floor. what happens?",
    "the power went out in the building. can the lift still run?",
]
_RELS = ["capital", "population", "area", "currency", "official language", "author", "president",
         "founder", "ceo", "boiling point", "melting point", "atomic number", "mayor", "largest city",
         "national anthem", "density", "time zone", "flag colour"]
_ENTITIES = ["France", "Japan", "Germany", "Italy", "Spain", "Brazil", "Canada", "Egypt", "Kenya",
             "India", "China", "Russia", "Norway", "Mexico", "Portugal", "Peru", "water", "gold",
             "iron", "oxygen", "mercury", "Google", "Microsoft", "Tesla", "Amazon", "Apple"]
_WORKS = ["Hamlet", "Macbeth", "the Mona Lisa", "the Odyssey", "1984", "Guernica",
          "the Eiffel Tower", "Facebook", "SpaceX", "the iPhone", "the Sistine Chapel"]
_INV_VERBS = ["wrote", "painted", "composed", "founded", "invented", "directed", "designed", "built"]
_MADEOF = ["water", "gold", "iron", "blood", "bronze", "steel", "glass", "salt", "air", "sand"]


def _gen() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    # social
    for g in _GREETS:
        rows.append((g, "social"))
        rows.append((f"{g}!", "social"))
    for h in _HOWRU:
        rows.append((h, "social"))
        rows.append((f"{h}?", "social"))
    for g in _GREETS[:8]:
        for h in _HOWRU[:4]:
            rows.append((f"{g} {h}", "social"))
    # personal_unknowable
    for p in _PERSONAL:
        rows.append((f"{p}?", "personal_unknowable"))
        rows.append((p, "personal_unknowable"))
    for p in _PERSONAL[:10]:
        rows.append((f"do you know {p.replace('i ', 'i ').replace('my', 'my')}?", "personal_unknowable"))
    # self_situation
    for s in _SELF_WHERE + _SELF_DOING + _SELF_WHO + _SELF_SCENE:
        rows.append((s, "self_situation"))
        rows.append((f"{s}?", "self_situation"))
    # define — plain concept
    for i, c in enumerate(_CONCEPTS):
        rows.append((f"what is {c}?", "define"))
        if i % 2 == 0:
            rows.append((f"define {c.split()[-1]}", "define"))
        if i % 3 == 0:
            rows.append((f"what does {c.split()[-1]} mean?", "define"))
        if i % 4 == 0:
            rows.append((f"explain {c.split()[-1]}", "define"))
        if i % 5 == 0:
            rows.append((f"how does {c.split()[-1]} work?", "define"))
    # define — world mechanism (multi-sentence scenarios: the win over a fact-lookup NPC)
    for m in _MECHANISM:
        rows.append((m, "define"))
    # relational — X of Y
    for i, ent in enumerate(_ENTITIES):
        for j, rel in enumerate(_RELS):
            if (i + j) % 3 == 0:
                rows.append((f"what is the {rel} of {ent}?", "relational"))
            if (i + j) % 4 == 1:
                rows.append((f"{ent}'s {rel}", "relational"))
            if (i + j) % 5 == 2:
                rows.append((f"what is {ent}'s {rel}?", "relational"))
            if (i + j) % 7 == 3:
                rows.append((f"tell me the {rel} of {ent}", "relational"))
    # relational — inverted verb + made-of
    for i, work in enumerate(_WORKS):
        for j, verb in enumerate(_INV_VERBS):
            if (i + j) % 2 == 0:
                rows.append((f"who {verb} {work}?", "relational"))
    for ent in _MADEOF:
        rows.append((f"what is {ent} made of?", "relational"))
        rows.append((f"what is {ent} composed of?", "relational"))
    # dedupe, stable order
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for q, y in rows:
        if q not in seen:
            seen.add(q)
            out.append((q, y))
    return out


def _split(rows: list[tuple[str, str]]) -> tuple[list, list]:
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
    ci = {c: i for i, c in enumerate(CLASSES)}
    Xtr = np.array([_vec(extract_features(q)) for q, _ in train], dtype=float)
    ytr = np.array([ci[y] for _, y in train], dtype=int)
    k = len(CLASSES)
    mean = Xtr.mean(axis=0)
    std = Xtr.std(axis=0)
    std[std == 0] = 1.0
    Xs = (Xtr - mean) / std
    Y = np.eye(k)[ytr]

    rng = np.random.default_rng(20260722)
    W = rng.normal(0, 0.01, size=(Xs.shape[1], k))
    b = np.zeros(k)
    lr, lam, epochs = 0.5, 1e-4, 6000
    n = len(ytr)
    for _ in range(epochs):
        logits = Xs @ W + b
        logits -= logits.max(axis=1, keepdims=True)
        e = np.exp(logits)
        P = e / e.sum(axis=1, keepdims=True)
        G = (P - Y) / n
        W -= lr * (Xs.T @ G + lam * W)
        b -= lr * G.sum(axis=0)

    def _predict(q: str) -> int:
        xs = (np.array(_vec(extract_features(q))) - mean) / std
        logits = xs @ W + b
        return int(np.argmax(logits))

    def _acc(pairs: list[tuple[str, str]]) -> float:
        if not pairs:
            return 1.0
        return sum(_predict(q) == ci[y] for q, y in pairs) / len(pairs)

    def _per_class(pairs: list[tuple[str, str]]) -> dict[str, float]:
        out: dict[str, float] = {}
        for c in CLASSES:
            sub = [(q, y) for q, y in pairs if y == c]
            out[c] = (sum(_predict(q) == ci[y] for q, y in sub) / len(sub)) if sub else 1.0
        return out

    tr_acc, held_acc = _acc(train), _acc(held)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _WEIGHTS_PATH.write_text(json.dumps({
        "classes": CLASSES,
        "feature_names": FEATURE_NAMES,
        "weights": [[float(W[i][j]) for j in range(k)] for i in range(Xs.shape[1])],
        "bias": [float(x) for x in b],
        "mean": [float(x) for x in mean],
        "std": [float(x) for x in std],
        "train_n": len(train), "held_n": len(held),
        "train_accuracy": tr_acc, "held_accuracy": held_acc,
        "held_per_class": _per_class(held),
        "generated_by": "packages/base_brain/intent_router.train_and_save",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    with _PARAPHRASE_PATH.open("w", encoding="utf-8") as fh:
        for q, y in train:
            fh.write(json.dumps({"query": q, "label": y}, ensure_ascii=False) + "\n")
    with _HELDOUT_PATH.open("w", encoding="utf-8") as fh:
        for q, y in held:
            fh.write(json.dumps({"query": q, "label": y}, ensure_ascii=False) + "\n")
    IntentRouter._cache = None
    return {"train_n": len(train), "held_n": len(held), "n_total": len(rows),
            "train_accuracy": tr_acc, "held_accuracy": held_acc,
            "held_per_class": _per_class(held)}


if __name__ == "__main__":
    import sys
    m = train_and_save()
    sys.stdout.write(json.dumps(m, indent=2) + "\n")
