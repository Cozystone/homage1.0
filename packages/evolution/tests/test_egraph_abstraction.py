# -*- coding: utf-8 -*-
"""Sealed gates for X2 — the babble-style tier-opening abstraction miner (egraph_abstraction.py).

Deterministic fixtures. Three gates:
  (a) TIER-OPENING (multiplicative property): on a fixture where naive anti-unification finds only a
      degenerate motif, the e-graph miner finds a real abstraction MODULO the equational theory, and
      that abstraction makes a previously-expensive target cheap (a description-length drop that only
      the modulo recognition unlocks — the tier opens only modulo theory).
  (b) MODULO-THEORY: syntactically-different-but-semantically-equivalent subtrees (a+b/b+a, x/x+0,
      x*1/x, x*0/0, x-x/0, len(map(f,xs))/len(xs)) collapse into one e-class / one abstraction, which
      naive syntactic anti-unification misses.
  (d) SAFETY / NON-REGRESSION: every canonicalisation preserves MEANING (no fabricated equivalence),
      the non-degeneracy gate rejects identities, mining is deterministic and bounded, and the X1/X2
      flags compose in auto_curriculum.
"""
import os
import random

import pytest

from packages.evolution import abstraction as ab
from packages.evolution import compression_progress as cp
from packages.evolution import egraph_abstraction as eg
from packages.evolution.code_evolver import evaluate

# --- shared fixtures: the two commuted forms of the "square-plus-self" motif ------------------------
T1 = ("op", "+", ("var", "a"), ("op", "*", ("var", "a"), ("var", "a")))    # a + a*a
T2 = ("op", "+", ("op", "*", ("var", "b"), ("var", "b")), ("var", "b"))    # b*b + b   (commuted)
P_SRC = "λ(x0). (x0 + (x0 * x0))"


def _rand_envs(n, seed=0):
    rng = random.Random(seed)
    return [{"a": rng.randint(0, 9), "b": rng.randint(0, 9), "x": rng.randint(0, 9),
             "_x": rng.randint(0, 9), "xs": [rng.randint(0, 7) for _ in range(rng.randint(0, 5))]}
            for _ in range(n)]


# ===================================================================================================
# GATE (a) — TIER-OPENING / multiplicative property
# ===================================================================================================
def test_a_naive_misses_but_egraph_finds_the_motif():
    """Naive anti-unification collapses the commuted pair to the degenerate 2-hole `(x0 + x1)` and
    mines NOTHING; the e-graph miner recovers λx. x + x*x (1 hole, shared body >= 2)."""
    lib = [T1, T2]
    naive_sources = [d["source"] for d in ab.mine(lib, top_k=6, min_gain=2)]
    egraph_sources = [d["source"] for d in eg.mine(lib, top_k=6, min_gain=2)]
    assert P_SRC not in naive_sources, f"naive unexpectedly found {P_SRC}: {naive_sources}"
    assert P_SRC in egraph_sources, f"e-graph miner failed to find {P_SRC}: {egraph_sources}"
    rec = next(d for d in eg.mine(lib) if d["source"] == P_SRC)
    assert rec["arity"] == 1                       # a genuine parameterised abstraction, not degenerate
    assert rec["gain"] >= 2


def test_a_multiplicative_property_mdl_tier_opens_only_modulo():
    """Deterministic 'expensive before, cheap after'. Target uses the motif TWICE, once commuted.
    Under a fixed budget the target is over-budget spelled raw AND over-budget with the naive
    (syntactic) template — the commuted occurrence stays expanded — but UNDER budget once the e-graph's
    modulo recognition collapses BOTH occurrences. The tier opens only modulo the equational theory."""
    P = eg.mine([T1, T2])[0]["template"]
    cP = ab.canonical(P)
    # target = (a + a*a) * (a*a + a):  first factor canonical, second factor COMMUTED
    T = ("op", "*", T1, ("op", "+", ("op", "*", ("var", "a"), ("var", "a")), ("var", "a")))

    raw = cp.raw_len(T)                                        # no abstraction: spell every node
    cost_syntactic = cp.mdl_cost(T, frozenset(), (P,))        # naive: syntactic template match only

    def cost_modulo(t):                                        # e-graph: recognise instances modulo theory
        if not (isinstance(t, tuple) and t):
            return 1.0
        binds = ab.match(cP, eg.canonical_form(t), {})
        if binds is not None:
            return 1.0 + sum(cost_modulo(v) for v in binds.values())
        return 1.0 + sum(cost_modulo(c) for c in t[1:] if isinstance(c, tuple))

    cost_mod = cost_modulo(T)
    BUDGET = 7
    assert raw > BUDGET                                        # unreachable/expensive spelled raw
    assert cost_syntactic > BUDGET                            # naive template still over budget (misses commuted)
    assert cost_mod <= BUDGET                                 # modulo abstraction makes it cheap
    assert cost_mod < cost_syntactic < raw                   # strictly monotone: modulo < syntactic < raw


