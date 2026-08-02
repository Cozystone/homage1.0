# -*- coding: utf-8 -*-
"""Open-vocabulary scene perception — the pure parts (grounded sentence composition, color mapping)
are tested without loading the 600MB detector; the model path is proven live on GPU (owner 2026-07-13)."""
from __future__ import annotations

from packages.perception.open_vocab import VOCAB_KO, _region, color_for, compose_scene


def test_color_is_stable_and_distinct_per_label():
    assert color_for("a book") == color_for("a book")             # stable
    assert color_for("a book") != color_for("an electric fan")    # distinct
    assert color_for("사람").startswith("hsl(")


def test_region_reads_left_center_right():
    assert _region([10, 10, 100, 100], 1000, 500) == "왼쪽"
    assert _region([450, 10, 560, 100], 1000, 500) == "가운데"
    assert _region([900, 10, 990, 100], 1000, 500) == "오른쪽"


def test_scene_sentence_is_grounded_in_detections_only():
    # a plausible room detection set → a grounded Korean sentence naming exactly what was seen
    dets = [
        {"label_ko": "사람", "box": [600, 300, 900, 800], "score": 0.9},
        {"label_ko": "책장", "box": [100, 200, 500, 800], "score": 0.85},
        {"label_ko": "선풍기", "box": [50, 600, 200, 850], "score": 0.6},
        {"label_ko": "책장", "box": [500, 200, 700, 800], "score": 0.7},   # a 2nd bookshelf box
    ]
    out = compose_scene(dets, (1280, 900))
    s = out["scene_sentence"]
    assert "사람" in s and "책장" in s and "선풍기" in s
    assert "책장 2개" in s                                        # duplicate type is counted
    assert "보이는 공간" in s
    # grounded: nothing NOT in the detections leaks into the sentence
    assert "강아지" not in s and "노트북" not in s


def test_empty_detections_says_so_honestly():
    out = compose_scene([], (640, 480))
    assert "알아볼 수 있는 사물이 없어요" in out["scene_sentence"]


def test_vocab_has_the_room_objects():
    for en, ko in [("a person", "사람"), ("a book", "책"), ("an electric fan", "선풍기"),
                   ("a wardrobe", "옷장"), ("glasses", "안경")]:
        assert VOCAB_KO[en] == ko
