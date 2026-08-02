# -*- coding: utf-8 -*-
"""World-state organs: location/possession/spatial/kind/motive state built from verb frames.
These are the organs the first external exam exposed as missing; each test is one organ."""
from packages.situation_model.builder import build
from packages.situation_model.reasoner import answer


def _ans(text, q):
    return answer(q, build(text))


def test_location_tracking_and_yesno():
    t = "Mary moved to the bathroom. John went to the hallway. Mary journeyed to the garden."
    assert _ans(t, "Where is Mary?")["answer"] == "garden"
    assert _ans(t, "Is John in the hallway?")["answer"] == "yes"
    assert _ans(t, "Is John in the garden?")["answer"] == "no"


def test_possession_follows_holder_and_counts():
    t = ("Daniel went to the kitchen. Daniel picked up the apple. Daniel took the milk. "
         "Daniel journeyed to the office. Daniel dropped the milk.")
    assert _ans(t, "Where is the apple?")["answer"] == "office"     # held -> holder's location
    assert _ans(t, "Where is the milk?")["answer"] == "office"      # released where dropped
    assert _ans(t, "How many objects is Daniel holding?")["answer"] == "one"
    assert _ans(t, "What is Daniel holding?")["answer"] == "apple"


def test_before_uses_most_recent_stay():
    t = ("Mary got the football. Mary moved to the office. Mary went to the bathroom. "
         "Mary journeyed to the office. Mary went to the garden.")
    # football was in office(2nd stay) before garden; 'before the office' = before the LAST stay
    assert _ans(t, "Where was the football before the garden?")["answer"] == "office"
    assert _ans(t, "Where was the football before the office?")["answer"] == "bathroom"


def test_negation_disjunction_and_maybe():
    t = "Daniel is no longer in the bathroom. Julie is either in the school or the park."
    assert _ans(t, "Is Daniel in the bathroom?")["answer"] == "no"
    assert _ans(t, "Is Julie in the school?")["answer"] == "maybe"
    assert _ans(t, "Is Julie in the office?")["answer"] == "no"


def test_pronoun_and_group_coref():
    t = ("Mary and Daniel travelled to the office. After that they went to the bathroom. "
         "Then Daniel journeyed to the garden. Afterwards he moved to the kitchen.")
    assert _ans(t, "Where is Daniel?")["answer"] == "kitchen"
    assert _ans(t, "Where is Mary?")["answer"] == "bathroom"


def test_spatial_direct_inverse_and_composed_yesno():
    t = "The office is east of the hallway. The kitchen is north of the office."
    assert _ans(t, "What is north of the office?")["answer"] == "kitchen"
    assert _ans(t, "What is the office east of?")["answer"] == "hallway"
    assert _ans(t, "How do you go from the hallway to the kitchen?")["answer"] == "e,n"


def test_positional_abstains_across_components_never_guesses():
    # two DISCONNECTED spatial groups: answering would be fabrication -> must abstain
    t = "The triangle is above the square. The circle is to the left of the star."
    out = _ans(t, "Is the triangle above the circle?")
    assert out["answer"] is None
    # 'above' without 'of' (bare complement) must still parse as spatial, not as an adjective
    t2 = "The triangle is above the pink rectangle. The blue square is to the left of the triangle."
    assert _ans(t2, "Is the blue square below the pink rectangle?")["answer"] == "no"


def test_kind_inheritance_and_peer_induction_is_hedged():
    t = "Mice are afraid of wolves. Gertrude is a mouse. Lily is a swan. Lily is white. Bernhard is a swan."
    assert _ans(t, "What is Gertrude afraid of?")["answer"] == "wolf"
    out = _ans(t, "What color is Bernhard?")
    assert out["answer"] == "white" and out.get("induced") is True   # epistemic hedge carried


def test_size_transitive_closure():
    t = "The box is bigger than the chocolate. The chest is bigger than the box."
    assert _ans(t, "Is the chest bigger than the chocolate?")["answer"] == "yes"
    assert _ans(t, "Does the chest fit in the chocolate?")["answer"] == "no"


def test_motive_from_state_and_left_of_does_not_collide_with_release():
    t = "Sumit is tired. Sumit went back to the bedroom. Sumit grabbed the pajamas there."
    assert _ans(t, "Why did Sumit go to the bedroom?")["answer"] == "tired"
    assert _ans(t, "Why did Sumit get the pajamas?")["answer"] == "tired"
    # 'to the left of' must be a spatial statement, not a 'left the object' release
    sit = build("The blue square is to the left of the triangle.")
    assert sit.state.w.spatial_edges and not sit.state.w.obj_at
