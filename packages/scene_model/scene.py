# -*- coding: utf-8 -*-
"""SCENE — one compositional representation for what a question describes.

The measured ceiling this replaces (docs/ATANOR_unified_scene_world_model_plan.md §1):
`parse_relational_shape` returns a flat `{rel, entity}` pair. "Which countries have no capital
city?" is not hard to ANSWER — the set-difference is computed elsewhere in this codebase every
day — it is impossible to REPRESENT in a flat pair, so no routing improvement can ever reach it.

A Scene has room for the pieces the owner named: a type slot ("countries"), relation conditions
("capital"), states like absence ("no"), and a readout. Composition, not classification: a new
question shape is a new arrangement of the same pieces, never a new lane.

Deliberately NOT here: no query text, no regexes, no store access. Scenes are built by
constructions (compose.py) and evaluated against a world surface (evaluate.py). This file is only
the shared shape both sides agree on — the lingua franca the plan doc describes.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Condition:
    """One relational constraint on the scene's variable.

    `obj=None` constrains mere possession of the relation (∃y: predicate(x, y)); a concrete `obj`
    constrains its value. `negated=True` asserts ABSENCE — which for a stored graph can only ever
    mean "no such edge in my graph", never "false in the world"; evaluate.py carries that
    distinction into the certificate rather than letting the surface overclaim."""
    predicate: str
    obj: str | None = None
    negated: bool = False


@dataclass(frozen=True)
class Scene:
    """What the utterance describes, ready for evaluation against any world surface.

    Exactly one of `var_type` / `entity` is set:
      * `var_type` — the variable ranges over the EXTENSION of a type ("countries", or equally
        `atanor_organ`: the self is just another type on the same surface);
      * `entity`   — the scene is about one named thing ("France", "atanor").
    """
    var_type: str | None = None
    entity: str | None = None
    conditions: tuple[Condition, ...] = field(default_factory=tuple)
    # set | count | exist | values -- what the asker wants read off the evaluated scene
    readout: str = "set"
    # for readout == "values": the relation whose objects are the answer
    readout_predicate: str | None = None
    # Words the composer recognised as GROUNDED (real graph terms) but had no slot to bind, e.g.
    # "atanor" in "which atanor organs have no tests" -- Scene has one var_type slot, so a
    # qualifying possessor/modifier the composer cannot yet represent as a second hop is dropped
    # rather than invented a slot for. Recorded here, never silently absorbed: answer_bridge reads
    # this to abstain instead of confidently answering a DIFFERENT, narrower question than the one
    # asked. Measured 2026-07-28: without this, "which atanor organs have no tests" answered about
    # human anatomy organs (a ConceptNet homonym) with useful_answer=True.
    dropped_qualifiers: tuple[str, ...] = field(default_factory=tuple)

    def well_formed(self) -> str | None:
        """None if evaluable; else the reason — surfaced verbatim as the abstention basis."""
        if (self.var_type is None) == (self.entity is None):
            return "scene needs exactly one of var_type or entity"
        if self.readout not in ("set", "count", "exist", "values"):
            return f"unknown readout {self.readout!r}"
        if self.readout == "values" and not self.readout_predicate:
            return "values readout without a readout_predicate"
        if self.var_type is not None and not self.conditions and self.readout in ("set", "count"):
            # "which countries?" with no condition is answerable but vacuous; allowed.
            pass
        return None
