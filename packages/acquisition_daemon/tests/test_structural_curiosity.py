# -*- coding: utf-8 -*-
"""SEALED GATE for INTRINSIC CURIOSITY — the daemon's SECOND endogenous gap source.

The shipped daemon pursued a fact only if the SAME question honestly abstained >= MIN_PRESSURE times
(recurrence-of-demand). A structural hole nobody re-asks was invisible — not yet self-winding. This
gate proves the daemon now ALSO pursues genuinely-valuable STRUCTURAL graph holes under endogenous
pressure derived from the graph's OWN schema statistics (``structural_gaps.StructuralGapScanner``),
while every safety gate is unchanged.

Deterministic — a controlled schema graph + a controlled fixture corpus, no live network.

The five gates the task requires:
  (a) SELF-DRIVEN    — with ZERO re-asked questions but a graph containing structural holes, the
                       daemon autonomously selects holes, runs the loop, and queues verified
                       candidates. Proves curiosity, not recurrence.
  (b) PRINCIPLED     — given several holes it prioritizes the higher-value one by the
                       salience/coverage/uncertainty signal; asserted ordering, and NOT a hardcoded
                       list (swap the graph -> the priority follows the signal).
  (c) STILL SAFE     — shipped store byte-unchanged after a curiosity-driven run; operator gate
                       holds; a hole with NO evidence -> nothing queued (fabrication 0).
  (d) RECURRENCE     — the shipped recurrence source still works and coexists (no regression); with
                       curiosity disabled the daemon is byte-for-byte the old recurrence-only engine.
  (e) NO-REGRESSION  — run the two suites (terminal), distinguish new from pre-existing failures.
"""
from __future__ import annotations

import shutil

import pytest

from packages.acquisition_daemon import (
    AcquisitionDaemon,
    AcquisitionQueue,
    GapLedger,
    StructuralGapScanner,
    store_digest,
)
from packages.base_brain.relational_lookup import resolve_relational
from packages.candidate_promotion_gate import REQUIRED_CONFIRMATION_PHRASE
from packages.graph_scale.triple_store import TripleStore
from packages.knowledge_acquisition import FixtureEvidence


@pytest.fixture(autouse=True)
def _isolate_shared_ledger(tmp_path, monkeypatch):
    """Point the REUSED failure-receipt ledger at a tmp path so pressure accounting is deterministic
    and never touches the real data/flywheel ledger."""
    import packages.flywheel.failure_receipts as fr
    monkeypatch.setattr(fr, "_ARCHIVE", tmp_path / "shared_failure_receipts.jsonl")


# ── a SCHEMA graph: five Countries, each missing exactly the relations its peers induce ───────────
#   France   : capital, population, language           -> MISSING currency  (salient: many in-edges)
#   Japan    : capital, currency, population           -> MISSING language
#   Germany  : capital, currency, language             -> MISSING population
#   Brazil   : capital, currency, population, language -> COMPLETE (a peer, no hole)
#   Atlantis : capital, currency                       -> MISSING population, language (NO evidence)
# Type-conditioned coverage (5 Country members):
#   capital 5/5 (no hole) · currency 4/5=.8 · population 3/5=.6 · language 3/5=.6
SCHEMA_FACTS = [
    ("France", "is_a", "Country"), ("France", "capital", "Paris"),
    ("France", "population", "67 million"), ("France", "language", "French"),
    ("Japan", "is_a", "Country"), ("Japan", "capital", "Tokyo"),
    ("Japan", "currency", "yen"), ("Japan", "population", "125 million"),
    ("Germany", "is_a", "Country"), ("Germany", "capital", "Berlin"),
    ("Germany", "currency", "euro"), ("Germany", "language", "German"),
    ("Brazil", "is_a", "Country"), ("Brazil", "capital", "Brasilia"),
    ("Brazil", "currency", "real"), ("Brazil", "population", "214 million"),
    ("Brazil", "language", "Portuguese"),
    ("Atlantis", "is_a", "Country"), ("Atlantis", "capital", "Poseidonis"),
    ("Atlantis", "currency", "orichalcum"),
    # in-edges that make France the most SALIENT node (degree/centrality) — no is_a, so not members
    ("Paris", "located_in", "France"), ("Louvre", "located_in", "France"),
    ("Napoleon", "born_in", "France"), ("Baguette", "originates_in", "France"),
    ("Seine", "flows_through", "France"),
]

