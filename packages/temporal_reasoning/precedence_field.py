# -*- coding: utf-8 -*-
"""Precedence field -- a LEARNED 1-D phase coordinate for event tokens.

Bradley-Terry fit over directed order observations mined from real text:
    P(a happened before b) = sigmoid(phase(b) - phase(a))
No classes, no frames, no hand-ranked lexicon: every coordinate comes from data. A token never seen
in training has NO coordinate -> inference must abstain from judgment (fail-closed honesty). Sealed
evaluation: pairs are split BEFORE training; unseen-pair direction accuracy is the gate.
See docs/ATANOR_temporal_causal_physics.md.
"""
from __future__ import annotations

import json
import math
import random
from collections import Counter
from pathlib import Path

_MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "temporal_reasoning" / "precedence_field.json"

# closed-class scaffolding on predicate names (grammar, not world knowledge)
_SCAFFOLD = {"at", "date", "time", "timestamp", "on", "of", "is", "was", "status"}

# Register-pollution stoplist -- a CLOSED list of wiki/HTML markup, entity codes, citation apparatus,
# URL/protocol and namespace tokens. This is the corpus's REGISTER (markup grammar), never world
# knowledge or events: `quot`/`ref`/`amp` are HTML entities, `page`/`article`/`user` are wiki
# boilerplate, `http`/`href`/`svg` are markup. The measured failure was exactly these dominating the
# learned 1-D phase by raw frequency (quot seen 679k, ref 316k, article 291k, page 265k) and being
# surfaced as "events". They are filtered from event surfacing so a projection never walks markup.
# Kept tight on purpose: only tokens that are NOT ordinary English event words (plus the three the
# task named -- page/article/user -- which are pure wiki boilerplate in this dump). Analogous to the
# LAD surface layer: a closed markup list, not a content whitelist.
MARKUP_STOP: frozenset[str] = frozenset({
    # HTML / wiki entity codes
    "quot", "amp", "nbsp", "lt", "gt", "apos", "ndash", "mdash", "middot", "hellip",
    "laquo", "raquo", "ldquo", "rdquo",
    # citation / reference apparatus + wiki namespace boilerplate (the task-named page/article/user)
    "ref", "refs", "reflist", "cite", "citation", "isbn", "issn", "doi", "pmid", "oclc",
    "wikipedia", "wiki", "wikitext", "mediawiki", "nowiki", "redirect", "disambiguation",
    "namespace", "infobox", "page", "article", "user",
    # URL / protocol / markup tags / attributes
    "http", "https", "www", "url", "uri", "href", "src", "colspan", "rowspan", "cellpadding",
    "cellspacing", "bgcolor", "valign", "html", "htm", "xml", "xhtml", "css", "svg", "php",
    "aspx", "png", "jpg", "jpeg", "gif", "ogg",
})


class PrecedenceField:
    def __init__(self, phase: dict[str, float] | None = None, seen: dict[str, int] | None = None,
                 event_vocab: set[str] | None = None,
                 causal_pairs: dict[tuple[str, str], int] | None = None):
        self.phase: dict[str, float] = phase or {}
        self.seen: dict[str, int] = seen or {}
        # When set, the CLEAN event vocabulary the field trusts for next-event surfacing (the causal
        # corpus's action tokens). None -> no restriction (a bare / toy field surfaces any non-markup
        # token). This is how the clean causal field is made to DOMINATE the noisy broad 1-D phase.
        self.event_vocab: set[str] | None = set(event_vocab) if event_vocab else None
        # When set, the mined DIRECTED pair evidence (typed causal edges: (earlier, later) -> count).
        # Used to rank margin-clearing successors by REAL observation, because 1-D 'nearest ahead' is
        # not 'the learned successor'. None -> phase-only ranking.
        self.causal_pairs: dict[tuple[str, str], int] | None = causal_pairs

    def is_event_token(self, tok: str) -> bool:
        """A surfaceable EVENT token: not register-pollution markup, and -- when a clean event
        vocabulary is declared -- a member of it. Markup and out-of-vocab tokens are never surfaced as
        events (register-pollution guard + clean-causal dominance, single source of truth)."""
        if tok in MARKUP_STOP:
            return False
        return self.event_vocab is None or tok in self.event_vocab

    # ------------------------------------------------------------------ training
    @classmethod
    def fit(cls, counts: Counter, epochs: int = 30, lr: float = 0.1, min_count: int = 2,
            seed: int = 13) -> "PrecedenceField":
        """SGD on Bradley-Terry over (earlier, later) counts. min_count filters mining noise."""
        pairs = [(a, b, c) for (a, b), c in counts.items() if c >= min_count]
        rng = random.Random(seed)
        phase: dict[str, float] = {}
        seen: Counter = Counter()
        for a, b, c in pairs:
            phase.setdefault(a, rng.uniform(-0.01, 0.01))
            phase.setdefault(b, rng.uniform(-0.01, 0.01))
            seen[a] += c
            seen[b] += c
        for _ in range(epochs):
            rng.shuffle(pairs)
            for a, b, c in pairs:
                # want phase[a] < phase[b]; gradient of -log sigmoid(pb - pa), weighted by count
                d = phase[b] - phase[a]
                g = (1.0 / (1.0 + math.exp(-d)) - 1.0) * min(c, 10)   # cap so one idiom can't dominate
                phase[a] -= lr * (-g)
                phase[b] -= lr * g
        return cls(phase, dict(seen))

    # ------------------------------------------------------------------ inference
    def token_phase(self, tok: str) -> float | None:
        return self.phase.get(tok)

    def predicate_phase(self, predicate: str) -> tuple[float, int] | None:
        """Phase of a compound predicate = confidence-weighted mean of its known tokens.
        Unknown predicate -> None (JUDGMENT ABSTAINED, never guessed)."""
        import re
        toks = [t for t in re.split(r"[^a-z]+", predicate.lower()) if t and t not in _SCAFFOLD]
        known = [(t, self.phase[t], self.seen.get(t, 1)) for t in toks if t in self.phase]
        if not known:
            return None
        wsum = sum(w for _, _, w in known)
        return (sum(p * w for _, p, w in known) / wsum, int(wsum))

    def order_confidence(self, pred_a: str, pred_b: str) -> float | None:
        """P(a canonically precedes b) from learned phases; None if either side is unknown."""
        pa, pb = self.predicate_phase(pred_a), self.predicate_phase(pred_b)
        if pa is None or pb is None:
            return None
        return 1.0 / (1.0 + math.exp(-(pb[0] - pa[0])))

    # ------------------------------------------------------------------ persistence
    def save(self, path: Path = _MODEL_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"phase": self.phase, "seen": self.seen}), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = _MODEL_PATH) -> "PrecedenceField | None":
        if not path.exists():
            return None
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(d["phase"], d["seen"])


