# -*- coding: utf-8 -*-
"""DELIBERATOR — the System-2 loop, assembled. This is the orchestrator the audit found MISSING: it
takes a multi-step goal, DECOMPOSES it (via the rule algebra / an explicit relation chain), DEDUCES
each sub-goal over the graph with the backward chainer, DERIVES the answer, and returns it only when
every inference step VERIFIES (backward propose → forward-closure verify, `back_chain.verify_proof`).
No LLM: symbolic resolution + a held-out-gated kernel library; a step that doesn't verify is dropped,
never a fabricated inference.

Two answering surfaces:
  • derive(subject, relation)         — single relation, may itself be multi-hop via the rules.
  • derive_path(subject, [r1,r2,…])   — an EXPLICIT relation chain (subject -r1-> b -r2-> answer): the
                                        multi-step question whose structure is given (the controlled
                                        probe's shape, and what an intent/decomposition layer emits).
  • answer_mcq(...)                    — derive the object and pick the option it equals, OR prove each
                                        option's ground goal; grounded only, else honest abstain.

The kernel library is wired here: `with_default_kernels` forges the small discrete-science kernels
(net charge, electron/nucleon counts, comparisons) the first time and hands them to the chainer, so a
computation sub-goal ("net_charge of an atom with p protons, e electrons") is resolved by RUNNING a
verified skill, not by lookup.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

from packages.reasoning_vm.deliberator.back_chain import (
    BackChainer, KernelBinding, Rule, Step, _norm, verify_proof,
)

FactsAbout = Callable[[str], list[tuple[str, str, str]]]


# ── kernel wiring ────────────────────────────────────────────────────────────────────────────────
# (kernel_name, vars, example generator, [(input_relation, kernel_var), ...] binding to a relation)
def _forge_science_kernels() -> list[KernelBinding]:
    """Forge (or recall) the small discrete-science kernels and return their relation bindings. Each
    is acquired by KernelForge from input→output examples under a HELD-OUT generalization gate — a
    kernel that fits train but fails unseen inputs never enters the library (작화0 for skills). These
    are the DISCRETE relations the audit named as KernelForge's honest scope; continuous/float physics
    is the separately-tracked DSL extension."""
    from packages.reasoning_vm.deliberator import kernel_forge as KF
    specs = [
        # name,           vars,                    examples,                                   binding
        ("net_charge", ["protons", "electrons"],
         [({"protons": p, "electrons": e}, p - e) for p in range(1, 12) for e in range(0, 12)],
         KernelBinding("net_charge", [("protons", "protons"), ("electrons", "electrons")], "net_charge")),
        ("neutron_count", ["mass_number", "protons"],
         [({"mass_number": a, "protons": z}, a - z) for a in range(1, 40) for z in range(0, 20) if a >= z],
         KernelBinding("neutron_count", [("mass_number", "mass_number"), ("atomic_number", "protons")],
                       "neutron_count")),
        ("nucleon_count", ["protons", "neutrons"],
         [({"protons": z, "neutrons": n}, z + n) for z in range(0, 20) for n in range(0, 20)],
         KernelBinding("nucleon_count", [("atomic_number", "protons"), ("neutron_number", "neutrons")],
                       "nucleon_count")),
    ]
    bindings: list[KernelBinding] = []
    for name, vars_, ex, binding in specs:
        try:
            KF.acquire_or_recall(name, ex, vars_, pop=80, generations=80, seed=0)
        except Exception:
            continue
        if (KF.recall(name) or {}).get("accepted"):
            bindings.append(binding)
    return bindings


class Deliberator:
    """The System-2 reasoner. Give it a `facts_about` (dict, TripleStore, MultiShardStore — anything
    with the (s,p,o) accessor) and it derives multi-step answers with proofs over that graph."""

    def __init__(self, facts_about: FactsAbout, *, rules: Optional[list[Rule]] = None,
                 kernels: Optional[list[KernelBinding]] = None,
                 inherit_props: Optional[Callable[[str], list]] = None,
                 with_kernels: bool = True, max_depth: int = 5, budget: int = 4000):
        kbs = list(kernels or [])
        if with_kernels:
            try:
                kbs += _forge_science_kernels()
            except Exception:
                pass
        self.chainer = BackChainer(facts_about, rules=rules, kernels=kbs, inherit_props=inherit_props,
                                   max_depth=max_depth, budget=budget)
        self.fa = facts_about

    # -- derivation --------------------------------------------------------------------------------
    def derive(self, subject: str, relation: str) -> dict[str, Any]:
        """Single-relation goal (may be multi-hop through the rules). See BackChainer.derive."""
        return self.chainer.derive(subject, relation)

    def derive_path(self, subject: str, relations: list[str]) -> dict[str, Any]:
        """EXPLICIT relation chain subject -r1-> b1 -r2-> … -rn-> answer. Solved as one conjunctive
        goal so every intermediate bridge is derived (each hop may itself expand via the rules) and
        the whole trail is verified end-to-end. Returns answer + fired (hops>=2) + the proof trail;
        answer None (honest abstain) if any hop can't be grounded — never a fabricated bridge."""
        if not relations:
            return {"answer": None, "fired": False, "grounded": False, "hops": 0, "proof": None}
        if len(relations) == 1:
            return self.derive(subject, relations[0])
        # build the conjunction: (subj r1 ?b1),(?b1 r2 ?b2),…,(?b{n-1} rn ?answer)
        goals: list[tuple[str, str, str]] = []
        cur = subject
        for i, r in enumerate(relations):
            nxt = "?answer" if i == len(relations) - 1 else f"?b{i}"
            goals.append((cur, r, nxt))
            cur = nxt
        self.chainer._n = 0
        for b, steps in self.chainer._solve_conj(goals, {}, 0, frozenset()):
            # a synthetic parent step over the chain, so hops/verify treat it as one derivation
            from packages.reasoning_vm.deliberator.back_chain import _walk
            concl = (subject, "→".join(relations), _walk("?answer", b))
            parent = Step(concl, "rule", "chain[" + "∘".join(relations) + "]", steps)
            if all(verify_proof(
                s, self.fa, inherit_props=self.chainer.inherit_props,
                kernel_bindings=self.chainer.kernel_bindings(),
            ) for s in steps):
                ans = _walk("?answer", b)
                if ans and not str(ans).startswith("?"):
                    return {"answer": ans, "grounded": True, "fired": parent.hops() >= 2,
                            "hops": parent.hops(), "depth": parent.depth(), "proof": parent,
                            "trail": parent.pretty(), "basis": parent.detail}
        return {"answer": None, "fired": False, "grounded": False, "hops": 0, "proof": None,
                "basis": "no verified chain"}

    def can_prove(self, subject: str, relation: str, obj: str) -> dict[str, Any]:
        return self.chainer.can_prove(subject, relation, obj)

    # -- MCQ ---------------------------------------------------------------------------------------
    def answer_mcq_derive(self, subject: str, relation: str, choices: dict[str, str],
                          *, relations: Optional[list[str]] = None) -> dict[str, Any]:
        """Derive the object of (subject, relation[/chain]) and pick the choice whose text equals it
        (loose-normalized, or numerically for a kernel result). Grounded pick + proof, or ABSTAIN —
        never a guess. This is the 'derive then match' MCQ move a computed/looked-up answer supports."""
        out = self.derive_path(subject, relations) if relations else self.derive(subject, relation)
        ans = out.get("answer")
        if ans is None:
            return {"choice_key": None, "mode": "abstain", "confidence": 0.0,
                    "basis": "engine derived nothing verified"}
        keys = list(choices)
        # Numeric kernel/arithmetic answers use exact rational-and-unit equality.  This admits
        # notation-equivalent choices (``1/2`` versus ``0.5`` and ``1 m`` versus ``100 cm``) while
        # keeping a nearby decimal or dimensionally different value from winning by list order.
        exact_quantity = _as_exact_quantity(ans)
        if exact_quantity is not None:
            matches = [
                k for k in keys if _as_exact_quantity(choices[k]) == exact_quantity
            ]
        else:
            matches = [k for k in keys if _norm(choices[k]) == _norm(ans)]
        if len(matches) == 1:
            return {"choice_key": matches[0], "mode": "grounded", "confidence": 0.9,
                    "fired": out.get("fired", False), "hops": out.get("hops", 0),
                    "basis": f"derived {relation} = {ans}", "proof": out.get("proof"),
                    "trail": out.get("trail")}
        if len(matches) > 1:
            return {"choice_key": None, "mode": "abstain", "confidence": 0.0,
                    "basis": f"derived {ans!r}; multiple choices match exactly"}
        return {"choice_key": None, "mode": "abstain", "confidence": 0.0,
                "basis": f"derived {ans!r}; no choice matches"}

    def answer_mcq_object(self, subject: str, relation: str, choices: dict[str, str],
                          *, negated: bool = False) -> dict[str, Any]:
        """Pick the choice C for which (subject, relation, C) is derivable — e.g. 'which continent is
        Seoul located_in?' proves (seoul, located_in, choice) for each option (multi-hop via the rules
        counts). GROUNDED on a single provable positive choice. A negated goal abstains until an
        explicit negative-proof relation is implemented; open-world absence is never a proof."""
        if negated:
            return {
                "choice_key": None,
                "mode": "abstain",
                "confidence": 0.0,
                "basis": "negated object goal requires explicit negative evidence; "
                         "absence of proof is not proof of absence",
                "open_world_negative": True,
            }
        provable: dict[str, bool] = {}
        proofs: dict[str, Any] = {}
        for k, choice in choices.items():
            r = self.chainer.can_prove(subject, relation, choice)
            provable[k] = r["provable"]
            if r["provable"]:
                proofs[k] = {"hops": r.get("hops", 0), "trail": r.get("trail")}
        n = sum(provable.values())
        if n == 1:
            k = next(k for k, ok in provable.items() if ok)
            return {"choice_key": k, "mode": "grounded", "confidence": 0.85,
                    "hops": proofs[k]["hops"], "basis": f"only provable: {subject} {relation} "
                    f"{choices[k]}", "trail": proofs[k]["trail"]}
        return {"choice_key": None, "mode": "abstain", "confidence": 0.0,
                "basis": f"{n} choices provable — cannot isolate"}

    def answer_mcq_prove(self, relation: str, target: str, choices: dict[str, str],
                         *, negated: bool = False) -> dict[str, Any]:
        """Prove each option's ground goal (choice, relation, target) — e.g. (choice, is_a, target).
        GROUNDED when exactly one positive choice is provable, else ABSTAIN. Negated goals
        abstain until the graph carries and the chainer verifies an explicit negative relation;
        an unprovable positive is not a grounded negative in an open world."""
        if negated:
            return {
                "choice_key": None,
                "mode": "abstain",
                "confidence": 0.0,
                "basis": f"negated {relation} goal requires explicit negative evidence; "
                         "absence of proof is not proof of absence",
                "open_world_negative": True,
            }
        provable: dict[str, bool] = {}
        proofs: dict[str, Any] = {}
        for k, choice in choices.items():
            r = self.chainer.can_prove(choice, relation, target)
            provable[k] = r["provable"]
            if r["provable"]:
                proofs[k] = {
                    "hops": r.get("hops", 0),
                    "proof": r.get("proof"),
                    "trail": r.get("trail"),
                }
        n = sum(provable.values())
        if n == 1:
            k = next(k for k, ok in provable.items() if ok)
            proof = proofs[k]
            return {"choice_key": k, "mode": "grounded", "confidence": 0.85,
                    "fired": proof["hops"] >= 2, "hops": proof["hops"],
                    "basis": f"only provable: {choices[k]} {relation} {target}",
                    "proof": proof["proof"], "trail": proof["trail"]}
        return {"choice_key": None, "mode": "abstain", "confidence": 0.0,
                "basis": f"{n} choices provable — cannot isolate"}


