# -*- coding: utf-8 -*-
"""Sealed gates for the X1 compression-progress drive (owner 2026-07-23;
docs/ATANOR_intelligence_explosion_research.md). Deterministic fixtures, no randomness.

Gate (a) SIGNAL SHAPE — on KNOWN trivial / mid-frontier / noise candidates the drive ranks the
                        mid-frontier highest and trivial + noise near zero, and the two rejections
                        come from the two DIFFERENT factors (Schmidhuber: reject already-learned AND
                        reject unlearnable/noise).
Gate (c) API          — interestingness() is standalone-callable (the CO-reusable value signal) and
                        yields the same ranking; rank()/most_interesting() agree.
Gate (d) SAFETY       — no fabrication (degenerate inputs score 0, never invent), interpreted trees are
                        never exec'd (pure structural computation), and scoring is side-effect free.
"""
from __future__ import annotations

import random

from packages.evolution import compression_progress as cp

# ---------------------------------------------------------------------------
# The KNOWN fixture (family 'ab' grammar). The (x*x)+5 motif is present once, on `a`.
#   trivial      = an EXACT known block          -> LOW novelty (already cheaply solvable)
#   mid-frontier = (b*b)+5, a NOVEL function that SHARES the (x*x)+5 motif -> learnable-but-not-learned
#   noise        = structurally alien recombination -> HIGH novelty but ZERO learnable structure
# ---------------------------------------------------------------------------
_BLOCK_SQ_A = ("op", "+", ("op", "*", ("var", "a"), ("var", "a")), ("const", 5))   # (a*a)+5
_BLOCK_ADD = ("op", "+", ("var", "a"), ("var", "b"))                               # a+b
_BLOCK_MAX = ("if", ("cmp", ">", ("var", "a"), ("var", "b")), ("var", "a"), ("var", "b"))
_LIBRARY = [_BLOCK_SQ_A, _BLOCK_ADD, _BLOCK_MAX]

_TRIVIAL = _BLOCK_SQ_A                                                              # exact known block
_MID = ("op", "+", ("op", "*", ("var", "b"), ("var", "b")), ("const", 5))          # (b*b)+5
_NOISE = ("op", "-", ("op", "%", ("var", "a"), ("const", 3)),
                     ("op", "//", ("var", "b"), ("const", 2)))                      # alien structure


def test_gate_a_signal_shape_mid_frontier_ranks_highest():
    """The drive ranks the mid-frontier strictly highest; trivial and noise are near zero."""
    s_triv = cp.compression_progress(_TRIVIAL, _LIBRARY)
    s_mid = cp.compression_progress(_MID, _LIBRARY)
    s_noise = cp.compression_progress(_NOISE, _LIBRARY)

    assert s_mid > s_triv and s_mid > s_noise           # mid-frontier is the peak
    assert s_triv < 0.1 and s_noise < 0.1               # trivial + noise near zero
    assert s_mid > 3 * max(s_triv, s_noise)             # a decisive, not marginal, separation
    # explicit ordering of the full ranking
    order = [t for _s, t in cp.rank([_TRIVIAL, _MID, _NOISE], {"library": _LIBRARY})]
    assert order[0] == _MID


def test_gate_a_two_rejections_come_from_different_factors():
    """Schmidhuber's core property: BOTH extremes are rejected, but for DIFFERENT reasons — trivial by
    the not-yet-learned (novelty) factor, noise by the learnable (compressible-structure) factor. A
    single novelty heuristic would (wrongly) rank NOISE highest; the learnable factor is what stops it."""
    b_triv = cp.progress_breakdown(_TRIVIAL, _LIBRARY)
    b_mid = cp.progress_breakdown(_MID, _LIBRARY)
    b_noise = cp.progress_breakdown(_NOISE, _LIBRARY)

    # trivial: rejected by LOW novelty (already cheaply expressible), not by lack of structure
    assert b_triv["novelty_under_compressor"] < 0.5
    # noise: MAXIMALLY novel yet rejected because it unlocks NO learnable abstraction
    assert b_noise["novelty_under_compressor"] > 0.9
    assert b_noise["learnable_abstraction"] < 1e-9
    # mid-frontier: both factors genuinely positive — learnable AND not-yet-learned
    assert b_mid["novelty_under_compressor"] > 0.9
    assert b_mid["learnable_abstraction"] > 0.2
    # the distributional MDL corroborates: only the mid-frontier unlocks compression of the family
    assert b_mid["distributional_gain"] > 0
    assert b_triv["distributional_gain"] == 0 and b_noise["distributional_gain"] == 0


def test_gate_a_noise_would_win_a_pure_novelty_heuristic():
    """Concretely: rank by novelty ALONE and noise ties for the top; the compression-progress drive
    demotes it to the bottom. This is the whole reason the signal is a PRODUCT, not novelty."""
    by_novelty = sorted(
        [_TRIVIAL, _MID, _NOISE],
        key=lambda t: -cp.novelty_under_compressor(t, frozenset(cp._freeze(b) for b in _LIBRARY)),
    )
    assert _NOISE in by_novelty[:2]                     # novelty alone rates noise at/near the top
    by_progress = [t for _s, t in cp.rank([_TRIVIAL, _MID, _NOISE], {"library": _LIBRARY})]
    assert by_progress[-1] in (_TRIVIAL, _NOISE) and by_progress[0] == _MID


