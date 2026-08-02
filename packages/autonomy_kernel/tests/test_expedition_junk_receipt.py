# -*- coding: utf-8 -*-
"""The AVOID direction of the self-correction loop: a web expedition that probes a topic but gets
no corroborated content records a junk receipt, so the learner later steers away from it."""
import packages.flywheel.failure_receipts as fr
from packages.autonomy_kernel import web_expedition as we


def test_no_consensus_records_junk_receipt(tmp_path):
    fr._ARCHIVE = tmp_path / "r.jsonl"                        # isolate the ledger
    # three benign snippets, all from ONE domain → no sentence reaches 2-domain consensus
    rows = [{"snippet": f"이것은 검증되지 않은 임의의 문장 {i} 이다.", "url": "http://example.com/x"}
            for i in range(3)]
    rep = we.expedition("헛도메인", fetch=lambda t, n: rows, min_consensus=2)
    assert rep["results_fetched"] == 3 and rep["consensus_backed"] == 0
    recs = fr._load()
    assert any(r.get("topic") == "헛도메인" and r.get("kind") == "junk" for r in recs)
    assert any("no_consensus" in r.get("causes", []) for r in recs)


def test_corroborated_topic_records_nothing(tmp_path):
    fr._ARCHIVE = tmp_path / "r.jsonl"
    # the SAME sentence from two DISTINCT domains → consensus met → a good topic, no junk receipt
    rows = [{"snippet": "물은 수소와 산소로 이루어진 화합물이다.", "url": "http://a.org/1"},
            {"snippet": "물은 수소와 산소로 이루어진 화합물이다.", "url": "http://b.org/2"}]
    rep = we.expedition("물", fetch=lambda t, n: rows, min_consensus=2)
    assert rep["consensus_backed"] >= 1
    assert fr._load() == []                                   # a corroborated topic is not junk
