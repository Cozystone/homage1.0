from __future__ import annotations

import numpy as np

from rhfc.anneal_select import anneal_select, qubo_energy


def test_anneal_select_prefers_compatible_negative_diagonal_subset() -> None:
    candidates = ["a", "b", "c"]
    q = np.array(
        [
            [-2.0, -0.4, 2.5],
            [-0.4, -2.0, 2.5],
            [2.5, 2.5, -0.3],
        ]
    )
    result = anneal_select(candidates, q, iterations=1500, seed=3)
    assert set(result.selected) == {0, 1}
    assert result.energy <= qubo_energy(np.array([1, 0, 0]), q)


def test_anneal_select_rejects_bad_matrix_shape() -> None:
    try:
        anneal_select(["a", "b"], np.eye(3))
    except ValueError as exc:
        assert "square" in str(exc)
    else:
        raise AssertionError("expected ValueError")