def test_a_commuted_occurrence_only_recognised_modulo():
    """The load-bearing fact behind the tier: the commuted motif `b*b + b` is an instance of P only
    modulo theory — syntactic match misses it, canonical-form (e-graph) match catches it."""
    P = ab.canonical(eg.mine([T1, T2])[0]["template"])
    assert ab.match(P, T2, {}) is None                        # naive syntactic: not an instance
    assert ab.match(P, eg.canonical_form(T2), {}) is not None  # modulo: it IS an instance


# ===================================================================================================
# GATE (b) — MODULO-THEORY equivalences
# ===================================================================================================
X, ZERO, ONE = ("var", "x"), ("const", 0), ("const", 1)


@pytest.mark.parametrize("t1,t2,label", [
    (("op", "+", ("var", "a"), ("var", "b")), ("op", "+", ("var", "b"), ("var", "a")), "a+b == b+a"),
    (X, ("op", "+", X, ZERO), "x == x+0"),
    (("op", "*", X, ONE), X, "x*1 == x"),
    (("op", "*", X, ZERO), ZERO, "x*0 == 0"),
    (("op", "-", X, X), ZERO, "x-x == 0"),
    (("op", "//", X, ONE), X, "x//1 == x"),
    (("op", "%", X, X), ZERO, "x%x == 0"),
    (("len", ("map", ("op", "+", ("var", "_x"), ("const", 1)), "xs")), ("len", "xs"), "len(map)==len"),
])
def test_b_modulo_equivalences(t1, t2, label):
    """Each pair is provably equal under the interpreter's own algebra; naive syntactic equality is not.
    The e-graph merges them into one class."""
    assert t1 != t2, f"{label}: fixtures must be syntactically distinct"
    assert eg.equivalent(t1, t2), f"{label}: e-graph failed to prove equivalence"


def test_b_canonical_form_normalises_identity():
    """x+0 and x*1 canonicalise to the same normal form as x (identity elimination)."""
    assert eg.canonical_form(("op", "+", X, ZERO)) == eg.canonical_form(X)
    assert eg.canonical_form(("op", "*", X, ONE)) == eg.canonical_form(X)


def test_b_modulo_anti_unify_beats_naive_on_commuted_pair():
    """anti_unify_modulo(a+a*a, b*b+b) yields the 1-hole λx.x+x*x; naive anti_unify yields the
    degenerate 2-hole (x0+x1)."""
    naive = ab.canonical(ab.anti_unify(T1, T2))
    modulo = eg.anti_unify_modulo(T1, T2)
    assert ab.holes_in(naive) == 2 and ab.size(naive) - ab._hole_occ(naive) < 2   # degenerate
    assert ab.holes_in(modulo) == 1 and ab.size(modulo) - ab._hole_occ(modulo) >= 2  # real motif
    assert ab._template_source(modulo) == P_SRC


