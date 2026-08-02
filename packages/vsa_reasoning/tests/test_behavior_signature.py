# -*- coding: utf-8 -*-
"""Gate (d): holographic behaviour-signature ranking genuinely discriminates (not noise).

Encode each primitive's behaviour on the spec's probe inputs as one FHRR signature; rank by phasor
resonance to the spec signature. The TRUE primitive (the one that generated the spec) must rank top
far above the random baseline, and its resonance must exceed the best distractor's by a clear margin.
"""
import random

from packages.vsa_reasoning.behavior_signature import (
    rank_candidates, spec_signature, behavior_signature,
)
from packages.vsa_reasoning.fhrr_core import resonance


# a small library of grid→grid ARC-style primitives
def identity(g):  return [r[:] for r in g]
def flip_h(g):    return [list(reversed(r)) for r in g]
def flip_v(g):    return [r[:] for r in reversed(g)]
def transpose(g): return [list(r) for r in zip(*g)]
def rot90(g):     return [list(r) for r in zip(*g[::-1])]
def rot180(g):    return [list(reversed(r)) for r in reversed(g)]
def rot270(g):    return [list(r) for r in zip(*g)][::-1]
def swap_1_2(g):  return [[{1: 2, 2: 1}.get(v, v) for v in r] for r in g]

LIBRARY = {
    "identity": identity, "flip_h": flip_h, "flip_v": flip_v, "transpose": transpose,
    "rot90": rot90, "rot180": rot180, "rot270": rot270, "swap_1_2": swap_1_2,
}


def _rand_grid(rng):
    R, C = rng.randint(2, 4), rng.randint(2, 4)
    return [[rng.randint(0, 4) for _ in range(C)] for _ in range(R)]


def test_true_primitive_ranks_top_far_above_random():
    rng = random.Random(20260723)
    trials = 60
    top1 = 0
    winners_include_true = 0
    for _ in range(trials):
        true_name = rng.choice(list(LIBRARY))
        true_fn = LIBRARY[true_name]
        examples = [(g, true_fn(g)) for g in (_rand_grid(rng) for _ in range(4))]
        ranked = rank_candidates(examples, LIBRARY)
        if ranked[0][0] == true_name:
            top1 += 1
        # tolerate genuine ties (e.g. a symmetric probe makes two primitives behave identically):
        # the true primitive must at least be AMONG the top-scoring winners
        top_score = ranked[0][1]
        if any(lbl == true_name and abs(sc - top_score) < 1e-6 for lbl, sc in ranked):
            winners_include_true += 1

    baseline = trials / len(LIBRARY)          # random top-1 expectation
    assert top1 >= 0.9 * trials, f"top-1 {top1}/{trials} not far above random {baseline:.1f}"
    assert winners_include_true == trials      # never ranks the true primitive below a distractor
    assert top1 > 4 * baseline                 # decisively beats chance


def test_exact_match_gives_resonance_near_one_and_clear_margin():
    grids = [[[1, 2, 0], [0, 3, 4]], [[5, 0], [0, 6], [7, 8]]]
    examples = [(g, rot180(g)) for g in grids]
    ranked = rank_candidates(examples, LIBRARY)
    # rot180 is exact -> resonance ~1.0; the runner-up is clearly lower (real discrimination)
    assert ranked[0][0] == "rot180"
    assert ranked[0][1] > 0.99
    assert ranked[0][1] - ranked[1][1] > 0.2


def test_rank_candidates_accepts_list_and_dict():
    examples = [([[1, 2]], flip_h([[1, 2]]))]
    as_list = rank_candidates(examples, [identity, flip_h, transpose])
    as_dict = rank_candidates(examples, {"identity": identity, "flip_h": flip_h})
    assert as_list[0][0] == "flip_h"
    assert as_dict[0][0] == "flip_h"
    # returns (label, score) pairs sorted descending
    scores = [s for _, s in as_list]
    assert scores == sorted(scores, reverse=True)


def test_signature_is_fixed_dimension_regardless_of_probe_count():
    a = spec_signature([([[1]], [[2]])])
    b = spec_signature([([[1]], [[2]])] * 25)
    assert a.shape == b.shape                  # holographic hash: fixed size, many probes
    # a primitive matching the spec on all probes resonates ~1 with it
    sig = behavior_signature(lambda g: [[v + 1 for v in r] for r in g], [[[1]]])
    assert resonance(spec_signature([([[1]], [[2]])]), sig) > 0.99
