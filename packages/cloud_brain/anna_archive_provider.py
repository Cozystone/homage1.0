from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


DEFAULT_SEARCH_PATH = "/api/search"
DEFAULT_TIMEOUT_SECONDS = 12
MAX_METADATA_RESULTS = 20

PRIVATE_FIELD_MARKERS = (
    "download",
    "torrent",
    "magnet",
    "ipfs",
    "full_text",
    "raw_text",
    "content",
    "file_path",
    "local_path",
)


@dataclass(frozen=True)
class AnnaArchiveConfig:
    enabled: bool
    endpoint: str
    api_key: str | None
    search_path: str
    query_param: str
    limit_param: str
    metadata_only: bool
    max_results: int

    def public_status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": bool(self.endpoint),
            "endpoint_configured": bool(self.endpoint),
            "api_key_configured": bool(self.api_key),
            "search_path": self.search_path,
            "query_param": self.query_param,
            "limit_param": self.limit_param,
            "metadata_only": self.metadata_only,
            "max_results": self.max_results,
            "full_text_downloads_allowed": False,
            "local_brain_write": False,
        }


def load_config(env: dict[str, str] | None = None) -> AnnaArchiveConfig:
    env = env or {**_dotenv_values(), **os.environ}
    endpoint = (
        env.get("ATANOR_ANNA_API_ENDPOINT")
        or env.get("ANNA_ARCHIVE_API_ENDPOINT")
        or env.get("ANNAS_BASE_URL")
        or ""
    ).strip()
    api_key = (
        env.get("ATANOR_ANNA_API_KEY")
        or env.get("ANNA_ARCHIVE_API_KEY")
        or env.get("ANNAS_SECRET_KEY")
        or ""
    ).strip() or None
    enabled = (
        env.get("ATANOR_ANNA_API_ENABLED")
        or env.get("ANNA_ARCHIVE_API_ENABLED")
        or env.get("ANNAS_API_ENABLED")
        or "0"
    ).strip() == "1"
    search_path = (env.get("ATANOR_ANNA_API_SEARCH_PATH") or DEFAULT_SEARCH_PATH).strip() or DEFAULT_SEARCH_PATH
    query_param = (env.get("ATANOR_ANNA_API_QUERY_PARAM") or "q").strip() or "q"
    limit_param = (env.get("ATANOR_ANNA_API_LIMIT_PARAM") or "limit").strip() or "limit"
    try:
        max_results = int(env.get("ATANOR_ANNA_API_MAX_RESULTS") or 8)
    except ValueError:
        max_results = 8
    return AnnaArchiveConfig(
        enabled=enabled,
        endpoint=endpoint.rstrip("/"),
        api_key=api_key,
        search_path=search_path,
        query_param=query_param,
        limit_param=limit_param,
        metadata_only=True,
        max_results=max(1, min(MAX_METADATA_RESULTS, max_results)),
    )


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8", errors="ignore")).hexdigest()


def _dotenv_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for filename in (".env", ".env.local"):
        path = Path.cwd() / filename
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _clean_text(value: Any, *, limit: int = 280) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _safe_metadata_url(value: Any) -> str:
    url = _clean_text(value, limit=500)
    if not url:
        return ""
    lower = url.lower()
    if any(marker in lower for marker in ("download", "torrent", "magnet:", "ipfs", "md5=", "file=")):
        return ""
    return url


def _authors(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean_text(item, limit=80) for item in value if _clean_text(item, limit=80)]
    if isinstance(value, str):
        parts = re.split(r"\s*(?:,|;|\band\b|&)\s*", value)
        return [_clean_text(part, limit=80) for part in parts if _clean_text(part, limit=80)][:8]
    return []


def _contains_blocked_field(payload: Any) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_lower = str(key).lower()
            if any(marker in key_lower for marker in PRIVATE_FIELD_MARKERS):
                return True
            if _contains_blocked_field(value):
                return True
    elif isinstance(payload, list):
        return any(_contains_blocked_field(item) for item in payload)
    return False


