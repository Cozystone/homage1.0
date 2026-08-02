from __future__ import annotations

from rhfc.hypervector import bundle, cosine_similarity, permute, random_bipolar, random_complex


def test_random_bipolar_is_deterministic() -> None:
    a = random_bipolar(256, seed=7)
    b = random_bipolar(256, seed=7)
    assert a.dim == 256
    assert cosine_similarity(a, b) == 1.0


def test_bundle_preserves_dimension_and_kind() -> None:
    vectors = [random_bipolar(512, seed=i) for i in range(4)]
    bundled = bundle(vectors)
    assert bundled.dim == 512
    assert bundled.kind == "bipolar"


def test_permute_is_reversible_by_inverse_shift() -> None:
    vector = random_complex(128, seed=3)
    restored = permute(permute(vector, 13), -13)
    assert cosine_similarity(vector, restored) > 0.999
