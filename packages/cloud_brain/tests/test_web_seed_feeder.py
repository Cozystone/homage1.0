from __future__ import annotations

import json
from pathlib import Path

from packages.cloud_brain.web_seed_feeder import (
    DEFAULT_STATE,
    DATA_ROOT,
    _link_allowed_for_frontier,
    feeder_status,
    is_safe_public_url,
    load_sources,
    reconcile_seed_sources,
    run_once,
    write_json,
)


def test_default_web_seed_root_is_project_absolute() -> None:
    assert DATA_ROOT.is_absolute()
    assert DATA_ROOT.name == "cloud_brain"
    assert DATA_ROOT.parent.name == "data"
    assert "apps" not in DATA_ROOT.parts[-4:]


def test_url_safety_rejects_private_and_local_targets() -> None:
    rejected = [
        "http://localhost:8500/api",
        "http://127.0.0.1:8500/api",
        "http://192.168.0.10/page",
        "file:///C:/secret.txt",
        "ftp://example.com/public.txt",
        "https://example.com/login",
        "C:\\Users\\private\\payload.md",
    ]
    for url in rejected:
        ok, _ = is_safe_public_url(url)
        assert ok is False

    ok, reason = is_safe_public_url("https://example.com/public-page")
    assert ok is True
    assert reason is None


def test_disabled_feeder_skips_sources(tmp_path: Path) -> None:
    root = tmp_path / "cloud_brain"
    write_json(
        root / "web_seed_sources.json",
        [
            {
                "source_id": "enabled_source",
                "name": "Enabled",
                "url": "https://example.com/public",
                "enabled": True,
                "source_type": "public_web",
                "trust_tier": "low",
                "crawl_interval_minutes": 1440,
                "last_fetched_at": None,
            }
        ],
    )
    write_json(root / "web_seed_feeder_state.json", {**DEFAULT_STATE, "enabled": False})

    result = run_once(root, fetcher=lambda url: "public text " * 20)

    assert result.status == "disabled"
    assert not list((root / "inbox").glob("*.json"))


def test_enabled_public_source_creates_candidate_fragment(tmp_path: Path) -> None:
    root = tmp_path / "cloud_brain"
    write_json(
        root / "web_seed_sources.json",
        [
            {
                "source_id": "public_seed",
                "name": "Public Seed",
                "url": "https://example.com/public",
                "enabled": True,
                "source_type": "public_web",
                "trust_tier": "medium",
                "crawl_interval_minutes": 1440,
                "last_fetched_at": None,
            }
        ],
    )
    write_json(root / "web_seed_feeder_state.json", {**DEFAULT_STATE, "enabled": True, "promote_to_semantic": False})

    result = run_once(root, fetcher=lambda url: "GraphRAG public evidence routing validates Cloud Brain fragments. " * 4)
    fragments = list((root / "inbox").glob("candidate_*.json"))

    assert result.status == "created_fragments"
    assert result.fragments_created == 1
    assert len(fragments) == 1
    fragment = json.loads(fragments[0].read_text(encoding="utf-8"))
    assert fragment["source_scope"] == "cloud"
    assert fragment["privacy_scope"] == "public"
    assert fragment["ingestion_state"] == "pending"
    assert fragment["created_by"] == "cloud_brain_web_seed_feeder"
    assert not (tmp_path / "data" / "memory").exists()


def test_public_source_rejects_seed_irrelevant_payload(tmp_path: Path) -> None:
    root = tmp_path / "cloud_brain"
    write_json(
        root / "web_seed_sources.json",
        [
            {
                "source_id": "random_public_page",
                "name": "Random Public Page",
                "url": "https://example.com/random",
                "enabled": True,
                "source_type": "public_web",
                "trust_tier": "medium",
                "crawl_interval_minutes": 1440,
                "last_fetched_at": None,
            }
        ],
    )
    write_json(root / "web_seed_feeder_state.json", {**DEFAULT_STATE, "enabled": True, "promote_to_semantic": True})

    result = run_once(root, fetcher=lambda url: "This article is about cooking, travel, gardens, and music. " * 4)

    assert result.fragments_created == 0
    assert result.semantic_ingested == 0
    assert result.fragments_rejected == 1
    assert result.status == "listening_with_rejections"
    assert not list((root / "inbox").glob("candidate_*.json"))


