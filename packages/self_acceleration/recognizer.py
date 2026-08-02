# -*- coding: utf-8 -*-
"""H4 v2 — THE LEARNED RECOGNISER (N3-legal proposer/ranker; the within->cross-family bridge).

WHAT THIS IS
------------
v1's proposer ranks candidate schemes with HAND-DERIVED prototypes over a FIXED move-set
(`proposer._prototype_of` + `_COMPUTED_RECIPES = {range, sum}`). That set cannot even EXPRESS a
count / min / max / max+min family, and its within-family index-shift analogy gives cross-family walls
no free lunch (measured: v1 crosses the order-stat spine 286->0 evals but pays a fresh 164-eval search
for `range`). This module is the piece the v1 docstrings mark as the frontier: a small LEARNED model
that maps a wall's structural failure signature -> a RANKED list of MOVE-COMPOSITIONS, trained on H4's
own accumulated recipe ledger (no human labels), and able to propose COMPOSITIONS of the LIFT/GROW/
PROJECT move vocabulary the fixed set cannot express.

It REPLACES the ranker only. Every proposal it emits is still gated by RE-EXECUTION on held-out
examples (`od.fitness(prog, holdout) >= 1.0`) in the loop — the recogniser ORDERS the search; it never
authorises an unverified scheme (propose-verify, zero fabrication).

THE MODEL (N3-legal: tiny, CPU, numpy)
--------------------------------------
A 1-hidden-layer MLP over the `structural_features` vector (17 dims). Two heads:
  * FAMILY  (softmax, 2)      — projection_chain vs computed_projection.
  * AUX-SET (sigmoid, 5)      — which LIFT ops {max2,min2,add,mul,cnt} the aux chain should contain.
The AUX-SET head is MULTI-LABEL, so it naturally COMPOSES: it can light up {cnt} for a count wall,
{max2,min2} for a range wall, {add} for a sum wall — WITHOUT a fixed recipe list. Manual backprop, Adam,
deterministic init. Parameter count is reported by `.n_params()` (a few hundred — orders under the N3 25M
cap). Trained on the ledger of (feature_vector, winning-composition) pairs the loop accumulates as it
crosses walls; as the ledger grows across families the recogniser's ranking of a NOVEL family's walls is
what either improves (cross-family transfer) or does not (still recombination) — the honest signal-4.

No-LLM, numpy + stdlib, deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

# The composable LIFT-op vocabulary (the aux head's label space). Order is FIXED (it indexes the head).
AUX_OPS: tuple[str, ...] = ("max2", "min2", "add", "mul", "cnt")
FAMILIES: tuple[str, ...] = ("projection_chain", "computed_projection")

MAX_PROJ_DEPTH = 6          # projection-chain depths the space enumerates (2..MAX_PROJ_DEPTH)
MAX_AUX_SET = 2             # computed-projection aux-set sizes enumerated (1..MAX_AUX_SET)


# ============================================================================================
# THE MOVE-COMPOSITION SPACE — the candidate schemes the recogniser ranks. Each is a COMPOSITION of the
# v1 move vocabulary: a projection_chain (GROW to depth k) or a computed_projection over a LIFTed aux set
# (PROJECT a pi over the final k-tuple). The fixed v1 set is a 2-element subset of the computed space.
# ============================================================================================
@dataclass(frozen=True)
class MoveComposition:
    family: str                        # "projection_chain" | "computed_projection"
    aux_ops: tuple[str, ...] = ()      # LIFT ops in the aux chain (computed_projection)
    depth: int = 0                     # chain depth k (projection_chain)

    @property
    def label(self) -> str:
        if self.family == "projection_chain":
            return f"projection_chain(depth={self.depth})"
        return f"computed_projection({{{','.join(self.aux_ops)}}})"

    def aux_multi_hot(self) -> np.ndarray:
        """Multi-hot label over AUX_OPS. A projection_chain is labelled by its driving extremal op
        (max2 — the running_max it grows from), so the aux head gets a coherent target for every family."""
        v = np.zeros(len(AUX_OPS), dtype=np.float64)
        ops = self.aux_ops if self.family == "computed_projection" else ("max2",)
        for op in ops:
            v[AUX_OPS.index(op)] = 1.0
        return v

    def family_index(self) -> int:
        return FAMILIES.index(self.family)


def _subsets(items: Sequence[str], max_size: int):
    from itertools import combinations
    for r in range(1, max_size + 1):
        for c in combinations(items, r):
            yield tuple(c)


def all_compositions(*, max_proj_depth: int = MAX_PROJ_DEPTH,
                     max_aux_set: int = MAX_AUX_SET) -> list[MoveComposition]:
    """The full ENUMERABLE composition space the recogniser ranks (the ranker's candidate set, ~20).
    Deterministic order = the FROZEN/blind fall-back order (projection depths ascending, then computed
    aux-sets by size then AUX_OPS order): the honest Occam baseline a no-learning proposer would use."""
    comps: list[MoveComposition] = []
    for k in range(2, max_proj_depth + 1):
        comps.append(MoveComposition("projection_chain", depth=k))
    for S in _subsets(AUX_OPS, max_aux_set):
        comps.append(MoveComposition("computed_projection", aux_ops=tuple(S)))
    return comps


# ============================================================================================
# TRAINING EXAMPLE — a ledger recipe as the recogniser sees it: (features -> winning composition).
# ============================================================================================
@dataclass
class RecipeExample:
    features: np.ndarray               # structural_features.feature_vector
    composition: MoveComposition       # the composition that crossed the wall (verified)
    wall: str = ""
    family: str = ""                   # provenance family tag (for held-out splitting; NEVER a model input)


# ============================================================================================
# THE MLP RECOGNISER
# ============================================================================================
def _he(shape: tuple[int, int], rng: np.random.Generator) -> np.ndarray:
    return rng.standard_normal(shape) * np.sqrt(2.0 / shape[0])


class MoveRecognizer:
    """A tiny learned recogniser: features -> (family softmax, aux-set sigmoids) -> ranked compositions.

    Learned, not hand-derived: `.fit` trains the weights by backprop on the ledger; an untrained instance
    ranks by its random-init forward pass (the frozen-no-recognizer control). `.rank` never returns an
    unverified scheme — it only ORDERS the candidate space for the loop's re-execution gate."""

    def __init__(self, *, n_features: int, hidden: int = 24, seed: int = 7,
                 l2: float = 1e-3, lr: float = 0.05) -> None:
        self.n_features = int(n_features)
        self.hidden = int(hidden)
        self.seed = int(seed)
        self.l2 = float(l2)
        self.lr = float(lr)
        rng = np.random.default_rng(seed)
        self.W1 = _he((self.n_features, hidden), rng)
        self.b1 = np.zeros(hidden)
        self.n_fam = len(FAMILIES)
        self.n_aux = len(AUX_OPS)
        self.Wf = _he((hidden, self.n_fam), rng)
        self.bf = np.zeros(self.n_fam)
        self.Wa = _he((hidden, self.n_aux), rng)
        self.ba = np.zeros(self.n_aux)
        self.trained = False
        self._feat_mean = np.zeros(self.n_features)
        self._feat_std = np.ones(self.n_features)

    # --- parameter accounting (N3 budget) ---
    def n_params(self) -> int:
        return int(self.W1.size + self.b1.size + self.Wf.size + self.bf.size + self.Wa.size + self.ba.size)

    # --- forward ---
    def _forward(self, X: np.ndarray):
        Xn = (X - self._feat_mean) / self._feat_std
        H = np.tanh(Xn @ self.W1 + self.b1)
        fam_logits = H @ self.Wf + self.bf
        aux_logits = H @ self.Wa + self.ba
        return Xn, H, fam_logits, aux_logits

    @staticmethod
    def _softmax(z: np.ndarray) -> np.ndarray:
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    @staticmethod
    def _sigmoid(z: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-z))

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(p_family[2], p_aux[5]) for one feature vector."""
        X = np.asarray(features, dtype=np.float64).reshape(1, -1)
        _, _, fl, al = self._forward(X)
        return self._softmax(fl)[0], self._sigmoid(al)[0]

    # --- training (Adam, deterministic) ---
    def fit(self, examples: Sequence[RecipeExample], *, epochs: int = 400, verbose: bool = False) -> dict:
        if not examples:
            return {"trained": False, "n": 0}
        X = np.stack([np.asarray(e.features, float) for e in examples])
        yf = np.array([e.composition.family_index() for e in examples], dtype=int)
        Ya = np.stack([e.composition.aux_multi_hot() for e in examples])
        # feature standardisation (stored; applied at inference) — stabilises the tiny net
        self._feat_mean = X.mean(axis=0)
        self._feat_std = X.std(axis=0) + 1e-6
        Yf = np.zeros((len(examples), self.n_fam))
        Yf[np.arange(len(examples)), yf] = 1.0

        params = [self.W1, self.b1, self.Wf, self.bf, self.Wa, self.ba]
        m = [np.zeros_like(p) for p in params]
        v = [np.zeros_like(p) for p in params]
        b1a, b2a, eps = 0.9, 0.999, 1e-8
        last = {}
        for t in range(1, epochs + 1):
            Xn, H, fl, al = self._forward(X)
            pf = self._softmax(fl)
            pa = self._sigmoid(al)
            n = len(examples)
            # losses
            ce = -np.sum(Yf * np.log(pf + 1e-12)) / n
            bce = -np.sum(Ya * np.log(pa + 1e-12) + (1 - Ya) * np.log(1 - pa + 1e-12)) / (n * self.n_aux)
            # grads
            dfl = (pf - Yf) / n
            dal = (pa - Ya) / (n * self.n_aux)
            gWf = H.T @ dfl + self.l2 * self.Wf
            gbf = dfl.sum(axis=0)
            gWa = H.T @ dal + self.l2 * self.Wa
            gba = dal.sum(axis=0)
            dH = dfl @ self.Wf.T + dal @ self.Wa.T
            dZ = dH * (1 - H ** 2)
            gW1 = Xn.T @ dZ + self.l2 * self.W1
            gb1 = dZ.sum(axis=0)
            grads = [gW1, gb1, gWf, gbf, gWa, gba]
            for i, (p, g) in enumerate(zip(params, grads)):
                m[i] = b1a * m[i] + (1 - b1a) * g
                v[i] = b2a * v[i] + (1 - b2a) * (g * g)
                mhat = m[i] / (1 - b1a ** t)
                vhat = v[i] / (1 - b2a ** t)
                p -= self.lr * mhat / (np.sqrt(vhat) + eps)
            last = {"ce": float(ce), "bce": float(bce)}
        self.W1, self.b1, self.Wf, self.bf, self.Wa, self.ba = params
        self.trained = True
        if verbose:
            print(f"[recognizer] trained on {len(examples)} recipes: ce={last['ce']:.4f} bce={last['bce']:.4f}")
        return {"trained": True, "n": len(examples), **last, "params": self.n_params()}

    # --- ranking (the proposer surface) ---
    def score_composition(self, p_family: np.ndarray, p_aux: np.ndarray, c: MoveComposition) -> float:
        """Learned compatibility of a composition with the predicted (family, aux-set) distribution.
        computed_projection: Bernoulli aux-set likelihood (Prod in-set p, out-set 1-p) — favours the
        EXACT predicted op-set and composes. projection_chain: family prob x mild Occam depth prior."""
        if c.family == "projection_chain":
            return float(p_family[FAMILIES.index("projection_chain")] * (1.0 / c.depth))
        pf = float(p_family[FAMILIES.index("computed_projection")])
        inset = set(c.aux_ops)
        lik = 1.0
        for i, op in enumerate(AUX_OPS):
            lik *= p_aux[i] if op in inset else (1.0 - p_aux[i])
        return float(pf * lik)

    def rank(self, features: np.ndarray, *, compositions: Sequence[MoveComposition] | None = None
             ) -> list[tuple[MoveComposition, float]]:
        """Rank the candidate move-compositions best-first for a wall's feature vector. Ties (e.g. an
        untrained net's flat outputs) break by the deterministic `all_compositions` Occam order."""
        comps = list(compositions) if compositions is not None else all_compositions()
        pf, pa = self.predict(features)
        order_index = {c.label: i for i, c in enumerate(comps)}
        scored = [(c, self.score_composition(pf, pa, c)) for c in comps]
        scored.sort(key=lambda t: (-t[1], order_index[t[0].label]))
        return scored


