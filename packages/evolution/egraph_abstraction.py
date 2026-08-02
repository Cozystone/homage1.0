# -*- coding: utf-8 -*-
"""X2 of the redirected explosion engine — a babble-style TIER-OPENING abstraction miner
(owner 2026-07-23; see docs/ATANOR_intelligence_explosion_research.md, deficit-2 "multiplicative reuse").

WHY THIS FILE REPLACES NAIVE ANTI-UNIFICATION FOR MINING
--------------------------------------------------------
`abstraction.py` anti-unifies statement-level SYNTAX. It factors a motif only when two library
subtrees are structurally identical up to their leaves (`a + a*a` vs `c + c*c`). That is an ADDITIVE
lever: it collapses exact repetitions, a constant level-shift on the ④ curve (X1 bent concave->linear).
It CANNOT see that `a + a*a` and `b*b + b` are the SAME motif — they differ by commutativity — so it
returns the degenerate 2-hole `(x0 + x1)` and mines NOTHING. The reusable "square-plus-self" function
is invisible to it. That missed class of motif is the MULTIPLICATIVE pathway (linear->super-linear):
recognising structure MODULO the domain's own equational theory opens a new TIER of reuse.

THE MECHANISM (babble: e-graph + equality saturation + anti-unification over e-classes)
---------------------------------------------------------------------------------------
1. E-GRAPH (`EGraph`): equivalence classes of subtrees over the whitelisted tuple-tree grammar,
   union-find + hash-consed e-nodes (congruence closure). Each e-class holds every expression proven
   equal so far.
2. EQUALITY SATURATION (`EGraph.saturate`): apply the interpreter's OWN algebraic identities as
   rewrites to a bounded fixpoint, merging e-classes. The identities are READ OFF `code_evolver`'s
   interpreter (never invented) — see `THEORY` below, each rule cited to the interpreter line it
   follows from.
3. ANTI-UNIFICATION OVER E-CLASSES (`anti_unify_modulo`): canonicalise each subtree to its normal
   form by EXTRACTING the least-cost member of its e-class (a structure-first, deterministic tie-break
   that puts commutative operands in a canonical order), THEN run the existing syntactic anti-unifier
   on the normal forms. Two structurally-different-but-semantically-equivalent forms now share ONE
   template. This finds tier-opening motifs the naive miner misses.

`mine()` is drop-in compatible with `abstraction.mine()` (same {template, arity, gain, source} records,
same non-degeneracy gates) so `auto_curriculum` / `open_domain` can swap it behind a flag.

HONESTY / propose-verify. Every rewrite is behaviour-preserving BY CONSTRUCTION (each is a true
identity of the interpreter), and `verify_semantics()` re-checks it empirically: the normal form must
evaluate IDENTICALLY to the original on a probe battery, else the canonicalisation is rejected. So
equality saturation can never change meaning — no fabricated equivalence can leak into a mined
abstraction. This is the same evidence discipline as X1: it steers mining, it promotes nothing on its
own (the caller's `_expands_reachable` semantic gate still guards solver admission).

SAFETY / No-LLM. Pure structural computation over the tuple-tree grammar. Nothing is evaluated for
CANONICALISATION except the optional `verify_semantics` self-check, which INTERPRETS (never exec's)
via `code_evolver.evaluate`. Total, bounded (capped e-node count + saturation iterations), no neural
component, no corpus.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from packages.evolution import abstraction as _ab
from packages.evolution.code_evolver import to_source

# ---------------------------------------------------------------------------
# Tree helpers (the same tuple-tree used by code_evolver / auto_curriculum / open_domain).
# A node is a tuple whose first element is a string TAG. A child that is a tuple is a subexpression;
# a non-tuple child (operator symbol, var name, const/int value, bare list-var) is a SCALAR slot.
# ---------------------------------------------------------------------------


def _is_node(t: Any) -> bool:
    return isinstance(t, tuple) and len(t) > 0 and isinstance(t[0], str)


# Commutative + associative binary operators (operator.add / operator.mul on ints).
#   code_evolver._OPS: "+" -> operator.add, "*" -> operator.mul   (code_evolver.py:31-34)
_AC_OPS = {"+", "*"}

# The e-graph serves TWO grammar conventions with the same equational theory:
#   * code_evolver / auto_curriculum:  ("op", opsym, L, R)  with opsym in + - * // %
#   * open_domain:                     (opname, L, R)        with opname in add sub mul idiv mod
# `_OPEN_OP` maps the open-domain TAG to its operator symbol so one set of identity rules covers both.
_OPEN_OP = {"add": "+", "sub": "-", "mul": "*", "idiv": "//", "mod": "%"}


# ===========================================================================
# THE EQUATIONAL THEORY — read off code_evolver's interpreter, NOT invented.
# Each identity is annotated with the interpreter line that makes it TRUE. Only SOUND rules under the
# interpreter's TOTAL, guarded semantics are included (e.g. NOT x//x==1, which fails at x==0 because
# the guard sends 0//0 -> 0; NOT x*x==x). Rules act on e-nodes inside the e-graph (see EGraph._rules).
# ===========================================================================
# Identity/absorption facts, expressed as (op, side, kind):
#   '+'  commutative; x+0 = x            (operator.add;                       code_evolver.py:31,72-76)
#   '*'  commutative; x*1 = x; x*0 = 0   (operator.mul;                       code_evolver.py:31,72-76)
#   '-'  x-0 = x; x-x = 0                 (operator.sub;                       code_evolver.py:31,72-76)
#   '//' x//1 = x; 0//x = 0              (guarded floordiv, b==0 -> 0;         code_evolver.py:33,72-76)
#   '%'  x%1 = 0; 0%x = 0; x%x = 0       (guarded mod,     b==0 -> 0;         code_evolver.py:33,72-76)
#   cmp  a==b <=> b==a; a<b <=> b>a; a<=b <=> b>=a  (operator.eq/lt/gt/le/ge; code_evolver.py:38-40)
#   len(map(body, src)) = len(src)       (map yields one output per input;    code_evolver.py:98-100)
_CMP_SWAP = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}   # a OP b  <=>  b SWAP(OP) a


class EGraph:
    """A small e-graph: equivalence classes of grammar subtrees with congruence closure, plus equality
    saturation over the interpreter's algebraic identities. Bounded (capped e-nodes + iterations) so
    saturation always terminates."""

    MAX_ENODES = 6000
    MAX_ITERS = 12

    def __init__(self) -> None:
        self._parent: dict[int, int] = {}          # union-find over e-class ids
        self._nodes: dict[int, set] = {}           # e-class id -> set of canonical e-nodes
        self._hashcons: dict[tuple, int] = {}      # canonical e-node -> e-class id
        self._next = 0
        self._const_cache: dict[Any, int] = {}
        self._capped = False

    # -- union-find -----------------------------------------------------------
    def _new_class(self) -> int:
        cid = self._next
        self._next += 1
        self._parent[cid] = cid
        self._nodes[cid] = set()
        return cid

    def find(self, cid: int) -> int:
        root = cid
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[cid] != root:            # path compression
            self._parent[cid], cid = root, self._parent[cid]
        return root

    def _canon_enode(self, enode: tuple) -> tuple:
        tag, slots = enode
        return (tag, tuple(("e", self.find(s[1])) if s[0] == "e" else s for s in slots))

    # -- construction ---------------------------------------------------------
    def add(self, tree: Any) -> int:
        """Add a tree, returning its e-class id. Hash-cons e-nodes; recurse into tuple children."""
        if not _is_node(tree):                      # a bare scalar used as a node (defensive)
            return self._add_enode(("__lit__", (("v", tree),)))
        slots = []
        for c in tree[1:]:
            if isinstance(c, tuple):
                slots.append(("e", self.find(self.add(c))))
            else:
                slots.append(("v", c))
        return self._add_enode((tree[0], tuple(slots)))

    def _add_enode(self, enode: tuple) -> int:
        enode = self._canon_enode(enode)
        cid = self._hashcons.get(enode)
        if cid is not None:
            return self.find(cid)
        if len(self._hashcons) >= self.MAX_ENODES:
            self._capped = True                     # honest bound: stop growing, keep what we have
            cid = self._new_class()
            self._nodes[cid].add(enode)
            return cid
        cid = self._new_class()
        self._hashcons[enode] = cid
        self._nodes[cid].add(enode)
        return cid

    def _const(self, v: Any) -> int:
        """The e-class of the integer literal `v`, with the two grammar conventions ('const' n) and
        ('int' n) UNIONED into one class so an identity that introduces a fresh 0/1 is recognised
        regardless of which convention the surrounding program uses."""
        if v not in self._const_cache:
            c = self.add(("const", v))
            c = self.union(c, self.add(("int", v)))
            self._const_cache[v] = c
        return self.find(self._const_cache[v])

    def _is_const(self, cid: int, v: Any) -> bool:
        """Does e-class `cid` contain the integer literal `v`? (Accepts both 'const' and 'int' tags so
        the same e-graph serves code_evolver's ('const', n) and open_domain's ('int', n).)"""
        cid = self.find(cid)
        for tag, slots in self._nodes[cid]:
            if tag in ("const", "int") and len(slots) == 1 and slots[0] == ("v", v):
                return True
        return False

    def _same(self, a: int, b: int) -> bool:
        return self.find(a) == self.find(b)

    # -- merge + congruence closure ------------------------------------------
    def union(self, a: int, b: int) -> int:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return ra
        # keep the smaller id as root for determinism
        if rb < ra:
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._nodes[ra] |= self._nodes[rb]
        self._nodes[rb] = set()
        return ra

    def _rebuild(self) -> bool:
        """Restore congruence: re-canonicalise every e-node; when two e-nodes canonicalise to the same
        form they denote the same value -> union their classes. Iterate to a fixpoint. Returns whether
        anything changed."""
        changed_any = False
        while True:
            self._hashcons = {}
            new_nodes: dict[int, set] = {}
            changed = False
            for cid in list(self._nodes):
                root = self.find(cid)
                bucket = new_nodes.setdefault(root, set())
                for enode in self._nodes[cid]:
                    cen = self._canon_enode(enode)
                    other = self._hashcons.get(cen)
                    if other is None:
                        self._hashcons[cen] = root
                        bucket.add(cen)
                    else:
                        r2 = self.find(other)
                        if r2 != self.find(root):
                            self.union(r2, root)
                            changed = True
            # rebuild _nodes from merged roots
            merged: dict[int, set] = {}
            for cid, enodes in new_nodes.items():
                merged.setdefault(self.find(cid), set()).update(
                    self._canon_enode(e) for e in enodes)
            self._nodes = merged
            self._hashcons = {}
            for cid, enodes in self._nodes.items():
                for e in enodes:
                    self._hashcons.setdefault(e, cid)
            changed_any = changed_any or changed
            if not changed:
                return changed_any

    # -- equality saturation --------------------------------------------------
    def saturate(self) -> "EGraph":
        """Apply the interpreter's algebraic identities as rewrites to a bounded fixpoint, merging
        e-classes. Terminates on convergence, iteration cap, or the e-node cap (honest bound)."""
        for _ in range(self.MAX_ITERS):
            changed = self._apply_rules()
            rebuilt = self._rebuild()
            if not (changed or rebuilt) or self._capped:
                break
        return self

    def _apply_rules(self) -> bool:
        """One pass of every rewrite rule over a snapshot of the current e-nodes."""
        changed = False
        snapshot = [(cid, en) for cid, ens in self._nodes.items() for en in list(ens)]
        for cid, enode in snapshot:
            root = self.find(cid)
            tag, slots = enode
            # ---- arithmetic identities for BOTH grammar conventions (code_evolver.py:31-34,72-76) ----
            op = None
            if tag == "op" and slots and slots[0][0] == "v":       # ("op", opsym, L, R)
                op = slots[0][1]
                kids = [s[1] for s in slots[1:] if s[0] == "e"]
                op_slots = slots[:1]                                # keep the opsym scalar slot
            elif tag in _OPEN_OP:                                   # open_domain (opname, L, R)
                op = _OPEN_OP[tag]
                kids = [s[1] for s in slots if s[0] == "e"]
                op_slots = ()
            else:
                kids = []
            if op is not None and len(kids) == 2:
                L, R = kids
                if op in _AC_OPS:                                   # commutativity (+, *)
                    swapped = (tag, op_slots + (("e", self.find(R)), ("e", self.find(L))))
                    nc = self._add_enode(swapped)
                    if not self._same(root, nc):
                        self.union(root, nc); changed = True
                if op == "+":
                    if self._is_const(R, 0) and not self._same(root, L):        # x+0 = x
                        self.union(root, L); changed = True
                    if self._is_const(L, 0) and not self._same(root, R):        # 0+x = x
                        self.union(root, R); changed = True
                elif op == "*":
                    if self._is_const(R, 1) and not self._same(root, L):        # x*1 = x
                        self.union(root, L); changed = True
                    if self._is_const(L, 1) and not self._same(root, R):        # 1*x = x
                        self.union(root, R); changed = True
                    if self._is_const(R, 0) and not self._same(root, R):        # x*0 = 0 (== that 0)
                        self.union(root, R); changed = True
                    if self._is_const(L, 0) and not self._same(root, L):        # 0*x = 0
                        self.union(root, L); changed = True
                elif op == "-":
                    if self._is_const(R, 0) and not self._same(root, L):        # x-0 = x
                        self.union(root, L); changed = True
                    if self._same(L, R) and not self._same(root, self._const(0)):   # x-x = 0
                        self.union(root, self._const(0)); changed = True
                elif op == "//":
                    if self._is_const(R, 1) and not self._same(root, L):        # x//1 = x
                        self.union(root, L); changed = True
                    if self._is_const(L, 0) and not self._same(root, L):        # 0//x = 0 (guard)
                        self.union(root, L); changed = True
                elif op == "%":
                    # x%1 = 0, 0%x = 0, x%x = 0  (guarded mod, b==0 -> 0)
                    if ((self._is_const(R, 1) or self._is_const(L, 0) or self._same(L, R))
                            and not self._same(root, self._const(0))):
                        self.union(root, self._const(0)); changed = True
            # ---- comparison symmetry (code_evolver.py:38-40) ----
            elif tag == "cmp" and slots and slots[0][0] == "v":
                op = slots[0][1]
                kids = [s[1] for s in slots[1:] if s[0] == "e"]
                if len(kids) == 2:
                    L, R = kids
                    if op == "==":                                              # a==b <=> b==a
                        sw = (tag, (slots[0], ("e", self.find(R)), ("e", self.find(L))))
                        nc = self._add_enode(sw)
                        if not self._same(root, nc):
                            self.union(root, nc); changed = True
                    elif op in _CMP_SWAP:                                        # a<b <=> b>a, etc.
                        sw = (tag, (("v", _CMP_SWAP[op]), ("e", self.find(R)), ("e", self.find(L))))
                        nc = self._add_enode(sw)
                        if not self._same(root, nc):
                            self.union(root, nc); changed = True
            # ---- len(map(body, src)) = len(src)  (map preserves length; code_evolver.py:98-100) ----
            # map's SOURCE is the last slot and may be a scalar (bare list-var "xs") or a nested e-class
            # (map/filter over another source) — wrap that same slot in a len(...) e-node either way.
            elif tag == "len":
                kids = [s[1] for s in slots if s[0] == "e"]
                if len(kids) == 1:
                    for stag, sslots in list(self._nodes[self.find(kids[0])]):
                        if stag == "map" and sslots:
                            src_slot = sslots[-1]
                            src_slot = ("e", self.find(src_slot[1])) if src_slot[0] == "e" else src_slot
                            lc = self._add_enode(("len", (src_slot,)))
                            if not self._same(root, lc):
                                self.union(root, lc); changed = True
        return changed

    # -- extraction (canonical normal form) -----------------------------------
    def extract(self, cid: int) -> Any:
        """The canonical normal form of an e-class: its least-cost member (cost = node count), with a
        deterministic, STRUCTURE-FIRST tie-break so commutative operands land in a canonical order
        (this is what aligns `a+a*a` and `b*b+b` for anti-unification). Fixpoint cost relaxation makes
        it safe on cyclic classes; small trees converge immediately."""
        INF = float("inf")
        cost: dict[int, float] = {c: INF for c in self._nodes}
        for _ in range(len(self._nodes) + 2):       # Bellman-Ford-style relaxation to a fixpoint
            stable = True
            for c in self._nodes:
                best = INF
                for tag, slots in self._nodes[c]:
                    k = 1.0
                    ok = True
                    for s in slots:
                        if s[0] == "e":
                            ck = cost[self.find(s[1])]
                            if ck == INF:
                                ok = False
                                break
                            k += ck
                    if ok and k < best:
                        best = k
                if best < cost[c]:
                    cost[c] = best
                    stable = False
            if stable:
                break
        return self._build(self.find(cid), cost, set())

    def _build(self, cid: int, cost: dict, guard: set) -> Any:
        cid = self.find(cid)
        if cid in guard:                            # cycle: fall back to any member, no recursion
            tag, slots = next(iter(self._nodes[cid]))
            return (tag,) + tuple(s[1] if s[0] == "v" else ("const", 0) for s in slots)
        guard = guard | {cid}
        # choose the min-cost e-node; tie-break structure-first for canonical operand order
        best_key = None
        best_enode = None
        for enode in self._nodes[cid]:
            tag, slots = enode
            k = 1.0
            child_keys = []
            feasible = True
            for s in slots:
                if s[0] == "e":
                    cc = cost[self.find(s[1])]
                    if cc == float("inf"):
                        feasible = False
                        break
                    k += cc
                    child_keys.append((cc, self.find(s[1])))
            if not feasible:
                continue
            key = (k, tag, tuple(child_keys), tuple(s for s in slots if s[0] == "v"))
            if best_key is None or key < best_key:
                best_key = key
                best_enode = enode
        if best_enode is None:                      # every member infeasible (shouldn't happen)
            tag, slots = next(iter(self._nodes[cid]))
            return (tag,) + tuple(s[1] if s[0] == "v" else ("const", 0) for s in slots)
        tag, slots = best_enode
        out = [tag]
        for s in slots:
            out.append(self._build(s[1], cost, guard) if s[0] == "e" else s[1])
        return tuple(out)

    # -- public queries -------------------------------------------------------
    def equivalent(self, t1: Any, t2: Any) -> bool:
        return self._same(self.add(t1), self.add(t2))


def canonical_form(tree: Any) -> Any:
    """Behaviour-preserving NORMAL FORM of a single tree under the interpreter's equational theory:
    build a fresh e-graph, saturate, extract the least-cost member of the tree's e-class. Deterministic.
    `a + a*a` and `b*b + b` map to structurally aligned forms (operands in canonical order); `x+0`->`x`;
    `x*1`->`x`; `len(map(f,xs))`->`len(xs)`."""
    eg = EGraph()
    cid = eg.add(tree)
    eg.saturate()
    return eg.extract(cid)


def equivalent(t1: Any, t2: Any) -> bool:
    """Are two trees provably equal under the interpreter's algebraic theory (commutativity, the
    identity/absorption laws, comparison symmetry, map-length)? Saturates a shared e-graph and checks
    the two land in one e-class. Naive syntactic equality (`t1 == t2`) is strictly weaker."""
    eg = EGraph()
    a, b = eg.add(t1), eg.add(t2)
    eg.saturate()
    return eg._same(a, b)


# ---------------------------------------------------------------------------
# Anti-unification OVER E-CLASSES = saturate-then-anti-unify.
# ---------------------------------------------------------------------------
def anti_unify_modulo(t1: Any, t2: Any) -> Any:
    """Anti-unify two trees MODULO the equational theory: canonicalise each to its e-class normal form,
    then run the existing syntactic anti-unifier on the normal forms. Structurally-different-but-
    semantically-equivalent forms now generalise to ONE template. Returns a canonical template (holes
    renumbered), exactly like `abstraction.canonical(abstraction.anti_unify(...))`."""
    c1, c2 = canonical_form(t1), canonical_form(t2)
    return _ab.canonical(_ab.anti_unify(c1, c2))


# ---------------------------------------------------------------------------
# Modulo-aware compression gain + the tier-opening miner (drop-in for abstraction.mine).
# ---------------------------------------------------------------------------
def _subtrees(t: Any) -> Iterable[Any]:
    if _is_node(t):
        yield t
        for c in t[1:]:
            if isinstance(c, tuple):
                yield from _subtrees(c)


def compression_gain_modulo(library: list, template: Any, *, _canon_cache: Optional[dict] = None) -> int:
    """Nodes saved by naming `template`, counting a library subtree as an occurrence when its NORMAL
    FORM is an instance of the template (so `b*b+b` counts toward `x + x*x`). Mirrors
    abstraction.compression_gain (= (body-1)*occ, occ>=2, body>=2) but modulo the equational theory —
    which is exactly the extra reuse the naive syntactic gain cannot see."""
    body = _ab.size(template) - _ab._hole_occ(template)
    ctmpl = _ab.canonical(template)
    cache = _canon_cache if _canon_cache is not None else {}
    occ = 0
    for lib in library:
        for st in _subtrees(lib):
            key = id(st)
            cst = cache.get(key)
            if cst is None:
                cst = canonical_form(st)
                cache[key] = cst
            if _ab.match(ctmpl, cst, {}) is not None:
                occ += 1
    if occ < 2 or body < 2:
        return 0
    return (body - 1) * occ


# Default (code_evolver / auto_curriculum) grammar: which subtree tags are minable value producers,
# the pool size window, and the root/well-formedness predicate a template must satisfy.
_CE_POOL_TAGS = ("op", "if", "fold", "len")


def _ce_root_ok(tmpl: Any) -> bool:
    return _ab._well_formed(tmpl)


def mine(library: list, *, top_k: int = 6, min_gain: int = 2, max_pool: int = 80,
         pool_tags: tuple = _CE_POOL_TAGS, size_lo: int = 3, size_hi: int = 10,
         root_ok=_ce_root_ok, source_of=None) -> list[dict]:
    """Tier-opening abstraction miner (babble-style). Pool the library's value-producing subtrees,
    CANONICALISE each to its equational normal form, and anti-unify pairs of NORMAL FORMS. A pair of
    subtrees that differ only by the theory (commutativity, x+0, x*1, len(map)) now share a real
    parameterised template the naive syntactic miner returns as degenerate `(x0 + x1)`. Keep the same
    non-degeneracy gates as abstraction.mine (1-2 holes, shared body >= 2, no pinned body-variable,
    grammar-valid root) and rank by MODULO compression gain. Same {template, arity, gain, source}
    records as abstraction.mine, so callers swap it in behind a flag.

    GRAMMAR-PARAMETRIC: `pool_tags`/`size_hi`/`root_ok`/`source_of` default to the code_evolver grammar
    (auto_curriculum). open_domain passes its own value tags + `source_of=open_domain.to_source` so the
    SAME e-graph theory serves both conventions ('op',opsym,L,R) and (opname,L,R) — no silent no-op."""
    src = source_of or _ab._template_source
    # 1) pool distinct value-producing subtrees (same criteria as the naive miner, grammar-parametric)
    pool: list = []
    for lib in library:
        for st in _subtrees(lib):
            if (_ab._tag(st) in pool_tags and size_lo <= _ab.size(st) <= size_hi
                    and not _ab._hole_occ(st) and st not in pool):
                pool.append(st)
        if len(pool) >= max_pool:
            break

    # 2) canonicalise the pool ONCE (equational normal forms).
    canon_pool = [canonical_form(st) for st in pool]
    gain_cache: dict = {}

    # 3) SUPERSET generation: for each pair, anti-unify BOTH the RAW forms (exactly what the naive
    #    miner does — guarantees we never lose a motif to canonicalisation reordering) AND the CANONICAL
    #    forms (the modulo pathway that unlocks commuted / identity-equivalent motifs the naive miner
    #    cannot see). Every candidate is then scored by the MODULO compression gain (>= syntactic gain),
    #    so egraph.mine() >= abstraction.mine() by construction, plus the tier-opening extras.
    seen: dict[str, dict] = {}
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            for tmpl in (_ab.canonical(_ab.anti_unify(pool[i], pool[j])),           # raw (naive) pair
                         _ab.canonical(_ab.anti_unify(canon_pool[i], canon_pool[j]))):  # modulo pair
                h = _ab.holes_in(tmpl)
                if not (1 <= h <= 2) or _ab.size(tmpl) - _ab._hole_occ(tmpl) < 2 or _ab._body_has_var(tmpl):
                    continue
                if not (_ab._tag(tmpl) in pool_tags and root_ok(tmpl)):
                    continue
                key = src(tmpl)
                if key in seen:
                    continue                                        # already scored this template
                # Gain = MAX(syntactic, modulo). Two lower bounds on the template's true reuse: the
                # syntactic count (abstraction.compression_gain — guarantees egraph.mine >= naive.mine
                # even when canonicalisation reorders a commutative operand away from the template's
                # order) and the modulo count (occurrences whose NORMAL FORM instantiates the template —
                # the tier-opening extra). Taking the max never overcounts and never loses a naive motif.
                gain = max(_ab.compression_gain(library, tmpl),
                           compression_gain_modulo(library, tmpl, _canon_cache=gain_cache))
                if gain < min_gain:
                    continue
                seen[key] = {"template": tmpl, "holes": h, "arity": h, "gain": gain, "source": key}
    return sorted(seen.values(), key=lambda d: -d["gain"])[:top_k]


# ---------------------------------------------------------------------------
# Honesty anchor — behaviour preservation self-check (propose-verify).
# ---------------------------------------------------------------------------
def verify_semantics(tree: Any, envs: list[dict]) -> bool:
    """Re-check, empirically, that canonicalisation preserved MEANING: the normal form must evaluate
    IDENTICALLY to the original on every env in `envs` (via code_evolver.evaluate — INTERPRETED, never
    exec'd). Returns True iff equality saturation changed only the SYNTAX, never the value. The tests
    use this as the gate that no rewrite fabricates an equivalence."""
    from packages.evolution.code_evolver import evaluate
    canon = canonical_form(tree)
    for env in envs:
        try:
            if evaluate(tree, env) != evaluate(canon, env):
                return False
        except Exception:
            return False
    return True
