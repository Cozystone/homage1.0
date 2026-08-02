# -*- coding: utf-8 -*-
"""Scene graph — relation reasoning over detections, by geometry alone (No-LLM, CPU). Verified on a
layout matching the owner's actual room (person in front of bookshelf, glasses on face, clothes in
wardrobe)."""
from __future__ import annotations

from packages.perception.scene_graph import (
    build_scene_graph,
    commonsense_context,
    describe_with_relations,
    spatial_relations,
)

SIZE = (1456, 816)
# a detection set matching the owner's screenshot layout
ROOM = [
    {"label_ko": "책장", "box": [180, 300, 1050, 780], "color": "r"},
    {"label_ko": "사람", "box": [640, 330, 1080, 816], "color": "o"},
    {"label_ko": "얼굴", "box": [690, 380, 880, 560], "color": "w"},
    {"label_ko": "안경", "box": [700, 430, 860, 492], "color": "y"},
    {"label_ko": "선풍기", "box": [90, 560, 380, 816], "color": "b"},
    {"label_ko": "택배 상자", "box": [0, 700, 210, 816], "color": "b"},
    {"label_ko": "옷장", "box": [1240, 340, 1456, 816], "color": "c"},
    {"label_ko": "옷", "box": [1280, 360, 1440, 700], "color": "g"},
]


def _has(rels, subj, rel, obj):
    return any(r["subject"] == subj and r["relation"] == rel and r["object"] == obj for r in rels)


def test_containment_glasses_in_face_clothes_in_wardrobe():
    rels = spatial_relations(ROOM, SIZE)
    assert _has(rels, "얼굴", "contains", "안경")      # glasses sit inside the face
    assert _has(rels, "옷장", "contains", "옷")         # clothes inside the wardrobe


def test_person_is_in_front_of_the_bookshelf():
    # THE scene-understanding relation: the person occludes and sits lower → in front of the bookshelf
    rels = spatial_relations(ROOM, SIZE)
    assert _has(rels, "사람", "in_front_of", "책장")


def test_left_right_layout():
    rels = spatial_relations(ROOM, SIZE)
    # the fan is to the left of the person (no overlap → a left_of relation)
    assert _has(rels, "선풍기", "left_of", "사람") or _has(rels, "선풍기", "near", "택배 상자")


def test_scene_graph_nodes_and_edges():
    g = build_scene_graph(ROOM, SIZE)
    labels = {n["label"] for n in g["nodes"]}
    assert {"책장", "사람", "안경", "선풍기", "옷장"} <= labels
    assert len(g["edges"]) >= 4                          # real relations were found


def test_commonsense_reads_a_study_context():
    ctx = commonsense_context(ROOM)
    assert ctx and ("책" in ctx or "공부" in ctx)         # bookshelf + person → a study/reading read


def test_relations_are_grounded_only_in_detections():
    # an object NOT detected must never appear in any relation
    out = describe_with_relations(ROOM, SIZE)
    joined = " ".join(out["relations_ko"]) + (out["commonsense"] or "")
    assert "강아지" not in joined and "자동차" not in joined