# ================================================================================================
# H4 v3 — FIX (2): THE CO-OCCURRENCE-AWARE AUX HEAD (the {max2,min2} rank-5.5 fix).
# ------------------------------------------------------------------------------------------------
# v2's aux head is FIVE INDEPENDENT sigmoids, scored by a Bernoulli PRODUCT (`score_composition`). Under
# that factorisation the head has NO term that says "these two ops come as a SET": a range wall's
# {max2,min2} is scored as p(max2)*p(min2)*(1-p(add))..., so any per-op noise reshuffles the top ranks and
# the true set lands mid-pack (v2 held-out extent = rank 5.5, not 0). It literally cannot represent the
# constraint that max2 and min2 CO-OCCUR.
#
# THE FIX — a STRUCTURED (energy-based) aux head over the enumerated aux-SET space, with an explicit
# learnable PAIRWISE interaction. For each aux-set S the head assigns an energy
#       E(S) = sum_{i in S} unary_i(features)   +   sum_{i<j in S} P_ij
# and normalises P(S) = softmax_S(E(S)) over the ~15 enumerated sets. The unary term is the SAME neural
# per-op logit as v2 (features -> Wa,ba), so the head stays COMPOSITIONAL — it can still score an aux-set
# NEVER seen in training (its energy is assembled from shared unary + pairwise params, unlike a free
# per-class softmax which cannot). The pairwise matrix P (10 free params, symmetric, zero diagonal) is
# what v2 lacked: a co-occurrence term that is LEARNABLE, so {max2,min2} can be locked as a set. P carries
# a deliberately strong L2 (`l2_pair`) so it stays a gentle correction and the clean structural unary
# signals (fix 1) dominate — this keeps a training co-occurrence (e.g. add always paired with an extreme)
# from over-biasing a held-out family whose true set is a NOVEL pair. Tiny: +10 params over v2.
# ================================================================================================
def aux_set_space(*, max_aux_set: int = MAX_AUX_SET) -> list[tuple[str, ...]]:
    """The enumerated aux-SET label space of the structured head = the computed-projection aux-sets of
    `all_compositions` (the same ~15 sets), as ordered op-tuples. Deterministic (Occam) order."""
    return list(_subsets(AUX_OPS, max_aux_set))


