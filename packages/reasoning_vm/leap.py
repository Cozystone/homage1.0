# -*- coding: utf-8 -*-
"""Generative Leap Loop v0 — intuition + analogy organs for the discovery engine (owner 2026-07-15:
" . ").

Doctrine-honest design: a PROPOSER, never an asserter. Human innovation (Kekulé's ring, Darwin's
selection, Rutherford's atom) is measured cognition: transfer of RELATIONAL STRUCTURE from a distant
domain + verification — not magic. So the loop is:

 ① INTUITION (System 1, learned): latent-space algebra over our self-supervised embeddings.
 analogy(a, b, c) = nearest neighbours of vec(b) − vec(a) + vec(c) (wide, fast, fallible)
 blend(x, y) = nearest neighbours of the normalized midpoint (conceptual blending)
 ② ANALOGY (System 2, symbolic): structure transfer over the knowledge graph — edges the SOURCE
 domain has but the analogically-mapped TARGET lacks become CANDIDATE hypotheses.
 ③ VERIFICATION (already built elsewhere): every output is a Conjecture with epistemic status
 'conjecture' — it enters the hippocampal sandbox / consensus gate; only survivors are promoted.
 NOTHING here is ever asserted as fact (hallucination-0 preserved).

No LLM. The generator's job is to be prolific and structured; the verify gate does the selecting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]


@dataclass
class Conjecture:
    """A proposed leap — NEVER a fact. Carries its derivation so the verifier (and the user) can see
    exactly how it was reached, and its status can only be upgraded BY the verify gate."""
    kind: str                    # analogy | blend | structure_transfer
    text: str                    # human-readable proposal
    triple: tuple | None = None  # (s, r, o) when the proposal is graph-shaped
    score: float = 0.0           # latent-space confidence (proposal strength, NOT truth)
    derivation: dict = field(default_factory=dict)
    status: str = "conjecture"   # conjecture → (verify gate) → verified | refuted


class LeapEngine:
    def __init__(self, emb, facts_about=None):
        """emb: learned_discriminator.Embeddings (self-supervised PPMI+SVD). facts_about: optional
        graph accessor used by structure transfer + type sanity."""
        self.emb = emb
        self.fa = facts_about
        self._terms = list(emb.idx)
        self._V = emb.vecs                                   # (V, D) L2-normalized

    # ── ① intuition: latent algebra ─────────────────────────────────────────────
    def _nn(self, v: np.ndarray, k: int, exclude: set[str]) -> list[tuple[str, float]]:
        n = float(np.linalg.norm(v))
        if n == 0:
            return []
        sims = self._V @ (v / n)
        order = np.argsort(-sims)
        out = []
        for i in order[: k + len(exclude) + 8]:
            t = self._terms[int(i)]
            if t in exclude:
                continue
            out.append((t, float(sims[int(i)])))
            if len(out) >= k:
                break
        return out

    def analogy(self, a: str, b: str, c: str, k: int = 5) -> list[Conjecture]:
        """a:b :: c:? — the displacement a→b applied at c. (king:queen :: man:? → woman)"""
        va, vb, vc = self.emb.embed(a), self.emb.embed(b), self.emb.embed(c)
        cands = self._nn(vb - va + vc, k, exclude={a, b, c})
        return [Conjecture("analogy", f"{a}:{b} :: {c}:{t}", score=s,
                           derivation={"a": a, "b": b, "c": c, "op": "vec(b)-vec(a)+vec(c)"})
                for t, s in cands]

    def blend(self, x: str, y: str, k: int = 5) -> list[Conjecture]:
        """Conceptual blending: what lives BETWEEN two concepts (the shared frame's neighbours)."""
        v = self.emb.embed(x) + self.emb.embed(y)
        cands = self._nn(v, k, exclude={x, y})
        return [Conjecture("blend", f"{x} × {y} → {t}", score=s,
                           derivation={"x": x, "y": y, "op": "normalized midpoint"})
                for t, s in cands]

    # ── ② analogy organ: structure transfer over the graph ─────────────────────
    def transfer(self, source: str, target: str, k_map: int = 3, limit: int = 12,
                 only_relations: set | None = None) -> list[Conjecture]:
        """Map SOURCE's relational neighbourhood onto TARGET: for each known edge (source, r, x), the
        proposal is (target, r, x') where x' is x displaced by the source→target direction. Edges the
        target does NOT already have are the interesting conjectures — candidate discoveries.

        `only_relations` enforces Gentner's SYSTEMATICITY: carry only relations the target already
        participates in, so the mapping is grounded in shared structure (both are things that are
        `located_in`/`capable_of`…) and only the specific filler is conjectured — not an arbitrary edge."""
        if self.fa is None:
            return []
        try:
            src_edges = list(self.fa(source) or [])[:limit]
            tgt_known = {(str(p), str(o)) for (_s, p, o) in (self.fa(target) or [])}
        except Exception:
            return []
        d = self.emb.embed(target) - self.emb.embed(source)   # the domain displacement
        out: list[Conjecture] = []
        for (_s, r, x) in src_edges:
            if only_relations is not None and str(r) not in only_relations:
                continue                                      # relation not shared → not systematic
            x = str(x)
            for xp, s in self._nn(self.emb.embed(x) + d, k_map, exclude={source, target, x}):
                if (str(r), xp) in tgt_known:
                    continue                                  # target already has it — not a leap
                out.append(Conjecture(
                    "structure_transfer", f"({target}, {r}, {xp})?  [because ({source}, {r}, {x})]",
                    triple=(target, str(r), xp), score=s,
                    derivation={"source": source, "target": target,
                                "carried_edge": (source, str(r), x), "mapped_via": "domain displacement"}))
        out.sort(key=lambda c: -c.score)
        return out[:limit]
