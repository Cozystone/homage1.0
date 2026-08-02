from __future__ import annotations

from rhfc.fft_binding import make_unitary_key
from rhfc.hypervector import cosine_similarity, random_bipolar
from rhfc.pipeline import bind_and_store, bind_value_with_keys, query_and_cleanup, unbind_value_with_keys


def test_multibind_unitary_keys_preserve_source_without_cleanup() -> None:
    value = random_bipolar(2048, seed=100)
    keys = [make_unitary_key(2048, seed=200 + i) for i in range(4)]
    recovered = unbind_value_with_keys(bind_value_with_keys(value, keys), keys)
    assert cosine_similarity(value, recovered) > 0.999


def test_multibind_cleanup_pipeline_returns_target_candidate() -> None:
    candidates = [random_bipolar(2048, seed=300 + i) for i in range(128)]
    target_index = 17
    keys = [make_unitary_key(2048, seed=500 + i) for i in range(3)]
    store = bind_and_store(candidates[target_index], keys, candidates)
    result = query_and_cleanup(store.composite, store.keys, store.memory, target=candidates[target_index])
    assert result.nearest_index == target_index
    assert result.target_cosine is not None
    assert result.target_cosine > 0.99