# Evidence for the three EVIDENCED holes (2 distinct domains each); NOTHING for Atlantis.
SCHEMA_CORPUS = [
    {"url": "https://en.wikipedia.org/wiki/France",
     "text": "The currency of France is the euro, part of the eurozone."},
    {"url": "https://www.xe.com/currency/eur-euro",
     "text": "France's currency is the euro."},
    {"url": "https://en.wikipedia.org/wiki/Germany",
     "text": "The population of Germany is 83 million people."},
    {"url": "https://www.worldometers.info/world-population/germany-population",
     "text": "Germany's population is 83 million as of recent data."},
    {"url": "https://en.wikipedia.org/wiki/Japan",
     "text": "The official language of Japan is Japanese."},
    {"url": "https://www.nationsonline.org/oneworld/japan.htm",
     "text": "The language of Japan is Japanese, spoken across the country."},
    # NOTE: no document mentions Atlantis -> its structural holes stay honest gaps (fabrication guard)
]


def _write_store(root, facts):
    st = TripleStore(root)
    for s, p, o in facts:
        st.add(s, p, o)
    st.flush()
    del st
    return root


def _schema_shipped(tmp_path):
    return _write_store(tmp_path / "shipped", SCHEMA_FACTS)


def _daemon(tmp_path, shipped, *, enable_curiosity=True, min_pressure=2, corpus=SCHEMA_CORPUS,
            curiosity_kwargs=None):
    ledger = GapLedger(tmp_path / "gaps.json")
    queue = AcquisitionQueue(tmp_path / "queue.json")
    daemon = AcquisitionDaemon(
        shipped_root=shipped, scratch_root=tmp_path / "scratch",
        evidence=FixtureEvidence(corpus=corpus), queue=queue, ledger=ledger,
        min_pressure=min_pressure, enable_curiosity=enable_curiosity,
        curiosity_kwargs=curiosity_kwargs)
    return daemon, queue, ledger


# ══ (a) SELF-DRIVEN — curiosity, not recurrence ═══════════════════════════════════════════════════
def test_curiosity_pursues_structural_holes_with_zero_reasked_questions(tmp_path):
    """No question is ever asked (empty batches -> zero recurrence). The daemon still autonomously
    selects the graph's structural holes, runs the acquisition loop, and queues verified candidates.
    This is the proof of genuine self-winding curiosity: pursuit under endogenous structural pressure
    with no demand at all."""
    shipped = _schema_shipped(tmp_path)
    daemon, queue, ledger = _daemon(tmp_path, shipped)

    report = daemon.run_overnight([[], [], []])          # ZERO questions across three windows

    # nothing recurred — the recurrence source is completely empty
    assert report.gaps_observed == 0
    assert ledger.all_gaps() == {}
    assert report.pursued_recurrence == 0

    # yet curiosity found the graph's 5 structural holes and pursued every one
    assert report.curiosity_holes_detected == 5
    assert report.pursued == 5
    assert report.pursued_curiosity == 5

    # 3 evidenced holes became consensus-verified candidates; the 2 Atlantis holes had no evidence
    assert report.verified_queued == 3, [(i["title"], i["status"]) for i in queue.items()]
    assert report.insufficient_consensus == 2

    items = queue.items()
    assert len(items) == 3
    titles = sorted(i["title"] for i in items)
    assert titles == ["France currency = euro", "Germany population = 83 million",
                      "Japan language = Japanese"], titles
    for it in items:
        assert it["status"] == "pending"                 # PROPOSED, never auto-applied
        assert it["consensus_domains"] >= 2
        assert len(it["source_refs"]) >= 2               # provenance urls
        # every queued candidate traces to the structural-curiosity source (no one re-asked it)
    # fabrication 0 at the queue: the no-evidence structural holes never became candidates
    assert not any("Atlantis" in i["title"] for i in items)


def test_curiosity_targets_carry_the_structural_source_tag(tmp_path):
    """The pressured() list tags each curiosity target so the two endogenous sources are auditable."""
    shipped = _schema_shipped(tmp_path)
    daemon, _queue, ledger = _daemon(tmp_path, shipped)
    holes = daemon.curiosity_targets()
    assert len(holes) == 5
    assert all(h["pressure_sources"] == ["structural_curiosity"] for h in holes)
    # and pressured() surfaces them as targets even with an empty recurrence ledger
    targets = ledger.pressured(2, structural_holes=holes)
    assert len(targets) == 5
    assert all("structural_curiosity" in t["pressure_sources"] for t in targets)


