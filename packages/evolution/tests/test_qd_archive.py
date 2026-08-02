# -*- coding: utf-8 -*-
"""Sealed gates for X3 — the MAP-Elites / QD DIVERGENT archive (qd_archive.py + auto_curriculum wiring).

Deterministic fixtures, no randomness in the gate assertions. Gates:
  (a) DIVERGENCE   — the archive keeps MULTIPLE diverse elites across niches and does NOT collapse to
                     one-smallest-per-signature; measured coverage strictly exceeds the convergent
                     baseline; the elite-per-niche rule still keeps the parsimonious representative.
  (c) NO-REGRESSION / SAFETY / HONESTY — default OFF is byte-identical (flag + channels), the module
                     never exec/eval's, the non-degeneracy gate (trivial/oversize) is intact, and
                     distinct_solved stays FUNCTION-count honest (never inflated by niches); the X1/X2/X3
                     flags compose independently.
"""
from __future__ import annotations

import random

from packages.evolution import auto_curriculum as ac
from packages.evolution import qd_archive as qd
from packages.evolution.code_evolver import to_source

# --- fixtures (family 'ab'). doub_add / doub_mul / doub_add2 all compute 2a but are spelled differently;
#     sum / prod / max are three further distinct functions. -------------------------------------------
_DOUB_ADD = ("op", "+", ("var", "a"), ("var", "a"))                       # 2a via +      prims{op:+} size3
_DOUB_MUL = ("op", "*", ("var", "a"), ("const", 2))                       # 2a via *      prims{op:*} size3
_DOUB_ADD2 = ("op", "+", ("var", "a"), ("op", "+", ("var", "a"), ("const", 0)))  # 2a via + (bloated) size5
_SUM = ("op", "+", ("var", "a"), ("var", "b"))                            # a+b
_PROD = ("op", "*", ("var", "a"), ("var", "b"))                           # a*b
_MAX = ("if", ("cmp", ">", ("var", "a"), ("var", "b")), ("var", "a"), ("var", "b"))  # max(a,b)
_LIB = [_DOUB_ADD, _DOUB_MUL, _DOUB_ADD2, _SUM, _PROD, _MAX]

_SIG_2A = ac.signature(_DOUB_ADD, "ab")


def _fill(cap: int = 100) -> dict:
    arch: dict = {}
    for t in _LIB:
        qd.insert(arch, t, ac.signature(t, "ab"), ac._size(t), to_source(t), cap=cap)
    return arch


def _convergent_baseline() -> dict:
    """What auto_curriculum's convergent _admit keeps: the SMALLEST program per signature."""
    conv: dict = {}
    for t in _LIB:
        s = ac.signature(t, "ab")
        if s not in conv or ac._size(t) < ac._size(conv[s]):
            conv[s] = t
    return conv


# ===================================================================================================
# GATE (a) — DIVERGENCE
# ===================================================================================================
def test_a_archive_does_not_collapse_to_smallest_per_signature():
    """The load-bearing property: two DIFFERENT spellings of the SAME function (2a via + and via *) are
    BOTH retained as distinct niches, where the convergent archive keeps only one."""
    arch = _fill()
    conv = _convergent_baseline()
    assert len(conv) == 4                                    # convergent collapses to 4 FUNCTIONS
    prims_for_2a = {rec["prim"] for rec in arch.values() if rec["sig"] == _SIG_2A}
    assert ("op:+",) in prims_for_2a and ("op:*",) in prims_for_2a   # both spellings kept, not collapsed
    assert len(arch) > len(conv)                            # STRICTLY more entries than convergent


def test_a_diversity_coverage_exceeds_convergent_baseline():
    """diversity() reports the divergence numerically: niches > distinct_sigs, and the extra is exactly
    the structural variants the convergent archive throws away."""
    arch = _fill()
    div = qd.diversity(arch)
    assert div["distinct_sigs"] == 4                        # four distinct FUNCTIONS
    assert div["niches"] >= 5                               # >= one structural variant retained
    assert div["niches"] > div["distinct_sigs"]            # DIVERGENCE
    assert div["structural_variants"] == div["niches"] - div["distinct_sigs"] >= 1
    assert div["prim_profiles"] >= 3                        # +, *, and if/cmp usage profiles all covered
    # elites() exposes one tree per niche — the diverse stepping-stone set the solver/miner consumes
    assert len(qd.elites(arch)) == div["niches"]


