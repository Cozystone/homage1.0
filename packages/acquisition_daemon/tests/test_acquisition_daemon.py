# -*- coding: utf-8 -*-
"""SEALED GATE for the autonomous acquisition DAEMON (the safe OAM engine).

Deterministic — a CONTROLLED fixture corpus + a scoped ephemeral store, no live network — so the
whole overnight run is reproducible. The shared failure-receipt ledger is isolated to tmp per test
(autouse fixture) so pressure accounting cannot leak between tests or touch the real ledger.

The five gates the acceptance spec requires:

  (a) OVERNIGHT-SIM   — seed a set of gaps, run the daemon N cycles against fixture evidence; it
                        produces a QUEUE of consensus-verified candidate facts, each with provenance
                        and >= 2 domains. Measured gaps -> verified-candidate throughput.
  (b) OPERATOR-GATE   — the shipped store is BYTE-UNCHANGED after a full daemon run (digest + row
                        count identical); and no fact is written anywhere without an operator
                        signature (wrong phrase / no confirmation -> zero writes).
  (c) APPROVE-ANSWER  — after an explicit operator approval into an ephemeral store, previously
                        abstained questions become answerable; a gap with NO evidence is in neither
                        the queue nor the graph (fabrication 0), before AND after approval.
  (d) ENDOGENOUS      — targets come from pressure, not a schedule: a gap NOT under pressure (yet
                        with valid evidence) is NOT pursued; the SAME gap, once it recurs past the
                        floor, IS pursued and queued. Proves pressure — not a hardcoded list — selects.
  (e) NO-REGRESSION   — the reused EXCLUDE_PAIRS test-lock still holds THROUGH the daemon path
                        (population of France stays an honest gap even under pressure with evidence),
                        while a non-excluded fact under the same conditions does acquire.
"""
from __future__ import annotations

import shutil

import pytest

from packages.base_brain.relational_lookup import resolve_relational
from packages.candidate_promotion_gate import REQUIRED_CONFIRMATION_PHRASE
from packages.graph_scale.triple_store import TripleStore
from packages.knowledge_acquisition import FixtureEvidence
from packages.acquisition_daemon import (
    AcquisitionDaemon,
    AcquisitionQueue,
    GapLedger,
    store_digest,
)


