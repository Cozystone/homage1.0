# -*- coding: utf-8 -*-
"""The image-schema basis: the closed set of primitives an instruction can mean.

Owner, 2026-07-29: 무궁무진한 행위에 일일히 다 매칭을 시킬 순 없잖아. 배선 안된건 못하는 게 아니라.

That objection rules out a handler per verb. The way out is the one every human language already
takes: verbs are not primitive, image schemas are. Before language, infants represent SOURCE-PATH-GOAL,
CONTAINER, CONTACT, SUPPORT, BLOCKAGE, ATTRACTION, LINK, NEAR-FAR, PART-WHOLE and FORCE; Talmy's force
dynamics covers the whole prevent/let/cause/hinder family with two participants and a tendency. There
are on the order of twenty, and the action vocabulary of every language is built on them.

So the wiring cost is O(1) in vocabulary: about twenty schemas are wired, and a new verb is a new
COMBINATION rather than new code.

WHERE THE LINE IS, because this project's standing rule is that hand-written rules are training wheels.
Writing the basis is legitimate in the way that declaring three colour channels is legitimate — it
states what the system can represent at all. Writing `avoid -> flee()` is not, because that table is
unbounded and must be learned. **This file contains the basis and NO verb.** The map from a word to a
schema is learned elsewhere and must generalise to words never seen, or the whole design is a lookup
table wearing a costume.

WHY EVERY SCHEMA CARRIES A GRADIENT AND NOT A TRUTH VALUE. A verb compiles to a PREFERENCE OVER
PREDICTED FUTURES, not to a procedure (ideomotor: actions are coded by their effects). `holds()` cannot
steer a search — every candidate future is equally false until the last step. `degree()` can. This is
the single design decision that makes one generic executor enough for every instruction.

ABSTENTION IS BUILT IN. A schema whose measurements the scene cannot supply returns None. It does not
guess, and it does not fall back to a default that happens to be measurable. A word that fits no
schema must surface as "not understood" rather than be forced into the nearest one — that failure is
how a wrong basis gets discovered instead of hidden.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


# --------------------------------------------------------------------------------------
# What a scene must be able to answer. Seven primitives; a domain implements what it has.
# A schema needing a measurement the domain lacks abstains rather than approximating.
# --------------------------------------------------------------------------------------
class Scene(Protocol):
    def participants(self) -> list[str]: ...
    def distance(self, a: str, b: str) -> float | None: ...
    def inside(self, figure: str, container: str) -> bool | None: ...
    def touching(self, a: str, b: str) -> bool | None: ...
    def holder(self, item: str) -> str | None: ...
    def at(self, entity: str) -> str | None: ...
    def exists(self, entity: str) -> bool | None: ...
    def blocked(self, figure: str, goal: str) -> bool | None: ...
    def scale(self) -> float: ...          # the domain's own unit, so degrees are comparable


def _sat(x: float | None) -> float | None:
    """Squash a distance-like quantity into [0,1] without a tunable constant: d/(1+d)."""
    if x is None:
        return None
    return float(x) / (1.0 + float(x))


@dataclass(frozen=True)
class Schema:
    """A relation over roles, with a satisfaction gradient. The unit of meaning, not of vocabulary.

    polarity flips the gradient and is why approach and avoid are ONE schema rather than two:
    Talmy's agonist/antagonist pair differs by the sign of the tendency, not by the schema."""

    name: str
    roles: tuple[str, ...]
    polarity: int = 1                       # +1 achieve, -1 prevent/avoid
    bind: dict[str, str] = field(default_factory=dict)

    def degree(self, scene: Scene) -> float | None:
        raise NotImplementedError

    def signed(self, scene: Scene) -> float | None:
        d = self.degree(scene)
        return None if d is None else (d if self.polarity > 0 else 1.0 - d)

    def _r(self, role: str) -> str | None:
        return self.bind.get(role)


# --------------------------------------------------------------------------------------
# The implemented basis. Nine of the ~twenty; the rest are named in NOT_YET, not stubbed,
# because a stub that returns a number is indistinguishable from an organ that works.
# --------------------------------------------------------------------------------------
class Proximity(Schema):
    """NEAR-FAR. degree rises as the figure nears the ground. polarity -1 is avoidance.

    This one schema underwrites approach, avoid, chase, flee, follow, guard, keep-away — which is the
    compression the whole design rests on."""

    def __init__(self, figure: str, ground: str, polarity: int = 1):
        super().__init__("PROXIMITY", ("figure", "ground"), polarity,
                         {"figure": figure, "ground": ground})

    def degree(self, scene: Scene) -> float | None:
        d = scene.distance(self._r("figure"), self._r("ground"))
        if d is None:
            return None
        s = max(scene.scale(), 1e-9)
        return 1.0 - _sat(d / s)


class Containment(Schema):
    """CONTAINER. In or out. Falls back to nearness only when the domain can measure distance,
    because 'nearly inside' is a real gradient for a mover and meaningless for a symbolic place."""

    def __init__(self, figure: str, container: str, polarity: int = 1):
        super().__init__("CONTAINMENT", ("figure", "container"), polarity,
                         {"figure": figure, "container": container})

    def degree(self, scene: Scene) -> float | None:
        f, c = self._r("figure"), self._r("container")
        v = scene.inside(f, c)
        if v is not None:
            return 1.0 if v else 0.0
        d = scene.distance(f, c)
        if d is None:
            return None
        return 1.0 - _sat(d / max(scene.scale(), 1e-9))


class Contact(Schema):
    def __init__(self, a: str, b: str, polarity: int = 1):
        super().__init__("CONTACT", ("a", "b"), polarity, {"a": a, "b": b})

    def degree(self, scene: Scene) -> float | None:
        v = scene.touching(self._r("a"), self._r("b"))
        return None if v is None else (1.0 if v else 0.0)