def test_a_elite_per_niche_keeps_the_parsimonious_representative():
    """Within a niche (same signature + primitives + depth-bin) the SMALLEST program is the elite: the
    bloated 2a-via-+ (size 5) must NOT displace the compact 2a-via-+ (size 3)."""
    arch = _fill()
    add_niche = [rec for rec in arch.values()
                 if rec["sig"] == _SIG_2A and rec["prim"] == ("op:+",)]
    assert len(add_niche) == 1 and add_niche[0]["size"] == 3     # smallest kept, bloated variant dropped
    # inserting a still-smaller equivalent improves the elite; a larger one is kept out
    a = dict(arch)
    assert qd.insert(a, _DOUB_ADD2, _SIG_2A, ac._size(_DOUB_ADD2), to_source(_DOUB_ADD2)) == "kept"


def test_a_superset_never_loses_a_distinct_function():
    """Divergence is a SUPERSET relationship: every distinct function the convergent archive holds is in
    the QD archive too (behavioural coverage is never sacrificed for structural diversity)."""
    arch = _fill()
    conv = _convergent_baseline()
    assert set(conv.keys()).issubset(qd.distinct_sigs(arch))


def test_a_cap_evicts_a_structural_duplicate_never_the_last_of_a_signature():
    """Bounded archive: at cap, eviction drops a structural DUPLICATE (a sig with >=2 niches), never the
    last representative of a signature — so a distinct function is never lost to the bound."""
    arch = _fill()                                          # sig 2a has 2 niches; the rest are singletons
    n_sigs_before = len(qd.distinct_sigs(arch))
    # force one insert at cap == current size: a NEW singleton sig must evict the 2a duplicate, not a unique
    new_fn = ("op", "-", ("op", "*", ("var", "a"), ("var", "a")), ("var", "b"))   # a*a - b, novel sig
    v = qd.insert(arch, new_fn, ac.signature(new_fn, "ab"), ac._size(new_fn), to_source(new_fn),
                  cap=len(arch))
    assert v == "new_niche"
    sigs_after = qd.distinct_sigs(arch)
    assert _SIG_2A in sigs_after                            # 2a still present (only its duplicate dropped)
    assert len(sigs_after) == n_sigs_before + 1            # gained the new function, lost none


# ===================================================================================================
# GATE (c) — NO-REGRESSION / SAFETY / HONESTY
# ===================================================================================================
def test_c_default_off_is_byte_identical_flag_and_channels(monkeypatch):
    """Default (flag unset) does not route through X3, and a round leaves the archive empty — the A/B is
    clean and the committed convergent behaviour is unchanged."""
    monkeypatch.delenv("ATANOR_QD_ARCHIVE", raising=False)
    assert ac._qd_on() is False
    state = ac.new_state()
    assert all(state["niches"][f] == {} for f in ac._FAMILIES)
    ac.autonomous_round(state, random.Random(0), problems=4)
    assert all(state["niches"][f] == {} for f in ac._FAMILIES)   # nothing recorded when off
    assert "qd_niches" not in state["frontier"]
    # default channel is mine-only (measurement: compose/solve dilute; mining is where diversity pays)
    monkeypatch.setenv("ATANOR_QD_ARCHIVE", "1")
    assert ac._qd_on() is True and ac._qd_channels() == {"mine"}


def test_c_flags_compose_independently(monkeypatch):
    """X1 / X2 / X3 flags are read independently, so the harness can set any subset in one process."""
    monkeypatch.setenv("ATANOR_COMPRESSION_DRIVE", "1")
    monkeypatch.setenv("ATANOR_EGRAPH_ABSTRACTION", "1")
    monkeypatch.setenv("ATANOR_QD_ARCHIVE", "1")
    assert ac._drive_on() and ac._egraph_on() and ac._qd_on()
    monkeypatch.setenv("ATANOR_QD_ARCHIVE", "0")
    assert ac._drive_on() and ac._egraph_on() and not ac._qd_on()
    monkeypatch.setenv("ATANOR_QD_CHANNELS", "all")
    assert ac._qd_channels() == {"mine", "compose", "solve"}
    monkeypatch.setenv("ATANOR_QD_CHANNELS", "mine,compose")
    assert ac._qd_channels() == {"mine", "compose"}


