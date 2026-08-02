# -*- coding: utf-8 -*-
"""Sealed gates for the R4 richer-relational-bone lever (graph frame-bone extraction).

The committed `composed` clause-planner (packages/fluency/register.py) fires apposition/coordination ONLY
when a subject's bones carry an action/possession predicate (capable_of / has_a) to promote; on taxonomic-
only bones it correctly stays flat. The binding constraint is therefore the RELATIONAL RICHNESS of the
bones base_brain emits. `_graph_frame_bones` pulls a concept's richer relational frame DIRECTLY from the
production triple store so the bones can carry the promotable predicates.

Two kinds of evidence, both here:
  * DETERMINISTIC FIXTURE — a hand-built in-memory TripleStore with known edges. Proves the extraction
    MECHANISM in isolation (independent of production-store content): richer stores yield richer bones,
    caps/ordering hold, and — the no-fabrication gate — a store with only is_a yields only is_a bones.
  * REAL-GRAPH PROBE — the actual production store (data/graph_scale/kg_triples). Skips gracefully when
    the store or a probed concept is absent, so the suite stays portable; asserts real richness + real
    provenance when it is present.
"""
from __future__ import annotations

import pytest

from packages.base_brain.zero_user_answer import (
    _graph_frame_bones,
    _pack_answer_bones,
    english_answer_bones,
)
from packages.fluency.realizer import realize_with_trace


# ── fixture store: a hand-built triple store with known edges (deterministic, no production dependency) ─
@pytest.fixture()
def fixture_store(tmp_path):
    from packages.graph_scale.triple_store import TripleStore

    st = TripleStore(tmp_path / "kg")
    # RICH concept: is_a + the promotable predicates + composition/use/part/property/location
    for p, o in [
        ("is_a", "gadget"),
        ("capable_of", "spin fast"),
        ("capable_of", "lift loads"),
        ("has_a", "lever"),
        ("made_of", "steel"),
        ("used_for", "cutting"),
        ("part_of", "machine"),
        ("has_property", "heavy"),
        ("located_in", "workshop"),
        # a non-frame predicate that MUST NOT leak into the bones (only frame relations are extracted)
        ("defined_as", "a mechanical contrivance"),
        ("alias", "gizmo"),
    ]:
        st.add("widget", p, o)
    # THIN concept: ONLY a taxonomic edge — the no-fabrication reference case
    st.add("stone", "is_a", "rock")
    # a concept whose ONLY rich edge is a capability but with NO is_a (composed cannot fire: no head)
    st.add("sprite", "capable_of", "flicker")
    st.flush()
    return st


# ══ GATE (a): richer bones on concepts that HAVE rich graph relations (count + relation-type delta) ══════
def test_gate_a_fixture_rich_concept_yields_promotable_relation_typed_bones(fixture_store):
    bones = _graph_frame_bones("widget", store=fixture_store)
    rels = [b[1] for b in bones]
    # more than a lone taxonomic bone, and the PROMOTABLE action/possession predicates are present
    assert len(bones) >= 5, bones
    assert "is_a" in rels
    assert "capable_of" in rels, rels          # the predicate the composed register promotes
    assert "has_a" in rels, rels
    assert "used_for" in rels and "made_of" in rels, rels
    # every bone carries the queried subject and a real object
    assert all(b[0] == "widget" and b[2] for b in bones)


def test_gate_a_delta_rich_vs_taxonomic_only(fixture_store):
    """The count delta the lever targets: a rich concept yields many relation-TYPES; a taxonomic-only
    concept yields exactly one. Distinct relation types is the honest richness measure."""
    rich = _graph_frame_bones("widget", store=fixture_store)
    thin = _graph_frame_bones("stone", store=fixture_store)
    rich_types = {b[1] for b in rich}
    thin_types = {b[1] for b in thin}
    assert len(rich_types) >= 6, rich_types
    assert thin_types == {"is_a"}, thin_types
    assert len(rich_types) > len(thin_types)


