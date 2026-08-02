# -*- coding: utf-8 -*-
"""DELIBERATOR organ ③ — the backward-chaining DERIVATION engine (System-2 spine).

The audit (2026-07-24) found the two hard organs already in the VM — `deduction.py` (forward
deductive closure with proof certificates) and `deliberator/kernel_forge.py` (VibeCode-synthesized,
held-out-gated computation kernels) — WORK and are tested, but are ISLANDS: nothing composed them
into an answering chain. The MCQ cascade (`exam_answer`) only ever did a SINGLE-FACT lookup or
entailment, then fell to a hash guess — so a multi-step question ("grandparent of X", "net charge of
an atom with Z protons and E electrons", "which continent is the capital's country on") could never
be DERIVED. GPQA sits at chance for exactly this reason (engine-absent), on top of the separate
knowledge gap.

This module is the missing spine: goal-directed SLD-style resolution over a knowledge base that is

    {graph facts}  ∪  {Horn rules (the relation algebra)}  ∪  {verified computation kernels}

To DERIVE a goal (subj, rel, ?answer) the resolver, backward:
  1. matches a stored graph FACT                                   (the base case, a leaf),
  2. applies a RULE whose head unifies with the goal and recursively derives its body sub-goals
     (this is DECOMPOSITION — a multi-property goal becomes a conjunction of sub-goals),
  3. applies a computation KERNEL: derive the kernel's typed numeric inputs as sub-goals, then run the
     held-out-gated kernel (this wires KernelForge into reasoning for the first time).

Every derivation carries a PROOF TREE whose leaves are stored facts or kernel applications. 작화0 is
structural: a step that cannot be grounded is never emitted, and `verify_proof` independently
re-checks every leaf (re-reads the fact from the KB, re-runs the kernel) AND cross-checks the derived
fact against `deduction.deduce`'s forward closure of the gathered leaves — a backward PROPOSE / forward
VERIFY loop, both symbolic, No-LLM. A proof that fails re-verification is dropped, never returned.

Reuse (not rebuild): the rule algebra is single-sourced from `deduction.py`
(TRANSITIVE/SYMMETRIC/COMPOSE/INHERIT); kernels come from `kernel_forge`; the graph accessor is the
same `facts_about(subject) -> [(s,p,o)]` every other organ uses, so the engine runs on the live
115M/141M-triple store unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable, Iterator, Optional

Fact = tuple[str, str, str]
FactsAbout = Callable[[str], list[Fact]]


# ── terms, variables, unification ────────────────────────────────────────────────────────────────
def is_var(t: Any) -> bool:
    return isinstance(t, str) and t.startswith("?")


def _norm(s: Any) -> str:
    """Loose match key for entities: strip a parenthetical clarifier, then spaces/punct, lowercase —
    the same normalization discrimination.py uses so a choice/label matches its stored form."""
    s = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", "", str(s))
    return re.sub(r"[\s·,.'\"]+", "", s).strip().lower()


def _rel(p: Any) -> str:
    return str(p).strip().lower()


_NUMERIC_TERM_RE = re.compile(
    r"[-+]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|\d+/\d+)\Z"
)


def _exact_number(term: Any):
    if type(term) is str and _NUMERIC_TERM_RE.fullmatch(term.strip()) is None:
        return None
    if type(term) not in (str, int, Fraction):
        return None
    from packages.evolution.rational_evolver import parse_value
    return parse_value(term)


def _same_term(left: Any, right: Any) -> bool:
    left_number = _exact_number(left)
    right_number = _exact_number(right)
    if left_number is not None or right_number is not None:
        return left_number is not None and left_number == right_number
    return _norm(left) == _norm(right)


def _proof_norm(term: Any) -> str:
    number = _exact_number(term)
    if number is None:
        return _norm(term)
    return f"#number:{number.numerator}/{number.denominator}"


def _walk(t: Any, b: dict[str, Any]) -> Any:
    seen: set[str] = set()
    while is_var(t) and t in b and t not in seen:
        seen.add(t)
        t = b[t]
    return t


def unify(a: Any, b: Any, binding: dict[str, Any], *, rel: bool = False) -> Optional[dict[str, Any]]:
    """Unify two terms under `binding`, returning an EXTENDED binding or None. `rel=True` compares as
    relations (case-fold only), else as entities (loose `_norm`)."""
    a, b = _walk(a, binding), _walk(b, binding)
    if is_var(a):
        nb = dict(binding); nb[a] = b; return nb
    if is_var(b):
        nb = dict(binding); nb[b] = a; return nb
    same = (_rel(a) == _rel(b)) if rel else _same_term(a, b)
    return binding if same else None


def unify_triple(pat: Fact, fact: Fact, binding: dict[str, Any]) -> Optional[dict[str, Any]]:
    b = unify(pat[1], fact[1], binding, rel=True)      # relation first (cheapest discriminator)
    if b is None:
        return None
    b = unify(pat[0], fact[0], b)
    if b is None:
        return None
    return unify(pat[2], fact[2], b)


# ── proof trees ──────────────────────────────────────────────────────────────────────────────────
@dataclass
class Step:
    """One node of a derivation. `kind` ∈ fact | rule | kernel. `conclusion` is the ground fact this
    step establishes; `premises` are the sub-derivations it rests on (empty for a fact leaf)."""
    conclusion: Fact
    kind: str
    detail: str = ""
    premises: list["Step"] = field(default_factory=list)

    def hops(self) -> int:
        """Number of grounded leaves (stored facts + kernel applications) — the derivation's LENGTH.
        A single lookup has hops 1; a genuine multi-step derivation has hops >= 2."""
        if not self.premises:
            return 1
        return sum(p.hops() for p in self.premises)

    def depth(self) -> int:
        return 1 + max((p.depth() for p in self.premises), default=0)

    def leaves(self) -> list[Fact]:
        if not self.premises:
            return [self.conclusion]
        out: list[Fact] = []
        for p in self.premises:
            out.extend(p.leaves())
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"conclusion": list(self.conclusion), "kind": self.kind, "detail": self.detail,
                "premises": [p.to_dict() for p in self.premises]}

    def pretty(self, indent: int = 0) -> str:
        pad = "  " * indent
        s = f"{pad}{self.conclusion[0]} -{self.conclusion[1]}-> {self.conclusion[2]}  [{self.kind}"
        s += f":{self.detail}]" if self.detail else "]"
        for p in self.premises:
            s += "\n" + p.pretty(indent + 1)
        return s


# ── rules & kernels ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Rule:
    name: str
    head: Fact
    body: list[Fact]

    def rename(self, n: int) -> "Rule":
        """Standardize apart: suffix every variable with #n so recursive re-use of a rule never
        collides variables across derivation levels."""
        def r(t: Any) -> Any:
            return f"{t}#{n}" if is_var(t) else t
        return Rule(self.name, (r(self.head[0]), self.head[1], r(self.head[2])),
                    [(r(a), p, r(o)) for (a, p, o) in self.body])


@dataclass
class KernelBinding:
    """Bind a relation to a verified KernelForge skill. To derive (E, out_rel, ?y): derive each input
    fact (E, in_rel_i, ?v_i) [typed numeric literal], then y = kernel(name)(v_1..v_n). The kernel is
    applied ONLY if it is in the held-out-gated library — an unverified kernel can never fire
    (작화0). Integer-v1 remains the default; rational-v1 is exact Fraction arithmetic."""
    out_rel: str
    inputs: list[tuple[str, str]]        # [(input_relation, kernel_var_name), ...]
    kernel_name: str


def default_rules() -> list[Rule]:
    """The backward Horn rules, single-sourced from `deduction.py`'s relation algebra so the forward
    closure and the backward chainer reason with the IDENTICAL rule set. Variables are ?x ?y ?z."""
    from packages.reasoning_vm import deduction as D
    rules: list[Rule] = []
    for p in sorted(D.TRANSITIVE):
        rules.append(Rule(f"transitive[{p}]", ("?x", p, "?z"), [("?x", p, "?y"), ("?y", p, "?z")]))
    for p in sorted(D.SYMMETRIC):
        rules.append(Rule(f"symmetric[{p}]", ("?x", p, "?y"), [("?y", p, "?x")]))
    for (p, q), r in D.COMPOSE.items():
        # compose is directional; keep the head relation r, body p then q
        rules.append(Rule(f"compose[{p}∘{q}⇒{r}]", ("?x", r, "?z"), [("?x", p, "?y"), ("?y", q, "?z")]))
    return rules


# ── the resolver ─────────────────────────────────────────────────────────────────────────────────
class BackChainer:
    """Backward-chaining derivation over facts ∪ rules ∪ kernels, subject-bound (matches the store's
    facts_about(subject) API and stays efficient on the 100M+ triple graph). Bounded by max_depth
    (rule-application chain length), max_leaves (proof size), and a per-derivation node budget so a
    hub near the top of a taxonomy cannot blow up the walk."""

    def __init__(self, facts_about: FactsAbout, *, rules: Optional[list[Rule]] = None,
                 kernels: Optional[list[KernelBinding]] = None,
                 inherit_props: Optional[Callable[[str], list[Fact]]] = None,
                 max_depth: int = 5, max_leaves: int = 24, budget: int = 4000):
        self.fa = facts_about
        self.rules = default_rules() if rules is None else rules
        self.kernels: dict[str, list[KernelBinding]] = {}
        for kb in (kernels or []):
            self.kernels.setdefault(_rel(kb.out_rel), []).append(kb)
        # type-inheritance is higher-order (predicate is a variable); handled specially, optionally
        # sourced from an inherit_props(type)->[(type,pred,val)] accessor (the store, a dict, …).
        self.inherit_props = inherit_props
        self.max_depth = max_depth
        self.max_leaves = max_leaves
        self.budget = budget
        self._n = 0
        self._rn = 0

    def kernel_bindings(self) -> list[KernelBinding]:
        return [binding for bindings in self.kernels.values() for binding in bindings]

    # -- facts ------------------------------------------------------------------------------------
    def _facts_of(self, subject: str) -> list[Fact]:
        try:
            return [(str(s), str(p), str(o)) for (s, p, o) in (self.fa(subject) or [])]
        except Exception:
            return []

    # -- the core generator ------------------------------------------------------------------------
    def solve(self, goal: Fact, binding: dict[str, Any], depth: int,
              stack: frozenset) -> Iterator[tuple[dict[str, Any], Step]]:
        """Yield (extended_binding, proof_step) for every way to derive `goal`."""
        self._n += 1
        if self._n > self.budget:
            return
        g = (_walk(goal[0], binding), goal[1], _walk(goal[2], binding))
        subj = g[0]
        # cycle guard on GROUND goals only. A variable-object goal (X p ?y) and its transitive body
        # (X p ?y') share the coarse key (X,p,?), so guarding them would self-block the very
        # transitivity we need (city→…→planet, is_a→…→ancestor); those terminate on the depth bound
        # instead. Ground goals (X p o) are guarded exactly, killing genuine (X p o)→…→(X p o) loops.
        is_ground = (not is_var(subj)) and (not is_var(g[2]))
        if is_ground:
            key = (_norm(subj), _rel(g[1]), _norm(g[2]))
            if key in stack:
                return
            stack2 = stack | {key}
        else:
            stack2 = stack

        # 1) FACT — the base case. Needs a bound subject (subject-indexed store).
        if not is_var(subj):
            for f in self._facts_of(subj):
                b2 = unify_triple(g, f, binding)
                if b2 is not None:
                    yield b2, Step((f[0], f[1], f[2]), "fact")

        if depth >= self.max_depth:
            return

        # 2) RULES — DECOMPOSE the goal into the rule body's sub-goals, derive each.
        for rule in self.rules:
            if _rel(rule.head[1]) != _rel(g[1]):            # cheap relation filter
                continue
            self._rn += 1
            rr = rule.rename(self._rn)
            b2 = unify_triple(g, rr.head, binding)
            if b2 is None:
                continue
            for b3, sub_steps in self._solve_conj(rr.body, b2, depth + 1, stack2):
                concl = (_walk(rr.head[0], b3), rr.head[1], _walk(rr.head[2], b3))
                if is_var(concl[0]) or is_var(concl[2]):
                    continue                                # only emit fully-ground conclusions
                step = Step(concl, "rule", rule.name, sub_steps)
                if len(step.leaves()) <= self.max_leaves:
                    yield b3, step

        # 2b) TYPE INHERITANCE — (X ?pred ?val) :- (X is_a T), (T ?pred ?val). Higher-order (the
        #     predicate is a variable), so handled specially: derive EVERY type T of the subject —
        #     direct OR transitive is_a, via the chainer itself — then inherit T's matching property.
        #     Deriving T through solve() is what makes "Socrates is_a philosopher, philosopher is_a
        #     human, human has_property mortal ⊢ Socrates has_property mortal" chain end-to-end.
        if (self.inherit_props is not None and not is_var(subj)
                and _rel(g[1]) not in ("is_a", "instance_of")):
            seen_t: set[str] = set()
            for bt, tstep in self.solve((subj, "is_a", "?T"), binding, depth + 1, stack2):
                T = _walk("?T", bt)
                if is_var(T) or _norm(T) in seen_t:
                    continue
                seen_t.add(_norm(T))
                for (t, hp, hv) in self._inherit_props(T):
                    cand = (subj, hp, hv)
                    b2 = unify_triple(g, cand, binding)
                    if b2 is not None:
                        yield b2, Step((subj, hp, hv), "rule", f"inherit[{T}]",
                                       [tstep, Step((str(t), str(hp), str(hv)), "fact")])

        # 3) KERNELS — derive typed numeric inputs as sub-goals, then run the held-out-gated skill.
        if not is_var(subj):
            for kbind in self.kernels.get(_rel(g[1]), []):
                yield from self._solve_kernel(g, kbind, binding, depth + 1, stack2)

    def _inherit_props(self, type_node: str) -> list[Fact]:
        try:
            return [(str(a), str(p), str(o)) for (a, p, o) in (self.inherit_props(type_node) or [])]
        except Exception:
            return []

    def _solve_conj(self, goals: list[Fact], binding: dict[str, Any], depth: int,
                    stack: frozenset) -> Iterator[tuple[dict[str, Any], list[Step]]]:
        if not goals:
            yield binding, []
            return
        first, rest = goals[0], goals[1:]
        for b1, s1 in self.solve(first, binding, depth, stack):
            for b2, srest in self._solve_conj(rest, b1, depth, stack):
                yield b2, [s1] + srest

    def _solve_kernel(self, g: Fact, kbind: KernelBinding, binding: dict[str, Any], depth: int,
                      stack: frozenset) -> Iterator[tuple[dict[str, Any], Step]]:
        from packages.reasoning_vm.deliberator import kernel_forge as KF
        spec = KF.recall(kbind.kernel_name) or {}
        if not spec.get("accepted"):
            return                                          # unverified kernel never fires (작화0)
        binding_vars = [var for _in_rel, var in kbind.inputs]
        if binding_vars != list(spec.get("vars") or []):
            return                                          # execution/proof input order must agree
        subj = g[0]
        inputs: dict[str, Any] = {}
        premises: list[Step] = []
        cur = binding
        for in_rel, var in kbind.inputs:
            sub = (subj, in_rel, "?_k")
            got = next(iter(self.solve(sub, cur, depth, stack)), None)
            if got is None:
                return                                      # a missing input → no derivation, no guess
            b_i, step_i = got
            val = _walk("?_k", b_i)
            inputs[var] = val                               # KernelForge applies the registered DSL
            premises.append(step_i)
            cur = {k: v for k, v in b_i.items() if k != "?_k"}
        try:
            out = KF.apply(kbind.kernel_name, inputs)
            out_text = str(out)
        except Exception:
            return
        if is_var(g[2]):
            b2 = unify(g[2], out_text, cur)
        else:
            # Numeric proof identity is exact, not entity-name normalization (which strips '.'
            # and could conflate decimal strings). This also lets 0.5 match canonical 1/2.
            from packages.evolution import rational_evolver as revo
            limits = dict(spec.get("limits") or {}) if spec.get("dsl") == revo.DSL else {}
            max_bits = limits.get("max_bits", revo.DEFAULT_MAX_BITS)
            max_exp10 = limits.get("max_exp10", revo.DEFAULT_MAX_EXP10)
            expected = revo.parse_value(_walk(g[2], cur), max_bits=max_bits, max_exp10=max_exp10)
            actual = revo.parse_value(out_text, max_bits=max_bits, max_exp10=max_exp10)
            # Every current KernelForge DSL is numeric. Never fall through to entity-name
            # normalization, which deliberately strips punctuation and can create false proofs.
            b2 = dict(cur) if expected is not None and expected == actual else None
        if b2 is not None:
            yield b2, Step((subj, g[1], out_text), "kernel", kbind.kernel_name, premises)

    # -- public entry points -----------------------------------------------------------------------
    def prove(self, goal: Fact) -> Optional[tuple[dict[str, Any], Step]]:
        """First VERIFIED derivation of a (possibly variable-carrying) goal, or None. The returned
        proof has passed `verify_proof` — every leaf re-checked, forward-closure cross-confirmed."""
        self._n = 0
        for b, step in self.solve(goal, {}, 0, frozenset()):
            if verify_proof(
                step, self.fa, inherit_props=self.inherit_props,
                kernel_bindings=self.kernel_bindings(),
            ):
                return b, step
        return None

    def derive(self, subject: str, relation: str) -> dict[str, Any]:
        """Derive the object of (subject, relation, ?answer): {answer, fired, hops, proof, ...}.
        `fired` marks a genuine MULTI-STEP derivation (hops >= 2) vs a single stored lookup (hops 1);
        `answer` is None (honest abstain) when nothing verified — never a fabricated value."""
        res = self.prove((subject, relation, "?answer"))
        if res is None:
            return {"answer": None, "fired": False, "grounded": False, "hops": 0,
                    "proof": None, "basis": "no verified derivation"}
        b, step = res
        ans = _walk("?answer", b)
        hops = step.hops()
        return {"answer": ans, "grounded": True, "fired": hops >= 2, "hops": hops,
                "depth": step.depth(), "kind": step.kind, "proof": step,
                "basis": step.detail or step.kind, "trail": step.pretty()}

    def can_prove(self, subject: str, relation: str, obj: str) -> dict[str, Any]:
        """Is the ground fact (subject, relation, obj) derivable & verified? {provable, hops, proof}."""
        res = self.prove((subject, relation, obj))
        if res is None:
            return {"provable": False, "hops": 0, "proof": None}
        _b, step = res
        return {"provable": True, "hops": step.hops(), "depth": step.depth(), "proof": step,
                "trail": step.pretty()}


# ── verification: the membrane (backward PROPOSE → forward VERIFY) ─────────────────────────────────
_BUILTIN_ALGEBRA = ("transitive[", "symmetric[", "compose[", "inherit[")


def verify_proof(step: Step, facts_about: FactsAbout, *,
                 inherit_props: Optional[Callable[[str], list[Fact]]] = None,
                 kernel_bindings: Optional[list[KernelBinding]] = None) -> bool:
    """Independently re-verify a proposed derivation — 작화0's teeth. Applied to EVERY node, bottom-up:

      • FACT leaf   — re-read from the graph; it must still be a stored fact, else reject.
      • KERNEL step — premises must match a trusted KernelBinding (subject, relations, variable order),
                      then the held-out-gated kernel is RE-RUN and must reproduce its stated output.
      • RULE step over the BUILT-IN relation algebra (transitive/symmetric/compose/inherit) — an
                      INDEPENDENT forward-closure confirmation: run `deduction.deduce` (the separate
                      forward engine) over this step's own leaves; its conclusion must appear in the
                      forward closure. Backward proposes, forward confirms — two engines agree.
      • RULE step over a CUSTOM Horn clause (e.g. grandparent_of) or an explicit chain — certified
                      STRUCTURALLY: every premise is itself a re-verified derivation resting on real
                      stored facts, and the clause is a declared rule the chainer only fires with a
                      fully-satisfied body. (deduction.py's fixed algebra can't reproduce a custom
                      relation, so the forward cross-check is not applicable there; the leaf-grounding
                      guarantee still holds — no fabricated fact can enter.)

    Any failure anywhere → the whole proof is rejected."""
    from packages.reasoning_vm import deduction as D

    def _fact_in_kb(f: Fact) -> bool:
        def _hit(rows) -> bool:
            return any(unify_triple(f, (str(a), str(p), str(o)), {}) is not None
                       for (a, p, o) in (rows or []))
        try:
            if _hit(facts_about(f[0])):
                return True
        except Exception:
            pass
        if inherit_props is not None:                      # inheritable property facts live here, not
            try:                                           # in facts_about — check both for the leaf.
                if _hit(inherit_props(f[0])):
                    return True
            except Exception:
                pass
        return False

    def _closure_confirms(s: Step) -> bool:
        stated = {_norm_fact(f) for f in s.leaves()}
        goal = _norm_fact(s.conclusion)
        if goal in stated or len(stated) <= 1:
            return True
        res = D.deduce(stated, max_depth=max(2, s.depth() + 1), inherit_props=_props_for(s))
        return goal in res.facts()

    def _verify(s: Step) -> bool:
        if s.kind == "fact":
            return _fact_in_kb(s.conclusion)
        if not all(_verify(p) for p in s.premises):
            return False
        if s.kind == "kernel":
            from packages.reasoning_vm.deliberator import kernel_forge as KF
            spec = KF.recall(s.detail)
            if not spec or not spec.get("accepted"):
                return False
            names = list(spec.get("vars") or [])
            for binding in (kernel_bindings or []):
                if binding.kernel_name != s.detail or _rel(binding.out_rel) != _rel(s.conclusion[1]):
                    continue
                if [var for _relation, var in binding.inputs] != names:
                    continue
                if len(binding.inputs) != len(s.premises):
                    continue
                subject = str(s.conclusion[0])
                if any(
                    str(premise.conclusion[0]) != subject
                    or _rel(premise.conclusion[1]) != _rel(input_relation)
                    for premise, (input_relation, _var) in zip(s.premises, binding.inputs)
                ):
                    continue
                vals = [premise.conclusion[2] for premise in s.premises]
                try:
                    got = KF.apply(s.detail, dict(zip(names, vals)))
                except Exception:
                    continue
                if str(got) == str(s.conclusion[2]):
                    return True
            return False
        # rule / inherit / chain node
        if (s.detail or "").startswith(_BUILTIN_ALGEBRA):
            return _closure_confirms(s)                    # independent forward confirmation
        return True                                        # custom Horn clause: leaf-grounded + declared

    return _verify(step)


def _all_steps(step: Step) -> list[Step]:
    out = [step]
    for p in step.premises:
        out.extend(_all_steps(p))
    return out


def _norm_fact(f: Fact) -> Fact:
    return (_proof_norm(f[0]), _rel(f[1]), _proof_norm(f[2]))


def _props_for(step: Step) -> Optional[dict[str, list[Fact]]]:
    """Build the inherit_props map deduce() needs, from any inherit[...] nodes in the proof (so the
    forward cross-check can reproduce a type-inheritance conclusion). Uses only facts already in the
    proof — no new lookups, so the cross-check stays independent of live store state."""
    props: dict[str, list[Fact]] = {}
    for s in _all_steps(step):
        if s.kind == "rule" and (s.detail or "").startswith("inherit[") and len(s.premises) == 2:
            isa, prop = s.premises[0].conclusion, s.premises[1].conclusion
            t = _proof_norm(isa[2])
            props.setdefault(t, []).append(
                (_proof_norm(prop[0]), _rel(prop[1]), _proof_norm(prop[2]))
            )
    return props or None