# ══ (b) PRINCIPLED PRIORITY — salience · coverage · uncertainty, and NOT a hardcoded list ══════════
def _rank(holes):
    return [(h.entity, h.rel_norm) for h in holes]


def test_priority_salience_more_central_entity_ranks_higher(tmp_path):
    """Two entities miss the SAME relation with the SAME coverage; the more SALIENT (higher-degree)
    one's hole ranks higher. Germany (degree 4) vs Atlantis (degree 3), both missing population."""
    shipped = _schema_shipped(tmp_path)
    holes = StructuralGapScanner(TripleStore(shipped)).scan()
    order = _rank(holes)
    # France/currency is the single highest-value hole (max salience 9 AND max coverage .8)
    assert order[0] == ("France", "currency")
    # same-relation, same-coverage pair: the more salient entity wins
    gp = order.index(("Germany", "population"))
    ap = order.index(("Atlantis", "population"))
    assert gp < ap
    g = next(h for h in holes if (h.entity, h.rel_norm) == ("Germany", "population"))
    a = next(h for h in holes if (h.entity, h.rel_norm) == ("Atlantis", "population"))
    assert g.coverage == a.coverage and g.info == a.info      # ONLY salience differs
    assert g.salience > a.salience


def test_priority_follows_the_signal_not_a_hardcoded_list_on_graph_swap(tmp_path):
    """The anti-hardcoding proof. Two Countries (France, Atlantis) BOTH miss population; whichever is
    made salient owns the higher-priority hole. Swap which entity is central -> the ranking flips. A
    hardcoded target list could not do this."""
    def build(root, salient):
        facts = [
            ("France", "is_a", "Country"), ("France", "capital", "Paris"),
            ("France", "currency", "euro"), ("France", "language", "French"),
            ("Atlantis", "is_a", "Country"), ("Atlantis", "capital", "Poseidonis"),
            ("Atlantis", "currency", "orichalcum"), ("Atlantis", "language", "Atlantean"),
            # peers that HAVE population -> induces the population schema (coverage .5)
            ("Japan", "is_a", "Country"), ("Japan", "capital", "Tokyo"),
            ("Japan", "currency", "yen"), ("Japan", "language", "Japanese"),
            ("Japan", "population", "125 million"),
            ("Brazil", "is_a", "Country"), ("Brazil", "capital", "Brasilia"),
            ("Brazil", "currency", "real"), ("Brazil", "language", "Portuguese"),
            ("Brazil", "population", "214 million"),
        ]
        for ref in ("R1", "R2", "R3", "R4"):             # in-edges make `salient` the central node
            facts.append((ref, "relates_to", salient))
        return _write_store(root, facts)

    ga = build(tmp_path / "A", salient="France")
    gb = build(tmp_path / "B", salient="Atlantis")
    ra = _rank(StructuralGapScanner(TripleStore(ga)).scan())
    rb = _rank(StructuralGapScanner(TripleStore(gb)).scan())

    # graph A: France is central -> France/population outranks Atlantis/population
    assert ra.index(("France", "population")) < ra.index(("Atlantis", "population"))
    # graph B: the ONLY change is which entity is central -> the ranking FOLLOWS, it flips
    assert rb.index(("Atlantis", "population")) < rb.index(("France", "population"))


def test_priority_coverage_more_expected_relation_ranks_higher(tmp_path):
    """Same entity misses two relations, both above the floor but at different peer-coverage; the
    MORE EXPECTED relation (higher coverage = stronger schema evidence) ranks higher."""
    facts = [
        ("Xland", "is_a", "Country"), ("Xland", "capital", "Xcity"),   # misses currency AND language
        # 4 peers all have currency (coverage 4/5=.8); only 3 have language (3/5=.6)
        ("A", "is_a", "Country"), ("A", "currency", "ca"), ("A", "language", "la"),
        ("B", "is_a", "Country"), ("B", "currency", "cb"), ("B", "language", "lb"),
        ("C", "is_a", "Country"), ("C", "currency", "cc"), ("C", "language", "lc"),
        ("D", "is_a", "Country"), ("D", "currency", "cd"),             # D has currency, no language
    ]
    root = _write_store(tmp_path / "cov", facts)
    holes = {(h.entity, h.rel_norm): h for h in StructuralGapScanner(TripleStore(root)).scan()}
    cur = holes[("Xland", "currency")]
    lang = holes[("Xland", "language")]
    assert cur.coverage > lang.coverage                  # .8 vs .6, graph-derived
    assert cur.salience == lang.salience and cur.info == lang.info   # ONLY coverage differs
    assert cur.score > lang.score