_CTX_PATH = _MODEL_PATH.parent / "ctx_counts.json"
_PAIR_PATH = _MODEL_PATH.parent / "order_counts.json"


class EvidenceStore:
    """Hierarchical order evidence. Tier 1: context-conditioned pair counts (sense-aware -- the
    direction of (a,b) observed in sentences sharing a context word with the query, so corpus
    'restored castles' cannot vouch for 'telemetry restored'). Tier 2: direct pair counts. Both are
    raw data lookups; nothing here is authored."""

    def __init__(self, pair: dict[tuple, int], ctx: dict[tuple, int]):
        self.pair = pair
        self.ctx = ctx

    @classmethod
    def load(cls) -> "EvidenceStore | None":
        if not (_PAIR_PATH.exists() and _CTX_PATH.exists()):
            return None
        pair = {tuple(k.split("|")): v for k, v in
                json.loads(_PAIR_PATH.read_text(encoding="utf-8")).items()}
        ctx = {tuple(k.split("|")): v for k, v in
               json.loads(_CTX_PATH.read_text(encoding="utf-8")).items()}
        return cls(pair, ctx)

    @staticmethod
    def _toks(predicate: str) -> list[str]:
        import re
        return [t for t in re.split(r"[^a-z]+", predicate.lower()) if t and t not in _SCAFFOLD]

    def pair_evidence(self, pred_a: str, pred_b: str) -> tuple[int, int]:
        """(n_ab, n_ba): direct corpus observations of a-before-b vs b-before-a."""
        ta, tb = self._toks(pred_a), self._toks(pred_b)
        n_ab = sum(self.pair.get((a, b), 0) for a in ta for b in tb)
        n_ba = sum(self.pair.get((b, a), 0) for a in ta for b in tb)
        return n_ab, n_ba

    def ctx_evidence(self, pred_a: str, pred_b: str, ctx_tokens: list[str]) -> tuple[int, int]:
        """(n_ab, n_ba) restricted to observations whose sentence shared a context word."""
        ta, tb = self._toks(pred_a), self._toks(pred_b)
        cs = [c.lower() for c in ctx_tokens if c]
        n_ab = sum(self.ctx.get((c, a, b), 0) for c in cs for a in ta for b in tb)
        n_ba = sum(self.ctx.get((c, b, a), 0) for c in cs for a in ta for b in tb)
        return n_ab, n_ba


def posterior_direction(n_ab: int, n_ba: int) -> float:
    """Beta(1,1)-posterior mean of P(a before b) from directed observations."""
    return (n_ab + 1) / (n_ab + n_ba + 2)


def holdout_eval(counts: Counter, test_frac: float = 0.2, seed: int = 7,
                 min_count: int = 2) -> dict:
    """Sealed evaluation: split PAIRS (not observations) before training; report unseen-pair
    direction accuracy. The 0.5 coin is the null."""
    items = [((a, b), c) for (a, b), c in counts.items() if c >= min_count]
    rng = random.Random(seed)
    rng.shuffle(items)
    n_test = max(1, int(len(items) * test_frac))
    test, train = items[:n_test], items[n_test:]
    field = PrecedenceField.fit(Counter(dict(train)), min_count=1)
    correct = scored = 0
    for (a, b), c in test:
        conf = field.order_confidence(a, b)
        if conf is None:
            continue                       # token unseen in train -> honest skip
        scored += 1
        if conf > 0.5:
            correct += 1
    return {"pairs_total": len(items), "test_pairs": len(test), "scored": scored,
            "accuracy": (correct / scored) if scored else None,
            "coverage": scored / len(test) if test else 0.0}
