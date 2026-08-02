from __future__ import annotations

from rhfc.resonator import compose_role_filler_pairs, factorize_role_filler_pairs
from rhfc.hypervector import random_bipolar


def test_resonator_recovers_two_role_filler_pairs() -> None:
    roles = {f"role{i}": random_bipolar(4096, seed=100 + i) for i in range(3)}
    fillers = {f"item{i}": random_bipolar(4096, seed=200 + i) for i in range(5)}
    expected = [("role0", "item1"), ("role2", "item4")]
    composite = compose_role_filler_pairs([(roles[r], fillers[f]) for r, f in expected])
    recovered = factorize_role_filler_pairs(composite, roles, fillers, threshold=0.16)
    pairs = {(item.role, item.filler) for item in recovered}
    assert ("role0", "item1") in pairs
    assert ("role2", "item4") in pairs


def test_resonator_empty_inputs_return_empty() -> None:
    composite = random_bipolar(256, seed=1)
    assert factorize_role_filler_pairs(composite, {}, {}) == []
