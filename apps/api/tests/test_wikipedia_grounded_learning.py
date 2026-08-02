from __future__ import annotations

import app.services.wikipedia_grounded_learning as wgl


def _fake_results(title: str, snippet: str, url: str) -> list[dict[str, str]]:
    return [{"title": title, "snippet": snippet, "url": url, "provider": "wikipedia"}]


def test_clean_definition_accepts_real_sentence_rejects_fragment():
    assert wgl._is_clean_definition(
        "Photosynthesis is the process used by plants to convert light into chemical energy."
    )
    # Nav cruft / short fragments are not real definitions.
    assert not wgl._is_clean_definition("Apr")
    assert not wgl._is_clean_definition("be It days the")


def test_build_payloads_are_wikipedia_typed_with_provenance(monkeypatch):
    monkeypatch.setattr(
        wgl,
        "wikipedia_search",
        lambda q, count=2: _fake_results(
            "Telephone",
            "The telephone is a telecommunications device that permits two or more users to converse.",
            "https://en.wikipedia.org/wiki/Telephone",
        ),
    )
    payloads = wgl.build_wikipedia_learning_payloads(["Telephone"])
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload.source_type == "wikipedia"
    assert payload.source_url_or_path == "https://en.wikipedia.org/wiki/Telephone"
    assert payload.provenance_hash  # provenance carried, not fabricated
    assert "telephone" in payload.normalized_text.lower()


def test_build_payloads_skips_fragment_snippets(monkeypatch):
    monkeypatch.setattr(
        wgl,
        "wikipedia_search",
        lambda q, count=2: _fake_results("Apr", "Apr", "https://en.wikipedia.org/wiki/Apr"),
    )
    assert wgl.build_wikipedia_learning_payloads(["Apr"]) == []


def test_ingest_offline_is_honest_not_fabricated(monkeypatch):
    monkeypatch.setattr(wgl, "wikipedia_search", lambda q, count=2: [])
    out = wgl.ingest_wikipedia_grounded_once(max_topics=2, advance_cursor=False)
    assert out["ingested"] is False
    assert out["reason"] == "no_grounded_payloads"
    assert out["concepts_added"] == 0


def test_ingest_end_to_end_is_candidate_only(monkeypatch, tmp_path):
    monkeypatch.setattr(
        wgl,
        "wikipedia_search",
        lambda q, count=2: _fake_results(
            "Photosynthesis",
            "Photosynthesis is the biological process by which green plants convert "
            "sunlight, water, and carbon dioxide into glucose and oxygen.",
            f"https://en.wikipedia.org/wiki/{q.replace(' ', '_')}",
        ),
    )
    out = wgl.ingest_wikipedia_grounded_once(
        max_topics=1, store_path=tmp_path / "store", advance_cursor=False
    )
    assert out["ingested"] is True
    assert out["production_store_mutated"] is False
    assert out["false_confident"] == 0
    assert out["payloads_accepted"] >= 1
    assert out["source_urls"] and out["source_urls"][0].startswith("https://en.wikipedia.org/")


def test_next_topics_rotates_without_advance():
    first = wgl.next_topics(3, advance=False)
    second = wgl.next_topics(3, advance=False)
    assert first == second  # no advance → stable
    assert len(first) == 3