_GROUPED_INTEGER_TOKEN = r"(?:0|[1-9]\d{0,2})(?:,\d{3})+"
_GROUPED_DECIMAL_TOKEN = (
    rf"[-+]?{_GROUPED_INTEGER_TOKEN}(?:\.\d*)?(?:[eE][-+]?\d+)?"
)
_GROUPED_FRACTION_TOKEN = (
    rf"[-+]?(?:{_GROUPED_INTEGER_TOKEN}|\d+)/"
    rf"(?:{_GROUPED_INTEGER_TOKEN}|\d+)"
)
_GROUPED_DECIMAL = re.compile(_GROUPED_DECIMAL_TOKEN + r"\Z")
_GROUPED_FRACTION = re.compile(_GROUPED_FRACTION_TOKEN + r"\Z")
_GROUPED_QUANTITY = re.compile(
    rf"(?P<number>(?:{_GROUPED_DECIMAL_TOKEN}|{_GROUPED_FRACTION_TOKEN}))"
    r"(?P<suffix>\s*\S.*)\Z",
)


def _normalize_grouping(token: str, *, allow_quantity_suffix: bool = False) -> str | None:
    if len(token) > 8192:
        return None
    if "," not in token:
        return token
    if _GROUPED_DECIMAL.fullmatch(token) is not None \
            or _GROUPED_FRACTION.fullmatch(token) is not None:
        return token.replace(",", "")
    if allow_quantity_suffix:
        match = _GROUPED_QUANTITY.fullmatch(token)
        if match is not None:
            return match.group("number").replace(",", "") + match.group("suffix")
    return None


def _as_number(x: Any):
    """Return a bounded exact rational for an MCQ scalar, never a binary-float approximation.

    Thousands separators are accepted only in their conventional three-digit grouping because MCQ
    display text commonly contains ``1,000``.  The rational DSL itself remains comma-free.
    """
    from packages.evolution.rational_evolver import parse_value
    if type(x) is str:
        token = _normalize_grouping(x.strip())
        if token is None:
            return None
        return parse_value(token)
    return parse_value(x)


def _as_exact_quantity(x: Any):
    """Return ``(exact value, canonical unit)`` for a bounded scalar or quantity token."""
    scalar = _as_number(x)
    if scalar is not None:
        return scalar, ""
    if type(x) is not str:
        return None
    token = _normalize_grouping(x.strip(), allow_quantity_suffix=True)
    if token is None:
        return None
    from packages.reasoning_vm.quantity import parse_quantity
    quantity = parse_quantity(token)
    if quantity is None or not quantity.unit:
        return None
    return quantity.value, quantity.unit