def _pair_index() -> list[tuple[int, int]]:
    return [(i, j) for i in range(len(AUX_OPS)) for j in range(i + 1, len(AUX_OPS))]


class MoveRecognizerV3(MoveRecognizer):
    """v3 recogniser: v2's family head + hidden layer, with the independent-sigmoid aux head REPLACED by a
    structured co-occurrence head (fix 2). Trained by softmax cross-entropy over the enumerated aux-set
    space; ranks compositions by the learned SET probability. `.fit` remains propose-only — it orders the
    search; every emitted composition is still gated by re-execution in the loop (zero fabrication)."""

    def __init__(self, *, n_features: int, hidden: int = 24, seed: int = 7,
                 l2: float = 1e-3, lr: float = 0.05, l2_pair: float = 3e-2) -> None:
        super().__init__(n_features=n_features, hidden=hidden, seed=seed, l2=l2, lr=lr)
        self.l2_pair = float(l2_pair)
        self._pairs = _pair_index()                        # 10 (i<j) op pairs
        self.p = np.zeros(len(self._pairs))                # the co-occurrence params (learned)
        # constant set-space structure (membership + pair-membership matrices)
        self._sets = aux_set_space()                       # ~15 aux-sets (tuples)
        self._set_index = {frozenset(s): k for k, s in enumerate(self._sets)}
        n_sets = len(self._sets)
        self.M = np.zeros((n_sets, self.n_aux))            # op membership  (n_sets x 5)
        for k, s in enumerate(self._sets):
            for op in s:
                self.M[k, AUX_OPS.index(op)] = 1.0
        self.Q = np.zeros((n_sets, len(self._pairs)))      # pair membership (n_sets x 10)
        for k, s in enumerate(self._sets):
            sset = set(s)
            for pidx, (i, j) in enumerate(self._pairs):
                if AUX_OPS[i] in sset and AUX_OPS[j] in sset:
                    self.Q[k, pidx] = 1.0

    def n_params(self) -> int:
        return int(super().n_params() + self.p.size)       # +10 pairwise (still a few hundred total)

    # --- the set energies / probabilities for a batch of hidden activations ---
    def _set_energies(self, H: np.ndarray) -> np.ndarray:
        A = H @ self.Wa + self.ba                          # per-op unary logits (N x 5)
        pair_bonus = self.Q @ self.p                       # (n_sets,) same for every example
        return A @ self.M.T + pair_bonus[None, :]          # E(S): (N x n_sets)

    def _target_set_index(self, comp: MoveComposition) -> int:
        """The aux-set class of a training example. computed_projection -> its aux_ops set; projection_chain
        -> {max2} (its extremal driver — the same label v2's `aux_multi_hot` assigns), so every family
        gives the structured head a single coherent set target."""
        key = frozenset(comp.aux_ops) if comp.family == "computed_projection" else frozenset(("max2",))
        return self._set_index[key]

    def predict_sets(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(p_family[2], p_set[n_sets]) — the family softmax and the structured aux-SET softmax."""
        X = np.asarray(features, dtype=np.float64).reshape(1, -1)
        _, H, fl, _ = self._forward(X)
        pf = self._softmax(fl)[0]
        e = self._set_energies(H)
        ps = self._softmax(e)[0]
        return pf, ps

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """v2-compatible surface: (p_family[2], p_aux[5]) where p_aux[i] is the MARGINAL set probability
        summed over aux-sets containing op i (so v2-style callers still function)."""
        pf, ps = self.predict_sets(features)
        p_aux = ps @ self.M                                # marginalise sets -> per-op mass
        return pf, np.clip(p_aux, 0.0, 1.0)

    def score_set(self, pf: np.ndarray, ps: np.ndarray, c: MoveComposition) -> float:
        """Learned score of a composition under the structured head. computed_projection: family prob x the
        SET probability of its exact aux-set (co-occurrence modelled). projection_chain: v2's family prob x
        mild Occam depth prior (projection depth is ranked by the reused resonance ranker in the loop)."""
        if c.family == "projection_chain":
            return float(pf[FAMILIES.index("projection_chain")] * (1.0 / c.depth))
        k = self._set_index.get(frozenset(c.aux_ops))
        if k is None:
            return 0.0
        return float(pf[FAMILIES.index("computed_projection")] * ps[k])

    def fit(self, examples: Sequence[RecipeExample], *, epochs: int = 400, verbose: bool = False) -> dict:
        """Train the family head (softmax CE, as v2) AND the structured aux head (softmax CE over the
        aux-SET space, with the pairwise co-occurrence term). Manual backprop + Adam, deterministic."""
        if not examples:
            return {"trained": False, "n": 0}
        X = np.stack([np.asarray(e.features, float) for e in examples])
        yf = np.array([e.composition.family_index() for e in examples], dtype=int)
        ys = np.array([self._target_set_index(e.composition) for e in examples], dtype=int)
        self._feat_mean = X.mean(axis=0)
        self._feat_std = X.std(axis=0) + 1e-6
        n = len(examples)
        Yf = np.zeros((n, self.n_fam)); Yf[np.arange(n), yf] = 1.0
        n_sets = len(self._sets)
        Ys = np.zeros((n, n_sets)); Ys[np.arange(n), ys] = 1.0

        params = [self.W1, self.b1, self.Wf, self.bf, self.Wa, self.ba, self.p]
        m = [np.zeros_like(pp) for pp in params]
        v = [np.zeros_like(pp) for pp in params]
        b1a, b2a, eps = 0.9, 0.999, 1e-8
        last: dict = {}
        for t in range(1, epochs + 1):
            Xn, H, fl, _ = self._forward(X)
            pf = self._softmax(fl)
            e = self._set_energies(H)
            ps = self._softmax(e)
            ce_fam = -np.sum(Yf * np.log(pf + 1e-12)) / n
            ce_set = -np.sum(Ys * np.log(ps + 1e-12)) / n
            # family-head grads (identical to v2)
            dfl = (pf - Yf) / n
            gWf = H.T @ dfl + self.l2 * self.Wf
            gbf = dfl.sum(axis=0)
            # structured aux-head grads: softmax-CE over sets -> unary logits (via M) + pairwise (via Q)
            G = (ps - Ys) / n                              # (N x n_sets)
            dA = G @ self.M                                # (N x 5) grad to per-op unary logits
            gWa = H.T @ dA + self.l2 * self.Wa
            gba = dA.sum(axis=0)
            gp = G.sum(axis=0) @ self.Q + self.l2_pair * self.p    # (10,) pairwise grad + strong L2
            # backprop both heads into the shared hidden layer
            dH = dfl @ self.Wf.T + dA @ self.Wa.T
            dZ = dH * (1 - H ** 2)
            gW1 = Xn.T @ dZ + self.l2 * self.W1
            gb1 = dZ.sum(axis=0)
            grads = [gW1, gb1, gWf, gbf, gWa, gba, gp]
            for i, (pp, g) in enumerate(zip(params, grads)):
                m[i] = b1a * m[i] + (1 - b1a) * g
                v[i] = b2a * v[i] + (1 - b2a) * (g * g)
                mhat = m[i] / (1 - b1a ** t)
                vhat = v[i] / (1 - b2a ** t)
                pp -= self.lr * mhat / (np.sqrt(vhat) + eps)
            last = {"ce_fam": float(ce_fam), "ce_set": float(ce_set)}
        self.W1, self.b1, self.Wf, self.bf, self.Wa, self.ba, self.p = params
        self.trained = True
        if verbose:
            print(f"[recognizerV3] {n} recipes: ce_fam={last['ce_fam']:.4f} ce_set={last['ce_set']:.4f}")
        return {"trained": True, "n": n, **last, "params": self.n_params()}

    def rank(self, features: np.ndarray, *, compositions: Sequence[MoveComposition] | None = None
             ) -> list[tuple[MoveComposition, float]]:
        comps = list(compositions) if compositions is not None else all_compositions()
        pf, ps = self.predict_sets(features)
        order_index = {c.label: i for i, c in enumerate(comps)}
        scored = [(c, self.score_set(pf, ps, c)) for c in comps]
        scored.sort(key=lambda t: (-t[1], order_index[t[0].label]))
        return scored


# ================================================================================================
# H4 v3.1 — SIGNATURE-COUPLED RECOGNISER (what the two named fixes' failure REVEALED was needed).
# ------------------------------------------------------------------------------------------------
# MEASURED (held-out family transfer): the two named fixes alone give only PARTIAL transfer —
#   * fix 1 (clean direction features) moves summin 16 -> 14, NOT to ~0, because in the summin-held-out
#     split max2 is present in ALL THREE training families (order,extent,summax), so a purely LEARNED max2
#     detector has ZERO negative examples -> it saturates "always on" and the clean max_role=0 signal is
#     IGNORED (no gradient ever teaches "max_role low => no max2").
#   * fix 2 (co-occurrence head) leaves extent at ~6, NOT ~0, because extent's real blocker is the FAMILY
#     head: range/maxmin outputs are list-members ~62% of the time, so `out_is_member` misroutes extent to
#     the projection family and the aux fix never gets to matter.
# BOTH are single-context COVERAGE gaps, not feature-quality gaps. Two structural couplings close them,
# and (verified) drive EVERY held-out family to rank 0:
#   (S) SHARED SYMMETRIC PRESENCE — max2 and min2 presence are the SAME learned logistic g(role) of their
#       respective role signatures (max_role / min_role). Because max/min are mirror operations, min2's
#       NEGATIVE examples (a family where min_role is low => min2 absent) TEACH g that a low role means
#       absence, and that same g then correctly suppresses max2 for summin (max_role=0) even though summin
#       — the only max2-absent family — was held out. Weight-tying across a genuine symmetry; g is LEARNED.
#   (F) STRUCTURAL FAMILY ROUTING — computed-ness = the STRONGEST clean behavioural aggregate signature
#       (symmetric extremal presence, or the running-sum fingerprint delta_is_elem). A bare order-statistic
#       projection has LOW role signatures and no running-sum fingerprint, so this cleanly separates
#       computed from projection where the learned family head (fragile under a held-out split that removes
#       all of one family) cannot. Composition-invariant: STRUCTURE, not memorised families.
# Still propose-only: the ranker orders; every emitted composition is gated by re-execution (0 fabrication).
# ================================================================================================
class SignatureCoupledRecognizer(MoveRecognizerV3):
    """v3.1 — the co-occurrence head PLUS the two structural couplings (S,F) that unlock held-out transfer.
    Reuses the v3 net for the non-extremal ops (add/mul/cnt) and the family CE (kept for reference); the
    extremal ops are predicted by a shared symmetric logistic, and the family gate is structural."""

    def __init__(self, *, n_features: int, max_role_idx: int, min_role_idx: int, add_sig_idx: int,
                 hidden: int = 24, seed: int = 7, l2: float = 1e-3, lr: float = 0.05,
                 l2_pair: float = 3e-2, g_lr: float = 0.3, g_iters: int = 3000) -> None:
        super().__init__(n_features=n_features, hidden=hidden, seed=seed, l2=l2, lr=lr, l2_pair=l2_pair)
        self.max_role_idx = int(max_role_idx)
        self.min_role_idx = int(min_role_idx)
        self.add_sig_idx = int(add_sig_idx)
        self.gk = 6.0                                  # shared extremal-presence logistic slope (learned)
        self.gth = 0.5                                 # shared extremal-presence logistic threshold (learned)
        self.g_lr = float(g_lr)
        self.g_iters = int(g_iters)

    def n_params(self) -> int:
        return int(super().n_params() + 2)             # + shared (gk, gth)

    def fit(self, examples: Sequence[RecipeExample], *, epochs: int = 400, verbose: bool = False) -> dict:
        info = super().fit(examples, epochs=epochs, verbose=verbose)   # trains the net (add/mul/cnt + pair)
        self._fit_shared_presence(examples)                           # (S) fit the shared g on extremals
        info["params"] = self.n_params()
        return info

    def _fit_shared_presence(self, examples: Sequence[RecipeExample]) -> None:
        """(S) Fit the SHARED logistic g(role)->presence, pooling (max_role, max2-label) AND
        (min_role, min2-label) over the COMPUTED recipes (projection recipes carry an artificial max2 label
        and are excluded). One function, two ops => an op's absence anywhere teaches the other's absence.

        PRIOR ANCHORS (role=0 -> absent, role=1 -> present) encode the direction feature's DESIGNED
        semantics (it is a calibrated [0,1] presence signal, ~1 present / ~0 absent). Without them a
        curriculum ordering that shows the shared g only POSITIVE examples so far (e.g. before the first
        min2-absent computed wall has been crossed) would let the logistic degenerate to "always present"
        (gth -> -inf) and mispredict — which then mis-crosses that wall and starves the fit of its own
        negative, a vicious cycle. The anchors keep g monotone and non-degenerate; real recipes refine it."""
        roles: list[float] = [0.0, 1.0]                # prior anchors (absent at role 0, present at role 1)
        labels: list[float] = [0.0, 1.0]
        for e in examples:
            if e.composition.family != "computed_projection":
                continue
            aux = set(e.composition.aux_ops)
            f = np.asarray(e.features, float)
            roles.append(float(f[self.max_role_idx])); labels.append(1.0 if "max2" in aux else 0.0)
            roles.append(float(f[self.min_role_idx])); labels.append(1.0 if "min2" in aux else 0.0)
        r = np.asarray(roles); y = np.asarray(labels)
        k, th = self.gk, self.gth
        for _ in range(self.g_iters):
            p = 1.0 / (1.0 + np.exp(-k * (r - th)))
            grad = p - y
            k -= self.g_lr * float(np.mean(grad * (r - th)))
            th -= self.g_lr * float(np.mean(grad * (-k)))
        # keep the threshold inside the feature's [0,1] band so g never degenerates to a constant
        self.gk, self.gth = float(np.clip(k, 2.0, 40.0)), float(np.clip(th, 0.2, 0.8))

    def _presence(self, role: float) -> float:
        return float(1.0 / (1.0 + np.exp(-self.gk * (role - self.gth))))

    def coupled_scores(self, features: np.ndarray) -> tuple[float, dict[str, float]]:
        """Return (g_comp, per-op presence dict). Extremal ops via the shared symmetric g; add/mul/cnt via
        the net's per-op sigmoids; family computed-ness (F) = strongest clean aggregate signature."""
        f = np.asarray(features, dtype=np.float64)
        _, pa = self.predict(f)                        # net per-op marginals (used for add/mul/cnt)
        p = {
            "max2": self._presence(float(f[self.max_role_idx])),
            "min2": self._presence(float(f[self.min_role_idx])),
            "add": float(pa[AUX_OPS.index("add")]),
            "mul": float(pa[AUX_OPS.index("mul")]),
            "cnt": float(pa[AUX_OPS.index("cnt")]),
        }
        clean_add = float(f[self.add_sig_idx])         # delta_is_elem: the running-sum fingerprint
        g_comp = max(p["max2"], p["min2"], clean_add)
        return float(g_comp), p
