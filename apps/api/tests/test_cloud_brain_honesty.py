from __future__ import annotations

from app.routers.cloud_brain import _classify_graph_nodes, _is_synthetic_proof_label


def test_synthetic_proof_labels_are_flagged():
    for label in (
        "AtanorSeedConcept012983",
        "resonance validation sector 001631",
        "surface planning sector 001578",
        "graph accumulation sector 001779",
        "a3f9c1d2e4b5a6c7d8e9f0a1b2c3d4e5",  # hex hash
        "",
    ):
        assert _is_synthetic_proof_label(label), label


def test_real_knowledge_labels_are_not_flagged():
    for label in ("Eiffel Tower", "Privacy Principles", "GitHub - fishaudio/fish-speech", "Marie Curie", "Docker"):
        assert not _is_synthetic_proof_label(label), label


def test_classify_graph_nodes_breakdown():
    nodes = [
        {"label": "Eiffel Tower"},
        {"label": "Marie Curie"},
        {"label": "AtanorSeedConcept001"},
        {"label": "resonance validation sector 000123"},
    ]
    out = _classify_graph_nodes(nodes)
    assert out["sample_size"] == 4
    assert out["real_knowledge"] == 2
    assert out["synthetic_proof"] == 2
    assert out["synthetic_ratio"] == 0.5


def test_extraction_noise_is_separated_from_real_knowledge():
    from app.routers.cloud_brain import _is_noise_label, _classify_graph_nodes
    for noise in ("Apr", "May", "be", "It", "days", "the", "a"):
        assert _is_noise_label(noise), noise
    for real in ("Eiffel Tower", "Marie Curie", "Photosynthesis"):
        assert not _is_noise_label(real), real
    out = _classify_graph_nodes([
        {"label": "Eiffel Tower"}, {"label": "Apr"}, {"label": "be"},
        {"label": "AtanorSeedConcept001"},
    ])
    assert out["real_knowledge"] == 1
    assert out["extraction_noise"] == 2
    assert out["synthetic_proof"] == 1