def test_load_sources_preserves_curated_seed_sources(tmp_path: Path) -> None:
    root = tmp_path / "cloud_brain"
    write_json(
        root / "web_seed_sources.json",
        [
            {
                "source_id": f"frontier_noise_{index}",
                "name": "Noise",
                "url": f"https://en.wikipedia.org/wiki/3M_{index}",
                "enabled": True,
                "source_type": "public_web",
                "trust_tier": "low",
                "crawl_interval_minutes": 1440,
                "last_fetched_at": None,
            }
            for index in range(12)
        ],
    )
    write_json(root / "web_seed_feeder_state.json", {**DEFAULT_STATE, "enabled": True})

    sources = load_sources(root)
    source_ids = {source["source_id"] for source in sources}

    assert "seed_retrieval_augmented_generation" in source_ids
    assert "seed_knowledge_graph" in source_ids
    assert "seed_kubernetes" in source_ids


def test_reconcile_seed_sources_honors_expanded_total_source_limit() -> None:
    sources = [
        {
            "source_id": f"frontier_many_{index}",
            "name": "Frontier",
            "url": f"https://en.wikipedia.org/wiki/Frontier_{index}",
            "enabled": True,
            "source_type": "public_web",
            "trust_tier": "medium",
        }
        for index in range(620)
    ]

    reconciled = reconcile_seed_sources(sources, max_total_sources=650)

    assert len(reconciled) > 500
    assert len(reconciled) <= 650


def test_run_once_prioritizes_seed_sources_even_when_cursor_is_on_frontier(tmp_path: Path) -> None:
    root = tmp_path / "cloud_brain"
    write_json(
        root / "web_seed_sources.json",
        [
            {
                "source_id": "seed_knowledge_graph",
                "name": "Knowledge graph",
                "url": "https://example.test/seed",
                "enabled": True,
                "trust_tier": "seed",
                "source_type": "public_web",
            },
            {
                "source_id": "frontier_noise",
                "name": "Frontier noise",
                "url": "https://example.test/noise",
                "enabled": True,
                "trust_tier": "medium",
                "source_type": "public_web",
            },
        ],
    )
    write_json(
        root / "web_seed_feeder_state.json",
        {
            **DEFAULT_STATE,
            "enabled": True,
            "crawler_cursor": 1,
            "max_sources_checked_per_run": 1,
            "promote_to_semantic": False,
        },
    )
    fetched_urls: list[str] = []

    def fake_fetcher(url: str) -> dict:
        fetched_urls.append(url)
        return {
            "text": (
                "Knowledge graph ontology semantic relation evidence concept graph "
                "retrieval reasoning fact verification node edge structure. "
                "Knowledge graph ontology semantic relation evidence concept graph "
                "retrieval reasoning fact verification node edge structure."
            ),
            "links": [],
        }

    result = run_once(root, fetcher=fake_fetcher)

    assert result.sources_checked == 1
    assert fetched_urls == ["https://example.test/seed"]