class Path(Schema):
    """SOURCE-PATH-GOAL. Satisfaction is nearness to the goal, so it steers before it succeeds."""

    def __init__(self, figure: str, goal: str, polarity: int = 1):
        super().__init__("PATH", ("figure", "goal"), polarity, {"figure": figure, "goal": goal})

    def degree(self, scene: Scene) -> float | None:
        f, g = self._r("figure"), self._r("goal")
        a = scene.at(f)
        if a is not None and a == g:
            return 1.0
        d = scene.distance(f, g)
        if d is None:
            return 0.0 if a is not None else None
        return 1.0 - _sat(d / max(scene.scale(), 1e-9))


class Blockage(Schema):
    def __init__(self, figure: str, goal: str, polarity: int = 1):
        super().__init__("BLOCKAGE", ("figure", "goal"), polarity, {"figure": figure, "goal": goal})

    def degree(self, scene: Scene) -> float | None:
        v = scene.blocked(self._r("figure"), self._r("goal"))
        return None if v is None else (1.0 if v else 0.0)


class Possession(Schema):
    def __init__(self, owner: str, item: str, polarity: int = 1):
        super().__init__("POSSESSION", ("owner", "item"), polarity, {"owner": owner, "item": item})

    def degree(self, scene: Scene) -> float | None:
        h = scene.holder(self._r("item"))
        return None if h is None else (1.0 if h == self._r("owner") else 0.0)


class Transfer(Schema):
    """The three-place give. Satisfaction is the item ending up with the recipient."""

    def __init__(self, agent: str, item: str, recipient: str, polarity: int = 1):
        super().__init__("TRANSFER", ("agent", "item", "recipient"), polarity,
                         {"agent": agent, "item": item, "recipient": recipient})

    def degree(self, scene: Scene) -> float | None:
        h = scene.holder(self._r("item"))
        return None if h is None else (1.0 if h == self._r("recipient") else 0.0)


class Existence(Schema):
    def __init__(self, entity: str, polarity: int = 1):
        super().__init__("EXISTENCE", ("entity",), polarity, {"entity": entity})

    def degree(self, scene: Scene) -> float | None:
        v = scene.exists(self._r("entity"))
        return None if v is None else (1.0 if v else 0.0)


class PartWhole(Schema):
    """PART-WHOLE. How much of the part is subsumed by the whole.

    The Gestalt relation a designed surface is built out of: a nav item is part of the nav bar because it
    lies INSIDE the bar's region, not because it is near its centre. That is why this schema needs EXTENT
    and not a point, and why it comes with a third scene adapter rather than reusing MetricScene -- a
    position cannot express containment of an area.

    degree is the fraction of the part's area that falls inside the whole's, so it is a gradient: a
    partially overlapping element scores partially, which is what a grouping process needs in order to
    prefer one candidate whole over another."""

    def __init__(self, part: str, whole: str, polarity: int = 1):
        super().__init__("PART_WHOLE", ("part", "whole"), polarity,
                         {"part": part, "whole": whole})

    def degree(self, scene: Scene) -> float | None:
        f = getattr(scene, "subsumption", None)
        if f is None:
            return None                      # a domain without extent cannot answer this
        return f(self._r("part"), self._r("whole"))


class Order(Schema):
    """Scalar precedence: a before/above/greater-than b. The one non-spatial primitive here."""

    def __init__(self, a: str, b: str, polarity: int = 1):
        super().__init__("ORDER", ("a", "b"), polarity, {"a": a, "b": b})

    def degree(self, scene: Scene) -> float | None:
        d = scene.distance(self._r("a"), self._r("b"))
        return None if d is None else (1.0 if d > 0 else 0.0)


#: Named, argued for in the design document, and deliberately NOT stubbed. A stub returning a number
#: is indistinguishable from a working organ, which is exactly the failure this project keeps finding.
NOT_YET = ("SUPPORT", "LINK", "FORCE", "CHANGE_OF_STATE",
           "PERCEPTION", "BELIEF", "INTENT", "ITERATION", "SALIENCE")

IMPLEMENTED = (Proximity, Containment, Contact, Path, Blockage,
               Possession, Transfer, Existence, Order, PartWhole)


# --------------------------------------------------------------------------------------
# The executor. ONE loop for every instruction. No verb appears here either.
# --------------------------------------------------------------------------------------
def satisfaction(schemas: list[Schema], scene: Scene) -> float | None:
    """How well a scene satisfies a conjunction of schemas. None if nothing is measurable.

    The weakest link decides, not the average: an instruction is met when ALL of it is met, and an
    average lets a well-satisfied clause pay for a violated one."""
    vals = [s.signed(scene) for s in schemas]
    have = [v for v in vals if v is not None]
    return min(have) if have else None


def choose(actions: list[Any], rollout, schemas: list[Schema], scene: Scene) -> tuple[Any, float]:
    """Pick the action whose PREDICTED scene best satisfies the instruction.

    `rollout(scene, action) -> predicted scene`. That is the entire coupling between an instruction and
    behaviour: no reward, no handler, no per-verb branch. It is also why this can act on a consequence
    the environment never pays for — the Atari agent dies more often than random precisely because
    death returns 0.00 reward, and a preference over predicted futures does not need a reward at all."""
    ruler = scene.scale()
    best, best_v = None, float("-inf")
    for a in actions:
        nxt = rollout(scene, a)
        if hasattr(nxt, "_scale"):
            nxt._scale = ruler          # one ruler for the whole comparison; see MetricScene.scale
        v = satisfaction(schemas, nxt)
        if v is None:
            continue
        if v > best_v:
            best, best_v = a, v
    return best, best_v
