from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

from .semantic_store import DEFAULT_SEMANTIC_CLOUD_ROOT

DATA_ROOT = DEFAULT_SEMANTIC_CLOUD_ROOT
SOURCES_PATH = DATA_ROOT / "web_seed_sources.json"
STATE_PATH = DATA_ROOT / "web_seed_feeder_state.json"
INBOX_DIR = DATA_ROOT / "inbox"

PRIVATE_NETWORKS = (
    ip_network("10.0.0.0/8"),
    ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("::1/128"),
    ip_network("fc00::/7"),
    ip_network("fe80::/10"),
)

DEFAULT_SOURCES = [
    {
        "source_id": "atanor_safe_demo_disabled",
        "name": "ATANOR Safe Demo Source",
        "url": "https://example.com/",
        "enabled": False,
        "source_type": "public_web",
        "trust_tier": "low",
        "crawl_interval_minutes": 1440,
        "last_fetched_at": None,
    },
    {
        "source_id": "seed_retrieval_augmented_generation",
        "name": "Retrieval Augmented Generation",
        "url": "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
        "enabled": True,
        "source_type": "public_web",
        "trust_tier": "seed",
        "crawl_interval_minutes": 1440,
        "last_fetched_at": None,
        "discover_links": True,
        "max_discovered_sources_per_run": 2,
        "discovery_same_host_only": True,
        "discovery_keywords": ["retrieval", "evidence", "knowledge graph", "semantic", "reasoning"],
    },
    {
        "source_id": "seed_knowledge_graph",
        "name": "Knowledge Graph",
        "url": "https://en.wikipedia.org/wiki/Knowledge_graph",
        "enabled": True,
        "source_type": "public_web",
        "trust_tier": "seed",
        "crawl_interval_minutes": 1440,
        "last_fetched_at": None,
        "discover_links": True,
        "max_discovered_sources_per_run": 2,
        "discovery_same_host_only": True,
        "discovery_keywords": ["knowledge graph", "ontology", "semantic", "database", "reasoning"],
    },
    {
        "source_id": "seed_ontology_information_science",
        "name": "Ontology Information Science",
        "url": "https://en.wikipedia.org/wiki/Ontology_(information_science)",
        "enabled": True,
        "source_type": "public_web",
        "trust_tier": "seed",
        "crawl_interval_minutes": 1440,
        "last_fetched_at": None,
        "discover_links": True,
        "max_discovered_sources_per_run": 2,
        "discovery_same_host_only": True,
        "discovery_keywords": ["ontology", "knowledge representation", "semantic", "concept", "relation"],
    },
    {
        "source_id": "seed_kubernetes",
        "name": "Kubernetes",
        "url": "https://en.wikipedia.org/wiki/Kubernetes",
        "enabled": True,
        "source_type": "public_web",
        "trust_tier": "seed",
        "crawl_interval_minutes": 1440,
        "last_fetched_at": None,
        "discover_links": True,
        "max_discovered_sources_per_run": 2,
        "discovery_same_host_only": True,
        "discovery_keywords": ["kubernetes", "container", "orchestration", "deployment", "cluster"],
    },
    {
        "source_id": "anna_archive_metadata_disabled",
        "name": "Anna Archive metadata connector",
        "url": "",
        "enabled": False,
        "source_type": "anna_archive_api",
        "query": "graph retrieval augmented generation",
        "trust_tier": "metadata_only",
        "crawl_interval_minutes": 1440,
        "last_fetched_at": None,
    }
]

SEED_RELEVANCE_KEYWORDS = [
    "graphrag",
    "retrieval augmented generation",
    "retrieval-augmented generation",
    "knowledge graph",
    "graph database",
    "ontology",
    "semantic",
    "evidence",
    "reasoning",
    "kubernetes",
    "container orchestration",
    "containerized application",
    "database",
    "sqlite",
    "local-first",
    "cloud brain",
    "payload vault",
    "ghost shell",
]

MIN_SEED_RELEVANCE_SCORE = 2

