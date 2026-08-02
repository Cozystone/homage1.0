"""Golden tests for the M4 scene-grounding extractor.

Locks the ATANOR philosophy: a particle scene is eligible ONLY when the verified
evidence is concrete (a placeable entity that physically moves). Abstract
definitions and method descriptions stay text-only (eligible=False).
"""

from __future__ import annotations

from packages.base_brain.scene_grounding import extract_scene_grounding


def test_concrete_motion_event_is_eligible() -> None:
    g = extract_scene_grounding("An apple fell from the tree toward Newton.")
    assert g["eligible"] is True
    assert g["basis"] == "concrete_entity_with_motion"
    ents = [e.lower() for e in g["entities"]]
    assert "apple" in ents
    assert "tree" in ents
    assert "Newton" in g["entities"]  # proper noun preserved
    assert "fell" in g["motion"]


def test_abstract_definition_is_not_eligible() -> None:
    g = extract_scene_grounding("Gravity is the attraction between masses.")
    assert g["eligible"] is False
    # 'between' inside a definition must not be treated as a placeable scene.
    assert g["basis"] != "concrete_entity_with_motion"


def test_method_description_is_not_eligible() -> None:
    answer = (
        "GraphRAG retrieves facts through graph relationships and evidence paths "
        "before composing an answer. It requires a semantic graph and is used for "
        "hallucination reduction."
    )
    g = extract_scene_grounding(answer)
    assert g["eligible"] is False  # 'retrieves'/'uses'/'requires' are not motion


def test_atanor_self_description_is_not_eligible() -> None:
    answer = (
        "ATANOR is a local-first knowledge engine that separates semantic reasoning "
        "from surface expression. It uses a semantic graph and a surface graph."
    )
    g = extract_scene_grounding(answer)
    assert g["eligible"] is False


def test_non_english_defers() -> None:
    g = extract_scene_grounding("사과가 나무에서 떨어졌다.", language="ko")
    assert g["eligible"] is False
    assert g["basis"] == "non_english_extractor_pending"


def test_evidence_sentences_are_considered() -> None:
    g = extract_scene_grounding(
        "Here is what happened.",
        evidence_sentences=["The ball rolled down the ramp and bounced off the wall."],
    )
    assert g["eligible"] is True
    assert any(v in g["motion"] for v in ("rolled", "bounced"))


def test_output_shape_is_stable() -> None:
    g = extract_scene_grounding("It uses a semantic graph.")
    assert set(g.keys()) == {"eligible", "basis", "entities", "spatial", "motion"}
    assert isinstance(g["entities"], list)
    assert isinstance(g["eligible"], bool)
