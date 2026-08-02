from packages.base_brain.models import SemanticConcept, SemanticRelation, SurfaceConstruction, honesty_flags


def test_base_models_to_dict() -> None:
    relation = SemanticRelation(source="a", relation="is_a", target="b")
    concept = SemanticConcept(
        concept_id="a",
        canonical_name="A",
        aliases=["alpha"],
        short_description="A concept.",
        relations=[relation],
    )
    construction = SurfaceConstruction(
        construction_id="direct_definition_en",
        language="en",
        function="definition",
        abstract_shape="X is Y.",
        allowed_discourse_moves=["direct_answer"],
        tone="clear",
        audience_level="beginner",
        slot_types=["concept"],
        prior_weight=0.8,
        avoid_repetition_group="definition",
    )
    assert concept.to_dict()["relations"][0]["relation"] == "is_a"
    assert construction.to_dict()["language"] == "en"
    assert honesty_flags()["external_llm_used"] is False
