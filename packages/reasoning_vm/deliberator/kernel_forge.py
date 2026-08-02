# -*- coding: utf-8 -*-
"""DELIBERATOR organ ⑤ — KernelForge: acquire VERIFIED computation kernels from examples via VibeCode.

The System-2 planner needs executable relations ("energy = h·frequency", "electrons = protons − charge",
"count isomers", "nth term") to chain over. Most are unknown at build time. KernelForge lets the circuit
ACQUIRE such a kernel on demand from input→output examples — VibeCode (No-LLM verifier-guided synthesis)
evolves it, and it enters the skill library ONLY if it passes a HELD-OUT generalization gate
(hallucination-0: a kernel that fits training but fails unseen examples is rejected at the sandbox
boundary). Acquired kernels are interpreted (never exec'd) and carry provenance, so the planner can both
USE them and cite them.

Honest scope: ``integer-v1`` retains VibeCode's integer/list arithmetic for discrete relations.
``rational-v1`` adds exact scalar +, −, ×, and ÷ over bounded ``Fraction`` values with an explicit,
disjoint holdout. It covers algebraic rational formulas, not transcendental functions, uncertainty,
unit inference, or arbitrary floating-point programs. No pretrained LLM anywhere.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
REGISTRY = REPO / "data" / "graph_scale" / "deliberator_kernels" / "registry.json"
INTEGER_DSL = "integer-v1"
RATIONAL_DSL = "rational-v1"


def _ce():
    import sys
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from packages.evolution import code_evolver
    return code_evolver


def _load() -> dict[str, Any]:
    if REGISTRY.exists():
        try:
            data = json.loads(REGISTRY.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _persist(reg: dict[str, Any]) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def _spec_dsl(spec: dict[str, Any]) -> str:
    """Old registry rows predate versioning and are integer kernels by construction."""
    if "dsl" not in spec:
        return INTEGER_DSL
    value = spec.get("dsl")
    return value if type(value) is str else ""


def _registered_schema_valid(spec: dict[str, Any]) -> bool:
    """Fail closed on unknown interpreter or registry schema while retaining legacy integer rows."""
    if type(spec.get("accepted")) is not bool:
        return False
    vars_ = spec.get("vars")
    if not isinstance(vars_, list) or not vars_ or any(type(var) is not str for var in vars_) \
            or len(set(vars_)) != len(vars_):
        return False
    dsl = _spec_dsl(spec)
    schema = spec.get("schema_version")
    encoding = spec.get("value_encoding")
    if dsl == INTEGER_DSL:
        return (schema is None or type(schema) is int and schema == 1) \
            and encoding in (None, "integer-v1")
    if dsl == RATIONAL_DSL:
        return type(schema) is int and schema == 2 \
            and encoding == "fraction-canonical-v1"
    return False


def _same_identity(spec: dict[str, Any], dsl: str, vars_: list[str]) -> bool:
    return _registered_schema_valid(spec) and _spec_dsl(spec) == dsl \
        and list(spec.get("vars") or []) == list(vars_)


def forge(name: str, examples: list[tuple[dict[str, Any], Any]], vars_: list[str], *,
          holdout_frac: float = 0.4, seed: int = 0, persist: bool = True,
          dsl: str = INTEGER_DSL,
          holdout_examples: list[tuple[dict[str, Any], Any]] | None = None,
          **kw: Any) -> dict[str, Any]:
    """Evolve a kernel for `name` from (env, output) examples. Split off a HELD-OUT set the search never
    optimizes against; accept ONLY if it generalizes (holdout fitness 1.0). Persist accepted kernels.

    ``integer-v1`` preserves the historical VibeCode behavior and random split. ``rational-v1`` is an
        additive exact-arithmetic DSL and requires an explicit disjoint holdout; binary floats are rejected.
    """
    import random
    ex = list(examples)
    if dsl not in (INTEGER_DSL, RATIONAL_DSL):
        return {"name": name, "dsl": dsl, "accepted": False, "verdict": "unsupported DSL"}
    existing = _load().get(name)
    if isinstance(existing, dict) and existing.get("accepted") \
            and not _same_identity(existing, dsl, vars_):
        return {"name": name, "dsl": dsl, "vars": list(vars_), "accepted": False,
                "verdict": "kernel name already belongs to a different DSL or variable signature"}

    extra: dict[str, Any] = {}
    if dsl == RATIONAL_DSL:
        if holdout_examples is None:
            return {"name": name, "dsl": dsl, "accepted": False,
                    "verdict": "rational-v1 requires explicit sealed holdout_examples"}
        from packages.evolution import rational_evolver as revo
        train = ex
        holdout = list(holdout_examples)
        limits = {k: v for k, v in kw.items()
                  if k in {"max_nodes", "max_steps", "max_bits", "max_exp10", "max_states"}}
        res = revo.synthesize_verified(train, holdout, vars_, **limits)
        extra = {
            "schema_version": 2,
            "dsl": RATIONAL_DSL,
            "value_encoding": "fraction-canonical-v1",
            "limits": {
                "max_nodes": limits.get("max_nodes", revo.DEFAULT_MAX_NODES),
                "max_steps": limits.get("max_steps", revo.DEFAULT_MAX_STEPS),
                "max_bits": limits.get("max_bits", revo.DEFAULT_MAX_BITS),
                "max_exp10": limits.get("max_exp10", revo.DEFAULT_MAX_EXP10),
                "max_states": limits.get("max_states", revo.DEFAULT_MAX_STATES),
            },
            "train_digest": res.get("train_digest"),
            "holdout_digest": res.get("holdout_digest"),
        }
    else:
        if len(ex) < 4:
            return {"name": name, "dsl": dsl, "accepted": False,
                    "verdict": "need >=4 examples to hold out honestly"}
        random.Random(seed).shuffle(ex)
        k = max(2, int(round(len(ex) * holdout_frac)))
        holdout, train = ex[:k], ex[k:]
        res = _ce().synthesize_verified(train, holdout, vars_, **kw)
        extra = {"schema_version": 1, "dsl": INTEGER_DSL, "value_encoding": "integer-v1"}

    kernel = {
        "name": name, "vars": list(vars_), "program": res.get("program"), "tree": res.get("tree"),
        "holdout_fitness": res.get("holdout_fitness"), "train_fitness": res.get("fitness"),
        "accepted": bool(res.get("accepted")), "verdict": res.get("verdict"),
        "n_examples": len(train) + len(holdout),
        "n_train": len(train), "n_holdout": len(holdout),
        "forged_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "provenance": ("exact-rational:bottom-up-synthesis; explicit disjoint holdout"
                       if dsl == RATIONAL_DSL else
                       "vibecode:verifier-guided-synthesis; held-out generalization gate"),
        **extra,
    }
    if kernel["accepted"] and persist:
        reg = _load()
        reg[name] = kernel
        _persist(reg)
    return kernel


def recall(name: str, *, dsl: str | None = None,
           vars_: list[str] | None = None) -> dict[str, Any] | None:
    spec = _load().get(name)
    if not isinstance(spec, dict) or not _registered_schema_valid(spec):
        return None
    if dsl is not None and _spec_dsl(spec) != dsl:
        return None
    if vars_ is not None and list(spec.get("vars") or []) != list(vars_):
        return None
    return spec


def apply(name: str, inputs: dict[str, Any]) -> int | str:
    """Run an acquired kernel. Interpreted (no exec); raises KeyError if the skill isn't in the library."""
    kernel = recall(name)
    if not kernel or not kernel.get("accepted"):
        raise KeyError(f"no verified kernel named {name!r}")
    names = list(kernel.get("vars") or [])
    if set(inputs) != set(names) or len(inputs) != len(names):
        raise ValueError("kernel inputs must match the registered variables exactly")
    ordered_inputs = {var: inputs[var] for var in names}
    dsl = _spec_dsl(kernel)
    if dsl == RATIONAL_DSL:
        from packages.evolution import rational_evolver as revo
        limits = dict(kernel.get("limits") or {})
        limits.pop("max_states", None)
        out = revo.evaluate(kernel["tree"], ordered_inputs, **limits)
        if out is None:
            raise ValueError("rational kernel input or evaluation failed")
        return revo.canonical(out)
    if dsl == INTEGER_DSL:
        return int(_ce().evaluate(kernel["tree"], ordered_inputs))
    raise ValueError(f"unsupported registered kernel DSL: {dsl!r}")


def acquire_or_recall(name: str, examples: list[tuple[dict[str, Any], Any]], vars_: list[str],
                      *, dsl: str = INTEGER_DSL,
                      holdout_examples: list[tuple[dict[str, Any], Any]] | None = None,
                      **kw: Any) -> dict[str, Any]:
    """The planner's entry point: reuse the skill if the library already holds it, else forge it."""
    have = recall(name, dsl=dsl, vars_=vars_)
    if have and have.get("accepted"):
        return {**have, "source": "recalled"}
    collision = recall(name)
    if collision and collision.get("accepted"):
        return {"name": name, "dsl": dsl, "vars": list(vars_), "accepted": False,
                "source": "rejected", "verdict": "kernel identity collision"}
    return {**forge(name, examples, vars_, dsl=dsl, holdout_examples=holdout_examples, **kw),
            "source": "forged"}


def library() -> list[dict[str, Any]]:
    return [{"name": k, "dsl": _spec_dsl(v), "program": v.get("program"),
             "holdout_fitness": v.get("holdout_fitness")}
            for k, v in sorted(_load().items())
            if isinstance(v, dict) and _registered_schema_valid(v)]
