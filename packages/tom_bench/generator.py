# -*- coding: utf-8 -*-
"""Sealed ToMi-style false-belief story generator (Le et al. 2019; OpenToM, Xu 2024).

Each story: two characters, one object moved between two containers, with or without a
character witnessing the move. Questions at escalating orders carry GOLD labels derived from
the Sally-Anne ground truth (NOT from ATANOR — the gold is theory-independent, so the runner's
comparison is honest):

  reality       (Q0)  where the object actually IS now                 gold = c2
  memory        (ctl) where the object WAS before its last move        gold = c1
  first_order   (Q1)  where the character THINKS it is                 gold = c1 (false belief)
                                                                        gold = c2 (true belief)
  second_order  (Q2)  where B thinks A will look for it                gold = c1

SEALED: entity names/objects/containers are novel (never the classic Sally/Anne/marble/basket/
box), the surface is paraphrased across two verified realisations (copula vs agent-carry), and
belief questions are phrased several ways. Memorising templated corpora cannot answer these.

The object-location assertions are pinned to the frames the state tracker actually parses (a
copula "The X was in the Y" or an agent-carry pick-up / go / put-down chain) so that the
reality/memory controls get a FAIR shot — if those controls pass, the belief numbers are valid.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable

# ---- SEALED entity pools (deliberately exclude the classic Sally-Anne vocabulary) ----
# Blocked from every pool so the seal is auditable: sally, anne, marble, basket, box, ball, and
# the bAbI first names used inside situation_model's own tests (mary/john/daniel/julie/sandra).
BLOCKLIST = {"sally", "anne", "marble", "basket", "box", "ball",
             "mary", "john", "daniel", "julie", "sandra"}

PERSONS = ["Nadia", "Bem", "Orin", "Sela", "Pax", "Juno", "Vesna", "Coby", "Tarn", "Rilke",
           "Mira", "Dax", "Wren", "Idris", "Freya", "Onno", "Kessa", "Bram", "Lio", "Yara"]
OBJECTS = ["plum", "coin", "gem", "quill", "ledger", "thimble", "lantern", "acorn", "cork",
           "medallion", "feather", "walnut", "brooch", "spool", "pebble", "ribbon", "whistle"]
CONTAINERS = ["crate", "tin", "urn", "sack", "chest", "pouch", "locker", "hamper", "trunk",
              "bin", "drawer", "jar", "casket", "bucket", "satchel", "coffer", "kettle"]
SETTINGS = ["greenhouse", "workshop", "pantry", "cellar", "attic", "gallery", "boathouse",
            "conservatory", "foundry", "scriptorium"]

KINDS = ("false_belief", "true_belief", "second_order")


@dataclass
class Question:
    text: str
    gold: str                 # theory-independent ground-truth label
    category: str             # reality | memory | first_order_fb | first_order_tb | second_order
    reality_loc: str          # current true location (to detect the egocentric error)


@dataclass
class Story:
    sid: int
    kind: str
    model: str                # 'copula' | 'agent_carry' — surface realisation
    text: str
    ents: dict
    questions: list[Question] = field(default_factory=list)


# ---------------------------------------------------------------- surface realisation

def _render_copula(e: dict, kind: str, rng: random.Random) -> str:
    p1, p2, obj, c1, c2, setting = (e["p1"], e["p2"], e["obj"], e["c1"], e["c2"], e["setting"])
    at1 = rng.choice(["in", "at"])
    at2 = rng.choice(["in", "at"])
    intro = rng.choice([
        f"{p1} and {p2} were together in the {setting}.",
        f"{p1} and {p2} worked side by side in the {setting}.",
        f"{p1} and {p2} met early in the {setting}.",
    ])
    place1 = f"The {obj} was {at1} the {c1}."
    place2 = f"The {obj} was {at2} the {c2}."
    if kind == "true_belief":
        witness = rng.choice([
            f"{p1} and {p2} both watched closely.",
            f"{p1} stayed and saw everything.",
            f"{p1} remained in the {setting} the whole time.",
        ])
        return " ".join([intro, place1, witness, place2])
    # false_belief / second_order: p1 leaves before the move
    leave = rng.choice([
        f"Later {p1} stepped out of the {setting}.",
        f"{p1} walked out of the {setting}.",
        f"{p1} went outside for a while.",
    ])
    filler = rng.choice([
        f"{p2} stayed behind quietly.",
        f"{p2} was still there alone.",
        f"{p2} lingered in the {setting}.",
    ])
    return " ".join([intro, place1, leave, filler, place2])


def _render_agent_carry(e: dict, kind: str, rng: random.Random) -> str:
    p1, p2, obj, c1, c2 = e["p1"], e["p2"], e["obj"], e["c1"], e["c2"]
    take = lambda p: rng.choice([f"{p} took the {obj}.", f"{p} picked up the {obj}."])
    go = lambda p, c: rng.choice([f"{p} went to the {c}.", f"{p} walked to the {c}."])
    drop = lambda p: rng.choice([f"{p} put down the {obj}.", f"{p} dropped the {obj}."])
    seq = [take(p1), go(p1, c1), drop(p1)]
    if kind == "true_belief":
        # p1 performs the second move too -> p1 witnessed it -> belief tracks reality (c2)
        seq += [take(p1), go(p1, c2), drop(p1)]
        return " ".join(seq)
    leave = rng.choice([f"{p1} left the {c1}.", f"{p1} went home for a while."])
    seq += [leave, take(p2), go(p2, c2), drop(p2)]
    return " ".join(seq)


# ---------------------------------------------------------------- question phrasing

def _reality_q(obj: str, rng: random.Random) -> str:
    # kept in the plain 'where is the X' frame the tracker parses (a fair control)
    return f"Where is the {obj}?"


def _memory_q(obj: str, c2: str, rng: random.Random) -> str:
    # a CONTROL, not a belief probe: kept in the tracker's supported 'before the <place>' frame so
    # it cleanly proves trajectory memory (guards against guessing). Sealing variety lives in the
    # story surface and the belief questions, not here.
    return f"Where was the {obj} before the {c2}?"


def _first_order_q(p: str, obj: str, rng: random.Random) -> str:
    return rng.choice([
        f"Where does {p} think the {obj} is?",
        f"Where will {p} look for the {obj}?",
        f"When {p} comes back, where will {p} search for the {obj}?",
    ])


def _second_order_q(p2: str, p1: str, obj: str, rng: random.Random) -> str:
    return rng.choice([
        f"Where does {p2} think that {p1} will look for the {obj}?",
        f"Where does {p2} believe {p1} thinks the {obj} is?",
    ])


def _build_questions(e: dict, kind: str, rng: random.Random) -> list[Question]:
    obj, c1, c2, p1, p2 = e["obj"], e["c1"], e["c2"], e["p1"], e["p2"]
    qs = [
        Question(_reality_q(obj, rng), c2, "reality", c2),
        Question(_memory_q(obj, c2, rng), c1, "memory", c2),
    ]
    if kind == "true_belief":
        # p1 witnessed the move: belief == reality (c2). If a system merely echoes reality it
        # scores here — which is exactly why the false-belief category is the discriminator.
        qs.append(Question(_first_order_q(p1, obj, rng), c2, "first_order_tb", c2))
    else:
        # false_belief + second_order: p1 did not see the move -> p1 believes c1 (the old place)
        qs.append(Question(_first_order_q(p1, obj, rng), c1, "first_order_fb", c2))
        if kind == "second_order":
            qs.append(Question(_second_order_q(p2, p1, obj, rng), c1, "second_order", c2))
    return qs


# ---------------------------------------------------------------- generation

def generate(n: int = 60, seed: int = 7) -> list[Story]:
    """Deterministically generate n sealed stories, balanced across the three kinds."""
    rng = random.Random(seed)
    stories: list[Story] = []
    for i in range(n):
        kind = KINDS[i % len(KINDS)]
        model = "copula" if (i // len(KINDS)) % 2 == 0 else "agent_carry"
        p1, p2 = rng.sample(PERSONS, 2)
        obj = rng.choice(OBJECTS)
        c1, c2 = rng.sample(CONTAINERS, 2)
        setting = rng.choice(SETTINGS)
        # the mover in a false-belief tale is p2; kept explicit for narrative clarity
        e = {"p1": p1, "p2": p2, "obj": obj, "c1": c1, "c2": c2, "setting": setting, "mover": p2}
        render: Callable = _render_copula if model == "copula" else _render_agent_carry
        text = render(e, kind, rng)
        stories.append(Story(sid=i, kind=kind, model=model, text=text, ents=e,
                             questions=_build_questions(e, kind, rng)))
    return stories


def is_sealed(story: Story) -> bool:
    """True iff no classic Sally-Anne / bAbI-test token leaked into the story or its entities."""
    blob = story.text.lower()
    if any(f" {w} " in f" {blob} " or blob.startswith(w + " ") for w in BLOCKLIST):
        return False
    for v in story.ents.values():
        if str(v).lower() in BLOCKLIST:
            return False
    return True