DEFAULT_STATE = {
    "enabled": False,
    "promote_to_semantic": True,
    "last_run_at": None,
    "last_status": "idle",
    "sources_checked": 0,
    "fragments_created": 0,
    "fragments_rejected": 0,
    "semantic_ingested": 0,
    "semantic_concepts_created": 0,
    "semantic_relations_created": 0,
    "semantic_relations_strengthened": 0,
    "anna_metadata_records": 0,
    "anna_metadata_rejected": 0,
    "discovered_sources_added": 0,
    "max_discovered_sources_per_run_total": 1000,
    "max_total_sources": 5000,
    "max_sources_checked_per_run": 1000,
    "max_effective_crawl_interval_minutes": 1,
    "crawler_cursor": 0,
    "last_error": None,
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = False
        self._chunks: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower == "a":
            for name, value in attrs:
                if name.lower() == "href" and value:
                    self.links.append(value)
        if tag_lower in {"script", "style", "noscript", "svg"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            cleaned = " ".join(data.split())
            if cleaned:
                self._chunks.append(cleaned)

    def text(self) -> str:
        return " ".join(self._chunks)


@dataclass(frozen=True)
class FeederResult:
    enabled: bool
    status: str
    sources_checked: int
    fragments_created: int
    fragments_rejected: int
    last_run_at: str | None
    promote_to_semantic: bool = True
    semantic_ingested: int = 0
    semantic_concepts_created: int = 0
    semantic_relations_created: int = 0
    semantic_relations_strengthened: int = 0
    anna_metadata_records: int = 0
    anna_metadata_rejected: int = 0
    discovered_sources_added: int = 0
    max_sources_checked_per_run: int = 6
    max_effective_crawl_interval_minutes: int = 1
    crawler_cursor: int = 0
    last_error: str | None = None

    def to_state(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "promote_to_semantic": self.promote_to_semantic,
            "last_run_at": self.last_run_at,
            "last_status": self.status,
            "status": self.status,
            "sources_checked": self.sources_checked,
            "fragments_created": self.fragments_created,
            "fragments_rejected": self.fragments_rejected,
            "semantic_ingested": self.semantic_ingested,
            "semantic_concepts_created": self.semantic_concepts_created,
            "semantic_relations_created": self.semantic_relations_created,
            "semantic_relations_strengthened": self.semantic_relations_strengthened,
            "anna_metadata_records": self.anna_metadata_records,
            "anna_metadata_rejected": self.anna_metadata_rejected,
            "discovered_sources_added": self.discovered_sources_added,
            "max_sources_checked_per_run": self.max_sources_checked_per_run,
            "max_effective_crawl_interval_minutes": self.max_effective_crawl_interval_minutes,
            "crawler_cursor": self.crawler_cursor,
            "last_error": self.last_error,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_layout(root: Path = DATA_ROOT) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "inbox").mkdir(parents=True, exist_ok=True)
    sources_path = root / "web_seed_sources.json"
    state_path = root / "web_seed_feeder_state.json"
    if not sources_path.exists():
        write_json(sources_path, DEFAULT_SOURCES)
    if not state_path.exists():
        write_json(state_path, DEFAULT_STATE)


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_sources(root: Path = DATA_ROOT) -> list[dict[str, Any]]:
    ensure_layout(root)
    sources = read_json(root / "web_seed_sources.json", DEFAULT_SOURCES)
    if not isinstance(sources, list):
        sources = []
    return reconcile_seed_sources(sources)


def reconcile_seed_sources(sources: list[dict[str, Any]], *, max_total_sources: int | None = None) -> list[dict[str, Any]]:
    """Keep curated seed sources present while bounding stale frontier drift."""

    default_ids = {str(source.get("source_id") or "") for source in DEFAULT_SOURCES}
    source_ids = {str(source.get("source_id") or "") for source in sources}
    if len(sources) < 10 and not source_ids.intersection(default_ids):
        return sources
    by_id: dict[str, dict[str, Any]] = {}
    for source in DEFAULT_SOURCES:
        source_id = str(source.get("source_id") or "")
        if source_id:
            by_id[source_id] = dict(source)
    for source in sources:
        source_id = str(source.get("source_id") or "")
        if source_id:
            if source_id in by_id:
                merged = {**by_id[source_id], **source}
                if source_id in default_ids and str(by_id[source_id].get("trust_tier") or "") == "seed":
                    merged["trust_tier"] = "seed"
                    merged["enabled"] = True
                by_id[source_id] = merged
            else:
                by_id[source_id] = dict(source)
    rows = list(by_id.values())
    rows.sort(key=_source_priority_key)
    limit = int(max_total_sources or DEFAULT_STATE["max_total_sources"])
    return rows[: max(1, min(50_000, limit))]


def _source_priority_key(source: dict[str, Any]) -> tuple[int, int, str]:
    trust = str(source.get("trust_tier") or "")
    if trust == "seed":
        tier = 0
    elif _is_anna_source(source):
        tier = 1
    elif str(source.get("discovered_from") or "").startswith("seed_"):
        tier = 2
    else:
        tier = 3
    score = int(source.get("discovery_score") or 0)
    return (tier, -score, str(source.get("source_id") or source.get("url") or ""))


def _scheduled_source_indices(sources: list[dict[str, Any]], cursor: int, max_checked: int) -> list[int]:
    """Prefer curated seed rails each tick, then rotate through the wider frontier."""

    source_count = len(sources)
    if source_count == 0:
        return []
    cursor = cursor % source_count
    seed_indices = [
        index
        for index, source in enumerate(sources)
        if str(source.get("trust_tier") or "").strip().lower() == "seed"
    ]
    seed_budget = min(len(seed_indices), max(1, min(4, max_checked)))
    ordered: list[int] = []
    seen: set[int] = set()
    for index in seed_indices[:seed_budget]:
        ordered.append(index)
        seen.add(index)
    for offset in range(source_count):
        index = (cursor + offset) % source_count
        if index in seen:
            continue
        ordered.append(index)
        seen.add(index)
    return ordered


def load_state(root: Path = DATA_ROOT) -> dict[str, Any]:
    ensure_layout(root)
    state = read_json(root / "web_seed_feeder_state.json", DEFAULT_STATE)
    if not isinstance(state, dict):
        return dict(DEFAULT_STATE)
    return {**DEFAULT_STATE, **state}


def save_state(state: dict[str, Any], root: Path = DATA_ROOT) -> None:
    write_json(root / "web_seed_feeder_state.json", {**DEFAULT_STATE, **state})


def is_safe_public_url(url: str) -> tuple[bool, str | None]:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        return False, "URL must use http or https."
    if parsed.username or parsed.password:
        return False, "Authenticated URLs are not allowed."
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "URL host is missing."
    if host in {"localhost", "0.0.0.0"} or host.endswith(".local"):
        return False, "Local or internal hosts are not allowed."
    if "\\" in url or re.match(r"^[a-zA-Z]:\\", url):
        return False, "Local file paths are not allowed."
    try:
        address = ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if address.is_private or address.is_loopback or address.is_link_local or any(address in network for network in PRIVATE_NETWORKS):
            return False, "Private, loopback, and link-local IP ranges are not allowed."
    path_lower = parsed.path.lower()
    if any(marker in path_lower for marker in ("/login", "/signin", "/auth", "/account", "/session")):
        return False, "Pages that appear to require authentication are not allowed."
    return True, None


def _is_wikipedia_article_url(parsed) -> bool:
    host = (parsed.hostname or "").lower()
    if not host.endswith(".wikipedia.org"):
        return True
    path = parsed.path
    if not path.startswith("/wiki/"):
        return False
    title = path.rsplit("/wiki/", 1)[-1]
    if not title or ":" in title:
        return False
    return not parsed.query


def normalize_text(raw: str) -> str:
    return normalize_public_payload(raw)["text"]


def normalize_public_payload(raw: str, *, base_url: str = "") -> dict[str, Any]:
    extractor = TextExtractor()
    try:
        extractor.feed(raw)
        text = extractor.text() or raw
    except Exception:
        text = raw
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    links: list[str] = []
    base = base_url or ""
    if extractor.links:
        for href in extractor.links:
            joined = urljoin(base, href)
            cleaned, _ = urldefrag(joined)
            if cleaned and cleaned not in links:
                links.append(cleaned)
    return {"text": text[:12_000], "links": links[:200]}


def fetch_public_payload(url: str, *, timeout_seconds: int = 10) -> dict[str, Any]:
    ok, reason = is_safe_public_url(url)
    if not ok:
        raise ValueError(reason or "Unsafe URL")
    request = Request(url, headers={"User-Agent": "ATANOR-WebSeedFeeder/0.1 (+public-fragment-candidate)"})
    with urlopen(request, timeout=timeout_seconds) as response:
        content_type = str(response.headers.get("content-type", ""))
        if "text" not in content_type and "html" not in content_type and "json" not in content_type:
            raise ValueError(f"Unsupported content type: {content_type}")
        body = response.read(512_000)
    return normalize_public_payload(body.decode("utf-8", errors="ignore"), base_url=url)


def fetch_public_text(url: str, *, timeout_seconds: int = 10) -> str:
    return str(fetch_public_payload(url, timeout_seconds=timeout_seconds)["text"])


def should_fetch(source: dict[str, Any], now: datetime | None = None, *, max_interval_minutes: int | None = None) -> bool:
    if not bool(source.get("enabled")):
        return False
    interval = int(source.get("crawl_interval_minutes") or 1440)
    if max_interval_minutes is not None:
        interval = min(interval, max(1, int(max_interval_minutes)))
    last = source.get("last_fetched_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return True
    return (now or datetime.now(timezone.utc)) - last_dt >= timedelta(minutes=max(1, interval))


def _is_anna_source(source: dict[str, Any]) -> bool:
    return str(source.get("source_type") or "").strip().lower() == "anna_archive_api"


def _anna_source_runtime_enabled(source: dict[str, Any]) -> bool:
    if not _is_anna_source(source):
        return bool(source.get("enabled"))
    if bool(source.get("enabled")):
        return True
    if source.get("auto_enable_from_env") is False:
        return False
    try:
        from .anna_archive_provider import load_config

        config = load_config()
        return bool(config.enabled and config.endpoint)
    except Exception:
        return False


def _anna_source_queries(source: dict[str, Any]) -> list[str]:
    raw_queries = source.get("queries")
    queries: list[str] = []
    if isinstance(raw_queries, list):
        queries.extend(str(item).strip() for item in raw_queries if str(item).strip())
    if queries:
        return list(dict.fromkeys(queries))
    single = str(source.get("query") or source.get("name") or "").strip()
    if single:
        queries.append(single)
    return list(dict.fromkeys(queries))


def _anna_source_should_fetch(source: dict[str, Any], now_dt: datetime | None = None, *, max_interval_minutes: int | None = None) -> bool:
    if not _anna_source_runtime_enabled(source):
        return False
    interval = int(source.get("crawl_interval_minutes") or 1440)
    if max_interval_minutes is not None:
        interval = min(interval, max(1, int(max_interval_minutes)))
    last = source.get("last_fetched_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return True
    return (now_dt or datetime.now(timezone.utc)) - last_dt >= timedelta(minutes=max(1, interval))


def candidate_from_text(source: dict[str, Any], text: str, *, extracted_at: str | None = None) -> dict[str, Any]:
    extracted_at = extracted_at or utc_now()
    source_id = str(source.get("source_id") or "unknown_source")
    source_url = str(source.get("url") or "")
    title = str(source.get("name") or source_id)
    canonical = "\n".join([source_id, source_url, title, text])
    content_hash = hashlib.sha256(canonical.encode("utf-8", errors="ignore")).hexdigest()
    return {
        "fragment_id": f"candidate_{content_hash[:24]}",
        "content_hash": content_hash,
        "source_scope": "cloud",
        "privacy_scope": "public",
        "origin": "web_seed_feeder",
        "source_url": source_url,
        "source_id": source_id,
        "title": title,
        "text": text,
        "extracted_at": extracted_at,
        "trust_state": "unverified",
        "verification_state": "web_seed_pending",
        "ingestion_state": "pending",
        "created_by": "cloud_brain_web_seed_feeder",
    }


def _source_url_set(sources: list[dict[str, Any]]) -> set[str]:
    urls: set[str] = set()
    for source in sources:
        url = str(source.get("url") or "").strip()
        if url:
            cleaned, _ = urldefrag(url)
            urls.add(cleaned)
    return urls


def _link_allowed_for_frontier(source: dict[str, Any], link: str) -> bool:
    ok, _ = is_safe_public_url(link)
    if not ok:
        return False
    parsed = urlparse(link)
    source_host = urlparse(str(source.get("url") or "")).hostname
    same_host_only = bool(source.get("discovery_same_host_only", True))
    if same_host_only and source_host and parsed.hostname != source_host:
        return False
    path_lower = parsed.path.lower()
    query = parse_qs(parsed.query, keep_blank_values=True)
    if parsed.query:
        denied_query_keys = {
            "action",
            "campaign",
            "centralauthlogintoken",
            "returnto",
            "returntoquery",
            "title",
            "usesul3",
            "useformat",
        }
        if denied_query_keys.intersection({key.lower() for key in query}):
            return False
        if "/w/index.php" in path_lower:
            return False
    if not _is_wikipedia_article_url(parsed):
        return False
    if any(path_lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".svg", ".pdf", ".zip", ".epub", ".mobi")):
        return False
    if "/wiki/" in path_lower and ":" in path_lower.rsplit("/wiki/", 1)[-1]:
        return False
    deny_markers = (
        "/login",
        "/signin",
        "/account",
        "/special:",
        "/help:",
        "/file:",
        "/category:",
        "/w/index.php",
        "redlink=1",
    )
    return not any(marker in path_lower for marker in deny_markers)


def _semantic_link_score(link: str, text: str, source: dict[str, Any]) -> int:
    haystack = f"{link} {text}".lower()
    keywords = source.get("discovery_keywords")
    if not isinstance(keywords, list) or not keywords:
        keywords = SEED_RELEVANCE_KEYWORDS
    return sum(1 for keyword in keywords if str(keyword).lower() in haystack)


def seed_relevance_score(source: dict[str, Any], text: str) -> int:
    haystack = f"{source.get('name') or ''} {source.get('url') or ''} {text}".lower()
    score = 0
    for keyword in SEED_RELEVANCE_KEYWORDS:
        if keyword in haystack:
            score += 2 if " " in keyword or "-" in keyword else 1
    source_keywords = source.get("discovery_keywords")
    if isinstance(source_keywords, list):
        for keyword in source_keywords:
            keyword_text = str(keyword).lower().strip()
            if keyword_text and keyword_text in haystack:
                score += 1
    return score


def is_seed_relevant_payload(source: dict[str, Any], text: str) -> tuple[bool, int, int]:
    minimum = int(source.get("min_seed_relevance_score") or MIN_SEED_RELEVANCE_SCORE)
    if str(source.get("trust_tier") or "") == "seed":
        minimum = 1
    score = seed_relevance_score(source, text)
    return score >= minimum, score, minimum


def discover_frontier_sources(
    source: dict[str, Any],
    payload: dict[str, Any],
    existing_sources: list[dict[str, Any]],
    *,
    now: str,
) -> list[dict[str, Any]]:
    if not bool(source.get("discover_links")):
        return []
    links = payload.get("links") if isinstance(payload, dict) else []
    if not isinstance(links, list):
        return []
    existing_urls = _source_url_set(existing_sources)
    max_new = max(0, min(10, int(source.get("max_discovered_sources_per_run") or 2)))
    scored: list[tuple[int, str]] = []
    text = str(payload.get("text") or "")
    min_discovery_score = max(1, int(source.get("min_discovery_score") or MIN_SEED_RELEVANCE_SCORE))
    for link in links:
        cleaned, _ = urldefrag(str(link))
        if not cleaned or cleaned in existing_urls or not _link_allowed_for_frontier(source, cleaned):
            continue
        score = _semantic_link_score(cleaned, text, source)
        if score < min_discovery_score and bool(source.get("require_discovery_keyword", True)):
            continue
        scored.append((score, cleaned))
    scored.sort(key=lambda item: (-item[0], item[1]))
    discovered: list[dict[str, Any]] = []
    parent_id = str(source.get("source_id") or "public_seed")
    for score, link in scored[:max_new]:
        digest = hashlib.sha256(link.encode("utf-8", errors="ignore")).hexdigest()[:12]
        discovered.append(
            {
                "source_id": f"frontier_{digest}",
                "name": f"Frontier from {parent_id}",
                "url": link,
                "enabled": True,
                "source_type": "public_web",
                "trust_tier": str(source.get("trust_tier") or "low"),
                "crawl_interval_minutes": int(source.get("frontier_crawl_interval_minutes") or source.get("crawl_interval_minutes") or 1440),
                "last_fetched_at": None,
                "discovered_from": parent_id,
                "discovered_at": now,
                "discovery_score": score,
                "discover_links": bool(source.get("propagate_discovery", True)),
                "max_discovered_sources_per_run": max(0, min(3, int(source.get("max_discovered_sources_per_run") or 2))),
                "discovery_same_host_only": bool(source.get("discovery_same_host_only", True)),
                "discovery_keywords": source.get("discovery_keywords") or [],
                "require_discovery_keyword": bool(source.get("require_discovery_keyword", True)),
                "min_seed_relevance_score": max(1, int(source.get("min_seed_relevance_score") or MIN_SEED_RELEVANCE_SCORE)),
                "min_discovery_score": min_discovery_score,
            }
        )
        existing_urls.add(link)
    return discovered


def write_candidate_fragment(fragment: dict[str, Any], root: Path = DATA_ROOT) -> bool:
    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    content_hash = str(fragment["content_hash"])
    path = inbox / f"candidate_{content_hash}.json"
    if path.exists():
        return False
    write_json(path, fragment)
    return True


def _candidate_from_anna_metadata(source: dict[str, Any], record: dict[str, Any], *, extracted_at: str) -> dict[str, Any]:
    from .anna_archive_provider import metadata_to_semantic_text

    text = metadata_to_semantic_text(record)
    source_id = str(record.get("source_id") or source.get("source_id") or "anna_archive_metadata")
    source_url = str(record.get("source_url") or source.get("url") or "")
    title = str(record.get("title") or source.get("name") or source_id)
    canonical = "\n".join([source_id, source_url, title, text, str(record.get("source_hash") or "")])
    content_hash = hashlib.sha256(canonical.encode("utf-8", errors="ignore")).hexdigest()
    return {
        "fragment_id": f"candidate_{content_hash[:24]}",
        "content_hash": content_hash,
        "source_scope": "cloud",
        "privacy_scope": "public_metadata",
        "origin": "anna_archive_metadata_api",
        "source_url": source_url,
        "source_id": source_id,
        "title": title,
        "text": text,
        "metadata": {
            "authors": record.get("authors") or [],
            "year": record.get("year") or "",
            "language": record.get("language") or "",
            "license": record.get("license") or "unknown",
            "raw_text_stored": False,
            "download_url_stored": False,
        },
        "extracted_at": extracted_at,
        "trust_state": "metadata_only_unverified",
        "verification_state": "anna_metadata_pending_semantic_projection",
        "ingestion_state": "pending",
        "created_by": "cloud_brain_anna_archive_metadata_connector",
    }


def promote_candidate_to_semantic(fragment: dict[str, Any], root: Path = DATA_ROOT) -> dict[str, Any]:
    """Promote a public web candidate into the local Semantic Cloud proof store.

    The raw web text is used only as a transient extraction input. The semantic
    store keeps derived concepts, relations, hashes, and permitted metadata; it
    does not write anything into the private Local Brain.
    """

    from .semantic_growth import ingest_semantic_source

    text = str(fragment.get("text") or "").strip()
    if len(text) < 80:
        return {"ingested": False, "reason": "fragment_text_too_short"}
    summary = ingest_semantic_source(
        text=text,
        source_id=str(fragment.get("source_id") or fragment.get("fragment_id") or "web_seed_fragment"),
        language="auto",
        url=str(fragment.get("source_url") or "") or None,
        title=str(fragment.get("title") or "") or None,
        license="public-web-derived-fragment",
        usage_allowed=False,
        cloud_root=root,
    )
    return {
        "ingested": True,
        "run_id": summary.get("run_id"),
        "concepts_created": int(summary.get("concepts_created") or 0),
        "concepts_merged": int(summary.get("concepts_merged") or 0),
        "relations_created": int(summary.get("relations_created") or 0),
        "relations_strengthened": int(summary.get("relations_strengthened") or 0),
        "local_brain_write": False,
    }


def run_once(
    root: Path = DATA_ROOT,
    *,
    fetcher=fetch_public_payload,
    force_enabled: bool = False,
    force_fetch: bool = False,
    max_sources_checked_per_run: int | None = None,
) -> FeederResult:
    ensure_layout(root)
    state = load_state(root)
    now = utc_now()
    if not (bool(state.get("enabled")) or force_enabled):
        result = FeederResult(False, "disabled", 0, 0, 0, now)
        save_state(result.to_state(), root)
        return result

    checked = 0
    created = 0
    rejected = 0
    semantic_ingested = 0
    semantic_concepts_created = 0
    semantic_relations_created = 0
    semantic_relations_strengthened = 0
    anna_metadata_records = 0
    anna_metadata_rejected = 0
    discovered_sources_added = 0
    last_error: str | None = None
    sources = load_sources(root)
    updated_sources: list[dict[str, Any]] = [dict(source) for source in sources]
    new_sources: list[dict[str, Any]] = []
    promote_to_semantic = bool(state.get("promote_to_semantic", True))
    run_discovery_limit = max(0, min(1000, int(state.get("max_discovered_sources_per_run_total") or 1000)))
    max_total_sources = max(1, min(50_000, int(state.get("max_total_sources") or DEFAULT_STATE["max_total_sources"])))
    max_checked = max(1, min(1000, int(max_sources_checked_per_run or state.get("max_sources_checked_per_run") or 1000)))
    max_effective_interval = max(1, min(1440, int(state.get("max_effective_crawl_interval_minutes") or 1)))
    source_count = len(updated_sources)
    cursor = int(state.get("crawler_cursor") or 0)
    cursor = cursor % source_count if source_count else 0
    if force_fetch:
        cursor = 0
    next_cursor = cursor
    indices = _scheduled_source_indices(updated_sources, cursor, max_checked)

    for index in indices:
        if checked >= max_checked:
            break
        source = dict(updated_sources[index])
        source_enabled = _anna_source_runtime_enabled(source)
        if not source_enabled:
            continue
        source_due = (
            _anna_source_should_fetch(source, max_interval_minutes=max_effective_interval)
            if _is_anna_source(source)
            else should_fetch(source, max_interval_minutes=max_effective_interval)
        )
        if not force_fetch and not source_due:
            continue
        checked += 1
        next_cursor = (index + 1) % source_count if source_count else 0
        if _is_anna_source(source):
            try:
                from .anna_archive_provider import fetch_metadata, load_config

                queries = _anna_source_queries(source)
                if not queries:
                    rejected += 1
                    last_error = "Anna Archive metadata source is missing query."
                    updated_sources[index] = source
                    continue
                config = load_config()
                for query in queries:
                    response = fetch_metadata(query, config=config)
                    anna_metadata_rejected += int(response.get("rejected") or 0)
                    records = list(response.get("records") or [])
                    if not records:
                        if response.get("status") == "disabled_or_unconfigured":
                            last_error = "Anna Archive metadata API is disabled or unconfigured."
                        continue
                    for record in records:
                        fragment = _candidate_from_anna_metadata(source, record, extracted_at=now)
                        candidate_written = write_candidate_fragment(fragment, root)
                        if candidate_written:
                            created += 1
                            anna_metadata_records += 1
                        if promote_to_semantic:
                            semantic = promote_candidate_to_semantic(fragment, root)
                            if semantic.get("ingested"):
                                semantic_ingested += 1
                                semantic_concepts_created += int(semantic.get("concepts_created") or 0)
                                semantic_relations_created += int(semantic.get("relations_created") or 0)
                                semantic_relations_strengthened += int(semantic.get("relations_strengthened") or 0)
                source["last_fetched_at"] = now
            except Exception as exc:
                rejected += 1
                last_error = str(exc)
            updated_sources[index] = source
            continue
        ok, reason = is_safe_public_url(str(source.get("url") or ""))
        if not ok:
            rejected += 1
            last_error = reason
            updated_sources[index] = source
            continue
        try:
            fetched = fetcher(str(source.get("url")))
            if isinstance(fetched, dict):
                payload = fetched
                text = str(payload.get("text") or "")
            else:
                text = str(fetched)
                payload = {"text": text, "links": []}
            if len(text) < 80:
                rejected += 1
                last_error = "Fetched text was too short to create a public fragment candidate."
                updated_sources[index] = source
                continue
            relevant, relevance_score, minimum_score = is_seed_relevant_payload(source, text)
            if not relevant:
                rejected += 1
                last_error = f"Fetched text seed relevance was {relevance_score}, below required {minimum_score}."
                source["last_fetched_at"] = now
                source["last_rejected_reason"] = "seed_relevance_below_threshold"
                source["last_seed_relevance_score"] = relevance_score
                updated_sources[index] = source
                continue
            fragment = candidate_from_text(source, text, extracted_at=now)
            candidate_written = write_candidate_fragment(fragment, root)
            if candidate_written:
                created += 1
            if promote_to_semantic:
                semantic = promote_candidate_to_semantic(fragment, root)
                if semantic.get("ingested"):
                    semantic_ingested += 1
                    semantic_concepts_created += int(semantic.get("concepts_created") or 0)
                    semantic_relations_created += int(semantic.get("relations_created") or 0)
                    semantic_relations_strengthened += int(semantic.get("relations_strengthened") or 0)
            remaining_total_slots = max_total_sources - len([*updated_sources, *new_sources])
            remaining_run_slots = run_discovery_limit - discovered_sources_added
            discovered = discover_frontier_sources(source, payload, [*updated_sources, *new_sources], now=now)
            if discovered and (remaining_total_slots <= 0 or remaining_run_slots <= 0):
                discovered = []
            elif discovered:
                discovered = discovered[: min(len(discovered), remaining_total_slots, remaining_run_slots)]
            if discovered:
                new_sources.extend(discovered)
                discovered_sources_added += len(discovered)
            source["last_fetched_at"] = now
        except Exception as exc:
            rejected += 1
            last_error = str(exc)
        updated_sources[index] = source

    write_json(root / "web_seed_sources.json", reconcile_seed_sources([*updated_sources, *new_sources], max_total_sources=max_total_sources))
    if created:
        status = "created_fragments"
    elif semantic_ingested:
        status = "strengthened_semantic_cloud"
    elif checked and rejected:
        # Individual frontier URLs can disappear or reject bot traffic. Treat a
        # rejected-only pass as a listening cycle with diagnostics, not as a
        # daemon failure that would make the Cloud Brain look stopped.
        status = "listening_with_rejections"
    elif checked == 0:
        status = "waiting_for_due_sources"
    else:
        status = "no_new_payload"
    result = FeederResult(
        True,
        status,
        checked,
        created,
        rejected,
        now,
        semantic_ingested=semantic_ingested,
        promote_to_semantic=promote_to_semantic,
        semantic_concepts_created=semantic_concepts_created,
        semantic_relations_created=semantic_relations_created,
        semantic_relations_strengthened=semantic_relations_strengthened,
        anna_metadata_records=anna_metadata_records,
        anna_metadata_rejected=anna_metadata_rejected,
        discovered_sources_added=discovered_sources_added,
        max_sources_checked_per_run=max_checked,
        max_effective_crawl_interval_minutes=max_effective_interval,
        crawler_cursor=next_cursor,
        last_error=last_error,
    )
    save_state(result.to_state(), root)
    return result


def feeder_status(root: Path = DATA_ROOT) -> dict[str, Any]:
    ensure_layout(root)
    state = load_state(root)
    try:
        from .anna_archive_provider import load_config

        anna_archive_api = load_config().public_status()
    except Exception as exc:
        anna_archive_api = {
            "enabled": False,
            "configured": False,
            "error": str(exc),
            "metadata_only": True,
            "full_text_downloads_allowed": False,
        }
    status = str(state.get("last_status") or "idle")
    if bool(state.get("enabled")) and status == "idle":
        status = "listening"
    return {
        "enabled": bool(state.get("enabled")),
        "status": status,
        "sources_checked": int(state.get("sources_checked") or 0),
        "fragments_created": int(state.get("fragments_created") or 0),
        "fragments_rejected": int(state.get("fragments_rejected") or 0),
        "semantic_ingested": int(state.get("semantic_ingested") or 0),
        "semantic_concepts_created": int(state.get("semantic_concepts_created") or 0),
        "semantic_relations_created": int(state.get("semantic_relations_created") or 0),
        "semantic_relations_strengthened": int(state.get("semantic_relations_strengthened") or 0),
        "anna_metadata_records": int(state.get("anna_metadata_records") or 0),
        "anna_metadata_rejected": int(state.get("anna_metadata_rejected") or 0),
        "discovered_sources_added": int(state.get("discovered_sources_added") or 0),
        "max_discovered_sources_per_run_total": int(state.get("max_discovered_sources_per_run_total") or 24),
        "max_total_sources": int(state.get("max_total_sources") or 500),
        "max_sources_checked_per_run": int(state.get("max_sources_checked_per_run") or 6),
        "max_effective_crawl_interval_minutes": int(state.get("max_effective_crawl_interval_minutes") or 1),
        "crawler_cursor": int(state.get("crawler_cursor") or 0),
        "anna_archive_api": anna_archive_api,
        "last_run_at": state.get("last_run_at"),
        "last_error": state.get("last_error"),
        "inbox_path": str((root / "inbox").as_posix()),
        "writes_local_brain": False,
        "privacy_scope": "public_cloud_candidates_only",
    }


def watch(root: Path = DATA_ROOT, *, interval_seconds: int = 60) -> None:
    while True:
        run_once(root)
        time.sleep(max(5, interval_seconds))


def main() -> None:
    parser = argparse.ArgumentParser(description="ATANOR Cloud Brain Web Seed Feeder")
    parser.add_argument("--once", action="store_true", help="Run one feeder pass and exit.")
    parser.add_argument("--watch", action="store_true", help="Run feeder loop. Disabled by default.")
    parser.add_argument("--root", default=str(DATA_ROOT), help="Cloud Brain data root.")
    parser.add_argument("--force-enabled", action="store_true", help="Run once even if feeder state is disabled.")
    parser.add_argument("--force-fetch", action="store_true", help="Ignore source crawl intervals for this pass.")
    args = parser.parse_args()
    root = Path(args.root)
    if args.watch:
        watch(root)
        return
    result = run_once(root, force_enabled=args.force_enabled, force_fetch=args.force_fetch)
    print(json.dumps(result.to_state(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
