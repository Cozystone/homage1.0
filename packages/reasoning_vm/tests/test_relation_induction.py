# -*- coding: utf-8 -*-
"""F3: relation-path procedures induced over a graph from (start, answer) examples, verify-gated."""
from packages.reasoning_vm.relation_induction import induce_relation_path, run_path


def _mini_graph():
    """A tiny world: people born_in countries, countries have capitals — for 2-hop composition."""
    facts = {
        "einstein": [("einstein", "born_in", "germany")],
        "curie": [("curie", "born_in", "poland")],
        "newton": [("newton", "born_in", "england")],
        "darwin": [("darwin", "born_in", "england")],
        "tesla": [("tesla", "born_in", "serbia")],
        "gauss": [("gauss", "born_in", "germany")],
        "germany": [("germany", "capital", "berlin"), ("germany", "is_a", "country")],
        "poland": [("poland", "capital", "warsaw")],
        "england": [("england", "capital", "london")],
        "serbia": [("serbia", "capital", "belgrade")],
    }
    return lambda e: facts.get(e, [])


def test_induces_one_hop_relation():
    fa = _mini_graph()
    caps = [("germany", "berlin"), ("poland", "warsaw"), ("england", "london"),
            ("serbia", "belgrade")]
    ind = induce_relation_path("capital_of", caps, fa)
    assert ind is not None and ind.path == ("capital",)
    assert ind.fn("germany") == "berlin" and ind.n_verified >= 1


def test_induces_two_hop_composition():
    """born_in ∘ capital — the composition chain_reasoner used to HARD-CODE, here INDUCED."""
    fa = _mini_graph()
    ex = [("einstein", "berlin"), ("curie", "warsaw"), ("newton", "london"),
          ("tesla", "belgrade"), ("gauss", "berlin"), ("darwin", "london")]
    ind = induce_relation_path("birthplace_capital", ex, fa, max_hops=2)
    assert ind is not None and ind.path == ("born_in", "capital")
    assert ind.fn("einstein") == "berlin"
    assert ind.certificate()["relation_path"] == ["born_in", "capital"]


def test_occam_prefers_one_hop():
    """When a 1-hop path already explains the data, the 2-hop search never overrides it."""
    fa = _mini_graph()
    ind = induce_relation_path("cap", [("germany", "berlin"), ("poland", "warsaw"),
                                       ("england", "london"), ("serbia", "belgrade")], fa,
                               max_hops=2)
    assert ind is not None and len(ind.path) == 1


def test_refuses_when_no_path_reproduces():
    fa = _mini_graph()
    bad = [("germany", "warsaw"), ("poland", "london"), ("england", "berlin"),
           ("serbia", "warsaw")]           # no consistent path maps these
    assert induce_relation_path("nonsense", bad, fa) is None


def test_live_graph_capital_induction():
    """The real (Kaikki) store already carries capital edges — induce the procedure on it."""
    try:
        from packages.graph_scale import answer_bridge as AB
        kg = AB._store()
    except Exception:
        return                              # store not available in this env — mini-graph tests cover the logic
    if kg is None:
        return
    fa = lambda e: kg.facts_about(e, limit=40)  # noqa: E731
    ex = [("프랑스", "파리"), ("독일", "베를린"), ("일본", "도쿄도"), ("영국", "런던"),
          ("이탈리아", "로마"), ("스페인", "마드리드"), ("캐나다", "오타와")]
    if not any(a in run_path(s, ("capital",), fa) for s, a in ex):
        return                              # capital edges absent in this env
    ind = induce_relation_path("capital_of", ex, fa)
    assert ind is not None and ind.path == ("capital",)
    assert ind.fn("대한민국") == "서울특별시"   # unseen, from the live graph


def test_resolving_facts_about_world_pack_qids():
    """World-pack schema: relation objects are Q-ids resolved via a 'qlabel' row. The
    resolving_facts_about adapter makes run_path/induce return readable labels; without it the
    raw store yields the opaque Q-id (proving the adapter is what grounds F3 on the world pack)."""
    from packages.reasoning_vm.relation_induction import (induce_relation_path,
                                                          resolving_facts_about, run_path)
    graph = {
        "프랑스": [("프랑스", "capital", "Q90")], "Q90": [("Q90", "qlabel", "파리")],
        "독일": [("독일", "capital", "Q64")], "Q64": [("Q64", "qlabel", "베를린")],
        "일본": [("일본", "capital", "Q1490")], "Q1490": [("Q1490", "qlabel", "도쿄도")],
        "영국": [("영국", "capital", "Q84")], "Q84": [("Q84", "qlabel", "런던")],
    }
    raw = lambda n: graph.get(n, [])           # noqa: E731
    fa = resolving_facts_about(raw)
    assert run_path("프랑스", ("capital",), fa) == {"파리"}       # Q-id resolved to label
    assert run_path("프랑스", ("capital",), raw) == {"Q90"}       # raw store: opaque Q-id
    ex = [("프랑스", "파리"), ("독일", "베를린"), ("일본", "도쿄도"), ("영국", "런던")]
    ind = induce_relation_path("capital_of", ex, fa)
    assert ind is not None and ind.path == ("capital",) and ind.fn("프랑스") == "파리"
