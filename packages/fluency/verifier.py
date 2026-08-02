# -*- coding: utf-8 -*-
"""ATANOR fluency VERIFIER — a calibrated naturalness judge, honestly a PROXY.

HONEST FRAMING (BINDING). Naturalness has NO ground-truth oracle the way code has unit tests: there
is no subprocess that can re-run a sentence and return pass/fail on "does this read like a human wrote
it". So this verifier is a PROXY, not a truth oracle. The fluency self-evolution domain therefore
stays 'proxy-optimized + human-anchored', NEVER fully autonomous like the code domain. Everything here
is designed AGAINST Goodharting — the failure mode where optimizing a proxy makes the proxy-number go
up while real quality goes down.

The judge ``score(sentence) -> [0, 1]`` is three layers, deliberately of DIFFERENT kinds so no single
gameable signal dominates:

  (1) LEARNED discriminator — a tiny logistic model over cheap, interpretable surface features
      (function-word ratio, connective VARIETY, n-gram repetition, clause-length variance, template-
      marker presence, agreement/number checks, type-token ratio, ...). It is trained to separate
      NATURAL human sentences (mined from the wild_web quarantine + a bundled hand-diverse set) from
      STIFF/TEMPLATE ones (the frame realizer's run-ons + synthetic templates + degraded variants).
      Weights persist to ``data/fluency/verifier.json``. Holdout accuracy is reported HONESTLY as a
      PROXY number, not a human-truth number.

  (2) STRUCTURAL hard-checks — a rule FLOOR, EXEMPT from learning: subject-verb agreement, no run-on
      (more than N connectives in one sentence), no immediate word repetition, closed on terminal
      punctuation. These are cheap invariants a natural sentence satisfies; a structural violation
      multiplies the final score DOWN (0-clamp doctrine) no matter how high the learned score is. The
      run-on check is intentionally RAW CONNECTIVE COUNT (a hard rule), while the learned layer only
      sees connective VARIETY — so a sentence that games "variety" by stuffing many distinct
      connectives still trips the structural run-on floor. That separation is the anti-Goodhart seam.

  (3) ANTI-GOODHART ANCHOR — a small FROZEN, hand-authored human-labeled anchor set (~20 sentence
      pairs, each a clear better/worse). ``verify_against_anchor()`` reports the fraction the verifier
      ranks correctly. DOCTRINE: self-evolution may optimize the learned proxy ONLY while anchor
      agreement stays high. If a proxy-optimizing retrain raises the learned holdout score but DROPS
      anchor agreement, that is Goodharting caught red-handed -> flag, do not promote. The anchor is
      the human ground-truth tether the cheap features cannot see; it never trains.

INTEGRATION. This module exposes a verifier callable + the flags ``IS_AUTONOMOUS_SAFE=False`` and
``NEEDS_HUMAN_ANCHOR=True`` (via ``evolution_descriptor()``) so the self-evolution orchestrator can flip
the fluency domain from 'needs-verifier' to 'proxy-evolvable-anchored' — an anchored, human-tethered
autonomy, NOT the crisp full autonomy the code domain has.

Run: python -X utf8 -m packages.fluency.verifier
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[2]
WEIGHTS_PATH = REPO / "data" / "fluency" / "verifier.json"
QUARANTINE_PATH = REPO / "data" / "wild_web" / "quarantine.jsonl"

_WORD = re.compile(r"[A-Za-z0-9']+")


# ── closed-class surface vocabulary (the LAD surface layer: function words only, allowed by doctrine)
_FUNCTION_WORDS = frozenset({
    "a", "an", "the",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their", "this", "that", "these", "those",
    "who", "whom", "which", "whose",
    "is", "am", "are", "was", "were", "be", "been", "being", "has", "have", "had",
    "do", "does", "did", "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    "in", "on", "at", "by", "for", "to", "of", "with", "from", "into", "onto", "over", "under",
    "above", "below", "between", "among", "through", "during", "before", "after", "about", "against",
    "without", "within", "across", "behind", "beyond", "near", "off", "out", "up", "down",
    "and", "or", "but", "so", "yet", "nor", "because", "although", "though", "while", "if", "unless",
    "since", "as", "than", "then", "when", "where", "why", "how",
    "not", "no", "also", "too", "very", "just", "only", "even", "still", "however", "there", "here",
})

# connective tokens/phrases used for BOTH the learned variety feature and the structural run-on count.
# multi-word phrases first so they match before their single-word substrings.
_CONNECTIVE_PHRASES = ("as well as", "in addition", "as a result", "which is why", "and in turn",
                       "on top of that", "even though", "so that")
_CONNECTIVE_WORDS = ("and", "but", "or", "so", "yet", "nor", "because", "although", "though", "while",
                     "whereas", "however", "therefore", "meanwhile", "which", "when", "since")

# template/stiffness markers — a leftover placeholder or the realizer's repeated-clause signature.
_TEMPLATE_MARKERS = (
    re.compile(r"\[[A-Z]{2,}\]"),                       # [SUBJ] [OBJ] leftover slot
    re.compile(r"\{\w+\}"),                             # {o} leftover placeholder
    re.compile(r"\b(TODO|FIXME|XXX)\b"),
    re.compile(r"(?:,\s+and\s+(?:can|is|has|it)\b.*?){2,}", re.I),   # ", and can ... , and is ..."
    re.compile(r"(?:\bis\s+an?\b.*?){3,}", re.I),       # "X is a ... is a ... is a" recitation
)

FEATURE_NAMES = (
    "function_word_ratio",
    "connective_variety",
    "ngram_repetition",
    "clause_length_variance",
    "template_marker_score",
    "agreement_error_rate",
    "opener_repetition",
    "type_token_ratio",
    "mean_word_length",
    "punct_closed",
    "comma_and_density",
)


# ── low-level surface primitives ──────────────────────────────────────────────────────────────────
def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


def _words(text: str) -> list[str]:
    return _WORD.findall(text or "")


def _connectives_in(text: str) -> list[str]:
    """Ordered list of connective occurrences (phrases + words), used by variety AND run-on count."""
    low = " " + (text or "").lower() + " "
    hits: list[tuple[int, str]] = []
    for phrase in _CONNECTIVE_PHRASES:
        for m in re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", low):
            hits.append((m.start(), phrase))
    # mask phrase spans so their component words are not double counted
    masked = low
    for phrase in _CONNECTIVE_PHRASES:
        masked = re.sub(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", " " * len(phrase), masked)
    for word in _CONNECTIVE_WORDS:
        for m in re.finditer(r"\b" + re.escape(word) + r"\b", masked):
            hits.append((m.start(), word))
    hits.sort()
    return [h[1] for h in hits]


_AGREEMENT_PATTERNS = (
    re.compile(r"\b(they|we|penguins|people|children|men|women|birds|bees|mice|things|these|those)\s+(is|has|was)\b", re.I),
    re.compile(r"\b(it|he|she|this|that)\s+(are|have|were)\b", re.I),
    re.compile(r"\b(i)\s+(is|has|are)\b", re.I),
    re.compile(r"\b(you)\s+(is|was)\b", re.I),
)


def _agreement_errors(text: str) -> int:
    return sum(len(p.findall(text or "")) for p in _AGREEMENT_PATTERNS)


def _immediate_repetition(text: str) -> int:
    """Count adjacent duplicate words ('the the', 'can can'), case-insensitive — a stutter a natural
    sentence never has. Deliberately excludes legitimate doubles are rare enough to ignore here."""
    toks = [w.lower() for w in _words(text)]
    return sum(1 for i in range(1, len(toks)) if toks[i] == toks[i - 1] and len(toks[i]) > 1)


# ── the feature vector (cheap, interpretable) ─────────────────────────────────────────────────────
def features(sentence: str) -> list[float]:
    """Extract the fixed-length feature vector (order = FEATURE_NAMES). All features are cheap surface
    statistics; NONE is a raw run-on count (that is the structural floor's job), so the learned layer
    and the structural layer catch DIFFERENT failure modes."""
    text = sentence or ""
    toks = _words(text)
    low = [w.lower() for w in toks]
    n = len(toks)
    if n == 0:
        return [0.0] * len(FEATURE_NAMES)

    # 1. function-word ratio
    fw = sum(1 for w in low if w in _FUNCTION_WORDS) / n

    # 2. connective variety: 1.0 when <=1 connective (nothing to vary); else distinct/total, so a
    #    "and ... and ... and" run-on scores LOW while a varied one scores HIGH.
    conns = _connectives_in(text)
    connective_variety = 1.0 if len(conns) <= 1 else len(set(conns)) / len(conns)

    # 3. n-gram (bigram) repetition: 1 - distinct/total bigrams; template run-ons repeat ("and can").
    bigrams = list(zip(low, low[1:]))
    ngram_rep = (1.0 - len(set(bigrams)) / len(bigrams)) if bigrams else 0.0

    # 4. clause-length variance (coefficient of variation of clause word-counts, capped).
    clause_len_var = _clause_length_cv(text)

    # 5. template-marker score: normalized count of stiffness markers (leftover slots / recitation).
    marker_hits = sum(len(p.findall(text)) for p in _TEMPLATE_MARKERS)
    template_score = min(1.0, marker_hits / 2.0)

    # 6. agreement error rate (per sentence).
    sents = _sentences(text) or [text]
    agreement_rate = min(1.0, _agreement_errors(text) / len(sents))

    # 7. opener repetition across sentences (template "X is... X can... X has...").
    opener_rep = _opener_repetition(sents)

    # 8. type-token ratio (lexical diversity).
    ttr = len(set(low)) / n

    # 9. mean word length, normalized (content-dense stiff text skews longer).
    mean_wl = min(1.0, (sum(len(w) for w in toks) / n) / 12.0)

    # 10. closed on terminal punctuation.
    punct_closed = 1.0 if text.strip().endswith((".", "!", "?")) else 0.0

    # 11. REPEATED ", and" density — the frame realizer's run-on signature. The FIRST ", and" is a
    #     free natural Oxford comma ("elegant, efficient, and robust"); only the REPETITION counts.
    comma_and = max(0, len(re.findall(r",\s+and\b", text.lower())) - 1) / n

    return [fw, connective_variety, ngram_rep, clause_len_var, template_score, agreement_rate,
            opener_rep, ttr, mean_wl, punct_closed, comma_and]


def _clause_length_cv(text: str) -> float:
    parts = re.split(r"[,;:]|\b(?:and|but|or|so|yet|because|while|which)\b", text.lower())
    lens = [len(_WORD.findall(p)) for p in parts if p and _WORD.findall(p)]
    if len(lens) < 2:
        return 0.0
    arr = np.asarray(lens, float)
    mean = float(arr.mean())
    if mean <= 0:
        return 0.0
    return float(min(1.0, arr.std() / mean))


def _opener_repetition(sents: Sequence[str]) -> float:
    if len(sents) <= 1:
        return 0.0
    openers = [(_WORD.findall(s) or [""])[0].lower() for s in sents]
    freq: dict[str, int] = {}
    for o in openers:
        freq[o] = freq.get(o, 0) + 1
    return (max(freq.values()) - 1) / len(sents)


# ── the learned model (tiny logistic; weights persisted as JSON floats) ───────────────────────────
@dataclass
class LogisticModel:
    weights: list[float]
    bias: float
    mean: list[float]
    std: list[float]
    feature_names: tuple[str, ...] = FEATURE_NAMES

    def prob(self, x: Sequence[float]) -> float:
        xa = (np.asarray(x, float) - np.asarray(self.mean, float)) / np.asarray(self.std, float)
        z = float(xa @ np.asarray(self.weights, float) + self.bias)
        z = max(-30.0, min(30.0, z))
        return 1.0 / (1.0 + math.exp(-z))

    def prob_sentence(self, sentence: str) -> float:
        return self.prob(features(sentence))

    @property
    def n_params(self) -> int:
        return len(self.weights) + 1 + len(self.mean) + len(self.std)


def _fit_logistic(X: np.ndarray, y: np.ndarray, epochs: int = 6000, lr: float = 0.2,
                  l2: float = 1e-3) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    """Deterministic full-batch gradient descent (no shuffling / no RNG -> reproducible weights)."""
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std < 1e-8] = 1.0
    Xs = (X - mean) / std
    n, d = Xs.shape
    w = np.zeros(d)
    b = 0.0
    for _ in range(epochs):
        z = np.clip(Xs @ w + b, -30, 30)
        p = 1.0 / (1.0 + np.exp(-z))
        g = p - y
        w -= lr * (Xs.T @ g / n + l2 * w)
        b -= lr * float(g.mean())
    return w, b, mean, std


# ── training corpus: NATURAL positives vs STIFF/TEMPLATE negatives ────────────────────────────────
def _bundled_natural() -> list[str]:
    """A hand-diverse set of natural English sentences (varied register, topic, length, <=3
    connectives, closed on punctuation). The reproducible floor when mining is thin."""
    return [
        "The morning light slipped through the curtains and warmed the whole room.",
        "She wasn't sure whether to laugh or apologize, so she did a little of both.",
        "Copper conducts electricity well, which is why we still use it in most wiring.",
        "After the storm passed, the streets smelled of rain and cut grass.",
        "He kept a small notebook in his pocket for the ideas that arrived at odd hours.",
        "Most of the crew had never sailed at night before.",
        "If you water the seedlings too much, the roots simply rot.",
        "The recipe looks complicated, but really it is just patience and good flour.",
        "Bees navigate by the sun, and they dance to tell the hive where the flowers are.",
        "We talked until the coffee went cold and the waiter started stacking chairs.",
        "A good argument changes your mind; a great one changes how you think.",
        "The bridge was closed for repairs, so we took the long way around the lake.",
        "Penguins are birds, though they swim far better than they walk.",
        "By the time the film ended, half the audience was quietly in tears.",
        "Iron rusts when it meets water and air over time.",
        "Nobody expected the quiet intern to ask the sharpest question in the room.",
        "The garden needs weeding, but the tomatoes are finally turning red.",
        "He learned the language slowly, one stubborn verb at a time.",
        "When the power went out, the whole street stepped outside to look at the stars.",
        "The old clock still keeps decent time if you wind it every morning.",
        "Volcanoes build islands as much as they destroy them.",
        "She reads the last page first, which drives her sister completely mad.",
        "The engine coughed twice, caught, and settled into a steady hum.",
        "Rivers carry more than water; they carry the shape of the land downstream.",
        "I meant to reply sooner, but the week got away from me.",
        "A violin sounds thin alone and enormous in a full hall.",
        "The dog waited by the door long after the children had grown and left.",
        "Photosynthesis turns sunlight into sugar, and it hands us oxygen as a bonus.",
        "They rebuilt the barn in a weekend because the whole valley showed up.",
        "Good bread wants time more than it wants skill.",
        "The map was wrong, but the wrong turn led somewhere better.",
        "Gravity is gentle up close and merciless across a galaxy.",
        "He apologized in the awkward, sincere way that is hard to stay angry at.",
        "The lake freezes from the edges inward every December.",
        "Her handwriting slanted uphill whenever she was excited.",
        "We planted the oak knowing we would never sit in its shade.",
        "The market was loud, bright, and impossible to leave empty-handed.",
        "A computer is patient in a way no teacher can afford to be.",
        "The trail narrowed until we walked single file between the pines.",
        "She fixed the leak with a hairpin and an alarming amount of confidence.",
        "Salt draws the water out of the cucumbers before you even start.",
        "The choir came in a half-beat late, then found each other beautifully.",
        "Some questions are worth asking even when the answer never comes.",
        "The kitten discovered the stairs and regretted the discovery immediately.",
        "Wind turbines look slow from the road and are terrifyingly fast up close.",
        "He wrote letters he never sent and felt better for having written them.",
        "The tide went out and left the harbor full of tilted, resting boats.",
        "A single candle changes the whole mood of a dark room.",
        "The lecture ran long, but nobody checked the time.",
        "Snow makes the loudest city quiet for exactly one morning.",
        "They named the telescope after a woman the textbooks had forgotten.",
        "The soup needs an hour and almost no attention.",
    ]


def _synthetic_stiff() -> list[str]:
    """Hand-authored STIFF/TEMPLATE negatives: recitation, run-on ', and', opener repetition,
    leftover placeholders, agreement slips — the register the corpus-composition diagnosis flags."""
    return [
        "Coffee is a beverage. Coffee is a drink. Coffee is a liquid. Coffee is hot.",
        "The engine is a machine, and is made of metal, and is used for propulsion, and can burn fuel, and has a piston.",
        "Water is a substance. Water is clear. Water is made of hydrogen. Water can freeze.",
        "The lion is a mammal, and it is large, and it is located in Africa, and it can hunt, and it has a mane.",
        "[SUBJ] is a [OBJ] and [SUBJ] can perform [OBJ].",
        "Penguins is a bird, and penguins has a flightless body, and penguins is located in Antarctica.",
        "The computer is a machine, and is made of silicon, and is used for computation, and can store data, and has a processor.",
        "A bee is an insect. A bee can fly. A bee is used for pollination. A bee has a stinger.",
        "The river is a waterway, and can flow, and is used for transport, and has a current, and can flood.",
        "Iron is a metal. Iron is magnetic. Iron is a metal. Iron is hard.",
        "The volcano is a mountain, and is made of rock, and can erupt, and has a crater, and can release lava.",
        "Copper is a metal, and copper is conductive, and copper is used for wiring, and copper is a metal.",
        "The guitar is an instrument, and is made of wood, and is used for music, and has strings.",
        "Sushi is a dish. Sushi is Japanese. Sushi is made of rice. Sushi is a dish.",
        "The heart is an organ, and is made of muscle, and is used for circulation, and can pump blood.",
        "It are a mammal and it have a mane and it are large.",
        "The dog is a mammal, and can bark, and it is a mammal, and can purr.",
        "Gravity is a force, and can attract mass, and is used for orbit, and is universal, and is a force.",
        "Photosynthesis is a process, and is used for energy, and can produce oxygen, and is a process.",
        "The oak is a tree. The oak is a plant. The oak is a tree. The oak is tall.",
        "Mice is a rodent, and mice is small, and mice can climb, and mice is a rodent.",
        "The machine is a device, and is a device, and is a device, and can operate.",
        "Paris is a city. Paris is a place. Paris is a city. Paris is in France.",
        "The bird is a bird, and is a bird, and can fly, and is a bird.",
        "Bees is an insect and bees can flies and bees has a stinger and bees is small.",
        "The violin is an instrument, and is made of wood, and is used for music, and is an instrument.",
    ]


def _degraded_variants(natural: Sequence[str]) -> list[str]:
    """Deterministically degrade natural sentences into stiff negatives: force ', and' run-ons,
    inject stutter repetition, and break subject-verb agreement. This teaches the discriminator that
    the SAME content becomes stiff when its FORM degrades (form-only, like the whole fluency package)."""
    out: list[str] = []
    for i, s in enumerate(natural):
        mode = i % 3
        core = s.rstrip(".!?")
        if mode == 0:
            clauses = [c.strip() for c in re.split(r"[,;]| and | but | so ", core) if c.strip()]
            if len(clauses) >= 2:
                out.append(", and ".join(clauses) + ", and it is so.")
            else:
                out.append(core + ", and " + core.lower() + ", and it is so.")
        elif mode == 1:
            toks = core.split()
            if len(toks) > 3:
                j = 2 + (i % (len(toks) - 2))
                toks = toks[:j] + [toks[j], toks[j]] + toks[j + 1:]     # stutter
            out.append(" ".join(toks) + ".")
        else:
            broken = re.sub(r"\b(it)\s+(is|was|has)\b", r"\1 are", core, flags=re.I)
            broken = re.sub(r"\b(they|we)\s+(are|were|have)\b", r"\1 is", broken, flags=re.I)
            out.append((broken if broken != core else core + " and they is here") + ".")
    return out


def _frame_realizer_stiff() -> list[str]:
    """Real stiff outputs from the single-register frame realizer over multi-fact bones (the BEFORE
    path whose ', and ... , and' run-on is the fluency ceiling). Best-effort: skipped if unavailable."""
    out: list[str] = []
    try:
        from packages.realizer_struct import frame_realizer as fr  # read-only reuse
        from packages.fluency.fluency_v1 import tasks
        for t in tasks():
            if len(t["bones"]) >= 4:
                txt = fr.realize(t["bones"])
                if txt:
                    out.append(txt)
    except Exception:
        pass
    return out


def _mine_quarantine(limit: int = 120) -> list[str]:
    """Mine NATURAL human sentences from the wild_web quarantine (propose->verify: these are real
    human web prose, used only to teach the natural FEATURE distribution — never surfaced as fact)."""
    if not QUARANTINE_PATH.exists():
        return []
    out: list[str] = []
    seen: set[str] = set()
    try:
        for line in QUARANTINE_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                seg = str(json.loads(line).get("segment", ""))
            except Exception:
                continue
            for s in _sentences(seg):
                s = s.strip()
                key = s.lower()
                if key in seen:
                    continue
                if _is_clean_natural(s):
                    out.append(s)
                    seen.add(key)
                    if len(out) >= limit:
                        return out
    except Exception:
        return out
    return out


def _is_clean_natural(s: str) -> bool:
    toks = _words(s)
    n = len(toks)
    if n < 6 or n > 28:
        return False
    if not s.endswith((".", "!", "?")):
        return False
    if "SPEAKER_" in s or "http" in s.lower() or "@" in s or "|" in s:
        return False
    if not s[0].isalpha() or not s[0].isupper():
        return False
    alpha = sum(c.isalpha() or c.isspace() or c in ".,;:'!?-" for c in s) / max(1, len(s))
    if alpha < 0.9:
        return False
    if len(_connectives_in(s)) > 3:                 # keep mined positives off the run-on floor
        return False
    if _immediate_repetition(s) or _agreement_errors(s):
        return False
    content = sum(1 for w in toks if w.lower() not in _FUNCTION_WORDS)
    return content >= 3


def build_training_corpus() -> tuple[list[str], list[int], dict[str, Any]]:
    """Assemble (sentences, labels, meta). label 1 = natural, 0 = stiff/template."""
    natural = list(dict.fromkeys(_bundled_natural() + _mine_quarantine()))
    stiff = list(dict.fromkeys(_synthetic_stiff() + _frame_realizer_stiff()
                               + _degraded_variants(_bundled_natural())))
    sentences = natural + stiff
    labels = [1] * len(natural) + [0] * len(stiff)
    meta = {"n_natural": len(natural), "n_stiff": len(stiff),
            "n_mined": len(_mine_quarantine()), "n_bundled_natural": len(_bundled_natural()),
            "n_frame_stiff": len(_frame_realizer_stiff())}
    return sentences, labels, meta


def _holdout_mask(sentences: Sequence[str], folds: int = 5) -> list[bool]:
    """Deterministic content-hash holdout (~1/folds), so the split never depends on ordering/RNG."""
    mask = []
    for s in sentences:
        h = int(hashlib.sha1(s.encode("utf-8")).hexdigest(), 16)
        mask.append(h % folds == 0)
    return mask


# ── train / evaluate / persist ────────────────────────────────────────────────────────────────────
def train_and_save(save: bool = True) -> dict[str, Any]:
    """Build the corpus, fit the logistic on the TRAIN split, evaluate on the deterministic HOLDOUT,
    and persist weights to data/fluency/verifier.json. Returns an HONEST report (proxy caveat included)."""
    sentences, labels, meta = build_training_corpus()
    X = np.asarray([features(s) for s in sentences], float)
    y = np.asarray(labels, float)
    held = np.asarray(_holdout_mask(sentences))
    Xtr, ytr = X[~held], y[~held]
    Xte, yte = X[held], y[held]

    w, b, mean, std = _fit_logistic(Xtr, ytr)
    model = LogisticModel(weights=[float(v) for v in w], bias=float(b),
                          mean=[float(v) for v in mean], std=[float(v) for v in std])

    def _acc(Xs: np.ndarray, ys: np.ndarray) -> float:
        if len(ys) == 0:
            return float("nan")
        preds = np.asarray([1.0 if model.prob(x) >= 0.5 else 0.0 for x in Xs])
        return float((preds == ys).mean())

    report = {
        "holdout_accuracy": round(_acc(Xte, yte), 4),
        "train_accuracy": round(_acc(Xtr, ytr), 4),
        "n_total": len(sentences),
        "n_holdout": int(held.sum()),
        "n_params": model.n_params,
        "meta": meta,
        "proxy_caveat": ("holdout accuracy is a PROXY: it measures separation of natural vs "
                         "stiff/template FEATURES, not human-judged naturalness. It is NOT a human-"
                         "truth number and must not be read as one."),
    }
    if save:
        WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_id": "fluency_verifier_v0",
            "kind": "logistic_over_surface_features",
            "feature_names": list(FEATURE_NAMES),
            "weights": model.weights,
            "bias": model.bias,
            "mean": model.mean,
            "std": model.std,
            "holdout_accuracy": report["holdout_accuracy"],
            "notes": [
                "PROXY judge, not a human-truth oracle; fluency stays proxy-optimized + human-anchored.",
                "Learned layer sees connective VARIETY, never a raw run-on count (that is the "
                "structural floor) — the anti-Goodhart seam.",
                "Self-evolution may optimize these weights ONLY while verify_against_anchor() stays "
                ">= ANCHOR_AGREEMENT_FLOOR; a proxy gain that drops anchor agreement is Goodharting.",
            ],
        }
        WEIGHTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


_MODEL: LogisticModel | None = None


def load_model(force_reload: bool = False) -> LogisticModel:
    """Load the persisted model; train+save on first use if the weights are absent. Cached."""
    global _MODEL
    if _MODEL is not None and not force_reload:
        return _MODEL
    if not WEIGHTS_PATH.exists():
        train_and_save(save=True)
    data = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    _MODEL = LogisticModel(weights=[float(v) for v in data["weights"]], bias=float(data["bias"]),
                           mean=[float(v) for v in data["mean"]], std=[float(v) for v in data["std"]],
                           feature_names=tuple(data.get("feature_names", FEATURE_NAMES)))
    return _MODEL


def learned_score(sentence: str) -> float:
    """The LEARNED discriminator probability alone (natural vs stiff), before the structural floor."""
    return load_model().prob_sentence(sentence)


# ── (2) structural hard-checks: the rule FLOOR, exempt from learning ──────────────────────────────
MAX_CONNECTIVES = 3          # more than this in ONE sentence = run-on (hard rule, not learned)
MAX_SENTENCE_WORDS = 45      # a single clauseless sentence longer than this is also a run-on

# per-violation multipliers applied to the final score (0-clamp doctrine: structure caps the proxy).
_PENALTY = {
    "agreement": 0.30,
    "run_on": 0.35,
    "immediate_repetition": 0.35,
    "unclosed_punctuation": 0.80,
    "empty": 0.0,
}


def structural_checks(sentence: str) -> dict[str, Any]:
    """Cheap structural invariants a natural sentence satisfies. Returns per-check booleans + the list
    of violations. EXEMPT from learning — these are hard rules, so they cannot be trained away."""
    text = (sentence or "").strip()
    violations: list[str] = []
    if not text or not _words(text):
        return {"agreement_ok": False, "no_run_on": False, "no_immediate_repetition": False,
                "closed_punctuation": False, "violations": ["empty"], "ok": False}

    agreement_ok = _agreement_errors(text) == 0
    if not agreement_ok:
        violations.append("agreement")

    # run-on: too many connectives in a single sentence, OR one very long unbroken sentence
    max_conn = max((len(_connectives_in(s)) for s in _sentences(text)), default=0)
    longest = max((len(_words(s)) for s in _sentences(text)), default=0)
    no_run_on = max_conn <= MAX_CONNECTIVES and longest <= MAX_SENTENCE_WORDS
    if not no_run_on:
        violations.append("run_on")

    no_rep = _immediate_repetition(text) == 0
    if not no_rep:
        violations.append("immediate_repetition")

    closed = text.endswith((".", "!", "?"))
    if not closed:
        violations.append("unclosed_punctuation")

    return {"agreement_ok": agreement_ok, "no_run_on": no_run_on,
            "no_immediate_repetition": no_rep, "closed_punctuation": closed,
            "violations": violations, "ok": not violations}


def structural_multiplier(sentence: str) -> float:
    """Product of per-violation penalty factors in [0, 1]. 1.0 = every hard check passed."""
    mult = 1.0
    for v in structural_checks(sentence)["violations"]:
        mult *= _PENALTY.get(v, 0.5)
    return mult


# ── the combined judge ────────────────────────────────────────────────────────────────────────────
def score(sentence: str) -> float:
    """The calibrated fluency judge in [0, 1]: LEARNED discriminator GATED by the structural floor.

    ``score = structural_multiplier(sentence) * learned_score(sentence)``

    A structural violation multiplies the learned score DOWN regardless of how natural the features
    look — so a sentence that games the learned proxy (e.g. stuffing many distinct connectives to
    inflate connective VARIETY) still cannot score high while it trips the raw-connective run-on floor.
    HONEST: this is a PROXY in [0,1], not a human naturalness rating."""
    if not (sentence or "").strip():
        return 0.0
    return max(0.0, min(1.0, structural_multiplier(sentence) * learned_score(sentence)))


# ── (3) the FROZEN human-labeled anchor (never trains; the anti-Goodhart tether) ──────────────────
# Each pair is (BETTER, WORSE) by clear human judgment. The verifier must rank score(BETTER) >
# score(WORSE). Pairs deliberately span every layer: template recitation, run-on, opener repetition,
# agreement, and leftover placeholders — so anchor agreement cannot be satisfied by one layer alone.
ANCHOR_PAIRS: tuple[tuple[str, str], ...] = (
    ("Copper conducts electricity, which is why we use it for wiring.",
     "Copper is a metal, and is conductive, and is used for wiring, and is a metal."),
    ("Penguins are birds, though they swim far better than they walk.",
     "Penguins is a bird, and penguins has a flightless body, and penguins can swim."),
    ("The engine coughed twice, caught, and settled into a steady hum.",
     "The engine is a machine, and is made of metal, and is used for propulsion, and can burn fuel, and has a piston."),
    ("Water is clear and freezes when it gets cold enough.",
     "Water is a substance. Water is clear. Water is made of hydrogen. Water can freeze."),
    ("A bee is an insect that flies from flower to flower to pollinate them.",
     "A bee is an insect. A bee can fly. A bee is used for pollination. A bee has a stinger."),
    ("The lion is a large African mammal that hunts in coordinated groups.",
     "The lion is a mammal, and it is large, and it is located in Africa, and it can hunt, and it has a mane."),
    ("Iron rusts when it meets water and air over time.",
     "Iron is a metal. Iron is magnetic. Iron is a metal. Iron is hard."),
    ("Photosynthesis turns sunlight into sugar and releases oxygen as a bonus.",
     "Photosynthesis is a process, and is used for energy, and can produce oxygen, and is a process."),
    ("The computer stores data patiently and never loses its temper.",
     "The computer is a machine, and is made of silicon, and is used for computation, and can store data, and has a processor."),
    ("Rivers carry more than water; they carry the shape of the land downstream.",
     "The river is a waterway, and can flow, and is used for transport, and has a current, and can flood."),
    ("Paris sits on the Seine and has drawn artists for centuries.",
     "Paris is a city. Paris is a place. Paris is a city. Paris is in France."),
    ("The guitar is a wooden instrument you play by plucking its strings.",
     "The guitar is an instrument, and is made of wood, and is used for music, and is an instrument."),
    ("Volcanoes build islands as much as they destroy them.",
     "The volcano is a mountain, and is made of rock, and can erupt, and has a crater, and can release lava."),
    ("Sushi is a Japanese dish built around vinegared rice.",
     "Sushi is a dish. Sushi is Japanese. Sushi is made of rice. Sushi is a dish."),
    ("The heart is a muscle that pumps blood through the whole body.",
     "It are a organ and it have a muscle and it are used for circulation."),
    ("The dog waited by the door long after the children had left.",
     "The dog is a mammal, and can bark, and it is a mammal, and can purr."),
    ("Mice are small rodents that climb surprisingly well.",
     "Mice is a rodent, and mice is small, and mice can climb, and mice is a rodent."),
    ("Gravity is gentle up close and merciless across a galaxy.",
     "Gravity is a force, and can attract mass, and is used for orbit, and is universal, and is a force."),
    ("The oak grows slowly into an enormous, patient tree.",
     "The oak is a tree. The oak is a plant. The oak is a tree. The oak is tall."),
    ("A violin sounds thin alone and enormous in a full hall.",
     "The violin is an instrument and it is an instrument and it is an instrument and it plays."),
)

ANCHOR_AGREEMENT_FLOOR = 0.90     # self-evolution may optimize the proxy ONLY while agreement >= this


def verify_against_anchor(scorer: Callable[[str], float] | None = None) -> dict[str, Any]:
    """Fraction of the FROZEN human-labeled pairs the scorer ranks correctly (better > worse).

    Pass a CANDIDATE scorer to test whether a proposed retrain still honors human judgment. If a
    proxy-optimizing candidate raises the learned holdout score but drops this agreement below
    ANCHOR_AGREEMENT_FLOOR, that is Goodharting -> the caller must NOT promote it."""
    scorer = scorer or score
    correct = 0
    mismatches: list[dict[str, Any]] = []
    for better, worse in ANCHOR_PAIRS:
        sb, sw = scorer(better), scorer(worse)
        if sb > sw:
            correct += 1
        else:
            mismatches.append({"better": better, "worse": worse,
                               "score_better": round(sb, 4), "score_worse": round(sw, 4)})
    n = len(ANCHOR_PAIRS)
    agreement = correct / n if n else 0.0
    return {"agreement": round(agreement, 4), "n_pairs": n, "correct": correct,
            "mismatches": mismatches, "floor": ANCHOR_AGREEMENT_FLOOR,
            "passes_floor": agreement >= ANCHOR_AGREEMENT_FLOOR}


# ── the anti-Goodhart contract + a live demonstration ─────────────────────────────────────────────
# A keyword/connective-stuffed sentence engineered to inflate the LEARNED features (high connective
# variety, high lexical diversity, low ', and' density) while being an unnatural run-on. It can fool
# the learned score, but it trips the RAW-connective structural run-on floor -> the final score is
# capped. This is the Goodhart guard made concrete.
GAMED_SENTENCE = ("The design is elegant and remarkably efficient, but genuinely powerful, "
                  "so impressively fast, yet quietly robust, while thoroughly scalable.")


def goodhart_guard_demo() -> dict[str, Any]:
    """Show that a proxy-gaming sentence is caught by the structural floor even though it fools the
    learned score, and that it ranks below its honest natural counterpart."""
    natural = "The design is elegant and surprisingly robust."
    learned = learned_score(GAMED_SENTENCE)
    struct = structural_checks(GAMED_SENTENCE)
    final = score(GAMED_SENTENCE)
    natural_final = score(natural)
    # caught iff: the learned layer was fooled (high), a structural rule fired, the final verdict is
    # below the fluent threshold, AND the honest counterpart outranks it. Any single clause could be
    # coincidental; together they are the guard doing its job.
    caught = (learned >= 0.5 and bool(struct["violations"])
              and final < 0.5 and final < natural_final)
    return {
        "gamed_sentence": GAMED_SENTENCE,
        "learned_score": round(learned, 4),
        "structural_violations": struct["violations"],
        "structural_multiplier": round(structural_multiplier(GAMED_SENTENCE), 4),
        "final_score": round(final, 4),
        "natural_counterpart": natural,
        "natural_final_score": round(natural_final, 4),
        "caught": caught,
        "explanation": ("learned score is inflated by stuffed connective VARIETY, but the raw-"
                        "connective run-on floor (a hard rule the learned layer never sees) caps the "
                        "final score below both the fluent threshold and the honest counterpart."),
    }


# ── self-evolution integration surface (importable; does NOT edit self_evolution files) ───────────
IS_AUTONOMOUS_SAFE = False        # naturalness has no ground-truth oracle -> never fully autonomous
NEEDS_HUMAN_ANCHOR = True         # promotion requires the frozen human anchor to keep agreeing
EVOLVED_STATUS = "proxy-evolvable-anchored"


def evolution_descriptor() -> dict[str, Any]:
    """The descriptor the self-evolution orchestrator can import to flip the fluency domain from
    'needs-verifier' to 'proxy-evolvable-anchored'. It exposes the verifier callables and the honest
    autonomy flags — WITHOUT this module editing any self_evolution file."""
    return {
        "domain": "fluency",
        "status": EVOLVED_STATUS,
        "verifier": "packages.fluency.verifier:score",
        "anchor_verifier": "packages.fluency.verifier:verify_against_anchor",
        "structural_verifier": "packages.fluency.verifier:structural_checks",
        "is_autonomous_safe": IS_AUTONOMOUS_SAFE,
        "needs_human_anchor": NEEDS_HUMAN_ANCHOR,
        "anchor_agreement_floor": ANCHOR_AGREEMENT_FLOOR,
        "doctrine": ("PROXY, not oracle. Self-evolution may optimize the learned discriminator "
                     "(data/fluency/verifier.json) ONLY while verify_against_anchor() stays >= "
                     "anchor_agreement_floor. A retrain that raises learned holdout accuracy but "
                     "drops anchor agreement is Goodharting: reject, do not promote. Structural "
                     "hard-checks are exempt from learning and cannot be trained away."),
    }


def main() -> None:
    import io
    import sys
    buf = io.StringIO()
    rep = train_and_save(save=True)
    anch = verify_against_anchor()
    demo = goodhart_guard_demo()
    buf.write("fluency VERIFIER v0 — calibrated naturalness judge (HONEST PROXY, human-anchored)\n\n")
    buf.write(f"  learned discriminator: holdout={rep['holdout_accuracy']} (PROXY, not human truth) "
              f"train={rep['train_accuracy']} n={rep['n_total']} params={rep['n_params']}\n")
    buf.write(f"    corpus: {rep['meta']['n_natural']} natural (+{rep['meta']['n_mined']} mined) vs "
              f"{rep['meta']['n_stiff']} stiff/template\n")
    buf.write(f"  structural floor: run-on(> {MAX_CONNECTIVES} connectives) / agreement / repetition / "
              f"punctuation\n")
    buf.write(f"  anchor agreement: {anch['agreement']} over {anch['n_pairs']} human pairs "
              f"(floor {anch['floor']}, passes={anch['passes_floor']})\n")
    buf.write(f"  Goodhart guard: gamed learned={demo['learned_score']} -> final={demo['final_score']} "
              f"(natural {demo['natural_final_score']}); violations={demo['structural_violations']}; "
              f"caught={demo['caught']}\n")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.stdout.write(buf.getvalue())


if __name__ == "__main__":
    main()
