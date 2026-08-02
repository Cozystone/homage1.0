from __future__ import annotations

from cgsr.english.construction_patterns import core_english_frames, frame_by_family


def test_core_frames_have_valid_templates() -> None:
    frames = core_english_frames()
    assert {frame.family for frame in frames} >= {
        "definition",
        "comparison",
        "procedure",
        "limitation",
        "evidence_based_claim",
        "abstention",
    }
    for frame in frames:
        frame.validate()
        assert frame.semantic_constraints["external_llm_reasoning"] is False


def test_definition_frame_fills_required_slots() -> None:
    frame = frame_by_family("definition")
    assert frame.required_slots == ["x", "category", "y"]
    assert "{x}" in frame.surface_template
