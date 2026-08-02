from __future__ import annotations

import json
from urllib.request import Request

from packages.cloud_brain.anna_archive_provider import (
    AnnaArchiveConfig,
    fetch_metadata,
    load_config,
    metadata_to_semantic_text,
    sanitize_metadata_entry,
)


def test_sanitize_metadata_entry_rejects_download_and_raw_text_fields() -> None:
    assert sanitize_metadata_entry({"title": "Unsafe", "download_url": "https://example.com/file.pdf"}, query="x") is None
    assert sanitize_metadata_entry({"title": "Unsafe", "raw_text": "full book text"}, query="x") is None


def test_metadata_record_is_metadata_only() -> None:
    record = sanitize_metadata_entry(
        {
            "id": "book-1",
            "title": "Graph Retrieval Systems",
            "authors": ["Ada Lovelace"],
            "year": 2026,
            "language": "en",
            "metadata_url": "https://example.org/metadata/book-1",
        },
        query="GraphRAG",
    )

    assert record is not None
    assert record["raw_text_stored"] is False
    assert record["download_url_stored"] is False
    text = metadata_to_semantic_text(record)
    assert "Graph Retrieval Systems" in text
    assert "full text" in text


def test_fetch_metadata_uses_configured_endpoint_and_filters_payload() -> None:
    requests: list[str] = []

    def requester(request: Request, timeout: int) -> bytes:
        requests.append(request.full_url)
        return json.dumps(
            {
                "results": [
                    {"id": "safe-1", "title": "Kubernetes Papers", "authors": "A. Kim", "year": "2024"},
                    {"id": "unsafe-1", "title": "Unsafe", "download_url": "https://example.org/file.epub"},
                ]
            }
        ).encode("utf-8")

    response = fetch_metadata(
        "kubernetes",
        config=AnnaArchiveConfig(
            enabled=True,
            endpoint="https://api.example.org",
            api_key="test-key",
            search_path="/search",
            query_param="q",
            limit_param="limit",
            metadata_only=True,
            max_results=5,
        ),
        requester=requester,
    )

    assert requests and "q=kubernetes" in requests[0]
    assert response["status"] == "metadata_fetched"
    assert len(response["records"]) == 1
    assert response["rejected"] == 1
    assert response["honesty"]["full_text_downloads"] is False


def test_fetch_metadata_disabled_without_endpoint() -> None:
    response = fetch_metadata(
        "kubernetes",
        config=AnnaArchiveConfig(
            enabled=False,
            endpoint="",
            api_key=None,
            search_path="/search",
            query_param="q",
            limit_param="limit",
            metadata_only=True,
            max_results=5,
        ),
    )

    assert response["status"] == "disabled_or_unconfigured"
    assert response["records"] == []


def test_load_config_accepts_common_annas_aliases() -> None:
    config = load_config(
        {
            "ANNAS_API_ENABLED": "1",
            "ANNAS_BASE_URL": "https://api.annas.example",
            "ANNAS_SECRET_KEY": "secret",
        }
    )

    assert config.enabled is True
    assert config.endpoint == "https://api.annas.example"
    assert config.api_key == "secret"
    assert config.metadata_only is True


def test_load_config_reads_dotenv_when_process_env_is_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ATANOR_ANNA_API_ENABLED", raising=False)
    monkeypatch.delenv("ATANOR_ANNA_API_ENDPOINT", raising=False)
    monkeypatch.delenv("ATANOR_ANNA_API_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "ATANOR_ANNA_API_ENABLED=1",
                "ATANOR_ANNA_API_ENDPOINT=https://api.annas.example",
                "ATANOR_ANNA_API_KEY=dotenv-secret",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config()

    assert config.enabled is True
    assert config.endpoint == "https://api.annas.example"
    assert config.api_key == "dotenv-secret"
