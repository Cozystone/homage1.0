# -*- coding: utf-8 -*-
"""X3 of the redirected explosion engine — a MAP-Elites / Quality-Diversity DIVERGENT archive
(owner 2026-07-23; see docs/ATANOR_intelligence_explosion_research.md, deficit-1 "발산 아카이브").

WHY THIS FILE REPLACES THE CONVERGENT (smallest-per-signature) ARCHIVE
----------------------------------------------------------------------
`auto_curriculum._admit` keeps exactly ONE program per behavioural SIGNATURE — the smallest. That is a
CONVERGENT archive: two structurally-different programs that compute the same function collapse to one,
and any alternative SPELLING of an already-reachable function is discarded as a `dup`. X2 (the e-graph
tier-opening miner) proved its multiplicative mechanism works — it finds abstractions modulo the
equational theory that naive anti-unification misses — but ④ PLATEAUED: those abstractions were just
alternative spellings of functions already in the convergent library, so mining them produced search
noise, no leverage. X2's own diagnosis: multiplicative reuse needs a DIVERGENT archive of diverse
stepping stones to compound. That is this module.

THE MECHANISM (MAP-Elites: an elite per behavioural-structural NICHE)
---------------------------------------------------------------------
Instead of one-smallest-per-signature, maintain an elite per NICHE, where a niche is a cell of a
behavioural DESCRIPTOR. Diverse stepping stones then ACCUMULATE (different niches) instead of collapsing
— structurally-distinct spellings of the same OR different functions are all retained, so:
  * the abstraction miner (X2) has DIVERSE raw material to anti-unify -> more / better tier-opening
    templates;
  * `compose_target` has DIVERSE building blocks to recombine -> compositions reach NEW behavioural
    regions the convergent library could not seed.

THE DESCRIPTOR (niche coordinates) — 3 dimensions, documented honestly
----------------------------------------------------------------------
  d0  BEHAVIOUR   = the exact functional signature over the family's fixed probe battery. Making the
                    behaviour dimension EXACT (not a coarse bin) guarantees the archive is a strict
                    SUPERSET of the convergent one — no distinct capability is ever lost to a bucket
                    collision, so `distinct_solved` (distinct FUNCTIONS) stays honest.
  d1  PRIMITIVES  = the set of primitive tags used (operator-resolved: `op:+`, `op:*`, `fold:+`, `if`,
                    `len`, `map`, `filter`, `let`, `cmp:>` ...). The "how it is built" axis: `a+a` and
                    `a*2` compute the SAME function but occupy DIFFERENT niches (the convergent archive
                    keeps only the smaller). This is the axis that preserves diverse spellings.
  d2  DEPTH-BIN   = tree depth // 2. A coarse structural-complexity axis: compact and elaborated
                    programs coexist as distinct stepping stones.
ELITE per niche = the SMALLEST program (parsimony), deterministic tie-break by source string. Diversity
is the point and it lives ACROSS niches; within a niche we still keep the cleanest representative.

HONESTY. This is a divergent LIBRARY of building blocks; it does NOT change the honest metric. The
number of distinct FUNCTIONS is still `len(distinct_sigs(archive))` — niches are a superset (structural
variants inflate niche count, never the function count). `diversity()` reports both so the A/B can show
the archive did not collapse to smallest-per-signature.

SAFETY / No-LLM. Pure structural computation over the whitelisted tuple-tree grammar (size / depth /
primitive-tag walks + `to_source` for a deterministic tie-break key). Nothing is evaluated, exec'd, or
learned from a corpus. Total and side-effect-free apart from the explicit `archive` dict it mutates.
"""
from __future__ import annotations

from typing import Any

from packages.evolution.code_evolver import to_source

# Delimiters chosen to never collide with signature text (comma-joined ints, possibly negative) or the
# primitive tags (which contain +, -, *, //, %, :). "‖" separates descriptor fields; "|" joins prims.
_FIELD = "‖"   # ‖
_PRIM = "|"


def _is_node(t: Any) -> bool:
    return isinstance(t, (tuple, list)) and len(t) > 0


def _child_nodes(t: Any):
    """Yield the tuple/list CHILDREN of a node (scalar slots — operator symbols, var names, const ints,
    bare list-var strings — are skipped). Uniform over the whole grammar: op/cmp/fold/if/len/let and the
    map/filter list sources, so depth and primitive walks need no per-tag special-casing."""
    if not _is_node(t):
        return
    for c in t[1:]:
        if _is_node(c):
            yield c


def depth(t: Any) -> int:
    """Structural depth — the longest chain of nested nodes (list sources included). A leaf is 1."""
    if not _is_node(t):
        return 1
    kids = [depth(c) for c in _child_nodes(t)]
    return 1 + (max(kids) if kids else 0)


def size(t: Any) -> int:
    """Node count — the parsimony measure (mirrors auto_curriculum._size / abstraction.size)."""
    if not _is_node(t):
        return 1
    return 1 + sum(size(c) for c in t[1:] if _is_node(c))


