# -*- coding: utf-8 -*-
"""Hermetic tests for the Wikidata truthy-dump ingest pipeline
(scripts/wikidata_truthy_ingest.py).

No network, no 66 GB dump, no shipped store: a tiny SYNTHETIC truthy .nt.gz fixture is built
in tmp_path and the full two-pass pipeline runs against it, so every gate the sealed report
claims (curated mapping, entity-object-only, English-only, is_a noise stoplist, self-loop drop,
truncation-style missing-label drop, provenance) is pinned. Parsing helpers are unit-tested
directly on real-shaped N-Triples lines.
"""
from __future__ import annotations

import gzip
import json
import os
import sqlite3
import struct
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (str(REPO_ROOT), str(REPO_ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import wikidata_truthy_ingest as wd  # noqa: E402


# ── pure parsing helpers ─────────────────────────────────────────────────────
def test_parse_en_label_and_qid():
    line = ('<http://www.wikidata.org/entity/Q31> '
            '<http://www.w3.org/2000/01/rdf-schema#label> "Belgium"@en .\n')
    s, p, o = wd.parse_triple(line)
    assert wd.qid_int(s) == 31
    assert p == wd._LABEL_PRED
    assert wd.parse_en_label(o) == "Belgium"
    for bad in (
        "<http://www.wikidata.org/entity/Q+31>",
        "<http://www.wikidata.org/entity/Q031>",
        "<http://www.wikidata.org/entity/Q0>",
        "<http://www.wikidata.org/entity/Q18446744073709551616>",
    ):
        assert wd.qid_int(bad) is None


def test_property_identity_type_and_revision_parsers_are_exact():
    assert wd.pid_int("<http://www.wikidata.org/entity/P31>") == 31
    assert wd.pid_int("<http://www.wikidata.org/entity/Q31>") is None
    assert (
        wd.property_data_pid_int(
            "<http://www.wikidata.org/wiki/Special:EntityData/P31>"
        )
        == 31
    )
    assert (
        wd.property_type_iri(
            "<http://wikiba.se/ontology#WikibaseItem>"
        )
        == "http://wikiba.se/ontology#WikibaseItem"
    )
    assert wd.property_type_iri("<https://evil.example/WikibaseItem>") is None
    assert (
        wd.property_revision(
            '"123"^^<http://www.w3.org/2001/XMLSchema#integer>'
        )
        == "123"
    )
    assert wd.property_revision('"123"') is None


def test_statement_mapping_and_entity_object():
    line = ('<http://www.wikidata.org/entity/Q142> '
            '<http://www.wikidata.org/prop/direct/P36> '
            '<http://www.wikidata.org/entity/Q90> .\n')
    s, p, o = wd.parse_triple(line)
    pid = p.split(wd._DIRECT)[1].rstrip(">")
    assert wd.RELMAP[pid] == "capital"
    assert wd.qid_int(s) == 142 and wd.qid_int(o) == 90


def test_non_en_label_and_literal_rejected():
    assert wd.parse_en_label('"Belgique"@fr') is None
    assert wd.qid_int('"1952-03-11"^^<http://www.w3.org/2001/XMLSchema#date>') is None
    # a lexeme / property URI is not a Q-id entity
    assert wd.qid_int("<http://www.wikidata.org/entity/P31>") is None


def test_profiled_literal_parser_is_exact_and_default_deny():
    integer = {"kind": "integer", "minimum": 1, "maximum": 200}
    assert wd.parse_literal_object(
        '"+118"^^<http://www.w3.org/2001/XMLSchema#decimal>', integer,
    )["value"] == "118"
    assert wd.parse_literal_object(
        '"1.5"^^<http://www.w3.org/2001/XMLSchema#decimal>', integer,
    ) is None
    assert wd.parse_literal_object('"0"^^<http://www.w3.org/2001/XMLSchema#integer>', integer) is None

    text = {"kind": "plain_string", "max_length": 20}
    assert wd.parse_literal_object(r'"H\u2082O"', text)["value"] == "H₂O"
    assert wd.parse_literal_object('"Wasser"@de', text) is None
    assert wd.parse_literal_object('"한국어"', text) is None

    date = {"kind": "date"}
    parsed = wd.parse_literal_object(
        '"1952-03-11T00:00:00Z"^^<http://www.w3.org/2001/XMLSchema#dateTime>', date,
    )
    assert parsed and parsed["value"] == "1952-03-11T00:00:00Z"
    assert wd.parse_literal_object('"not-a-date"^^<http://www.w3.org/2001/XMLSchema#date>', date) is None
    assert wd.parse_literal_object("<http://www.wikidata.org/entity/Q5>", text) is None


def test_literal_parser_rejects_invalid_lexicals_escapes_dates_and_predicate_hosts():
    integer = {"kind": "integer", "minimum": 1, "maximum": 200}
    assert wd.parse_literal_object(
        '"1.0"^^<http://www.w3.org/2001/XMLSchema#integer>', integer,
    ) is None
    assert wd.parse_literal_object(
        '"1e2"^^<http://www.w3.org/2001/XMLSchema#decimal>', integer,
    ) is None
    assert wd.parse_literal_object(r'"bad\q"', {"kind": "plain_string", "max_length": 20}) is None
    assert wd.parse_literal_object(
        '"2026-99-99"^^<http://www.w3.org/2001/XMLSchema#date>', {"kind": "date"},
    ) is None
    assert wd.parse_literal_object(
        '"+0000-01-01T00:00:00Z"^^'
        '<http://www.w3.org/2001/XMLSchema#dateTime>', {"kind": "date"},
    )["value"] == "+0000-01-01T00:00:00Z"
    assert wd.parse_triple(
        "<http://www.wikidata.org/entity/Q1> "
        "<http://www.wikidata.org/prop/direct/P31> "
        "<http://www.wikidata.org/entity/Q2>\n"
    ) is None
    assert wd.direct_property_id(
        "<https://evil.example/prop/direct/P1086>"
    ) is None


def test_literal_schema_is_data_owned_and_hashed():
    props, digest, doc = wd.load_literal_schema()
    assert doc["profile"] == "wikidata_science_literals_v1"
    assert props["P1086"]["predicate"] == "atomic_number"
    assert props["P274"]["predicate"] == "chemical_formula"
    assert len(digest) == 64


def test_literal_schema_rejects_unknown_keys_and_noninteger_constraints(tmp_path):
    base = {
        "schema_version": 1,
        "profile": "test_profile_v1",
        "quantity_semantics": "unit-bearing quantities deferred",
        "properties": {
            "P1086": {
                "predicate": "atomic_number",
                "kind": "integer",
                "minimum": 1,
                "maximum": 200,
                "source": "https://www.wikidata.org/wiki/Property:P1086",
            },
        },
    }
    path = tmp_path / "schema.json"
    bad = json.loads(json.dumps(base))
    bad["properties"]["P1086"]["maximum"] = 200.0
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        wd.load_literal_schema(path)
    bad = json.loads(json.dumps(base))
    bad["properties"]["P1086"]["maximim"] = bad["properties"]["P1086"].pop("maximum")
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        wd.load_literal_schema(path)


def test_direct_normalized_is_not_direct():
    # external-ID noise carries /prop/direct-normalized/, which must NOT match /prop/direct/
    assert wd._DIRECT not in "<http://www.wikidata.org/prop/direct-normalized/P214>"


def test_escapes_and_inner_period():
    assert wd.parse_en_label(r'"say \"hi\""@en') == 'say "hi"'
    assert wd.parse_en_label('"J. R. R. Tolkien"@en') == "J. R. R. Tolkien"
    assert wd.unescape_nt(r"aAb") == "aAb"


# ── full-pipeline fixture ────────────────────────────────────────────────────
def _write_fixture(path: Path) -> None:
    L = "<http://www.w3.org/2000/01/rdf-schema#label>"
    A = "<http://www.w3.org/2004/02/skos/core#altLabel>"
    T = "<http://wikiba.se/ontology#propertyType>"
    V = "<http://schema.org/version>"
    def ent(q):  return f"<http://www.wikidata.org/entity/Q{q}>"
    def pent(p): return f"<http://www.wikidata.org/entity/P{p}>"
    def pdata(p):
        return f"<http://www.wikidata.org/wiki/Special:EntityData/P{p}>"
    def prop(pid): return f"<http://www.wikidata.org/prop/direct/{pid}>"
    def lab(q, text, lang="en"): return f'{ent(q)} {L} "{text}"@{lang} .'
    def plab(p, text, lang="en"): return f'{pent(p)} {L} "{text}"@{lang} .'
    def palias(p, text, lang="en"): return f'{pent(p)} {A} "{text}"@{lang} .'
    def ptype(p, kind):
        return f"{pent(p)} {T} <http://wikiba.se/ontology#{kind}> ."
    def prev(p, revision):
        return (
            f'{pdata(p)} {V} "{revision}"^^'
            "<http://www.w3.org/2001/XMLSchema#integer> ."
        )
    def stmt(sq, pid, oq): return f"{ent(sq)} {prop(pid)} {ent(oq)} ."

    lines = [
        # --- property catalog rows (all four evidence dimensions required) ---
        plab(36, "capital"),
        palias(36, "seat of government"),
        palias(36, "capitale", "fr"),  # non-English alias must be ignored
        ptype(36, "WikibaseItem"),
        prev(36, 111),
        plab(1086, "atomic number"),
        palias(1086, "proton number"),
        ptype(1086, "Quantity"),
        prev(1086, 222),
        # --- labels (@en) ---
        lab(42, "Douglas Adams"), lab(42, "Douglas Adams", "fr"),   # @fr must be ignored
        lab(142, "France"), lab(90, "Paris"), lab(36180, "writer"),
        lab(5, "human"), lab(515, "city"),
        lab(64, "Berlin"), lab(183, "Germany"), lab(188, "German"),
        lab(31, "Belgium"), lab(7411, "Dutch"),
        lab(556, "hydrogen"), lab(283, "water"),
        lab(4167410, "Wikimedia disambiguation page"),             # is_a noise class
        lab(1000, "Mercury"),                                       # instance-of a disambig page
        lab(999, "한국어"),                             # @en-tagged Hangul (defensive)
        # --- statements ---
        stmt(42, "P106", 36180),   # Douglas Adams occupation writer   KEEP
        stmt(42, "P31", 5),        # Douglas Adams is_a human          KEEP
        stmt(142, "P36", 90),      # France capital Paris              KEEP (fills the gap)
        stmt(142, "P31", 6256),    # object Q6256 has NO label -> DROP (truncation-style)
        stmt(90, "P17", 142),      # Paris country France             KEEP
        stmt(90, "P31", 515),      # Paris is_a city                  KEEP
        stmt(64, "P17", 183),      # Berlin country Germany           KEEP
        stmt(183, "P37", 188),     # Germany official_language German KEEP
        stmt(31, "P37", 7411),     # Belgium official_language Dutch  KEEP
        stmt(1000, "P31", 4167410),# Mercury is_a <disambig>          DROP (noise stoplist)
        stmt(5, "P279", 5),        # human is_a human                 DROP (self-loop)
        stmt(999, "P31", 5),       # <Hangul> is_a human              DROP (hangul defensive)
        # literal-object statement (date of birth) -> DROP (object not a Q-id)
        ('<http://www.wikidata.org/entity/Q42> '
         '<http://www.wikidata.org/prop/direct/P569> '
         '"1952-03-11"^^<http://www.w3.org/2001/XMLSchema#date> .'),
        # profiled literal statements: ignored by entity PASS-2, consumed by literal-only mode
        ('<http://www.wikidata.org/entity/Q556> '
         '<http://www.wikidata.org/prop/direct/P1086> '
         '"+1"^^<http://www.w3.org/2001/XMLSchema#decimal> .'),
        ('<http://www.wikidata.org/entity/Q556> '
         '<http://www.wikidata.org/prop/direct/P274> "H" .'),
        ('<http://www.wikidata.org/entity/Q283> '
         '<http://www.wikidata.org/prop/direct/P274> "H\\u2082O" .'),
        # rejected literal candidates
        ('<http://www.wikidata.org/entity/Q283> '
         '<http://www.wikidata.org/prop/direct/P1086> '
         '"1.5"^^<http://www.w3.org/2001/XMLSchema#decimal> .'),
        ('<http://www.wikidata.org/entity/Q283> '
         '<http://www.wikidata.org/prop/direct/P274> "Wasser"@de .'),
        ('<http://www.wikidata.org/entity/Q9999> '
         '<http://www.wikidata.org/prop/direct/P274> "X" .'),
        # direct-NORMALIZED instance-of -> DROP (not /prop/direct/)
        ('<http://www.wikidata.org/entity/Q42> '
         '<http://www.wikidata.org/prop/direct-normalized/P31> '
         '<http://www.wikidata.org/entity/Q5> .'),
        # un-curated property (P18 image, entity-shaped here) -> DROP (not in RELMAP)
        stmt(142, "P1889", 90),
    ]
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _staged_set(staging: Path):
    from packages.graph_scale.triple_store import TripleStore
    st = TripleStore(staging, dict_backend="ram")
    cols = st.open_columns()
    s, p, o = cols["s"], cols["p"], cols["o"]
    triples = {(st.terms.term(int(s[i])), st.terms.term(int(p[i])), st.terms.term(int(o[i])))
               for i in range(len(s))}
    return triples, st


def test_full_pipeline_on_fixture(tmp_path):
    dump = tmp_path / "fixture.nt.gz"
    label_db = tmp_path / "labels.sqlite"
    staging = tmp_path / "staging_b1_wikidata"
    _write_fixture(dump)

    report = wd.run(dump, label_db, staging, do_pass1=True, do_pass2=True,
                    dict_backend="ram", trace_n=50)
    triples, st = _staged_set(staging)

    # --- KEEPs: real curated common-sense edges land ---
    assert ("Douglas Adams", "occupation", "writer") in triples
    assert ("Douglas Adams", "is_a", "human") in triples
    assert ("France", "capital", "Paris") in triples          # the known-gap fix
    assert ("Paris", "country", "France") in triples
    assert ("Paris", "is_a", "city") in triples
    assert ("Berlin", "country", "Germany") in triples
    assert ("Germany", "official_language", "German") in triples
    assert ("Belgium", "official_language", "Dutch") in triples

    # --- DROPs ---
    assert ("Mercury", "is_a", "Wikimedia disambiguation page") not in triples  # noise stoplist
    assert ("human", "is_a", "human") not in triples                            # self-loop
    assert not any(s == "한국어" for s, _, _ in triples)            # hangul defensive
    assert not any(p == "P31" for _, p, _ in triples)                           # relations are OUR vocab
    # no literal ever became an object (date of birth dropped)
    assert not any("1952" in o for _, _, o in triples)
    # P1889 was not in the curated map -> nothing from it
    assert all(p in set(wd.RELMAP.values()) for _, p, _ in triples)

    # --- drop counters reflect each gate firing ---
    d = report["pass2_join"]["dropped"]
    assert d["is_a_noise_class"] >= 1
    assert d["self_loop"] >= 1
    assert d["hangul_defensive"] >= 1
    assert d["no_object_label_in_slice"] >= 1     # Q6256 had no label in the slice

    # --- English-only: no Hangul survives anywhere in the staged vocab ---
    assert not any(wd.HANGUL.search(t) for t in st.terms._i2s)

    # --- provenance: every staged row cites the dump ---
    fws = st.facts_with_sources("France")
    assert fws and all(name == "wikidata-truthy" for *_rest, name, _url in fws)

    # --- 0 fabrication: staged edge count == distinct KEEP set (no phantom rows) ---
    assert report["pass2_join"]["staged_edges"] == len(triples)


def test_pass1_captures_pid_catalog_without_hand_mapping(tmp_path):
    dump = tmp_path / "fixture.nt.gz"
    label_db = tmp_path / "labels.sqlite"
    _write_fixture(dump)

    result = wd.build_label_db(dump, label_db)
    con = sqlite3.connect(label_db)
    try:
        assert con.execute("SELECT k, v FROM pl ORDER BY k").fetchall() == [
            (36, "capital"),
            (1086, "atomic number"),
        ]
        assert con.execute("SELECT k, v FROM pa ORDER BY k, v").fetchall() == [
            (36, "seat of government"),
            (1086, "proton number"),
        ]
        assert con.execute("SELECT k, v FROM pt ORDER BY k").fetchall() == [
            (36, "http://wikiba.se/ontology#WikibaseItem"),
            (1086, "http://wikiba.se/ontology#Quantity"),
        ]
        assert con.execute("SELECT k, v FROM pr ORDER BY k").fetchall() == [
            (36, "111"),
            (1086, "222"),
        ]
        meta = dict(con.execute("SELECT k, v FROM meta"))
    finally:
        con.close()

    assert result["property_labels"] == 2
    assert result["property_aliases"] == 2
    assert result["property_types"] == 2
    assert result["property_revisions"] == 2
    assert meta["property_catalog_profile"] == "wikidata_property_catalog_v1"
    assert meta["scope"] == "complete"


def test_pass1_rejects_conflicting_property_identity(tmp_path):
    dump = tmp_path / "conflict.nt.gz"
    label_db = tmp_path / "labels.sqlite"
    subject = "<http://www.wikidata.org/entity/P36>"
    predicate = "<http://www.w3.org/2000/01/rdf-schema#label>"
    with gzip.open(dump, "wt", encoding="utf-8") as fh:
        fh.write(f'{subject} {predicate} "capital"@en .\n')
        fh.write(f'{subject} {predicate} "not capital"@en .\n')

    with pytest.raises(ValueError, match="conflicting.*label"):
        wd.build_label_db(dump, label_db)
    assert not label_db.exists()


def test_shipped_store_is_never_touched(tmp_path):
    """The pipeline must write ONLY under the staging dir it is given — never the shipped store.
    Pinned by construction: run() with a tmp staging path leaves nothing outside tmp_path."""
    import hashlib

    shipped = REPO_ROOT / "data" / "graph_scale" / "kg_triples" / "s.col"
    before = None
    if shipped.exists():
        before = hashlib.sha256(shipped.read_bytes()).hexdigest()

    dump = tmp_path / "fixture.nt.gz"
    _write_fixture(dump)
    wd.run(dump, tmp_path / "labels.sqlite", tmp_path / "staging",
           do_pass1=True, do_pass2=True, dict_backend="ram")

    if before is not None:
        assert hashlib.sha256(shipped.read_bytes()).hexdigest() == before, \
            "shipped kg_triples/s.col changed — pipeline must never write the shipped store"


def test_literal_pass_uses_separate_stage_with_manifest_and_exact_provenance(tmp_path):
    dump = tmp_path / "fixture.nt.gz"
    label_db = tmp_path / "labels.sqlite"
    staging = tmp_path / "staging_s1_wikidata_literals"
    _write_fixture(dump)

    report = wd.run_literal_ingest(
        dump, label_db, staging, build_labels=True, dict_backend="ram", trace_n=20,
    )
    triples, st = _staged_set(staging)
    assert ("hydrogen", "atomic_number", "1") in triples
    assert ("hydrogen", "chemical_formula", "H") in triples
    assert ("water", "chemical_formula", "H₂O") in triples
    assert len(triples) == 3
    assert report["literal_pass"]["staged_edges"] == 3
    assert report["literal_pass"]["dropped"]["literal_parse_or_constraint"] == 2
    assert report["literal_pass"]["dropped"]["no_subject_label_in_slice"] == 1
    manifest = json.loads((staging / wd._LITERAL_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["mode"] == "wikidata-truthy-literal-only"
    assert manifest["schema_sha256"] == report["schema_sha256"]
    assert manifest["gates"]["unit_bearing_quantities_deferred"] is True
    assert manifest["label_db"]["binding_status"] == "verified_dump_identity"
    assert manifest["promotion_eligible"] is True
    raw_binding = (staging / "qid_pid.col").read_bytes()
    assert len(raw_binding) == 3 * 12
    assert {
        (qid, pid) for qid, pid in struct.iter_unpack("<QI", raw_binding)
    } == {(556, 1086), (556, 274), (283, 274)}
    trace = (staging / "PROVENANCE_TRACE.jsonl").read_text(encoding="utf-8")
    assert "P1086" in trace and "atomic_number" in trace
    sources = st.facts_with_sources("hydrogen")
    assert sources and all(name == "wikidata-truthy-literal" for *_r, name, _u in sources)
    from packages.reasoning_vm.deliberator.reasoner import Deliberator
    dlb = Deliberator(st.facts_about, with_kernels=False)
    mcq = dlb.answer_mcq_derive(
        "hydrogen", "atomic_number", {"A": "8", "B": "1", "C": "6", "D": "2"},
    )
    assert mcq["choice_key"] == "B" and mcq["mode"] == "grounded"

    with pytest.raises(FileExistsError):
        wd.run_literal_ingest(
            dump, label_db, staging, build_labels=False, dict_backend="ram",
        )
    # Windows keeps numpy memmaps locked until the read-only probe object is collected.
    import gc
    del dlb, sources, st, triples
    gc.collect()
    rerun = wd.run_literal_ingest(
        dump, label_db, staging, build_labels=False, dict_backend="ram", replace=True,
    )
    assert rerun["literal_pass"]["staged_edges"] == 3


def test_bounded_literal_run_is_marked_partial_and_not_promotion_eligible(tmp_path):
    dump = tmp_path / "fixture.nt.gz"
    label_db = tmp_path / "labels.sqlite"
    staging = tmp_path / "partial-stage"
    _write_fixture(dump)
    wd.build_label_db(dump, label_db)
    report = wd.run_literal_ingest(
        dump, label_db, staging, max_lines=1000, dict_backend="ram",
    )
    assert report["completion_state"] == "partial"
    assert not (staging / wd._LITERAL_MANIFEST).exists()
    partial = json.loads(
        (staging / wd._LITERAL_PARTIAL_MANIFEST).read_text(encoding="utf-8")
    )
    assert partial["completion_state"] == "partial"
    assert partial["max_lines"] == 1000
    assert partial["promotion_eligible"] is False
    import landing_chain_lib as landing
    ok, detail = landing.store_completeness(staging)
    assert not ok and "partial" in detail["reason"]


def test_partial_label_db_never_makes_a_full_literal_stage_promotion_eligible(tmp_path):
    dump = tmp_path / "fixture.nt.gz"
    label_db = tmp_path / "partial-labels.sqlite"
    staging = tmp_path / "stage"
    _write_fixture(dump)
    wd.build_label_db(dump, label_db, max_lines=2)
    report = wd.run_literal_ingest(dump, label_db, staging, dict_backend="ram")
    manifest = json.loads((staging / wd._LITERAL_MANIFEST).read_text(encoding="utf-8"))
    assert report["completion_state"] == "complete"
    assert manifest["label_db"]["binding_status"] == "partial_dump_identity"
    assert manifest["promotion_eligible"] is False
    import landing_chain_lib as landing
    ok, detail = landing.store_completeness(staging)
    assert not ok and "promotion eligible" in detail["reason"]


def test_literal_promotion_completeness_requires_manifest_source_and_aligned_evidence(tmp_path):
    dump = tmp_path / "fixture.nt.gz"
    label_db = tmp_path / "labels.sqlite"
    staging = tmp_path / "stage"
    _write_fixture(dump)
    wd.run_literal_ingest(
        dump, label_db, staging, build_labels=True, dict_backend="ram",
    )
    import landing_chain_lib as landing
    ok, _detail = landing.store_completeness(staging)
    assert ok

    manifest = staging / wd._LITERAL_MANIFEST
    manifest_bytes = manifest.read_bytes()
    manifest.unlink()
    ok, detail = landing.store_completeness(staging)
    assert not ok and "without a literal manifest" in detail["reason"]
    manifest.write_bytes(manifest_bytes)

    source_column = staging / "src.col"
    source_bytes = source_column.read_bytes()
    source_column.unlink()
    ok, detail = landing.store_completeness(staging)
    assert not ok and "one source id per edge" in detail["reason"]
    source_column.write_bytes(source_bytes)

    evidence = staging / "qid_pid.col"
    evidence.write_bytes(evidence.read_bytes()[:-1])
    ok, detail = landing.store_completeness(staging)
    assert not ok and "sidecar is torn" in detail["reason"]


def test_literal_scan_rejects_dump_identity_change_before_install(tmp_path, monkeypatch):
    dump = tmp_path / "fixture.nt.gz"
    label_db = tmp_path / "labels.sqlite"
    staging = tmp_path / "stage"
    _write_fixture(dump)
    wd.build_label_db(dump, label_db)
    original = wd.join_literal_statements

    def join_then_mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        stat = dump.stat()
        os.utime(dump, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
        return result

    monkeypatch.setattr(wd, "join_literal_statements", join_then_mutate)
    with pytest.raises(RuntimeError, match="changed during"):
        wd.run_literal_ingest(dump, label_db, staging, dict_backend="ram")
    assert not staging.exists()


def test_invalid_utf8_fails_the_stream_instead_of_staging_replacement_text(tmp_path):
    dump = tmp_path / "invalid.nt.gz"
    with gzip.open(dump, "wb") as fh:
        fh.write(
            b'<http://www.wikidata.org/entity/Q283> '
            b'<http://www.wikidata.org/prop/direct/P274> "H\xffO" .\n'
        )
    with pytest.raises(UnicodeDecodeError):
        list(wd.stream_nt_lines(dump))


def test_failed_literal_replacement_preserves_previous_completed_stage(tmp_path):
    dump = tmp_path / "fixture.nt.gz"
    label_db = tmp_path / "labels.sqlite"
    staging = tmp_path / "literal-stage"
    _write_fixture(dump)
    wd.run_literal_ingest(
        dump, label_db, staging, build_labels=True, dict_backend="ram",
    )
    before = (staging / wd._LITERAL_MANIFEST).read_bytes()
    label_db.unlink()
    with pytest.raises(FileNotFoundError):
        wd.run_literal_ingest(
            dump, label_db, staging, build_labels=False,
            dict_backend="ram", replace=True,
        )
    assert (staging / wd._LITERAL_MANIFEST).read_bytes() == before


def test_sqlite_readonly_uri_handles_fragment_characters(tmp_path):
    dump = tmp_path / "fixture.nt.gz"
    label_db = tmp_path / "labels #1.sqlite"
    _write_fixture(dump)
    wd.build_label_db(dump, label_db)
    con = wd.open_label_db_readonly(label_db)
    try:
        assert con.execute("SELECT COUNT(*) FROM l").fetchone()[0] > 0
    finally:
        con.close()


def test_staging_path_guard_refuses_shipped_ancestors_and_entity_collision(tmp_path, monkeypatch):
    shipped = tmp_path / "graph" / "kg_triples"
    entity = tmp_path / "graph" / "staging_b1_wikidata"
    literal = tmp_path / "graph" / "staging_s1_wikidata_literals"
    shipped.mkdir(parents=True)
    entity.mkdir()
    literal.mkdir()
    sentinel = shipped / "sentinel"
    sentinel.write_text("untouched", encoding="utf-8")
    monkeypatch.setattr(wd, "_SHIPPED_ROOT", shipped)
    monkeypatch.setattr(wd, "_ENTITY_STAGING_ROOT", entity)
    monkeypatch.setattr(wd, "_LITERAL_STAGING_ROOT", literal)

    for unsafe in (shipped, shipped / "child", shipped.parent, entity, entity / "child"):
        with pytest.raises(ValueError):
            wd.guard_staging_target(unsafe, literal_mode=True)
    with pytest.raises(ValueError):
        wd.guard_staging_target(literal, literal_mode=False)
    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_literal_preflight_guards_label_db_before_destructive_pass1(tmp_path, monkeypatch):
    graph = tmp_path / "graph"
    shipped = graph / "kg_triples"
    entity = graph / "staging_b1_wikidata"
    literal = graph / "staging_s1_wikidata_literals"
    shipped.mkdir(parents=True)
    entity.mkdir()
    literal.mkdir()
    sentinel = shipped / "meta.json"
    sentinel.write_text("untouched", encoding="utf-8")
    monkeypatch.setattr(wd, "_SHIPPED_ROOT", shipped)
    monkeypatch.setattr(wd, "_ENTITY_STAGING_ROOT", entity)
    monkeypatch.setattr(wd, "_LITERAL_STAGING_ROOT", literal)

    dump = tmp_path / "fixture.nt.gz"
    _write_fixture(dump)
    with pytest.raises(ValueError, match="label DB target"):
        wd.run_literal_ingest(
            dump, sentinel, tmp_path / "safe-stage",
            build_labels=True, dict_backend="ram",
        )
    assert sentinel.read_text(encoding="utf-8") == "untouched"
    assert not (tmp_path / "safe-stage").exists()


def test_entity_replace_refuses_unowned_directory_without_deleting_it(tmp_path):
    dump = tmp_path / "fixture.nt.gz"
    label_db = tmp_path / "labels.sqlite"
    staging = tmp_path / "unowned"
    _write_fixture(dump)
    wd.build_label_db(dump, label_db)
    staging.mkdir()
    sentinel = staging / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="unowned"):
        wd.run(
            dump, label_db, staging, do_pass1=False, do_pass2=True,
            dict_backend="ram", replace=True,
        )
    assert sentinel.read_text(encoding="utf-8") == "keep"


# ── firewall membrane (Pass 2): --firewall observe wiring, default-off ────────
def test_firewall_membrane_default_off_is_unchanged(tmp_path):
    """run() with stage_pass=None (the default) leaves the report firewall-free -- proving the
    membrane is a strict no-op unless opted in."""
    dump = tmp_path / "fixture.nt.gz"
    _write_fixture(dump)
    report = wd.run(dump, tmp_path / "labels.sqlite", tmp_path / "staging",
                    do_pass1=True, do_pass2=True, dict_backend="ram")
    assert "firewall_membrane" not in report


def test_firewall_membrane_observes_every_staged_edge(tmp_path):
    """stage_pass=FirewallStagePass observes each staged edge (provenance/justification), and a
    seeded T0 fact nogood-quarantines the contradicting staged edge -- all on the tmp fixture."""
    from packages.truth_maintenance.live_membrane import FirewallStagePass

    dump = tmp_path / "fixture.nt.gz"
    _write_fixture(dump)

    # seed an operator fact that the fixture's "France capital Paris" edge contradicts
    fp = FirewallStagePass(provenance="wikidata-truthy",
                           t0_facts=[("France", "capital", "Lyon")])
    report = wd.run(dump, tmp_path / "labels.sqlite", tmp_path / "staging",
                    do_pass1=True, do_pass2=True, dict_backend="ram", stage_pass=fp)

    staged = report["pass2_join"]["staged_edges"]
    assert fp.observed == staged                                  # every staged edge was observed
    assert report["firewall_membrane"]["provenance"] == "wikidata-truthy"

    # the T0-contradicting edge is quarantined; the rest pass and carry a single_source tier
    qkeys = [q["fact_key"] for q in fp.quarantined]
    assert "capital(France)=Paris" in qkeys
    assert fp.passed == staged - 1
    assert all(r["tier"] == "single_source" for r in fp.sample_records)
    # staging store contents are unchanged by the membrane (still lists the edge it flagged)
    triples, _ = _staged_set(tmp_path / "staging")
    assert ("France", "capital", "Paris") in triples             # observe-only: nothing dropped


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