def test_gate_c_interestingness_standalone_and_same_ranking():
    """interestingness() is callable standalone with a lightweight compressor (the CO-reusable form) and
    returns exactly the compression_progress score — the same ranking as the internal computation."""
    state = {"library": _LIBRARY, "templates": []}
    for t in (_TRIVIAL, _MID, _NOISE):
        assert cp.interestingness(t, state) == cp.compression_progress(t, _LIBRARY)
    # dict-candidate + curriculum-state form resolves the same family and gives the same numbers
    cstate = {"libraries": {"ab": _LIBRARY, "xs": []}, "abstractions": {"ab": [], "xs": []}}
    for t in (_TRIVIAL, _MID, _NOISE):
        assert cp.interestingness({"tree": t, "family": "ab"}, cstate) == cp.compression_progress(t, _LIBRARY)
    assert cp.most_interesting([_TRIVIAL, _MID, _NOISE], state) == _MID


def test_gate_c_signal_is_deterministic():
    """The CO value signal must be stable — identical (candidate, state) always yields the same score."""
    state = {"library": _LIBRARY, "templates": []}
    a = [cp.interestingness(t, state) for t in (_TRIVIAL, _MID, _NOISE)]
    b = [cp.interestingness(t, state) for t in (_TRIVIAL, _MID, _NOISE)]
    assert a == b


def test_gate_d_degenerate_inputs_score_zero_no_fabrication():
    """No fabrication: with nothing to compare against, or nothing there, the signal is 0 — it never
    invents interest. Empty library => no learnable abstraction => 0; None candidate => 0."""
    assert cp.compression_progress(_MID, []) == 0.0                 # no compressor -> nothing learnable
    assert cp.interestingness(None, {"library": _LIBRARY}) == 0.0    # no candidate
    assert cp.interestingness(_MID, {}) == 0.0                       # empty state


def test_gate_d_scoring_is_side_effect_free():
    """Scoring must not mutate the library, the candidate, or leak state between calls."""
    import copy
    lib_before = copy.deepcopy(_LIBRARY)
    cand_before = copy.deepcopy(_MID)
    _ = cp.compression_progress(_MID, _LIBRARY)
    _ = cp.progress_breakdown(_MID, _LIBRARY)
    assert _LIBRARY == lib_before and _MID == cand_before


def test_gate_d_interpreter_never_exec_pure_structural():
    """The drive is pure structural tree computation — it never evaluates, exec's, or compiles a
    candidate (interpreted-never-exec'd discipline). Static check on the module source."""
    import pathlib
    src = pathlib.Path(cp.__file__).read_text(encoding="utf-8")
    for forbidden in ("eval(", "exec(", "compile(", "__import__(", "os.system", "subprocess"):
        assert forbidden not in src, forbidden


# ---------------------------------------------------------------------------
# WIRING — the flag routes target selection through the drive; default off is byte-identical.
# ---------------------------------------------------------------------------
def test_wiring_select_target_picks_highest_interestingness(monkeypatch):
    """With the drive on, _select_target ranks a pool by interestingness and keeps the argmax. Feed a
    controlled pool (trivial, mid, noise, repeating) and assert it returns the mid-frontier."""
    from packages.evolution import auto_curriculum as ac

    cycle = [_TRIVIAL, _NOISE, _MID, _TRIVIAL, _NOISE, _MID, _TRIVIAL, _NOISE]
    box = {"i": 0}

    def fake_compose(library, family, tier, rng, abstractions=()):
        t = cycle[box["i"] % len(cycle)]
        box["i"] += 1
        return t

    monkeypatch.setattr(ac, "compose_target", fake_compose)
    state = {"sigs": {"ab": []}, "libraries": {"ab": _LIBRARY}, "abstractions": {"ab": []}}
    chosen = ac._select_target(_LIBRARY, "ab", 1, random.Random(0), (), state, pool=8)
    assert chosen == _MID                                            # the highest-progress candidate


def test_wiring_known_signature_scores_zero_not_yet_learned(monkeypatch):
    """A candidate whose behavioural signature is ALREADY known scores 0 (no progress from re-learning
    a solved function) — the not-yet-learned half of the drive, enforced at the selection site."""
    from packages.evolution import auto_curriculum as ac

    # pool of ONLY mid-frontier trees, but mark _MID's signature as already known -> must fall back to
    # a non-zero-progress alternative rather than re-picking the solved function.
    alt = ("op", "+", ("op", "*", ("var", "a"), ("var", "a")), ("const", 7))       # (a*a)+7, novel+learnable
    cycle = [_MID, alt, _MID, alt, _MID, alt, _MID, alt]
    box = {"i": 0}

    def fake_compose(library, family, tier, rng, abstractions=()):
        t = cycle[box["i"] % len(cycle)]
        box["i"] += 1
        return t

    monkeypatch.setattr(ac, "compose_target", fake_compose)
    known_sig = ac.signature(_MID, "ab")
    state = {"sigs": {"ab": [known_sig]}, "libraries": {"ab": _LIBRARY}, "abstractions": {"ab": []}}
    chosen = ac._select_target(_LIBRARY, "ab", 1, random.Random(0), (), state, pool=8)
    assert chosen == alt                                            # not the already-known _MID


def test_wiring_default_off_uses_baseline_compose(monkeypatch):
    """Default (flag unset) must NOT route through the drive — the baseline blind compose is used, so
    the A/B is clean and the committed curriculum behaviour is unchanged."""
    from packages.evolution import auto_curriculum as ac

    monkeypatch.delenv("ATANOR_COMPRESSION_DRIVE", raising=False)
    assert ac._drive_on() is False
    monkeypatch.setenv("ATANOR_COMPRESSION_DRIVE", "1")
    assert ac._drive_on() is True
    monkeypatch.setenv("ATANOR_COMPRESSION_DRIVE", "0")
    assert ac._drive_on() is False