# ── controlled evidence corpus (distinct domains per fact; varied phrasing) ───────────────────────
CORPUS = [
    # capital of France = Paris (3 distinct domains)
    {"url": "https://en.wikipedia.org/wiki/Paris",
     "text": "Paris is the capital of France and its most populous city, on the river Seine."},
    {"url": "https://www.britannica.com/place/France",
     "text": "France is a country in Western Europe. The capital of France is Paris."},
    {"url": "https://www.reddit.com/r/travel/comments/paris",
     "text": "Honestly France's capital is Paris and the food there is unbelievable."},

    # capital of Japan = Tokyo (2 distinct domains)
    {"url": "https://en.wikipedia.org/wiki/Tokyo",
     "text": "Tokyo is the capital of Japan and the seat of the Japanese government."},
    {"url": "https://www.nationsonline.org/oneworld/japan.htm",
     "text": "The capital of Japan is Tokyo, one of the largest metropolitan areas in the world."},

    # currency of Japan = yen (2 distinct domains)
    {"url": "https://www.xe.com/currency/jpy-japanese-yen",
     "text": "The currency of Japan is the yen, issued by the central bank."},
    {"url": "https://www.boj.or.jp/en/about",
     "text": "Japan's currency is the yen. It has been in use since the 19th century."},

    # capital of Brazil = Brasilia (2 distinct domains)
    {"url": "https://en.wikipedia.org/wiki/Brasilia",
     "text": "Brasilia is the capital of Brazil, a planned city inaugurated in 1960."},
    {"url": "https://www.britannica.com/place/Brazil",
     "text": "The capital of Brazil is Brasilia. Brazil is the largest country in South America."},

    # official language of Brazil = Portuguese (2 distinct domains) — the (d) unpressured-yet-provable gap
    {"url": "https://en.wikipedia.org/wiki/Brazil",
     "text": "The official language of Brazil is Portuguese, a legacy of colonial history."},
    {"url": "https://www.worldatlas.com/articles/brazil",
     "text": "Brazil's official language is Portuguese, spoken by nearly the entire population."},

    # who wrote Hamlet = William Shakespeare (2 distinct domains, active + passive)
    {"url": "https://en.wikipedia.org/wiki/Hamlet",
     "text": "Hamlet was written by William Shakespeare between 1599 and 1601."},
    {"url": "https://www.gutenberg.org/ebooks/hamlet",
     "text": "William Shakespeare wrote Hamlet, among the most influential tragedies in English."},

    # population of Japan = 125 million (NON-excluded, proves coverage is real)
    {"url": "https://en.wikipedia.org/wiki/Japan",
     "text": "The population of Japan is 125 million, concentrated on the main islands."},
    {"url": "https://www.worldometers.info/world-population/japan-population",
     "text": "Japan's population is 125 million people as of the latest estimate."},

    # population of France = 68 million — EXCLUDE_PAIRS test-locked (must stay abstained even here)
    {"url": "https://en.wikipedia.org/wiki/France",
     "text": "The population of France is 68 million, most in urban areas."},
    {"url": "https://www.worldometers.info/world-population/france-population",
     "text": "France's population is 68 million people according to recent data."},

    # single-domain only -> below consensus floor (never verifies)
    {"url": "https://narnia.fandom.com/wiki/Cair_Paravel",
     "text": "The capital of Narnia is Cair Paravel, the castle of the High King."},
    # NOTE: no document states the capital of Atlantis -> a gap with NO evidence (fabrication guard)
]

ENTITIES = [("France", "Country"), ("Japan", "Country"), ("Brazil", "Country"),
            ("Hamlet", "Play"), ("Narnia", "Country"), ("Atlantis", "Country")]


@pytest.fixture(autouse=True)
def _isolate_shared_ledger(tmp_path, monkeypatch):
    """Point the REUSED failure-receipt ledger at a tmp path so pressure accounting is deterministic
    and never touches the real data/flywheel ledger."""
    import packages.flywheel.failure_receipts as fr
    monkeypatch.setattr(fr, "_ARCHIVE", tmp_path / "shared_failure_receipts.jsonl")


def _shipped(tmp_path):
    """A store that holds is_a facts (rich entity context, but NO relational edge) so the target
    questions HONESTLY ABSTAIN — exactly the shipped-graph condition the loop is built for."""
    root = tmp_path / "shipped"
    st = TripleStore(root)
    for ent, kind in ENTITIES:
        st.add(ent, "is_a", kind)
    st.flush()
    del st
    return root


def _daemon(tmp_path, shipped, *, min_pressure=2):
    ledger = GapLedger(tmp_path / "gaps.json")
    queue = AcquisitionQueue(tmp_path / "queue.json")
    daemon = AcquisitionDaemon(shipped_root=shipped, scratch_root=tmp_path / "scratch",
                               evidence=FixtureEvidence(corpus=CORPUS), queue=queue, ledger=ledger,
                               min_pressure=min_pressure)
    return daemon, queue, ledger


VERIFIABLE = [
    "what is the capital of France?",
    "what is the capital of Japan?",
    "what is the currency of Japan?",
    "what is the capital of Brazil?",
    "who wrote Hamlet?",
]
UNVERIFIABLE_UNDER_PRESSURE = [
    "what is the capital of Narnia?",     # single domain -> below floor
    "what is the capital of Atlantis?",   # NO evidence at all
]


