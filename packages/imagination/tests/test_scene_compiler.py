# -*- coding: utf-8 -*-
"""The imagination compiler must lay a thought out legibly and move each relation by its kind."""
from packages.imagination.scene_compiler import compile_scene


def _concepts():
    return [
        {"id": "c_water", "label": "물", "type": "liquid", "weight": 1.0},
        {"id": "c_boil", "label": "끓음", "type": "process", "weight": 0.4},
        {"id": "c_steam", "label": "수증기", "type": "gas", "weight": 0.3},
    ]


def test_empty_thought_is_empty_scene():
    s = compile_scene([], [])
    assert s["objects"] == [] and s["motion"] == [] and s["meta"]["empty"] is True


def test_subject_is_centered_and_heaviest_by_default():
    s = compile_scene(_concepts(), [])
    assert s["meta"]["subject"] == "c_water"                     # heaviest weight
    subj = next(o for o in s["objects"] if o["id"] == "c_water")
    assert subj["pos"] == [0.0, 0.0, 0.0] and subj["role"] == "subject"
    # satellites sit off-origin
    assert all(o["pos"] != [0.0, 0.0, 0.0] for o in s["objects"] if o["id"] != "c_water")


def test_archetype_from_type_not_a_name_table():
    s = compile_scene(_concepts(), [])
    by = {o["id"]: o["archetype"] for o in s["objects"]}
    assert by["c_water"] == "blob"        # liquid
    assert by["c_boil"] == "swirl"        # process
    assert by["c_steam"] == "blob"        # gas


def test_relation_kind_selects_motion():
    rels = [
        {"from": "c_water", "to": "c_steam", "predicate": "끓어서 되다"},   # transform
        {"from": "c_boil", "to": "c_steam", "predicate": "유발한다"},        # causal
        {"from": "c_steam", "to": "c_water", "predicate": "is_a"},            # structural
        {"from": "c_water", "to": "c_boil", "predicate": "관련"},            # link (fallback)
    ]
    s = compile_scene(_concepts(), rels)
    actions = {(m.get("from"), m.get("to")): m["action"] for m in s["motion"] if m.get("action") != "appear"}
    assert actions[("c_water", "c_steam")] == "morph"
    assert actions[("c_boil", "c_steam")] == "flow"
    assert actions[("c_steam", "c_water")] == "nest"
    assert actions[("c_water", "c_boil")] == "tether"


def test_physics_motion_from_relation_semantics():
    # the Jarvis directive: a relation that NAMES a motion drives a real physics motion, with the
    # params a renderer needs — derived from the predicate's meaning, not a per-concept table.
    concepts = [
        {"id": "c_gravity", "label": "중력", "weight": 1.0},
        {"id": "c_apple", "label": "사과", "weight": 0.5},
        {"id": "c_moon", "label": "달", "weight": 0.5},
        {"id": "c_light", "label": "빛", "weight": 0.4},
    ]
    rels = [
        {"from": "c_gravity", "to": "c_apple", "predicate": "사과를 떨어뜨린다"},   # fall
        {"from": "c_gravity", "to": "c_moon", "predicate": "달을 궤도에 붙든다"},    # orbit
        {"from": "c_gravity", "to": "c_apple", "predicate": "끌어당긴다"},          # attract
        {"from": "c_light", "to": "c_apple", "predicate": "방출된다"},              # emit
    ]
    s = compile_scene(concepts, rels, subject_id="c_gravity")
    phys = {m["action"] for m in s["motion"] if m["action"] != "appear"}
    assert {"fall", "orbit", "attract", "emit"} <= phys
    fall = next(m for m in s["motion"] if m["action"] == "fall")
    assert fall["target"] == "c_apple" and "accel" in fall           # a fall carries acceleration
    orbit = next(m for m in s["motion"] if m["action"] == "orbit")
    assert orbit["around"] == "c_gravity" and "radius" in orbit      # an orbit carries a center


def test_non_motion_relation_stays_structural():
    concepts = [{"id": "a", "label": "A", "weight": 1.0}, {"id": "b", "label": "B", "weight": 0.5}]
    s = compile_scene(concepts, [{"from": "a", "to": "b", "predicate": "관련"}])
    # no motion named → honest fall-back to the link/tether kind, NOT invented physics
    assert all(m["action"] in ("appear", "tether") for m in s["motion"])


def test_objects_appear_before_relations_move():
    rels = [{"from": "c_water", "to": "c_steam", "predicate": "되다"}]
    s = compile_scene(_concepts(), rels, duration=6.0)
    last_appear = max(m["t"] for m in s["motion"] if m["action"] == "appear")
    first_rel = min(m["t"] for m in s["motion"] if m["action"] != "appear")
    assert first_rel > last_appear


def test_hue_is_stable_per_concept():
    a = compile_scene(_concepts(), [])
    b = compile_scene(list(reversed(_concepts())), [])
    ha = {o["id"]: o["hue"] for o in a["objects"]}
    hb = {o["id"]: o["hue"] for o in b["objects"]}
    assert ha == hb                                              # order-independent, id-stable


def test_explicit_subject_overrides_weight():
    s = compile_scene(_concepts(), [], subject_id="c_steam")
    assert s["meta"]["subject"] == "c_steam"
    subj = next(o for o in s["objects"] if o["id"] == "c_steam")
    assert subj["pos"] == [0.0, 0.0, 0.0]