# ===================================================================================================
# GATE (d) — SAFETY / NON-REGRESSION
# ===================================================================================================
def test_d_canonicalisation_preserves_semantics():
    """Every rewrite is behaviour-preserving: the normal form evaluates IDENTICALLY to the original on
    a random env battery (no fabricated equivalence can leak into a mined abstraction)."""
    envs = _rand_envs(60, seed=7)
    trees = [
        T1, T2,
        ("op", "-", ("var", "a"), ("op", "*", ("var", "a"), ("const", 0))),   # a - a*0
        ("op", "//", ("var", "a"), ("const", 1)),                              # a // 1
        ("op", "%", ("var", "a"), ("var", "a")),                               # a % a
        ("op", "+", ("op", "*", ("var", "a"), ("var", "b")), ("const", 0)),    # a*b + 0
        ("if", ("cmp", "<", ("var", "a"), ("var", "b")),
         ("op", "+", ("var", "a"), ("const", 0)), ("var", "b")),               # (a+0 if a<b else b)
        ("len", ("map", ("op", "*", ("var", "_x"), ("const", 2)), "xs")),      # len(map(_x*2, xs))
    ]
    for t in trees:
        assert eg.verify_semantics(t, envs), f"canonicalisation changed meaning of {ab._template_source(t) if ab._is_node(t) else t}"


def test_d_non_degeneracy_gate_rejects_identities():
    """A library whose only shared motif is an IDENTITY must not yield a degenerate abstraction. Given
    [a+0, b+0] the naive miner and the e-graph miner both refuse (no pinned-var, body>=2, no identity).
    The e-graph must NOT be fooled into naming λx.x by its own simplification."""
    lib = [("op", "+", ("var", "a"), ("const", 0)), ("op", "+", ("var", "b"), ("const", 0))]
    mined = eg.mine(lib, top_k=6, min_gain=2)
    for d in mined:
        # never an identity: template body must be >= 2 real nodes and depend on its hole
        assert ab.size(d["template"]) - ab._hole_occ(d["template"]) >= 2
        assert d["arity"] >= 1
        assert d["source"] not in ("λ(x0). x0", "λ(). x")


def test_d_mining_is_deterministic():
    """Same library -> byte-identical mined records (canonicalisation + extraction are deterministic)."""
    lib = [T1, T2, ("op", "*", ("var", "a"), ("op", "+", ("var", "a"), ("var", "b")))]
    r1 = eg.mine(lib, top_k=6, min_gain=2)
    r2 = eg.mine(lib, top_k=6, min_gain=2)
    assert [(d["source"], d["gain"], d["arity"]) for d in r1] == \
           [(d["source"], d["gain"], d["arity"]) for d in r2]


def test_d_egraph_is_bounded_on_large_tree():
    """Saturation is bounded (capped e-nodes + iterations): a deep nested tree canonicalises without
    hanging or exploding, and the result still preserves meaning."""
    t = ("var", "a")
    for _ in range(40):
        t = ("op", "+", t, ("op", "*", ("var", "a"), ("const", 1)))   # deep, with x*1 identities
    c = eg.canonical_form(t)                                            # must terminate
    env = {"a": 3}
    assert evaluate(c, env) == evaluate(t, env)


def test_d_x1_x2_flags_compose_in_auto_curriculum(monkeypatch):
    """X2 is composable with X1: the two flags are read independently, and X2 swaps the miner while the
    downstream semantic admission gate is unchanged."""
    from packages.evolution import auto_curriculum as ac
    monkeypatch.setenv("ATANOR_COMPRESSION_DRIVE", "1")
    monkeypatch.setenv("ATANOR_EGRAPH_ABSTRACTION", "1")
    assert ac._drive_on() is True and ac._egraph_on() is True
    monkeypatch.setenv("ATANOR_EGRAPH_ABSTRACTION", "0")
    assert ac._drive_on() is True and ac._egraph_on() is False
    # _mine_for dispatches to the e-graph miner only when flagged
    monkeypatch.setenv("ATANOR_EGRAPH_ABSTRACTION", "1")
    got = ac._mine_for([T1, T2], top_k=6, min_gain=2)
    assert any(d["source"] == P_SRC for d in got)


def test_d_no_exec_in_module():
    """No-LLM / safety: the miner never exec/eval/compiles — it only INTERPRETS via code_evolver."""
    import inspect
    src = inspect.getsource(eg)
    for forbidden in ("exec(", "eval(", "compile(", "__import__"):
        assert forbidden not in src, f"egraph_abstraction must not use {forbidden}"