def test_enabled_public_source_promotes_candidate_to_semantic_store(tmp_path: Path) -> None:
    root = tmp_path / "cloud_brain"
    write_json(
        root / "web_seed_sources.json",
        [
            {
                "source_id": "public_kubernetes_seed",
                "name": "Public Kubernetes Seed",
                "url": "https://example.com/kubernetes",
                "enabled": True,
                "source_type": "public_web",
                "trust_tier": "medium",
                "crawl_interval_minutes": 1440,
                "last_fetched_at": None,
            }
        ],
    )
    write_json(root / "web_seed_feeder_state.json", {**DEFAULT_STATE, "enabled": True, "promote_to_semantic": True})

    result = run_once(
        root,
        fetcher=lambda url: (
            "Kubernetes is an open-source platform that manages containerized applications "
            "and automates deployment. "
        )
        * 2,
    )
    status = feeder_status(root)

    assert result.fragments_created == 1
    assert result.semantic_ingested == 1
    assert result.semantic_concepts_created > 0
    assert result.semantic_relations_created > 0
    assert status["semantic_ingested"] == 1
    assert (root / "store" / "semantic_concepts.json").exists()
    assert not (tmp_path / "data" / "memory").exists()


def test_duplicate_content_hash_is_skipped(tmp_path: Path) -> None:
    root = tmp_path / "cloud_brain"
    source = {
        "source_id": "public_seed",
        "name": "Public Seed",
        "url": "https://example.com/public",
        "enabled": True,
        "source_type": "public_web",
        "trust_tier": "medium",
        "crawl_interval_minutes": 0,
        "last_fetched_at": None,
    }
    write_json(root / "web_seed_sources.json", [source])
    write_json(root / "web_seed_feeder_state.json", {**DEFAULT_STATE, "enabled": True, "promote_to_semantic": False})

    text = "Cloud Brain duplicate public fragment candidate should not be written twice. " * 4
    first = run_once(root, fetcher=lambda url: text)
    write_json(root / "web_seed_sources.json", [{**source, "last_fetched_at": None}])
    second = run_once(root, fetcher=lambda url: text)

    assert first.fragments_created == 1
    assert second.fragments_created == 0
    assert second.status == "no_new_payload"
    assert len(list((root / "inbox").glob("candidate_*.json"))) == 1


def test_duplicate_public_source_strengthens_semantic_cloud_without_new_fragment(tmp_path: Path) -> None:
    root = tmp_path / "cloud_brain"
    source = {
        "source_id": "public_kubernetes_seed",
        "name": "Public Kubernetes Seed",
        "url": "https://example.com/kubernetes",
        "enabled": True,
        "source_type": "public_web",
        "trust_tier": "medium",
        "crawl_interval_minutes": 0,
        "last_fetched_at": None,
    }
    write_json(root / "web_seed_sources.json", [source])
    write_json(root / "web_seed_feeder_state.json", {**DEFAULT_STATE, "enabled": True, "promote_to_semantic": True})
    text = (
        "Kubernetes is an open-source platform that manages containerized applications "
        "and automates deployment. "
    ) * 2

    first = run_once(root, fetcher=lambda url: text)
    write_json(root / "web_seed_sources.json", [{**source, "last_fetched_at": None}])
    second = run_once(root, fetcher=lambda url: text)

    assert first.fragments_created == 1
    assert second.fragments_created == 0
    assert second.semantic_ingested == 1
    assert second.semantic_relations_strengthened > 0
    assert second.status == "strengthened_semantic_cloud"


def test_feeder_caps_effective_interval_and_checks_small_batches(tmp_path: Path) -> None:
    root = tmp_path / "cloud_brain"
    sources = [
        {
            "source_id": f"public_seed_{index}",
            "name": f"Public Seed {index}",
            "url": f"https://example.com/public-{index}",
            "enabled": True,
            "source_type": "public_web",
            "trust_tier": "medium",
            "crawl_interval_minutes": 1440,
            "last_fetched_at": "2026-06-16T18:00:00Z",
        }
        for index in range(5)
    ]
    write_json(root / "web_seed_sources.json", sources)
    write_json(
        root / "web_seed_feeder_state.json",
        {
            **DEFAULT_STATE,
            "enabled": True,
            "promote_to_semantic": False,
            "max_sources_checked_per_run": 2,
            "max_effective_crawl_interval_minutes": 1,
        },
    )

    result = run_once(root, fetcher=lambda url: f"{url} GraphRAG evidence routing. " * 4)
    state = json.loads((root / "web_seed_feeder_state.json").read_text(encoding="utf-8"))

    assert result.sources_checked == 2
    assert result.fragments_created == 2
    assert result.crawler_cursor == 2
    assert state["crawler_cursor"] == 2
    assert state["max_effective_crawl_interval_minutes"] == 1


