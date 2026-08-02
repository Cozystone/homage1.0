# -*- coding: utf-8 -*-
"""The turbovec light-vector codec: field <-> light vector round trip + compression."""
from __future__ import annotations

import numpy as np

from packages.splatra_worldmodel.forward_model import DynamicsParams, simulate_episode
from packages.splatra_worldmodel.turbovec_field import (
    DEFAULT_FIELD_BITS,
    FIELD_NAMES,
    FieldState,
    TurbovecFieldCodec,
)


def _states(n_eps: int = 3, steps: int = 12):
    d = DynamicsParams(count=200)
    out = []
    for i in range(n_eps):
        ep = simulate_episode(d, steps=steps, seed=100 + i,
                              init_offset=np.zeros(3), init_vel=np.zeros(3))
        out.extend(ep.states)
    return out


def test_field_names_and_bits():
    assert FIELD_NAMES == ("x", "y", "z", "vx", "vy", "vz")
    assert set(DEFAULT_FIELD_BITS) == set(FIELD_NAMES)


def test_light_vector_dim_and_compression():
    states = _states()
    codec = TurbovecFieldCodec.fit(states)
    n = states[0].n
    assert codec.light_vector_dim(n) == n * 6
    # 3*10 + 3*8 = 54 bits/particle vs float32 6*4*8=192 bits -> ~3.56x
    assert 3.0 < codec.compression_ratio < 4.0


def test_round_trip_preserves_positions():
    states = _states()
    codec = TurbovecFieldCodec.fit(states)
    st = states[5]
    light = codec.encode(st)
    back = codec.decode(light, st.n)
    assert back.pos.shape == st.pos.shape
    assert back.vel.shape == st.vel.shape
    # positions round-trip tightly (10-bit position codebook over a ~4-unit box)
    pos_err = float(np.linalg.norm(st.pos - back.pos, axis=1).mean())
    assert pos_err < 0.02


def test_light_vector_is_particle_contiguous():
    states = _states()
    codec = TurbovecFieldCodec.fit(states)
    st = states[3]
    light = codec.encode(st)
    # first 6 entries are particle 0's (x,y,z,vx,vy,vz) -> position matches within distortion
    assert abs(light[0] - st.pos[0, 0]) < 0.05
    assert abs(light[1] - st.pos[0, 1]) < 0.05
    assert abs(light[2] - st.pos[0, 2]) < 0.05


def test_pooled_distortion_is_bounded():
    states = _states()
    codec = TurbovecFieldCodec.fit(states)
    dist = codec.distortion_pooled(states)
    # normalized RMSE well below 1 for every field (calibrated Lloyd-Max)
    for f in FIELD_NAMES:
        assert dist[f] < 0.2, (f, dist[f])


def test_fieldstate_helpers():
    st = FieldState(pos=np.zeros((5, 3)), vel=np.ones((5, 3)))
    assert st.n == 5
    cols = st.columns()
    assert set(cols) == set(FIELD_NAMES)
    assert np.allclose(cols["vx"], 1.0)
    assert st.copy().pos is not st.pos