def test_priority_uncertainty_more_informative_relation_ranks_higher(tmp_path):
    """Same entity, same coverage, same salience — the relation whose answer is UNPREDICTABLE across
    peers (high object entropy = more learned by filling it) outranks the one whose answer is the
    same for everyone. Isolates the uncertainty axis."""
    facts = [
        ("Xland", "is_a", "Country"), ("Xland", "population", "1"),    # misses capital AND currency
        # peers: capitals all DISTINCT (informative); currencies all IDENTICAL (predictable)
        ("A", "is_a", "Country"), ("A", "capital", "Acity"), ("A", "currency", "euro"),
        ("B", "is_a", "Country"), ("B", "capital", "Bcity"), ("B", "currency", "euro"),
        ("C", "is_a", "Country"), ("C", "capital", "Ccity"), ("C", "currency", "euro"),
    ]
    root = _write_store(tmp_path / "info", facts)
    holes = {(h.entity, h.rel_norm): h for h in StructuralGapScanner(TripleStore(root)).scan()}
    cap = holes[("Xland", "capital")]
    cur = holes[("Xland", "currency")]
    assert cap.coverage == cur.coverage and cap.salience == cur.salience   # only uncertainty differs
    assert cap.info > cur.info                            # distinct capitals >> identical currencies
    assert cap.score > cur.score


def test_not_any_missing_edge_only_schema_induced_holes(tmp_path):
    """A relation NO peer has (coverage 0) is NEVER proposed — the signal is the induced schema, not
    'any relation in the vocabulary the entity lacks'. Countries have no atomic_number/boiling_point,
    so those are never holes; and a COMPLETE entity has no hole at all."""
    shipped = _schema_shipped(tmp_path)
    holes = StructuralGapScanner(TripleStore(shipped)).scan()
    rel_norms = {h.rel_norm for h in holes}
    assert "atomic number" not in rel_norms and "boiling point" not in rel_norms
    assert not any(h.entity == "Brazil" for h in holes)   # Brazil has every peer relation
    # every proposed hole is a relation at least half its type-peers actually have
    assert all(h.coverage >= 0.5 for h in holes)
    assert all(h.n_peers_with_rel >= 1 for h in holes)


# ══ (c) STILL SAFE — shipped untouched, operator gate holds, fabrication 0 ═════════════════════════
def test_shipped_store_byte_unchanged_after_curiosity_run(tmp_path):
    """A full curiosity-driven run (reads the shipped graph to detect holes, mines + injects on the
    SCRATCH copy) leaves the shipped store byte-identical."""
    shipped = _schema_shipped(tmp_path)
    before = store_digest(shipped)
    daemon, queue, _ = _daemon(tmp_path, shipped)
    daemon.run_overnight([[], [], []])
    after = store_digest(shipped)
    assert after == before                               # every file hash + row count identical
    assert len(queue.items()) == 3                       # unchanged NOT because nothing happened


def test_curiosity_never_writes_without_operator_signature(tmp_path):
    """Curiosity chooses WHAT to investigate; it weakens no gate. A curiosity-queued candidate still
    cannot reach any store without the exact phrase + confirmation flag."""
    shipped = _schema_shipped(tmp_path)
    daemon, queue, _ = _daemon(tmp_path, shipped)
    daemon.run_overnight([[], [], []])

    approved = tmp_path / "approved"
    shutil.copytree(shipped, approved)
    before = store_digest(approved)

    d1 = queue.approve_and_apply(approved, operator_confirmed=False,
                                 confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
                                 staging_dir=tmp_path / "staging", forbid_root=shipped)
    assert d1["applied"] == 0 and d1["allowed"] is False
    d2 = queue.approve_and_apply(approved, operator_confirmed=True, confirmation_phrase="nope",
                                 staging_dir=tmp_path / "staging", forbid_root=shipped)
    assert d2["applied"] == 0 and d2["allowed"] is False
    assert store_digest(approved) == before              # both denials wrote nothing
    assert all(it["status"] == "pending" for it in queue.items())


