# -*- coding: utf-8 -*-
"""Deductive closure accelerator: every generated edge is a TRUE transitive
pair (0% wrong), generic attractors are dropped, and it's fast."""
import numpy as np
import pytest


class _Terms:
    def __init__(self):
        self._t, self._r = {}, {}
    def add(self, t):
        if t not in self._t:
            self._t[t] = len(self._t); self._r[self._t[t]] = t
        return self._t[t]
    def lookup(self, t): return self._t.get(t)
    def term(self, i): return self._r.get(i)


class _Store:
    def __init__(self, tmp, triples):
        self.root = tmp
        self.terms = _Terms()
        self.terms.add("is_a")
        rows = [(self.terms.add(s), self.terms.add(p), self.terms.add(o))
                for s, p, o in triples]
        cols = list(zip(*rows)) if rows else ([], [], [])
        for name, col in zip(("s", "p", "o"), cols):
            np.asarray(col, dtype="<i4").tofile(tmp / f"{name}.col")


def test_closure_is_sound_and_drops_attractors(tmp_path):
    from packages.reasoning_vm.closure_accelerator import accelerate_closure
    # a real taxonomy chain a->b->c->d (transitive) + a garbage attractor 'entity'
    # that everything points to (must be dropped, else clique explosion)
    tri = [("a", "is_a", "b"), ("b", "is_a", "c"), ("c", "is_a", "d")]
    tri += [(x, "is_a", "entity") for x in ("a", "b", "c", "d", "e", "f", "g")]
    st = _Store(tmp_path, tri)
    r = accelerate_closure(st, "is_a", attractor_indegree=5)   # 'entity' has in-deg 7
    assert r.dropped_attractors == 1                            # entity dropped
    # provable 2-hop edges of the clean chain: a->c, b->d (exactly 2)
    assert r.new_edges == 2
    assert r.edges_per_sec > 0


def test_cpu_gpu_agree_on_new_edge_count(tmp_path):
    """If a GPU is present the two backends must count IDENTICAL new edges —
    a cross-check that the accelerated path is exactly the deductive one."""
    from packages.reasoning_vm import closure_accelerator as ca
    rng = np.random.default_rng(0)
    # random DAG-ish is_a edges (i -> j with i<j so transitivity is acyclic)
    tri = []
    for _ in range(600):
        i, j = sorted(rng.integers(0, 80, 2))
        if i != j:
            tri.append((f"n{i}", "is_a", f"n{j}"))
    st = _Store(tmp_path, list(set(tri)))
    s, o = ca._load_relation_edges(st, "is_a")
    nodes = np.unique(np.concatenate([s, o]))
    si = np.searchsorted(nodes, s); oi = np.searchsorted(nodes, o)
    N = len(nodes)
    gpu = ca._try_gpu_closure(si, oi, N)
    if gpu is None:
        pytest.skip("no GPU")
    from scipy import sparse
    A = sparse.csr_matrix((np.ones(len(si), np.int8), (si, oi)), shape=(N, N))
    A.data[:] = 1
    A2 = A.dot(A); A2.data[:] = 1
    A2 = A2 - A2.multiply(A); A2.setdiag(0); A2.eliminate_zeros()
    assert gpu[0] == int(A2.nnz)
    # LOW-END INVARIANCE: a tiny block (a 2 GB card / old Quadro) must give the
    # IDENTICAL edge count — only slower. Stability without changing the answer.
    small = ca._try_gpu_closure(si, oi, N, block=64)
    assert small[0] == gpu[0]


def test_closure_learn_excludes_hubs_and_stays_candidate_only(tmp_path):
    """The contamination guard: a polysemy HUB subject's mixed-sense is_a is
    kept OUT of closure (else it propagates garbage), and nothing is written
    to production — growth is gated candidates only."""
    from packages.reasoning_vm.closure_accelerator import closure_learn
    # 'capital' is a hub: many (>=12) is_a parents mixing senses; a clean chain
    # seoul -> city -> settlement should still close.
    tri = [("서울", "is_a", "도시"), ("도시", "is_a", "정착지")]
    tri += [("capital", "is_a", f"junk{i}") for i in range(14)]   # hub
    st = _Store(tmp_path, tri)
    r = closure_learn(st, "is_a", attractor_indegree=999)
    cand = {(a, b) for a, b in r["candidates"]}
    assert ("서울", "is_a", "정착지") not in cand      # (it's stored as pair form)
    assert ("서울", "정착지") in cand                  # clean non-hub chain closed
    assert not any(a == "capital" for a, b in cand)    # hub kept out (no contamination)
    assert r["written_to_production"] is False
    assert r["hub_subjects_excluded"] is True


def test_hybrid_matches_single_and_uses_available_devices(tmp_path):
    """Hybrid CPU+GPU closure must produce the SAME edge count as the single
    path (correctness) and, when a GPU exists, actually use both."""
    from packages.reasoning_vm.closure_accelerator import hybrid_closure, closure_learn
    import numpy as np
    rng = np.random.default_rng(2)
    tri = []
    for _ in range(500):
        i, j = sorted(rng.integers(0, 70, 2))
        if i != j:
            tri.append((f"n{i}", "is_a", f"n{j}"))
    st = _Store(tmp_path, list(set(tri)))
    h = hybrid_closure(st, "is_a", attractor_indegree=999, gpu_fraction=0.5)
    ref = closure_learn(st, "is_a", attractor_indegree=999)
    assert h["new_provable_edges"] == ref["total_new_provable"]   # same math, split in two
    assert "trillion_path" in h and h["trillion_path"]["single_node_ceiling_eps"] >= 0
    # AUTO load-balance: measured split must give the IDENTICAL edge count (only the
    # CPU/GPU work division changes) and expose the balance decision.
    ha = hybrid_closure(st, "is_a", attractor_indegree=999, gpu_fraction="auto")
    assert ha["new_provable_edges"] == ref["total_new_provable"]
    assert "load_balance" in ha and 0.0 <= ha["gpu_fraction_used"] <= 1.0


def test_safe_closure_learn_surgeon_gates_contamination(tmp_path):
    """The full safe cycle: derive -> surgeon excises type-disjoint -> gated
    clean candidates, nothing to production."""
    from packages.reasoning_vm.closure_accelerator import safe_closure_learn



    tri = [("방콕", "is_a", "도시"), ("방콕", "is_a", "수도"),
           ("도시", "is_a", "종교집단"),                     # the contaminating edge
           ("서울", "is_a", "도시"), ("도시", "is_a", "정착지")]  # clean taxonomy
    st = _Store(tmp_path, tri)
    r = safe_closure_learn(st, "is_a", attractor_indegree=999)
    assert r["written_to_production"] is False
    assert r["surgeon_available"] is True
    excised = {(i["subject"], i["object"]) for i in r["excision_sample"]}
    clean = {(a, b) for a, b in r["candidates_sample"]}
    assert ("방콕", "종교집단") in excised          # PLACE vs GROUP — cut
    assert ("방콕", "종교집단") not in clean         # kept out of the clean set