# ══ (a) OVERNIGHT-SIM THROUGHPUT ══════════════════════════════════════════════════════════════════
def test_overnight_sim_produces_verified_candidate_queue(tmp_path):
    """Seed a set of gaps, run the daemon over cycles; measure gaps -> verified candidates queued."""
    shipped = _shipped(tmp_path)
    daemon, queue, ledger = _daemon(tmp_path, shipped)

    asked = VERIFIABLE + UNVERIFIABLE_UNDER_PRESSURE
    # three time windows, each asking the whole set -> every gap RECURS -> crosses the pressure floor
    report = daemon.run_overnight([list(asked), list(asked), list(asked)])

    # 7 distinct gaps detected, all crossed the pressure floor, all pursued exactly once
    assert report.gaps_observed == 7
    assert report.gaps_under_pressure == 7
    assert report.pursued == 7
    # 5 evidence-backed facts became consensus-verified candidates; 2 (single-source + no-evidence) did not
    assert report.verified_queued == 5, [(i["title"], i["status"]) for i in queue.items()]
    assert report.insufficient_consensus == 2

    # every queued candidate carries provenance + >= 2 consensus domains, and is PENDING (unapproved)
    items = queue.items()
    assert len(items) == 5
    for it in items:
        assert it["status"] == "pending"
        assert it["item_type"] == "cloud_candidate"
        assert it["consensus_domains"] >= 2
        assert len(it["source_refs"]) >= 2            # provenance urls
        assert it["confidence"] >= 0.5
    # measured throughput signal
    verified_titles = sorted(i["title"] for i in items)
    assert "France capital = Paris" in verified_titles
    assert "Japan capital = Tokyo" in verified_titles


def test_pursued_once_no_double_mining_across_cycles(tmp_path):
    """A gap pursued in one cycle is not re-pursued on later cycles (idempotent), and re-queuing is
    deduped — the queue holds one candidate per fact."""
    shipped = _shipped(tmp_path)
    daemon, queue, _ = _daemon(tmp_path, shipped)
    daemon.run_overnight([list(VERIFIABLE), list(VERIFIABLE), list(VERIFIABLE), list(VERIFIABLE)])
    assert daemon.run_overnight.__self__ is daemon  # sanity
    assert len(queue.items()) == 5
    # each fact id appears once
    ids = [i["item_id"] for i in queue.items()]
    assert len(ids) == len(set(ids))


# ══ (b) OPERATOR-GATE HOLDS — shipped store provably untouched, no write without signature ════════
def test_shipped_store_byte_unchanged_after_daemon_run(tmp_path):
    """The safety-critical claim: an entire unattended run leaves the shipped store byte-identical."""
    shipped = _shipped(tmp_path)
    before = store_digest(shipped)
    daemon, queue, _ = _daemon(tmp_path, shipped)
    daemon.run_overnight([list(VERIFIABLE), list(VERIFIABLE)])
    after = store_digest(shipped)
    assert after == before                          # every file hash + row count identical
    assert before["rows"] == after["rows"] == len(ENTITIES)
    # the run DID produce candidates — the store being unchanged is not because nothing happened
    assert len(queue.items()) == 5


def test_no_write_without_operator_signature(tmp_path):
    """A queued candidate cannot reach any store without the exact phrase + confirmation flag."""
    shipped = _shipped(tmp_path)
    daemon, queue, _ = _daemon(tmp_path, shipped)
    daemon.run_overnight([list(VERIFIABLE), list(VERIFIABLE)])

    approved = tmp_path / "approved"
    shutil.copytree(shipped, approved)
    before = store_digest(approved)

    # no confirmation flag
    d1 = queue.approve_and_apply(approved, operator_confirmed=False,
                                 confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
                                 staging_dir=tmp_path / "staging", forbid_root=shipped)
    assert d1["applied"] == 0 and d1["allowed"] is False
    assert "operator_confirmation_required" in d1["reasons"]

    # wrong phrase
    d2 = queue.approve_and_apply(approved, operator_confirmed=True, confirmation_phrase="promote please",
                                 staging_dir=tmp_path / "staging", forbid_root=shipped)
    assert d2["applied"] == 0 and d2["allowed"] is False
    assert "required_phrase_mismatch" in d2["reasons"]

    # both denials wrote NOTHING, and left every queue item pending
    assert store_digest(approved) == before
    assert all(it["status"] == "pending" for it in queue.items())


