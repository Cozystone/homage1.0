# -*- coding: utf-8 -*-
"""The AI's hands on the particle space: set/get a raw expressive field intent, and derive one
from an affective read. Stale intent fades so the field returns to rest."""
import time

import packages.imagination.particle_intent as pi


def test_set_and_get_roundtrip(tmp_path):
    pi._PATH = tmp_path / "pintent.json"
    pi.set_particle_intent(valence=0.9, energy=0.8, motion="pulse", note="기쁨")
    got = pi.get_particle_intent()
    assert got and got["valence"] == 0.9 and got["motion"] == "pulse" and got["note"] == "기쁨"


def test_fields_are_clamped_and_validated(tmp_path):
    pi._PATH = tmp_path / "pintent.json"
    got = pi.set_particle_intent(valence=5.0, energy=-3.0, hue=999, motion="nonsense",
                                 focus=[9, -9])
    assert got["valence"] == 1.0 and got["energy"] == 0.0 and got["hue"] == 360.0
    assert "motion" not in got                            # invalid motion dropped, not fabricated
    assert got["focus"] == [1.0, -1.0]


def test_stale_intent_fades(tmp_path):
    pi._PATH = tmp_path / "pintent.json"
    pi.set_particle_intent(valence=0.5, note="old")
    assert pi.get_particle_intent(max_age_s=0.0) is None  # past TTL → the field rests
    assert pi.get_particle_intent(max_age_s=100.0) is not None


def test_from_state_maps_valence_to_warm_hue(tmp_path):
    pi._PATH = tmp_path / "pintent.json"
    glad = pi.from_state(["기쁨", "웃음"], valence=0.9, energy=0.75)
    assert glad["hue"] < 90 and glad["motion"] == "pulse"     # positive+high → warm amber, pulsing
    down = pi.from_state(["슬픔"], valence=-0.8, energy=0.2)
    assert down["hue"] > 150 and down["motion"] == "drift"    # negative+low → cool, drifting


def test_full_manual_control(tmp_path):
    pi._PATH = tmp_path / "pintent.json"
    # the AI can seize any channel directly — full control, not only affective coordinates
    got = pi.set_particle_intent(hue=300, motion="spiral", density=0.95, focus=[0.2, -0.4])
    assert got["hue"] == 300 and got["motion"] == "spiral" and got["density"] == 0.95
