# -*- coding: utf-8 -*-
"""Gate (a): FHRR bind/unbind roundtrip + cleanup correctness (the reused algebra + the new ring)."""
import numpy as np

from packages.vsa_reasoning.fhrr_core import (
    RingCodebook, bind, unbind, superpose, resonance, cleanup, atom,
)


def test_bind_unbind_roundtrip_is_exact():
    a, b = atom("role"), atom("filler")
    c = bind(a, b)
    rec = unbind(c, a)
    assert resonance(rec, b) > 0.999          # unbind inverts bind (phase subtraction)
    assert abs(resonance(a, b)) < 0.1          # distinct atoms are near-orthogonal


def test_superpose_then_unbind_retrieves_a_bound_pair():
    # a key-value bundle: bind two (role, filler) pairs, superpose, unbind one role back to its filler
    r1, f1 = atom("k1"), atom("v1")
    r2, f2 = atom("k2"), atom("v2")
    bundle = superpose(bind(r1, f1), bind(r2, f2))
    got1 = unbind(bundle, r1)
    # the retrieved vector is closest to f1 among the stored fillers (crosstalk-tolerant)
    cb = np.stack([f1, f2])
    label, _ = cleanup(got1, cb, ["v1", "v2"])
    assert label == "v1"


def test_cleanup_nearest_atom_exact_and_noisy():
    cb = RingCodebook(10, dim=2048, seed=7, tag="color")
    # exact
    val, res = cb.decode(cb.encode(7))
    assert val == 7 and res > 0.999
    # noisy: a perturbed atom still snaps to the right symbol
    rng = np.random.default_rng(0)
    noise = np.exp(1j * rng.uniform(0, 2 * np.pi, 2048))
    q = cb.encode(4) + 0.25 * noise
    val, _ = cb.decode(q)
    assert val == 4


def test_ring_periodicity_and_shift_composition():
    cb = RingCodebook(10, dim=2048, seed=7, tag="color")
    # exact periodicity mod M
    assert resonance(cb.encode(3), cb.encode(13)) > 0.999
    # the shift vector composes: T_k ⊛ φ(c) == φ(c+k) for EVERY c (the generalization property)
    for c in range(10):
        q = bind(cb.shift_vector(3), cb.encode(c))
        assert resonance(q, cb.encode((c + 3) % 10)) > 0.999


def test_distinct_ring_atoms_are_separable():
    cb = RingCodebook(10, dim=2048, seed=7, tag="color")
    off_diag = [resonance(cb.encode(i), cb.encode(j))
                for i in range(10) for j in range(10) if i != j]
    assert max(abs(x) for x in off_diag) < 0.2      # clean-up memory is well-conditioned
