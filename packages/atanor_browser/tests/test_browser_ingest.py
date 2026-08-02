# -*- coding: utf-8 -*-
"""Browser ingest — host-voiced consensus + judge gate, no verified-store write."""

from __future__ import annotations

from packages.atanor_browser.browser_ingest import BrowserEvidenceLedger, ingest_page


def _page(subject: str, body: str, title: str | None = None) -> str:
    title = title or f"{subject} - 위키백과"
    return (f"<html><head><title>{title}</title></head><body>"
            f"<article><p>{subject}는 {body}이다.</p></article></body></html>")


def test_single_host_is_not_promotable(tmp_path):
    led = BrowserEvidenceLedger(tmp_path / "l.jsonl", min_hosts=2)
    ingest_page(_page("팔란티어", "미국의 소프트웨어 기업"),
                url="https://ko.wikipedia.org/wiki/팔란티어", ledger=led)
    assert led.promotable() == []  # one voice never promotes
    assert led.stats()["candidates"] == 1


def test_two_hosts_reach_consensus(tmp_path):
    led = BrowserEvidenceLedger(tmp_path / "l.jsonl", min_hosts=2)
    ingest_page(_page("팔란티어", "미국의 소프트웨어 기업"),
                url="https://ko.wikipedia.org/wiki/팔란티어", ledger=led)
    ingest_page(_page("팔란티어", "미국의 소프트웨어 기업"),
                url="https://namu.wiki/w/팔란티어", ledger=led)
    prom = led.promotable()
    assert len(prom) == 1
    assert prom[0]["host_voices"] == 2
    assert prom[0]["subject"] == "팔란티어"


def test_same_host_repeats_are_one_voice(tmp_path):
    led = BrowserEvidenceLedger(tmp_path / "l.jsonl", min_hosts=2)
    for path in ("/a", "/b", "/c"):  # same host, different pages
        ingest_page(_page("팔란티어", "미국의 소프트웨어 기업"),
                    url=f"https://ko.wikipedia.org{path}", ledger=led)
    assert led.promotable() == []  # Sybil cap: one host = one voice


def test_judge_contradiction_blocks_promotion(tmp_path):
    # the curated judge only contradicts on predicates it KNOWS are functional
    # (capital_of etc.); use one so the mechanism is exercised honestly.
    class _Store:
        def __len__(self):
            return 5

        def facts_about(self, s, limit=20):
            return [("Australia", "capital_of", "Canberra")] if s == "Australia" else []

    led = BrowserEvidenceLedger(tmp_path / "l.jsonl", min_hosts=2)
    # two independent host-voices assert a value the curated store contradicts
    led.record("Australia", "capital_of", "Sydney", "https://blog-a.com/x")
    led.record("Australia", "capital_of", "Sydney", "https://blog-b.com/y")
    prom = led.promotable(store=_Store())
    assert all(c["object"] != "Sydney" for c in prom)  # 2 voices, still blocked
    # a value the store agrees with is NOT blocked by the judge
    led.record("Australia", "capital_of", "Canberra", "https://blog-a.com/x")
    led.record("Australia", "capital_of", "Canberra", "https://blog-b.com/y")
    prom2 = led.promotable(store=_Store())
    assert any(c["object"] == "Canberra" for c in prom2)


def test_gate_preview_default_deny_and_auto(tmp_path):
    led = BrowserEvidenceLedger(tmp_path / "l.jsonl", min_hosts=2)
    ingest_page(_page("팔란티어", "미국의 소프트웨어 기업"),
                url="https://ko.wikipedia.org/wiki/팔란티어", ledger=led)
    ingest_page(_page("팔란티어", "미국의 소프트웨어 기업"),
                url="https://namu.wiki/w/팔란티어", ledger=led)
    # default (operator) mode: status=pending is NOT approved -> blocked, not written
    prev = led.gate_preview()
    assert prev["available"] and prev["candidates"] == 1
    assert len(prev["eligible"]) == 0
    assert any("not_human_approved" in r
               for b in prev["blocked"] for r in b["rejection_reasons"])
    # auto mode drops the approval gate but keeps provenance + confidence floors
    auto = led.gate_preview(auto_mode=True)
    assert len(auto["eligible"]) == 1  # 2 host-voices -> confidence 0.5, real urls


def test_gate_items_carry_real_provenance(tmp_path):
    led = BrowserEvidenceLedger(tmp_path / "l.jsonl", min_hosts=2)
    for host in ("https://a.org/x", "https://b.org/y"):
        ingest_page(_page("바다", "소금물이 넓게 고인 곳"), url=host, ledger=led)
    items = led.to_gate_items()
    assert len(items) == 1
    it = items[0]
    assert it["item_type"] == "cloud_candidate"
    assert set(it["source_refs"]) == {"https://a.org/x", "https://b.org/y"}
    assert it["payload"]["origin"] == "atanor_browser"


def test_ingest_never_writes_verified_store(tmp_path):
    led = BrowserEvidenceLedger(tmp_path / "l.jsonl")
    out = ingest_page(_page("바다", "소금물이 넓게 고인 곳"),
                      url="https://ko.wikipedia.org/wiki/바다", ledger=led)
    assert out["written_to_verified_store"] is False
    assert out["anchor"] == "바다" and out["recorded"] == 1