def test_apply_refuses_to_target_the_shipped_store(tmp_path):
    """Even with a valid signature, the apply step refuses to write the shipped store (guard)."""
    shipped = _shipped(tmp_path)
    daemon, queue, _ = _daemon(tmp_path, shipped)
    daemon.run_overnight([list(VERIFIABLE), list(VERIFIABLE)])
    before = store_digest(shipped)
    r = queue.approve_and_apply(shipped, operator_confirmed=True,
                                confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
                                staging_dir=tmp_path / "staging", forbid_root=shipped)
    assert r["applied"] == 0 and r["allowed"] is False
    assert "refused_target_is_shipped_store" in r["reasons"]
    assert store_digest(shipped) == before


# ══ (c) APPROVE-THEN-ANSWER + FABRICATION 0 ═══════════════════════════════════════════════════════
def test_operator_approval_makes_abstained_questions_answerable(tmp_path):
    """After an explicit operator approval into an EPHEMERAL store, previously-abstained questions
    ground; a no-evidence gap grounds in neither queue nor graph (fabrication 0)."""
    shipped = _shipped(tmp_path)
    daemon, queue, _ = _daemon(tmp_path, shipped)
    daemon.run_overnight([list(VERIFIABLE + UNVERIFIABLE_UNDER_PRESSURE)] * 2)

    # fabrication-0 at the QUEUE: no candidate for the no-evidence / single-source gaps
    titles = " ".join(i["title"] for i in queue.items())
    assert "Atlantis" not in titles and "Narnia" not in titles

    approved = tmp_path / "approved"
    shutil.copytree(shipped, approved)

    # every target abstains against the ephemeral store BEFORE approval
    st0 = TripleStore(approved)
    for q in VERIFIABLE:
        assert resolve_relational(q, "en", store=st0)["answer_kind"] == "honest_abstain_relational"

    signed = queue.approve_and_apply(approved, operator_confirmed=True,
                                     confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
                                     staging_dir=tmp_path / "staging", forbid_root=shipped)
    assert signed["allowed"] is True and signed["applied"] == 5
    assert signed["production_store_mutated"] is False

    # previously-abstained questions now answer with a grounded edge
    st1 = TripleStore(approved)
    for q, expect in [("what is the capital of France?", "Paris"),
                      ("what is the capital of Japan?", "Tokyo"),
                      ("who wrote Hamlet?", "Shakespeare")]:
        core = resolve_relational(q, "en", store=st1)
        assert core["answer_kind"] == "relational_edge_lookup", (q, core["answer_kind"])
        assert expect.lower() in core["answer"].lower()
        assert core["reasoning_certificate"]["guarantees"]["fabricated_facts"] is False

    # fabrication-0 in the GRAPH: the no-evidence gap stays abstained even after approval
    core_atl = resolve_relational("what is the capital of Atlantis?", "en", store=st1)
    assert core_atl["answer_kind"] == "honest_abstain_relational"
    assert not TripleStore(approved).facts_about("Atlantis") or all(
        p != "capital" for (_s, p, _o) in TripleStore(approved).facts_about("Atlantis"))


def test_no_evidence_gap_never_enters_queue_even_under_heavy_pressure(tmp_path):
    """Pursuing a no-evidence gap many times still yields no candidate (no guess is ever queued)."""
    shipped = _shipped(tmp_path)
    daemon, queue, ledger = _daemon(tmp_path, shipped)
    daemon.run_overnight([["what is the capital of Atlantis?"]] * 5)
    assert ledger.count("what is the capital of Atlantis?") == 5     # heavily pressured
    assert queue.items() == []                                       # yet nothing queued