def test_gate_a_per_predicate_caps_bound_the_flood(tmp_path):
    """The located_in flood (20-40 ConceptNet edges/subject) must not swamp the bones: per-predicate
    caps hold, and is_a is ranked first (the appositive head the composed planner demotes)."""
    from packages.base_brain.zero_user_answer import _GRAPH_FRAME_PRED_CAP
    from packages.graph_scale.triple_store import TripleStore

    # a subject with MANY located_in edges plus a couple of promotable ones
    st = TripleStore(tmp_path / "flood_kg")
    for i in range(30):
        st.add("flooded", "located_in", f"place {i}")
    st.add("flooded", "is_a", "thing")
    st.add("flooded", "capable_of", "move")
    st.flush()
    bones = _graph_frame_bones("flooded", store=st)
    from collections import Counter
    per = Counter(b[1] for b in bones)
    assert per["located_in"] <= _GRAPH_FRAME_PRED_CAP["located_in"], per
    assert bones[0][1] == "is_a", bones            # is_a first
    assert "capable_of" in per, per                # the rare promotable predicate survived the flood


@pytest.mark.parametrize("concept", ["comb", "dog", "knife"])
def test_gate_a_real_graph_rich_concepts_gain_promotable_bones(concept):
    """REAL-GRAPH PROBE: on the production store, a ConceptNet-rich concept yields promotable bones."""
    from packages.graph_scale.answer_bridge import _store

    store = _store()
    if store is None:
        pytest.skip("production triple store not present")
    bones = _graph_frame_bones(concept, store=store)
    if not bones:
        pytest.skip(f"{concept!r} absent from this store snapshot")
    rels = {b[1] for b in bones}
    assert "is_a" in rels, (concept, bones)
    assert rels & {"capable_of", "has_a"}, (concept, rels)   # at least one PROMOTABLE predicate


# ══ GATE (b): NO FABRICATION — every bone is a real stored edge; a thin concept stays thin ═══════════════
def test_gate_b_thin_concept_yields_only_its_real_relation(fixture_store):
    """The no-fabrication reference: 'stone' has ONLY is_a in the store, so extraction invents NO
    capable_of/has_a/used_for — the bones are exactly the one real edge."""
    bones = _graph_frame_bones("stone", store=fixture_store)
    assert bones == [["stone", "is_a", "rock"]], bones


def test_gate_b_non_frame_predicates_never_leak(fixture_store):
    """defined_as / alias exist on 'widget' in the store but are NOT frame relations — they must never
    appear as bones (the extraction emits only the frame lexicon, never arbitrary store predicates)."""
    rels = {b[1] for b in _graph_frame_bones("widget", store=fixture_store)}
    assert "defined_as" not in rels and "alias" not in rels, rels


def test_gate_b_every_bone_traces_to_a_real_edge(fixture_store):
    """Provenance by construction: assert each emitted bone is an edge the store actually holds."""
    for subj in ("widget", "stone", "sprite"):
        for s, r, o in _graph_frame_bones(subj, store=fixture_store):
            got = fixture_store.facts_about(s, limit=80, preds=(r,))
            assert (s, r, o) in got, (s, r, o, got)


def test_gate_b_real_graph_provenance():
    """REAL-GRAPH PROBE: every bone from the production store is a genuine stored edge (no invention)."""
    from packages.graph_scale.answer_bridge import _store

    store = _store()
    if store is None:
        pytest.skip("production triple store not present")
    checked = 0
    for concept in ("comb", "dog", "knife", "guitar", "kettle"):
        bones = _graph_frame_bones(concept, store=store)
        for s, r, o in bones:
            got = store.facts_about(s, limit=200, preds=(r,))
            assert (s, r, o) in got, (s, r, o)
            checked += 1
    if checked == 0:
        pytest.skip("no probed concept present in this store snapshot")


