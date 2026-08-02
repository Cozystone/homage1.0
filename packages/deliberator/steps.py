# -*- coding: utf-8 -*-
"""Steps — the typed sub-goal, the five GROUNDED-ORGAN adapters, and structural decomposition.

Each adapter DISPATCHES one sub-goal to an existing, already-proved organ and returns a uniform
``StepOutcome`` carrying {answer, grounded, certificate}. The contract is the whole safety story:

  * grounded=True  iff the organ actually grounded the sub-goal (a real law fired, an edge was found,
                   a belief was witnessed, an expression evaluated, a program verified). The
                   certificate then names the exact evidence (law + sentence, edge label, witnessed
                   placement, computation, synthesized+verified body).
  * grounded=False iff the organ ABSTAINS. No answer is fabricated; the certificate records WHY it
                   could not be grounded. The controller turns any ungrounded REQUIRED step into a
                   whole-deliberation abstention.

No adapter ever invents a fact. Every ``answer`` is the organ's own grounded output, verbatim.

The organs (READ-only imports; never modified here):
  * mechanism  packages.situation_model.mechanism.answer_mechanism  — how/why (blocked / locked / edge)
  * belief     packages.situation_model.state_tracker.StateTracker  — who-knows-what (witnessed belief)
  * relational packages.base_brain.relational_lookup.resolve_relational — X-of-Y over a graph store
  * arithmetic a small safe AST evaluator here                       — numeric / comparison / boolean
  * predicate  packages.code_reason.code_author.author              — L3: synthesize + VERIFY a program
"""
from __future__ import annotations

import ast
import operator
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# ── grounded organs (imported, never edited) ─────────────────────────────────────────────────────
from packages.situation_model.mechanism import answer_mechanism
from packages.situation_model.state_tracker import StateTracker
from packages.base_brain.relational_lookup import resolve_relational


# organ cost ranks (declared control constants, NOT knowledge): the MEC re-steer schedules cheaper
# organs first so a chain that is going to abstain does so BEFORE paying for expensive synthesis.
COST_RANK: dict[str, int] = {
    "arithmetic": 1,
    "belief": 2,
    "mechanism": 2,
    "relational": 3,
    "predicate": 5,     # L3 program synthesis is the costliest — always last among ready steps
}

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class SubGoal:
    """One ordered, typed sub-goal of a deliberation. ``payload`` carries the organ's inputs; string
    values may contain ``{name}`` placeholders that are filled from earlier steps' verified answers
    (this binding is what makes the deliberation a CHAIN, not a bag of independent lookups).

    ``binds`` optionally names this step's verified answer so a later step can reference it. This is
    the ONLY channel between steps — a mechanical value substitution, never a generated bridge.
    """
    organ: str                                   # mechanism | belief | relational | arithmetic | predicate
    description: str                             # human-readable sub-goal (used in the certificate + abstain msg)
    payload: dict[str, Any] = field(default_factory=dict)
    binds: str | None = None                     # name to bind this step's verified answer under

    def references(self) -> set[str]:
        """The bind-names this sub-goal consumes (its dependencies) — scanned from its payload."""
        names: set[str] = set()
        _walk_placeholders(self.payload, names)
        return names


@dataclass
class StepOutcome:
    """The uniform result of dispatching one sub-goal to its organ."""
    organ: str
    description: str
    answer: Any
    grounded: bool
    certificate: dict[str, Any]
    bind_value: Any = None
    ms: float = 0.0


# ── placeholder machinery (the chain's only inter-step channel) ──────────────────────────────────

