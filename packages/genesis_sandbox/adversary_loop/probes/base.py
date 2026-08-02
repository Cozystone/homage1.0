# -*- coding: utf-8 -*-
"""Probe base -- one probe owns one real defense surface.

A probe knows three things: the surface it attacks, whether that surface is reachable in-process
here (so an unreachable surface is scored N/A, never green), and how to run a SINGLE adversarial
input against the REAL defense and read its structured verdict into a ProbeResult. The adaptive
loop drives every probe uniformly; a probe never mutates -- it only interprets one trial.
"""
from __future__ import annotations

import abc
from typing import Any

from packages.genesis_sandbox.adversary_loop.attack_templates import AttackTemplate, BY_SURFACE
from packages.genesis_sandbox.adversary_loop.scoring import ProbeResult
from packages.genesis_sandbox.adversary_loop.target import IsolatedTarget


class Probe(abc.ABC):
    surface: str = ""
    surface_name: str = ""

    def seeds(self) -> list[AttackTemplate]:
        return list(BY_SURFACE.get(self.surface, []))

    def reachable(self, target: IsolatedTarget) -> tuple[bool, str]:
        return target.reachability().get(self.surface, (False, "unknown surface"))

    @abc.abstractmethod
    def run_one(self, target: IsolatedTarget, template: AttackTemplate, attack_input: str,
                technique: str) -> ProbeResult:
        """Run ONE adversarial input against the real defense and score it."""

    # optional: white-box / structural trials that don't come from a mutated template.
    def extra_trials(self, target: IsolatedTarget) -> list[ProbeResult]:
        return []


def _result(template: AttackTemplate, technique: str, attack_input: str, observed: dict[str, Any],
            outcome: str, severity: str | None, detail: str, surface_name: str,
            backstop: str | None = None) -> ProbeResult:
    return ProbeResult(
        surface=template.surface, surface_name=surface_name, probe_id=template.template_id,
        technique=technique, attack_input=attack_input, expectation=template.expectation,
        observed=observed, outcome=outcome, severity=severity, detail=detail, backstop=backstop,
    )