def test_gate_b_hangul_objects_are_filtered(tmp_path):
    """English-only containment: a Hangul object edge is never emitted as a bone."""
    from packages.graph_scale.triple_store import TripleStore

    st = TripleStore(tmp_path / "kg")
    st.add("thing", "is_a", "object")
    st.add("thing", "capable_of", "움직이다")     # Hangul object — must be dropped
    st.flush()
    rels = [b for b in _graph_frame_bones("thing", store=st)]
    assert rels == [["thing", "is_a", "object"]], rels


# ══ GATE (c): DOWNSTREAM — richer bones raise the composed register's fire-rate vs thin bones ════════════
def _fires(bones) -> bool:
    """True iff the composed register ADOPTED a combined structure (apposition/relative), not flat."""
    _, structures = realize_with_trace(bones, "composed")
    return any(s in ("apposition", "relative") for s in structures)


def test_gate_c_composed_fires_on_rich_bones_not_on_thin(fixture_store):
    rich = _graph_frame_bones("widget", store=fixture_store)          # is_a + capable_of + has_a + ...
    thin = _graph_frame_bones("stone", store=fixture_store)           # is_a only
    assert _fires(rich), rich                                         # promotable predicate -> combines
    assert not _fires(thin), thin                                    # taxonomic only -> flat (correct)


def test_gate_c_no_head_no_fire(fixture_store):
    """'sprite' has a capability but NO is_a — the composed register cannot demote a head, so it stays
    flat. Honest: richness alone does not force a combination; the shape must support it."""
    assert not _fires(_graph_frame_bones("sprite", store=fixture_store))


def test_gate_c_real_graph_fire_rate_rises(capsys):
    """REAL-GRAPH PROBE + the reported measurement: feed thin (is_a-only) vs graph-rich bones for a set
    of real concepts to the committed composed register and compare the ADOPTION rate."""
    from packages.graph_scale.answer_bridge import _store

    store = _store()
    if store is None:
        pytest.skip("production triple store not present")
    concepts = ["comb", "dog", "knife", "guitar", "car", "lion", "kettle", "container", "cat", "hammer"]
    rich_fires = thin_fires = present = 0
    for c in concepts:
        rich = _graph_frame_bones(c, store=store)
        if not rich:
            continue
        present += 1
        thin = [b for b in rich if b[1] == "is_a"]                    # the taxonomic-only baseline
        if _fires(rich):
            rich_fires += 1
        if _fires(thin):
            thin_fires += 1
    if present == 0:
        pytest.skip("no probed concept present in this store snapshot")
    with capsys.disabled():
        print(f"\n[gate c] concepts probed={present} | composed fires: "
              f"rich={rich_fires} thin={thin_fires}")
    assert thin_fires == 0                       # is_a-only can NEVER combine
    assert rich_fires > thin_fires               # richer bones raise the fire-rate


# ══ GATE (d): NO REGRESSION — default extraction is byte-identical to the curated-pack baseline ══════════
@pytest.mark.parametrize("query", [
    "What is Kubernetes?", "What is Docker?", "What is a container?",
    "What is a semantic graph?", "Explain machine learning.",
])
def test_gate_d_default_is_byte_identical_to_pack_baseline(query):
    """The default (`enrich_from_graph=False`) path must equal the curated-pack extraction exactly, so
    every existing caller (dual_brain CO KEYSTONE, the co-central keystone tests) is unchanged."""
    assert english_answer_bones(query) == _pack_answer_bones(query)


def test_gate_d_enriched_is_a_superset_of_pack_bones():
    """Enrichment is strictly ADDITIVE: the pack bones are all still present (never dropped/reordered
    away), only real graph bones are appended."""
    q = "What is a container?"
    pack = english_answer_bones(q)
    enriched = english_answer_bones(q, enrich_from_graph=True)
    for b in pack:
        assert b in enriched, (b, enriched)
    assert len(enriched) >= len(pack)