def sanitize_metadata_entry(entry: dict[str, Any], *, query: str) -> dict[str, Any] | None:
    """Return metadata-only record, never raw copyrighted text or download links."""

    if not isinstance(entry, dict) or _contains_blocked_field(entry):
        return None
    title = _clean_text(entry.get("title") or entry.get("name"), limit=180)
    if not title:
        return None
    authors = _authors(entry.get("authors") or entry.get("author"))
    year = _clean_text(entry.get("year") or entry.get("published_year") or entry.get("date"), limit=24)
    language = _clean_text(entry.get("language") or entry.get("lang"), limit=32)
    license_value = _clean_text(entry.get("license") or entry.get("rights"), limit=120)
    source_url = _safe_metadata_url(entry.get("metadata_url") or entry.get("url") or "")
    record_id = _clean_text(entry.get("id") or entry.get("md5") or entry.get("isbn") or "", limit=120)
    content_hash = _stable_id("anna-archive-metadata", query, record_id, title, "|".join(authors), year)
    return {
        "source_id": f"anna_meta_{content_hash[:16]}",
        "source_hash": content_hash,
        "title": title,
        "authors": authors,
        "year": year,
        "language": language,
        "license": license_value or "unknown",
        "source_url": source_url,
        "query": _clean_text(query, limit=160),
        "privacy_scope": "public_metadata",
        "raw_text_stored": False,
        "download_url_stored": False,
        "usage_allowed": False,
    }


def metadata_to_semantic_text(record: dict[str, Any]) -> str:
    authors = ", ".join(record.get("authors") or []) or "unknown author"
    year = record.get("year") or "unknown year"
    language = record.get("language") or "unknown language"
    query = record.get("query") or "research topic"
    title = record.get("title") or "untitled work"
    return (
        f"{title} is a public metadata record related to {query}. "
        f"{title} was authored by {authors}. "
        f"{title} has publication year {year} and language {language}. "
        "This ATANOR fragment stores metadata only and does not store full text or download links."
    )


def _items_from_response(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "results", "data", "records", "books"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def fetch_metadata(
    query: str,
    *,
    config: AnnaArchiveConfig | None = None,
    requester: Callable[[Request, int], bytes] | None = None,
) -> dict[str, Any]:
    config = config or load_config()
    if not config.enabled or not config.endpoint:
        return {
            "enabled": config.enabled,
            "configured": bool(config.endpoint),
            "status": "disabled_or_unconfigured",
            "records": [],
            "rejected": 0,
            "honesty": {
                "metadata_only": True,
                "full_text_downloads": False,
                "local_brain_write": False,
            },
        }
    url = urljoin(config.endpoint + "/", config.search_path.lstrip("/"))
    separator = "&" if "?" in url else "?"
    url = f"{url}{separator}{urlencode({config.query_param: query, config.limit_param: config.max_results})}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "ATANOR-AnnaArchiveMetadataConnector/0.1",
    }
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    request = Request(url, headers=headers)

    def default_requester(req: Request, timeout: int) -> bytes:
        with urlopen(req, timeout=timeout) as response:
            return response.read(1_000_000)

    requester = requester or default_requester
    payload = json.loads(requester(request, DEFAULT_TIMEOUT_SECONDS).decode("utf-8", errors="ignore"))
    records: list[dict[str, Any]] = []
    rejected = 0
    for item in _items_from_response(payload)[: config.max_results]:
        record = sanitize_metadata_entry(item, query=query)
        if record is None:
            rejected += 1
            continue
        records.append(record)
    return {
        "enabled": True,
        "configured": True,
        "status": "metadata_fetched",
        "records": records,
        "rejected": rejected,
        "honesty": {
            "metadata_only": True,
            "full_text_downloads": False,
            "local_brain_write": False,
        },
    }
