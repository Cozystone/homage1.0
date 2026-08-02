from __future__ import annotations

from packages.surface_brain.q_cortex_bridge import select_surface_candidates


def test_q_cortex_bridge_falls_back_safely_for_empty_candidates(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = select_surface_candidates([], max_selected=3)

    assert result["q_cortex_used"] is False
    assert result["selected"] == []
    assert result["honesty"]["local_brain_write"] is False


def test_q_cortex_bridge_selects_candidates_without_external_models(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = select_surface_candidates(
        [
            {"construction_id": "definition.simple", "fit_score": 0.9, "style_score": 0.8, "language_score": 0.9},
            {"construction_id": "summary.compact", "fit_score": 0.7, "style_score": 0.7, "language_score": 0.8},
        ],
        max_selected=1,
    )

    assert len(result["selected"]) <= 1
    assert result["honesty"]["external_llm_used"] is False
    assert result["honesty"]["real_quantum_hardware_used"] is False

