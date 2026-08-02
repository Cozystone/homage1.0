# -*- coding: utf-8 -*-
"""Delexicalization + copy gate: the skeleton holds no entity, and a slot is filled ONLY from the
grounding — an entity absent from the grounding is never invented (abstain / copy-empty)."""
from packages.fluency.delex import (
    Grounding,
    copy_fill,
    delexicalize,
    realize_reduced,
)


def test_delex_separates_skeleton_from_slots():
    plans = delexicalize([["Einstein", "is_a", "physicist"]])
    assert len(plans) == 1
    plan = plans[0]
    # the REGISTER SKELETON carries function words + typed placeholders and ZERO entities
    assert plan.skeleton() == "[SUBJ] is [DET] [OBJ]"
    assert "Einstein" not in plan.skeleton() and "physicist" not in plan.skeleton()
    # the entities live in the SLOTS, copied from the bone
    content = {s.role: s.value for s in plan.content_slots()}
    assert content["SUBJ"] == "Einstein" and content["OBJ"] == "physicist"


def test_skeleton_is_entity_free_for_every_relation():
    bones = [["water", "made_of", "hydrogen"], ["bee", "capable_of", "fly"],
             ["rose", "has_property", "fragrant"], ["x", "unknown_rel", "y"]]
    for plan in delexicalize(bones):
        skel = plan.skeleton().lower()
        for entity in (plan.subject.lower(),) + tuple(
                s.value.lower() for s in plan.content_slots() if s.role == "OBJ"):
            if entity and entity != plan.relation.replace("_", " "):
                assert entity not in skel, (plan.relation, entity, skel)


def test_copy_fill_uses_grounding_only():
    plan = delexicalize([["Einstein", "is_a", "physicist"]])[0]
    grounding = Grounding.from_bones([["Einstein", "is_a", "physicist"]])
    assert copy_fill(plan, grounding) == "Einstein is a physicist"


def test_copy_gate_abstains_on_ungrounded_entity():
    """The core anti-memorization contract: a slot whose value is not in the grounding is dropped,
    the clause abstains, and the ungrounded string never appears — it is never invented."""
    plan = delexicalize([["Einstein", "is_a", "physicist"]])[0]
    restricted = Grounding()
    restricted.add("Einstein")                     # subject grounded, object 'physicist' is NOT
    out = copy_fill(plan, restricted)
    assert out == ""                               # abstains rather than inventing
    assert "physicist" not in out


def test_copy_gate_abstains_on_ungrounded_subject():
    plan = delexicalize([["Xanadu", "located_in", "Mongolia"]])[0]
    grounding = Grounding()
    grounding.add("Mongolia")                      # object grounded, subject 'Xanadu' is NOT
    assert copy_fill(plan, grounding) == ""
    assert realize_reduced(plan, grounding) == "located in Mongolia"  # reduced gate uses the OBJECT


def test_grounding_accepts_realizer_morphology():
    """Plural (bird->birds) and demonym case (german->German) the morphology floor produces are
    accepted as grounded; a genuinely new word is not."""
    g = Grounding.from_bones([["penguins", "is_a", "bird"], ["x", "has_property", "german"]])
    assert g.has("birds") and g.has("German")
    assert not g.has("cheese")


def test_degenerate_bones_make_no_plan():
    assert delexicalize([]) == []
    assert delexicalize([["", "is_a", ""]]) == []
    assert delexicalize([["Fairy tale", "alias", "fairy tale"]]) == []   # self-alias says nothing


def test_pronoun_and_drop_do_not_invent():
    """A subject_ref override (pronoun, or "" to drop it in a conjunction) is a function word, not a
    content copy — it changes surface without touching the copy gate."""
    plan = delexicalize([["penguins", "capable_of", "swim"]])[0]
    g = Grounding.from_bones([["penguins", "capable_of", "swim"]])
    assert copy_fill(plan, g, subject_ref="they", agree_plural=True) == "they can swim"
    assert copy_fill(plan, g, subject_ref="") == "can swim"