def test_c_distinct_solved_stays_function_count_honest(monkeypatch):
    """HONESTY: with X3 on, distinct_solved counts distinct FUNCTIONS (signatures), never niches. The
    archive may hold many more niches (stepping stones) than verified functions — those are diversity,
    not claimed capability."""
    monkeypatch.setenv("ATANOR_COMPRESSION_DRIVE", "1")
    monkeypatch.setenv("ATANOR_EGRAPH_ABSTRACTION", "1")
    monkeypatch.setenv("ATANOR_QD_ARCHIVE", "1")
    state = ac.new_state()
    rec = None
    for _ in range(3):
        rec = ac.autonomous_round(state, random.Random(1), problems=6)
    distinct = rec["frontier"]["distinct_solved"]
    niches = rec["frontier"]["qd_niches"]
    assert distinct == sum(len(state["sigs"][f]) for f in ac._FAMILIES)   # from the verified sig set
    assert niches >= distinct                              # niches are a superset (diversity), never fewer
    # and distinct_solved equals the number of distinct sigs verified, NOT the niche count
    assert distinct == len({s for f in ac._FAMILIES for s in state["sigs"][f]})


def test_c_qd_record_and_harvest_reject_trivial_and_oversize(monkeypatch):
    """The non-degeneracy gate is intact on the QD path: a constant / identity projection (computes
    nothing) and an oversize tree are never recorded as stepping stones."""
    state = ac.new_state()
    assert ac._qd_record(state, "ab", ("const", 5)) == "reject"           # constant
    assert ac._qd_record(state, "ab", ("var", "a")) == "reject"           # identity projection
    big = ("var", "a")
    for _ in range(20):
        big = ("op", "+", big, ("var", "a"))                              # size > _MAX_KEEP_SIZE
    assert ac._qd_record(state, "ab", big) == "reject"
    assert all(state["niches"][f] == {} for f in ac._FAMILIES)            # nothing degenerate admitted
    # a real function IS recorded
    assert ac._qd_record(state, "ab", _SUM) == "new_niche"


def test_c_wiring_qd_on_populates_archive_and_diverges(monkeypatch):
    """WIRING: with X3 on, a few rounds populate the archive and it DIVERGES (more niches than verified
    functions) — the divergent stepping stones actually accumulate in the live loop, not just the unit
    fixture."""
    monkeypatch.setenv("ATANOR_COMPRESSION_DRIVE", "1")
    monkeypatch.setenv("ATANOR_EGRAPH_ABSTRACTION", "1")
    monkeypatch.setenv("ATANOR_QD_ARCHIVE", "1")
    monkeypatch.setenv("ATANOR_QD_CHANNELS", "all")       # exercise every consumer channel
    state = ac.new_state()
    for _ in range(3):
        rec = ac.autonomous_round(state, random.Random(2), problems=6)
    assert rec["frontier"]["qd_niches"] > rec["frontier"]["distinct_solved"]   # divergence in the wild
    total_niches = sum(len(state["niches"][f]) for f in ac._FAMILIES)
    assert total_niches == rec["frontier"]["qd_niches"] > 0


def test_c_no_exec_in_module():
    """No-LLM / safety: qd_archive is pure structural computation — never exec/eval/compile/subprocess."""
    import pathlib
    src = pathlib.Path(qd.__file__).read_text(encoding="utf-8")
    for forbidden in ("eval(", "exec(", "compile(", "__import__(", "os.system", "subprocess"):
        assert forbidden not in src, forbidden


def test_c_archive_survives_state_round_trip():
    """Persistence: the archive (tuple trees, tuple prim-profiles) round-trips through JSON save/load."""
    import json
    state = ac.new_state()
    ac._qd_record(state, "ab", _SUM)
    ac._qd_record(state, "ab", _MAX)
    restored = ac.load_state  # noqa: F841 (referenced for clarity)
    blob = json.dumps(state, ensure_ascii=False)
    back = json.loads(blob)
    arch = qd.restore(back["niches"]["ab"])
    assert len(arch) == 2
    for rec in arch.values():
        assert isinstance(rec["tree"], tuple) and isinstance(rec["prim"], tuple)
        assert isinstance(to_source(rec["tree"]), str)     # a real, renderable tree
