# -*- coding: utf-8 -*-
"""Browse director: chooses safe reference destinations for a frontier topic, only when enabled,
rate-limited, and never off the allowlist."""
from packages.autonomy_kernel import browse_director as bd


def _setup(tmp_path, monkeypatch, enabled=True, last_nav_at=0.0, visited=None):
    cfg = tmp_path / "bd.json"
    import json
    cfg.write_text(json.dumps({"enabled": enabled, "last_nav_at": last_nav_at,
                               "visited": visited or []}), encoding="utf-8")
    monkeypatch.setattr(bd, "_STATE", cfg)
    monkeypatch.setattr(bd, "_JOURNAL", tmp_path / "j.jsonl")
    # isolate from the REAL episodic visit_index (the novelty gate reads it): empty in tests
    monkeypatch.setattr(bd, "_VISIT_INDEX_PATH", tmp_path / "visit_index.json")


def test_disabled_does_not_navigate(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, enabled=False)
    assert bd.next_destination(now=10_000)["navigate"] is False


def test_enabled_goes_search_first_on_allowlisted_host(tmp_path, monkeypatch):
    """Search-first (owner 2026-07-10): topic outings start at a Google SEARCH for the topic —
 never a guessed wiki URL (Sediba/Philipota landed on , measured) — and the
 host still stays on the allowlist."""
    _setup(tmp_path, monkeypatch)
    r = bd.next_destination(now=10_000)
    assert r["navigate"] is True
    assert r["mode"] == "search" and r["url"].startswith("https://www.google.com/search?q=")
    from urllib.parse import urlparse
    assert urlparse(r["url"]).hostname in bd._SAFE_HOSTS


def test_rate_floor_paces_navigation(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, last_nav_at=10_000)
    r = bd.next_destination(now=10_050)   # 50s < 120 floor
    assert r["navigate"] is False and r["reason"] == "rate_floor"


def test_tour_rotates_platforms_and_takes_field_trips(tmp_path, monkeypatch):
    """The tour must not circle Wikipedia forever (owner 2026-07-10): platforms rotate with
    nav_count, every 4th outing is a field-trip page, and EVERY url stays on the allowlist."""
    _setup(tmp_path, monkeypatch)
    from urllib.parse import urlparse
    hosts = []
    now = 10_000
    for i in range(8):
        r = bd.next_destination(now=now)
        assert r["navigate"] is True
        host = urlparse(r["url"]).hostname
        assert host in bd._SAFE_HOSTS          # belt-and-suspenders always holds
        hosts.append(host)
        now += 200                              # step past the rate floor
    assert len(set(hosts)) >= 3                 # actually visits DIFFERENT platforms
    field_hosts = {h for h, _u, _l in bd._FIELD_TRIPS}
    assert hosts[3] in field_hosts and hosts[7] in field_hosts   # 4th/8th are field trips


def test_reason_is_telemetry_not_authored_prose(tmp_path, monkeypatch):
    """New contract (owner 2026-07-11: — ): journal
 reasons carry raw DECISION VARIABLES (telemetry register), never first-person polite prose
 pretending to be the voice."""
    _setup(tmp_path, monkeypatch)
    r = bd.next_destination(now=10_000)
    assert r["reason"].split(":")[0] in ("프런티어 검색", "드릴다운", "필드트립")
    assert not r["reason"].endswith("요")       # no authored speech endings in the data channel