def test_feeder_status_reports_public_cloud_candidate_policy(tmp_path: Path) -> None:
    root = tmp_path / "cloud_brain"
    status = feeder_status(root)

    assert status["enabled"] is False
    assert status["writes_local_brain"] is False
    assert status["privacy_scope"] == "public_cloud_candidates_only"


def test_anna_archive_metadata_source_creates_metadata_only_candidates(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "cloud_brain"
    write_json(
        root / "web_seed_sources.json",
        [
            {
                "source_id": "anna_metadata",
                "name": "Anna metadata",
                "url": "",
                "enabled": True,
                "source_type": "anna_archive_api",
                "query": "GraphRAG",
                "trust_tier": "metadata_only",
                "crawl_interval_minutes": 1440,
                "last_fetched_at": None,
            }
        ],
    )
    write_json(root / "web_seed_feeder_state.json", {**DEFAULT_STATE, "enabled": True, "promote_to_semantic": True})

    def fake_fetch_metadata(query, config=None):
        return {
            "status": "metadata_fetched",
            "records": [
                {
                    "source_id": "anna_meta_test",
                    "source_hash": "hash1",
                    "title": "GraphRAG Evidence Systems",
                    "authors": ["A. Researcher"],
                    "year": "2025",
                    "language": "en",
                    "license": "unknown",
                    "source_url": "https://example.org/metadata",
                    "query": query,
                    "raw_text_stored": False,
                    "download_url_stored": False,
                }
            ],
            "rejected": 2,
            "honesty": {"metadata_only": True, "full_text_downloads": False, "local_brain_write": False},
        }

    monkeypatch.setattr("packages.cloud_brain.anna_archive_provider.fetch_metadata", fake_fetch_metadata)

    result = run_once(root)
    fragments = list((root / "inbox").glob("candidate_*.json"))
    fragment = json.loads(fragments[0].read_text(encoding="utf-8"))

    assert result.fragments_created == 1
    assert result.anna_metadata_records == 1
    assert result.anna_metadata_rejected == 2
    assert result.semantic_ingested == 1
    assert fragment["origin"] == "anna_archive_metadata_api"
    assert fragment["privacy_scope"] == "public_metadata"
    assert fragment["metadata"]["raw_text_stored"] is False
    assert fragment["metadata"]["download_url_stored"] is False
    assert "download" not in fragment["source_url"].lower()
    assert not (tmp_path / "data" / "memory").exists()


def test_anna_archive_metadata_source_auto_enables_from_env(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "cloud_brain"
    write_json(
        root / "web_seed_sources.json",
        [
            {
                "source_id": "anna_metadata",
                "name": "Anna metadata",
                "url": "",
                "enabled": False,
                "auto_enable_from_env": True,
                "source_type": "anna_archive_api",
                "queries": ["GraphRAG", "ontology"],
                "trust_tier": "metadata_only",
                "crawl_interval_minutes": 1440,
                "last_fetched_at": None,
            }
        ],
    )
    write_json(root / "web_seed_feeder_state.json", {**DEFAULT_STATE, "enabled": True, "promote_to_semantic": False})
    monkeypatch.setenv("ATANOR_ANNA_API_ENABLED", "1")
    monkeypatch.setenv("ATANOR_ANNA_API_ENDPOINT", "https://api.example.org")
    seen_queries: list[str] = []

    def fake_fetch_metadata(query, config=None):
        seen_queries.append(query)
        return {
            "status": "metadata_fetched",
            "records": [
                {
                    "source_id": f"anna_meta_{query}",
                    "source_hash": f"hash-{query}",
                    "title": f"{query} Research Metadata",
                    "authors": ["A. Researcher"],
                    "year": "2026",
                    "language": "en",
                    "license": "unknown",
                    "source_url": "https://example.org/metadata",
                    "query": query,
                    "raw_text_stored": False,
                    "download_url_stored": False,
                }
            ],
            "rejected": 0,
            "honesty": {"metadata_only": True, "full_text_downloads": False, "local_brain_write": False},
        }

    monkeypatch.setattr("packages.cloud_brain.anna_archive_provider.fetch_metadata", fake_fetch_metadata)

    result = run_once(root)

    assert seen_queries == ["GraphRAG", "ontology"]
    assert result.fragments_created == 2
    assert result.anna_metadata_records == 2
    assert len(list((root / "inbox").glob("candidate_*.json"))) == 2


def test_public_source_discovers_safe_frontier_links(tmp_path: Path) -> None:
    root = tmp_path / "cloud_brain"
    write_json(
        root / "web_seed_sources.json",
        [
            {
                "source_id": "wiki_seed",
                "name": "Wiki Seed",
                "url": "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
                "enabled": True,
                "source_type": "public_web",
                "trust_tier": "medium",
                "crawl_interval_minutes": 1440,
                "last_fetched_at": None,
                "discover_links": True,
                "max_discovered_sources_per_run": 2,
                "discovery_same_host_only": True,
                "discovery_keywords": ["graph", "knowledge"],
            }
        ],
    )
    write_json(root / "web_seed_feeder_state.json", {**DEFAULT_STATE, "enabled": True, "promote_to_semantic": True})
    html = """
      <html><body>
      <p>GraphRAG uses knowledge graph evidence to route retrieval and answer verification.</p>
      <a href="/wiki/Knowledge_graph">Knowledge graph</a>
      <a href="/wiki/Graph_database">Graph database</a>
      <a href="https://evil.example.test/wiki/Graph">External graph</a>
      <a href="/wiki/File:Graph.svg">File graph</a>
      </body></html>
    """

    result = run_once(root, fetcher=lambda url: {"text": "GraphRAG uses knowledge graph evidence. " * 4, "links": [
        "https://en.wikipedia.org/wiki/Knowledge_graph",
        "https://en.wikipedia.org/wiki/Graph_database",
        "https://evil.example.test/wiki/Graph",
        "https://en.wikipedia.org/wiki/File:Graph.svg",
    ]})
    sources = json.loads((root / "web_seed_sources.json").read_text(encoding="utf-8"))
    frontier_sources = [source for source in sources if str(source.get("source_id", "")).startswith("frontier_")]

    assert result.fragments_created == 1
    assert result.discovered_sources_added == 2
    assert len(frontier_sources) == 2
    assert all(source["enabled"] is True for source in frontier_sources)
    assert all("en.wikipedia.org" in source["url"] for source in frontier_sources)
    assert all("File:" not in source["url"] for source in frontier_sources)
    assert not (tmp_path / "data" / "memory").exists()


def test_frontier_rejects_wikipedia_system_and_edit_links() -> None:
    source = {
        "url": "https://en.wikipedia.org/wiki/Kubernetes",
        "discovery_same_host_only": True,
    }
    rejected = [
        "https://en.wikipedia.org/w/index.php?title=Kubernetes&action=edit",
        "https://en.wikipedia.org/wiki/Special:CreateAccount",
        "https://en.wikipedia.org/wiki/Help:Contents",
        "https://en.wikipedia.org/wiki/Category:Containerization",
        "https://en.wikipedia.org/w/index.php?title=Special:UserLogin&returnto=Kubernetes",
        "https://en.wikipedia.org/wiki/File:Graph.svg",
    ]

    for link in rejected:
        assert _link_allowed_for_frontier(source, link) is False

    assert _link_allowed_for_frontier(source, "https://en.wikipedia.org/wiki/Container_orchestration") is True