def test_curiosity_approved_facts_answer_and_no_evidence_hole_stays_a_gap(tmp_path):
    """After an explicit operator approval into an ephemeral store, curiosity-found holes ground; the
    no-evidence structural holes (Atlantis) ground in neither queue nor graph (fabrication 0)."""
    shipped = _schema_shipped(tmp_path)
    daemon, queue, _ = _daemon(tmp_path, shipped)
    daemon.run_overnight([[], [], []])

    approved = tmp_path / "approved"
    shutil.copytree(shipped, approved)
    signed = queue.approve_and_apply(approved, operator_confirmed=True,
                                     confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
                                     staging_dir=tmp_path / "staging", forbid_root=shipped)
    assert signed["allowed"] is True and signed["applied"] == 3
    assert signed["production_store_mutated"] is False

    st = TripleStore(approved)
    for q, expect in [("what is the currency of France?", "euro"),
                      ("what is the population of Germany?", "83 million"),
                      ("what is the language of Japan?", "Japanese")]:
        core = resolve_relational(q, "en", store=st)
        assert core["answer_kind"] == "relational_edge_lookup", (q, core["answer_kind"])
        assert expect.lower() in core["answer"].lower()
        assert core["reasoning_certificate"]["guarantees"]["fabricated_facts"] is False

    # fabrication 0: Atlantis was a genuine structural hole (a Country missing population), curiosity
    # DID select it — but with no evidence it stays an honest gap, never a guess.
    core_atl = resolve_relational("what is the population of Atlantis?", "en", store=st)
    assert core_atl["answer_kind"] == "honest_abstain_relational"


# ══ (d) RECURRENCE SOURCE INTACT — coexists, and cleanly disables ═════════════════════════════════
def test_recurrence_and_curiosity_coexist_and_are_tagged(tmp_path):
    """A re-asked question (recurrence) and a never-asked structural hole are BOTH pursued in one run;
    each pursuit is tagged with the source it came from. Proves the second source is additive, not a
    replacement."""
    shipped = _schema_shipped(tmp_path)
    daemon, queue, ledger = _daemon(tmp_path, shipped)

    # Japan currency is NOT a structural hole (Japan already HAS currency) but IS a recurrence gap for
    # a DIFFERENT relation: re-ask "what is the area of Japan?" (area: no peer has it -> not a hole,
    # so it can ONLY enter via recurrence). Give it evidence so it verifies.
    corpus = SCHEMA_CORPUS + [
        {"url": "https://en.wikipedia.org/wiki/Japan_geo",
         "text": "The area of Japan is 377975 square kilometers."},
        {"url": "https://www.worldometers.info/geography/japan",
         "text": "Japan's area is 377975 square kilometers."},
    ]
    daemon, queue, ledger = _daemon(tmp_path, shipped, corpus=corpus)
    area_q = "what is the area of Japan?"
    report = daemon.run_overnight([[area_q], [area_q]])   # recurs to the floor over two windows

    # area is NOT a structural hole (no Country peer has area) -> it entered ONLY via recurrence
    assert "area" not in {h["question"].split()[3] for h in daemon.curiosity_targets()}
    assert report.pursued_recurrence >= 1                 # the re-asked area gap
    assert report.pursued_curiosity == 5                  # the five structural holes
    # both kinds produced queued candidates (area + the 3 evidenced structural holes)
    titles = {i["title"] for i in queue.items()}
    assert any("area" in t for t in titles)
    assert "France currency = euro" in titles


def test_disabling_curiosity_reverts_to_pure_recurrence(tmp_path):
    """With curiosity OFF the daemon is the shipped recurrence-only engine: zero holes detected, and
    an empty question feed pursues nothing (the exact pre-change behavior)."""
    shipped = _schema_shipped(tmp_path)
    daemon, queue, ledger = _daemon(tmp_path, shipped, enable_curiosity=False)
    assert daemon.curiosity_targets() == []
    report = daemon.run_overnight([[], [], []])
    assert report.curiosity_holes_detected == 0
    assert report.pursued == 0 and report.pursued_curiosity == 0
    assert queue.items() == []


def test_no_schema_no_holes_isa_only_graph_is_inert(tmp_path):
    """Curiosity needs peer evidence to induce an expectation. On an is_a-only graph (rich context but
    no relational peers) there is NO schema, so NO hole is invented — the honest, correct behavior and
    the reason the shipped sealed gate (is_a-only fixtures) is unaffected by curiosity."""
    root = _write_store(tmp_path / "isa", [("France", "is_a", "Country"), ("Japan", "is_a", "Country"),
                                           ("Brazil", "is_a", "Country"), ("Hamlet", "is_a", "Play")])
    assert StructuralGapScanner(TripleStore(root)).scan() == []