def _collect_prims(t: Any, acc: set) -> None:
    """Accumulate operator-resolved primitive tags. `op`/`fold` carry their operator symbol in slot 1
    (`op:+`, `fold:*`); `cmp` its comparison (`cmp:>`); `if`/`len`/`let`/`map`/`filter` are bare tags.
    `var`/`const` are leaves (no primitive). Recurse into every child node (value slots + list sources)."""
    if not _is_node(t):
        return
    tag = t[0]
    if tag in ("op", "fold") and len(t) > 1 and isinstance(t[1], str):
        acc.add(f"{tag}:{t[1]}")
    elif tag == "cmp" and len(t) > 1 and isinstance(t[1], str):
        acc.add(f"cmp:{t[1]}")
    elif tag in ("if", "len", "let", "map", "filter"):
        acc.add(tag)
    for c in _child_nodes(t):
        _collect_prims(c, acc)


def primitives(t: Any) -> tuple:
    """The sorted tuple of distinct primitive tags used — the descriptor's 'how it is built' axis."""
    acc: set = set()
    _collect_prims(t, acc)
    return tuple(sorted(acc))


def descriptor(tree: Any, sig: str) -> tuple:
    """The niche coordinates: (behaviour signature, primitive-usage tuple, depth-bin). Behaviour is the
    EXACT signature (superset guarantee); primitive-usage + depth-bin are the structural diversity axes."""
    return (sig, primitives(tree), depth(tree) // 2)


def key_of(desc: tuple) -> str:
    """A JSON-safe string identity for a descriptor (dict keys must be hashable + serialisable across the
    curriculum-state round-trip). The structured fields are also stored in the record, so the key is only
    an identity, never parsed back."""
    sig, prims, dbin = desc
    return f"{sig}{_FIELD}{_PRIM.join(prims)}{_FIELD}{dbin}"


def _record(tree: Any, sig: str, sz: int, program: str, desc: tuple) -> dict:
    return {"tree": tree, "sig": sig, "size": sz, "program": program,
            "prim": desc[1], "depth_bin": desc[2]}


def _evict_one(archive: dict, incoming_sig: str) -> bool:
    """Make room WITHOUT losing a distinct function: evict the least-valuable stepping stone (largest
    elite) among niches whose signature has >= 2 niches (a structural duplicate), never the last niche
    of a signature. Returns False when no such eviction exists (all sigs are singletons) — the caller
    then rejects the insert rather than dropping a capability."""
    counts: dict[str, int] = {}
    for rec in archive.values():
        counts[rec["sig"]] = counts.get(rec["sig"], 0) + 1
    evictable = [(rec["size"], k) for k, rec in archive.items()
                 if counts[rec["sig"]] >= 2]
    if not evictable:
        return False
    evictable.sort(reverse=True)                        # largest elite first (least parsimonious)
    del archive[evictable[0][1]]
    return True


def insert(archive: dict, tree: Any, sig: str, sz: int, program: str, *, cap: int = 160) -> str:
    """Add a solved program to the MAP-Elites archive. Returns:
      'new_niche'      — first program in its niche (a new stepping stone),
      'elite_improved' — a strictly smaller (or tie-broken-earlier) program replaced the niche elite,
      'kept'           — the niche already holds a better/equal elite; unchanged,
      'reject'         — the archive is at `cap` and no structural duplicate could be evicted.
    A niche is (signature, primitive-usage, depth-bin); the elite is the smallest program in it."""
    desc = descriptor(tree, sig)
    k = key_of(desc)
    rec = archive.get(k)
    if rec is None:
        if len(archive) >= cap and not _evict_one(archive, sig):
            return "reject"
        archive[k] = _record(tree, sig, sz, program, desc)
        return "new_niche"
    if sz < rec["size"] or (sz == rec["size"] and program < rec["program"]):
        archive[k] = _record(tree, sig, sz, program, desc)
        return "elite_improved"
    return "kept"


def elites(archive: dict) -> list:
    """The diverse stepping stones — one elite tree per niche, deterministically ordered by (size,
    source) so the library the solver/composer sees is reproducible run-to-run."""
    recs = sorted(archive.values(), key=lambda r: (r["size"], r["program"]))
    return [r["tree"] for r in recs]


def distinct_sigs(archive: dict) -> set:
    """The set of distinct behavioural signatures — the honest 'distinct FUNCTIONS' count. A superset
    relationship holds: every function in the convergent archive is here too, plus structural variants."""
    return {r["sig"] for r in archive.values()}


def diversity(archive: dict) -> dict:
    """Archive diversity / coverage vs a convergent (smallest-per-signature) baseline. `niches` is the QD
    entry count; `distinct_sigs` is what a convergent archive would keep; `structural_variants` =
    niches - distinct_sigs is the divergence the convergent archive throws away; `prim_profiles` /
    `depth_bins` report coverage of the two structural axes."""
    sigs = distinct_sigs(archive)
    prims = {r["prim"] for r in archive.values()}
    dbins = {r["depth_bin"] for r in archive.values()}
    return {"niches": len(archive), "distinct_sigs": len(sigs),
            "structural_variants": len(archive) - len(sigs),
            "prim_profiles": len(prims), "depth_bins": len(dbins)}


def restore(raw: Any) -> dict:
    """Rebuild an archive dict from its JSON round-trip (tuples arrive as lists). Trees are re-tupled and
    `prim` restored to a tuple; unknown/empty input yields an empty archive."""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for k, r in raw.items():
        if not isinstance(r, dict):
            continue
        out[k] = {**r, "tree": _as_tree(r.get("tree")), "prim": tuple(r.get("prim", ()))}
    return out


def _as_tree(t: Any) -> Any:
    if isinstance(t, list):
        return tuple(_as_tree(x) for x in t)
    return t
