# -*- coding: utf-8 -*-
"""NS-5 — VSA resonance verifier (a nonconformity signal for the conformal gate).

M1 shipped ``nonconformity.from_cleanup_sims``: it reads a raw similarity array and reports
top-1 resonance + margin. This module adds the missing half — proper ACCEPT / REJECT verifier
semantics over the FHRR clean-up memory, as a first-class check the gate can call.

The physics (all from ``vsa_reasoning.fhrr_core`` / ``holographic_lm``, imported READ-ONLY):
a candidate answer is a noisy filler vector ``q``. Clean-up snaps it to the nearest codebook
atom by phase interference (``resonance`` in [-1,1]). Two quantities decide acceptance:

  * CONVERGENCE  = top-1 resonance. A vector that genuinely encodes one atom resonates near 1;
    junk / an unseen binding resonates near 0.
  * MARGIN       = top1 - top2 resonance. A CLEAN filler is close to exactly one atom and far
    from the rest -> large margin. A filler that is a SUPERPOSITION of two competing atoms
    (the query has two plausible answers) snaps only weakly -> the runner-up resonates almost
    as strongly -> tiny margin. That is the graph/VSA face of ambiguity, and it is the honest
    reason to abstain: the algebra itself failed to converge to a single answer.

``verify_binding`` returns ``accepted`` iff resonance AND margin clear their floors (and, if an
``expected_label`` is supplied, the winner matches it). Failure-to-converge (low resonance) or a
tiny margin -> ``accepted=False`` and, through ``nonconformity.from_resonance_margin``, HIGH
nonconformity -> the gate abstains. Nothing is fabricated: an empty/zero query returns a null
verdict (no signal), which the gate reads as doubt.

Honest boundary (measured, see the M3 probe): the margin detects a filler built from COMPETING
atoms (ambiguity). If the graph delivers a single, confident-but-WRONG atom, the margin is large
and this verifier accepts it -> like NS-2, it does not catch confidently-wrong graph facts.

Pure numpy. No training, no LLM, deterministic (seeded atoms).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence


def build_codebook(labels: Sequence[str], *, space: Any = None):
    """Stack per-label FHRR atoms into an (N, D) codebook (rows = ``fhrr_core.atom(label)``).

    Reuses the shared HoloSpace so atoms are deterministic and consistent with the rest of the
    VSA lane. Returns (codebook, labels_list)."""
    import numpy as np
    from packages.vsa_reasoning.fhrr_core import atom

    labs = [str(x) for x in labels]
    if not labs:
        return np.zeros((0, 0), dtype=np.complex128), []
    rows = [atom(l, space=space) for l in labs]
    return np.stack(rows), labs


def weighted_superposition(items: Iterable[tuple[str, float]], *, space: Any = None):
    """Build a filler = Σ weight * atom(label) (the FHRR bundle of a set of candidate answers).

    ``items`` = (label, weight) pairs (e.g. answer value -> its spreading-activation mass). A
    single dominant item yields a near-pure atom (large clean-up margin); two comparable items
    yield a genuine superposition (small margin). Empty -> zero vector (null verdict downstream)."""
    import numpy as np
    from packages.vsa_reasoning.fhrr_core import atom

    acc = None
    for label, w in items:
        v = atom(str(label), space=space) * float(w)
        acc = v if acc is None else acc + v
    if acc is None:
        return np.zeros(0, dtype=np.complex128)
    return acc


def verify_binding(
    query_vec: Any,
    codebook: Any,
    labels: Sequence,
    *,
    expected_label: Optional[Any] = None,
    min_resonance: float = 0.15,
    min_margin: float = 0.08,
) -> dict:
    """Clean up ``query_vec`` against ``codebook`` and return an accept/reject verdict.

    Returns a dict::

        {accepted, converged, top_label, resonance, top2_label, top2_resonance,
         margin, expected_label, min_resonance, min_margin}

    ``accepted`` = converged (margin >= min_margin) AND resonance >= min_resonance AND
    (expected_label is None or top_label == expected_label). A null query (empty / zero-norm /
    empty codebook) returns ``resonance=None`` -> ``nonconformity.from_resonance_margin`` treats
    it as an ABSENT signal (doubt), never a confident accept."""
    import numpy as np

    cb = np.asarray(codebook, dtype=np.complex128)
    q = np.asarray(query_vec, dtype=np.complex128).ravel()
    null = {
        "accepted": False, "converged": False, "top_label": None, "resonance": None,
        "top2_label": None, "top2_resonance": None, "margin": None,
        "expected_label": expected_label, "min_resonance": min_resonance, "min_margin": min_margin,
    }
    if cb.ndim != 2 or cb.shape[0] == 0 or q.size == 0 or cb.shape[1] != q.size:
        return null
    nq = float(np.linalg.norm(q))
    if nq == 0.0:
        return null

    # cosine of phase interference against every atom (same formula as fhrr_core.cleanup)
    row_norms = np.linalg.norm(cb, axis=1)
    sims = (cb @ np.conj(q)).real / (row_norms * nq + 1e-12)

    order = np.argsort(sims)[::-1]
    i1 = int(order[0])
    top1 = float(sims[i1])
    if sims.size > 1:
        i2 = int(order[1])
        top2 = float(sims[i2])
        top2_label = labels[i2]
    else:
        top2 = -1.0
        top2_label = None
    margin = max(0.0, top1 - top2)
    top_label = labels[i1]

    converged = margin >= min_margin
    accepted = bool(converged and top1 >= min_resonance
                    and (expected_label is None or top_label == expected_label))
    return {
        "accepted": accepted,
        "converged": bool(converged),
        "top_label": top_label,
        "resonance": top1,
        "top2_label": top2_label,
        "top2_resonance": top2,
        "margin": float(margin),
        "expected_label": expected_label,
        "min_resonance": min_resonance,
        "min_margin": min_margin,
    }