# ══ (d) ENDOGENOUS, NOT SCHEDULED ═════════════════════════════════════════════════════════════════
def test_unpressured_gap_with_valid_evidence_is_not_pursued(tmp_path):
    """A gap that has PERFECT evidence but is NOT under pressure (asked once) is NOT pursued — proof
    the selector is pressure, not a hardcoded target list. The SAME gap, once it recurs, IS pursued."""
    shipped = _shipped(tmp_path)
    daemon, queue, ledger = _daemon(tmp_path, shipped)

    lang_q = "what is the official language of Brazil?"     # has 2-domain evidence in the corpus

    # Phase 1: asked ONCE -> below the pressure floor -> NOT pursued, NOT queued
    r1 = daemon.run_overnight([[lang_q]])
    assert ledger.count(lang_q) == 1
    assert r1.pursued == 0 and r1.gaps_under_pressure == 0
    assert queue.items() == []

    # it is genuinely a real, abstaining gap with usable evidence — the ONLY reason it wasn't
    # pursued is the lack of pressure (not lack of a gap, not lack of evidence)
    assert resolve_relational(lang_q, "en",
                              store=TripleStore(shipped))["answer_kind"] == "honest_abstain_relational"

    # Phase 2: it recurs -> crosses the floor -> now pursued and queued
    r2 = daemon.run_overnight([[lang_q]])                   # second observation -> count 2 -> pressure
    assert ledger.count(lang_q) == 2
    assert r2.pursued == 1 and r2.verified_queued == 1
    assert any("Portuguese" in i["title"] for i in queue.items())


def test_targets_are_not_a_hardcoded_list(tmp_path):
    """With an EMPTY question feed there is no pressure and nothing is pursued, even though the
    evidence corpus is full of facts the daemon COULD acquire — it chases pressure, not the corpus."""
    shipped = _shipped(tmp_path)
    daemon, queue, ledger = _daemon(tmp_path, shipped)
    report = daemon.run_overnight([[], [], []])
    assert report.gaps_observed == 0 and report.pursued == 0
    assert queue.items() == []


# ══ (e) NO-REGRESSION — reused invariants survive the daemon path ═════════════════════════════════
def test_excluded_test_lock_holds_through_daemon_path(tmp_path):
    """population of France has 2-domain evidence AND is under pressure, but the reused EXCLUDE_PAIRS
    test-lock keeps it an honest gap (never queued); population of Japan (non-excluded) DOES acquire."""
    shipped = _shipped(tmp_path)
    daemon, queue, _ = _daemon(tmp_path, shipped)
    daemon.run_overnight([["what is the population of France?", "what is the population of Japan?"]] * 2)

    titles = [i["title"] for i in queue.items()]
    assert not any("France population" in t or ("France" in t and "68" in t) for t in titles)
    assert any("Japan" in t and "125 million" in t for t in titles)

    # and even after operator approval, France population stays abstained (the lock is honest)
    approved = tmp_path / "approved"
    shutil.copytree(shipped, approved)
    queue.approve_and_apply(approved, operator_confirmed=True,
                            confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
                            staging_dir=tmp_path / "staging", forbid_root=shipped)
    st = TripleStore(approved)
    assert resolve_relational("what is the population of France?", "en",
                              store=st)["answer_kind"] == "honest_abstain_relational"


def test_non_relational_question_is_not_a_gap(tmp_path):
    """A plain define is not a relational gap -> never recorded, never pursued."""
    shipped = _shipped(tmp_path)
    daemon, queue, ledger = _daemon(tmp_path, shipped)
    daemon.run_overnight([["what is photosynthesis?"]] * 3)
    assert ledger.all_gaps() == {}
    assert queue.items() == []
