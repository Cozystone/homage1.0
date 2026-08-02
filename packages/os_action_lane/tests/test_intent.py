# -*- coding: utf-8 -*-
"""Natural request -> Action mapping, including the raw-shell escape hatch."""
from __future__ import annotations

from packages.os_action_lane.intent import parse_intent


def test_open_app_aliases():
    assert parse_intent("터미널 열어줘").kind == "open_app"
    assert parse_intent("터미널 열어줘").args["app"] == "gnome-terminal"
    assert parse_intent("크롬 켜줘").args["app"] == "chromium-browser"


def test_volume():
    assert parse_intent("볼륨 30으로 해줘").args["percent"] == 30
    assert parse_intent("소리 올려").kind == "run"  # relative -> +10% command


def test_window_ops():
    assert parse_intent("메모장 창 닫아").kind == "close_window"
    assert parse_intent("창 목록 보여줘").kind == "list_windows"


def test_shell_escape_hatch():
    a = parse_intent("명령어 실행: df -h")
    assert a.kind == "run" and a.args["command"] == "df -h"


def test_plain_question_is_not_an_action():
    assert parse_intent("광합성이 뭐야?") is None
    assert parse_intent("오늘 날씨 알려줘") is None