def _walk_placeholders(obj: Any, out: set[str]) -> None:
    if isinstance(obj, str):
        out.update(_PLACEHOLDER.findall(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_placeholders(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk_placeholders(v, out)


def _substitute(obj: Any, bindings: dict[str, Any]) -> Any:
    """Fill ``{name}`` placeholders from bindings. A whole-string ``"{name}"`` is replaced by the RAW
    bound value (so a number stays a number); an embedded ``"...{name}..."`` is string-interpolated."""
    if isinstance(obj, str):
        m = _PLACEHOLDER.fullmatch(obj.strip())
        if m and m.group(1) in bindings:
            return bindings[m.group(1)]                 # preserve type (e.g. an int)
        return _PLACEHOLDER.sub(lambda k: str(bindings.get(k.group(1), k.group(0))), obj)
    if isinstance(obj, dict):
        return {k: _substitute(v, bindings) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(_substitute(v, bindings) for v in obj)
    return obj


def _unresolved(obj: Any, bindings: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    _walk_placeholders(obj, refs)
    return {r for r in refs if r not in bindings}


# ── safe arithmetic / comparison evaluator (a real evaluator, not a guess) ───────────────────────

_BINOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_CMPOPS: dict[type, Callable[[Any, Any], bool]] = {
    ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
}


def _safe_eval(node: ast.AST) -> Any:
    """Evaluate a whitelisted numeric/boolean AST. Anything outside the grammar (a NAME, a call, an
    attribute) raises — so an unresolved placeholder or a non-numeric operand can never be guessed at;
    it forces an honest abstention upstream."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"non-numeric constant {node.value!r}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
        v = _safe_eval(node.operand)
        if isinstance(node.op, ast.USub):
            return -v
        if isinstance(node.op, ast.UAdd):
            return +v
        return not v
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.BoolOp):
        vals = [_safe_eval(v) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.Compare):
        left = _safe_eval(node.left)
        for op, comp in zip(node.ops, node.comparators):
            if type(op) not in _CMPOPS:
                raise ValueError("unsupported comparison")
            right = _safe_eval(comp)
            if not _CMPOPS[type(op)](left, right):
                return False
            left = right
        return True
    raise ValueError(f"disallowed expression node {type(node).__name__}")


def safe_arithmetic(expr: str) -> tuple[Any, bool]:
    """Evaluate a numeric/comparison/boolean expression string safely. Returns (value, ok). ok=False
    means the string is not a pure arithmetic expression (e.g. it still holds an unbound name) —
    the caller then ABSTAINS rather than fabricate a number."""
    try:
        tree = ast.parse(str(expr).strip(), mode="eval")
        return _safe_eval(tree), True
    except Exception:
        return None, False


def _coerce_num(x: Any) -> Any:
    if isinstance(x, bool) or isinstance(x, (int, float)):
        return x
    s = str(x).strip()
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return x


# ── a situation-scoped graph store (the relational organ's knowledge source) ─────────────────────

class _MiniStore:
    """A tiny in-memory graph the relational lane resolves against — situation-scoped knowledge, the
    same category the belief tracker uses (facts from the passage, never smuggled world facts). It
    exposes exactly the ``facts_about`` surface resolve_relational consumes."""

    def __init__(self, triples: list[tuple[str, str, Any]]):
        self._t = [(str(s), str(p), o) for (s, p, o) in (triples or [])]

    def facts_about(self, entity: Any, limit: int = 60) -> list[tuple[str, str, str]]:
        key = str(entity).strip().lower()
        return [(s, p, str(o)) for (s, p, o) in self._t if s.lower() == key][:limit]


# ── the five grounded-organ adapters ─────────────────────────────────────────────────────────────

def run_mechanism(question: str, text: str) -> StepOutcome:
    """Mechanism reasoner: how the world WORKS from stated conditions (blocked / locked / at-edge).
    Grounds only when a domain-blind law fires on conditions stated IN THE TEXT; abstains otherwise
    (the honesty floor — it never smuggles a material fact)."""
    r = answer_mechanism(question or "", text or "")
    if r and r.get("supported"):
        return StepOutcome(
            organ="mechanism", description=question, answer=r["answer"], grounded=True,
            bind_value=r["answer"],
            certificate={"organ": "mechanism", "law": r["law"], "evidence": r["evidence"],
                         "reasoning": r["reasoning"], "grounded": True})
    return StepOutcome(
        organ="mechanism", description=question, answer=None, grounded=False, bind_value=None,
        certificate={"organ": "mechanism", "grounded": False,
                     "reason": "no domain-blind law grounded on the stated conditions "
                               "(a material property the text does not give -> abstain)"})


def run_belief(sentences: list[str], kind: str, *, agent: str = "", entity: str = "",
               place: str = "", holder: str = "", subject: str = "") -> StepOutcome:
    """Situation belief tracker: WHO-KNOWS-WHAT from witnessed placements. Grounds a first/second-order
    belief, a location, or a yes/no only when the state was actually tracked; an unwitnessed query
    abstains (the agent was never co-present -> its belief is ungrounded)."""
    t = StateTracker()
    for i, s in enumerate(sentences or []):
        t.ingest(s, i)
    desc = f"{kind}({agent or holder} -> {entity})"
    res = None
    if kind == "believes":
        res = t.believes(agent, entity)
    elif kind == "believes_second":
        res = t.believes_second(holder, subject, entity)
    elif kind == "where_is":
        res = t.where_is(entity)
    elif kind == "loc_yesno":
        res = t.loc_yesno(entity, place)
    if res is not None:
        answer, evidence = res
        return StepOutcome(
            organ="belief", description=desc, answer=answer, grounded=True, bind_value=answer,
            certificate={"organ": "belief", "kind": kind, "answer": answer,
                         "evidence": evidence, "grounded": True,
                         "hedge": ("disjunctive/maybe" if answer == "maybe" else None)})
    return StepOutcome(
        organ="belief", description=desc, answer=None, grounded=False, bind_value=None,
        certificate={"organ": "belief", "kind": kind, "grounded": False,
                     "reason": "state not tracked / agent never co-present with the placement -> abstain"})


def run_relational(query: str, facts: list[tuple[str, str, Any]]) -> StepOutcome:
    """Relational graph lane: X-of-Y resolved from a situation-scoped graph store. Grounds only when
    the entity carries an edge whose label matches the asked relation; otherwise HONEST abstention
    (never the head-noun define)."""
    store = _MiniStore(facts or [])
    r = resolve_relational(query or "", "en", store=store)
    if r and r.get("relational", {}).get("resolved"):
        cert = dict(r.get("reasoning_certificate", {}))
        cert["organ"] = "relational"
        cert["grounded"] = True
        targets = [c for c in cert.get("evidence_concepts", [])[1:]]
        bind = targets[0] if targets else r.get("answer")
        return StepOutcome(
            organ="relational", description=query, answer=r["answer"], grounded=True,
            bind_value=bind, certificate=cert)
    reason = (r.get("answer") if r else "not a relational shape / no store edge for the asked relation")
    return StepOutcome(
        organ="relational", description=query, answer=None, grounded=False, bind_value=None,
        certificate={"organ": "relational", "grounded": False, "reason": reason})


def run_arithmetic(expr: str, *, label: str = "") -> StepOutcome:
    """Safe arithmetic / comparison / boolean evaluator. Grounds a deterministic value; abstains if
    the string is not a pure numeric expression (e.g. an unbound reference survived) — never guesses."""
    value, ok = safe_arithmetic(expr)
    desc = label or f"evaluate {expr}"
    if ok:
        return StepOutcome(
            organ="arithmetic", description=desc, answer=value, grounded=True, bind_value=value,
            certificate={"organ": "arithmetic", "expression": str(expr), "value": value,
                         "grounded": True, "method": "safe AST evaluation (whitelisted operators)"})
    return StepOutcome(
        organ="arithmetic", description=desc, answer=None, grounded=False, bind_value=None,
        certificate={"organ": "arithmetic", "expression": str(expr), "grounded": False,
                     "reason": "not a pure numeric expression (unbound/non-numeric operand) -> abstain"})


def run_predicate(name: str, signature: str, docstring: str, test: str,
                  apply: list[Any] | None = None, *, library: Any = None) -> StepOutcome:
    """L3 predicate check: SYNTHESIZE a small program for the sub-goal and VERIFY it through the
    isolated oracle (code_author.author). Grounds only if a verified body is found; then the verified
    body is APPLIED to the chain's bound arguments. If synthesis abstains, the step abstains (no
    guessed predicate is ever run)."""
    from packages.code_reason import code_author as ca
    from packages.code_reason.authorship_harness import Task
    # optional LIBRARY isolation so a benchmark/test run does not append to the shared authored library
    saved_lib = None
    if library is not None:
        saved_lib, ca.LIBRARY = ca.LIBRARY, library
    try:
        task = Task(name, signature, docstring, test)
        authored = ca.author(task)
    finally:
        if library is not None:
            ca.LIBRARY = saved_lib
    if not (authored.verified and authored.body):
        return StepOutcome(
            organ="predicate", description=docstring, answer=None, grounded=False, bind_value=None,
            certificate={"organ": "predicate", "grounded": False, "signature": signature,
                         "reason": "no program passed the isolated verifier -> abstain over a wrong program"})
    result = None
    applied = None
    if apply is not None:
        applied = [_coerce_num(a) for a in apply]
        try:
            result = _apply_verified_body(signature, authored.body, applied)
        except Exception as e:                       # a verified body should not raise on valid args
            return StepOutcome(
                organ="predicate", description=docstring, answer=None, grounded=False, bind_value=None,
                certificate={"organ": "predicate", "grounded": False, "signature": signature,
                             "reason": f"verified body raised on the supplied arguments: {e!r}"})
    return StepOutcome(
        organ="predicate", description=docstring, answer=result, grounded=True, bind_value=result,
        certificate={"organ": "predicate", "grounded": True, "signature": signature,
                     "synthesized_body": authored.body, "source": authored.source,
                     "verified": True, "applied_args": applied, "result": result,
                     "method": "propose (synthesize) + verify (isolated oracle) + apply"})


def _apply_verified_body(signature: str, body: str, args: list[Any]) -> Any:
    """Compile signature+verified body in code_author's restricted namespace and call it on args.
    Safe only for OUR OWN verified bodies (exactly the namespace code_author certifies them in)."""
    import textwrap
    from packages.code_reason.code_author import _SAFE_BUILTINS
    src = signature + "\n" + textwrap.indent(textwrap.dedent(body).strip(), "    ") + "\n"
    ns: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
    exec(compile(src, "<deliberator-predicate>", "exec", optimize=0), ns)
    fname = re.search(r"def\s+(\w+)", signature).group(1)
    return ns[fname](*args)


# ── dispatch (organ router) ──────────────────────────────────────────────────────────────────────

def dispatch(subgoal: SubGoal, bindings: dict[str, Any] | None = None) -> StepOutcome:
    """Route one sub-goal to its grounded organ, after filling any placeholders from earlier verified
    answers. Times the call so MEC can watch step latency. Never raises to the caller — an organ that
    cannot ground returns grounded=False, which the controller turns into an honest abstention."""
    bindings = bindings or {}
    missing = _unresolved(subgoal.payload, bindings)
    t0 = time.perf_counter()
    if missing:
        out = StepOutcome(
            organ=subgoal.organ, description=subgoal.description, answer=None, grounded=False,
            bind_value=None,
            certificate={"organ": subgoal.organ, "grounded": False,
                         "reason": f"unbound reference(s) {sorted(missing)} — a prior step did not "
                                   f"ground them, so this step cannot proceed"})
        out.ms = (time.perf_counter() - t0) * 1000.0
        return out
    p = _substitute(subgoal.payload, bindings)
    org = subgoal.organ
    try:
        if org == "mechanism":
            out = run_mechanism(p.get("question", subgoal.description), p.get("text", ""))
        elif org == "belief":
            out = run_belief(p.get("sentences", []), p.get("kind", "believes"),
                             agent=p.get("agent", ""), entity=p.get("entity", ""),
                             place=p.get("place", ""), holder=p.get("holder", ""),
                             subject=p.get("subject", ""))
        elif org == "relational":
            out = run_relational(p.get("query", subgoal.description), p.get("facts", []))
        elif org == "arithmetic":
            out = run_arithmetic(p.get("expr", ""), label=subgoal.description)
        elif org == "predicate":
            out = run_predicate(p.get("name", "pred"), p.get("signature", ""),
                                p.get("docstring", subgoal.description), p.get("test", ""),
                                apply=p.get("apply"), library=p.get("library"))
        else:
            out = StepOutcome(org, subgoal.description, None, False, None,
                              certificate={"organ": org, "grounded": False,
                                           "reason": f"unknown organ '{org}'"})
    except Exception as e:                            # defensive: an organ crash is an abstention, not a guess
        out = StepOutcome(org, subgoal.description, None, False, None,
                          certificate={"organ": org, "grounded": False,
                                       "reason": f"organ raised: {e!r}"})
    # preserve the sub-goal's own description/binding intent
    out.description = subgoal.description
    out.ms = (time.perf_counter() - t0) * 1000.0
    return out


# ── structural decomposition (rule/pattern -> ordered typed plan; NEVER generative) ──────────────

# A composition PATTERN maps a multi-step question SHAPE to an ordered list of typed sub-goal
# skeletons. This is the DECOMPOSE step: recognition of a known composite shape, not generation of
# new sub-goals. Each skeleton names the organ and which pieces of the caller-supplied ``grounding``
# it needs. Questions outside the library return None, and the caller supplies an explicit plan
# (also structural — the plan a symbolic decomposer emits).

_REACH_IN_TIME = re.compile(
    r"\b(reach|arrive|arrives?|get|deliver|make it)\b.*\b(in time|on time|within|before the deadline)\b",
    re.IGNORECASE)
_WILL_FIND = re.compile(r"\bwill\s+\w+\s+(find|look|search|open|reach|get)\b", re.IGNORECASE)
_MORE_THAN_ENOUGH = re.compile(
    r"\b(more|greater|larger|bigger|higher|faster)\b.*\bthan\b.*\b(enough|exceed|meets?|threshold|"
    r"charter|minimum|requirement)\b", re.IGNORECASE)


def decompose(question: str, grounding: dict[str, Any]) -> list[SubGoal] | None:
    """Recognize a known composite shape and emit its ordered typed plan, binding the caller's
    ``grounding`` pieces into each sub-goal's payload. Returns None for an unrecognized shape (the
    caller then supplies a declared structural plan). Purely structural — no sub-goal is invented.

    Recognized families:
      * "... reach/deliver ... in time?"  -> [mechanism(route blocked?), relational(detour length),
                                              arithmetic(length <= budget?)]
      * "will <agent> find/open ...?"     -> [belief(where agent looks), mechanism|relational(that place)]
      * "... more/faster than ... enough?" -> [relational(A attr), relational(B attr)|arithmetic threshold]
    """
    q = str(question or "")
    g = grounding or {}

    if _REACH_IN_TIME.search(q) and {"cross_question", "block_text", "detour_query",
                                     "detour_facts", "budget_expr"} <= set(g):
        return [
            SubGoal("mechanism", g["cross_question"],
                    {"question": g["cross_question"], "text": g["block_text"]}, binds="blocked"),
            SubGoal("relational", g["detour_query"],
                    {"query": g["detour_query"], "facts": g["detour_facts"]}, binds="detour_len"),
            SubGoal("arithmetic", "is the detour within the time budget?",
                    {"expr": g["budget_expr"]}, binds="in_time"),
        ]

    if _WILL_FIND.search(q) and {"belief", "second"} <= set(g):
        first = g["belief"]
        second = g["second"]
        return [
            SubGoal("belief", first["description"], first["payload"], binds="place"),
            SubGoal(second["organ"], second["description"], second["payload"], binds="outcome"),
        ]

    if _MORE_THAN_ENOUGH.search(q) and {"attr_a", "attr_b", "compare_expr"} <= set(g):
        return [
            SubGoal("relational", g["attr_a"]["query"],
                    {"query": g["attr_a"]["query"], "facts": g["attr_a"]["facts"]}, binds="a"),
            SubGoal("relational", g["attr_b"]["query"],
                    {"query": g["attr_b"]["query"], "facts": g["attr_b"]["facts"]}, binds="b"),
            SubGoal("arithmetic", "does the comparison meet the threshold?",
                    {"expr": g["compare_expr"]}, binds="verdict"),
        ]

    return None
