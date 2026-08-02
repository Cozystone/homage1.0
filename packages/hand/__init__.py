# -*- coding: utf-8 -*-
"""ATANOR's hand — one door for motor output, the counterpart to `packages.eye`.

The eye takes screen, window, video and camera and produces one `Frame`, so nothing downstream can
tell which door the light came through. The hand takes one `Move` and sends it through whatever
effector is present, so nothing upstream has to know what body it is wearing. That symmetry is what
makes "learn to move in a city" and "learn to move a limb" the same problem instead of two.

    from packages.eye import open_eye, WindowSource
    from packages.hand import WindowEffector, Move, babble

    eye  = open_eye(WindowSource(title_contains="CitySample"))
    hand = WindowEffector(title_contains="CitySample")
    schema = babble(eye, hand, [Move(keys=("w",), seconds=0.4), Move(mouse_dx=200)])
    print(schema.describe())     # what each thing DID, discovered, not declared

Nothing here is told which key means what. It presses, watches, and keeps the pair.
"""
from .babble import BodySchema, babble, flow_signature
from .explore import Territory, explore
from .effector import SCAN, Effector, Move, WindowEffector

ATANOR_TIER = "motor"

__all__ = ["Move", "Effector", "WindowEffector", "SCAN",
           "babble", "BodySchema", "flow_signature", "explore", "Territory", "ATANOR_TIER"]
