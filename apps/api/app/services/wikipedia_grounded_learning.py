"""Wikipedia-grounded cumulative learning for the autonomous loop.

The autonomous loop's old live-web step crawled raw HTML and tokenised page
text, which let navigation cruft ("Apr", "be", "It") leak into the candidate
graph as single-token "concepts". This module routes the loop's web learning
through the SAME clean Wikipedia grounding path the chat engine uses
(``web_search.wikipedia_search``): each topic resolves to a real article title
plus a well-formed definition sentence with a source URL.

Those clean definitions become ``source_type="wikipedia"`` ``LearningPayload``
rows — the verified ingestion schema — so CGSR extracts proper noun-phrase
concepts, every row carries provenance, and the existing mock/quality gates
still apply. Nothing here writes production directly: payloads land in a
candidate store that the loop's normal auto-promote/merge path picks up.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.web_search import wikipedia_search

from packages.cloud_brain.bounded_learning_runner import (
    BoundedLearningRunConfig,
    run_bounded_candidate_learning,
)
from packages.cloud_brain.candidate_read_model import DEFAULT_CANDIDATE_RUNS_DIR
from packages.cloud_brain.verified_payload_feeder import (
    LearningPayload,
    payload_from_mapping,
)

# Durable candidate store the loop's merge/auto-promote path resolves by mtime.
WIKIPEDIA_GROUNDED_STORE = DEFAULT_CANDIDATE_RUNS_DIR / "wikipedia_grounded_live"
_CURSOR_PATH = (
    Path(__file__).resolve().parents[3]
    / "runtime"
    / "cloud_brain"
    / "wikipedia_grounded_cursor.json"
)

# A curated rotation of real, well-known concepts: general knowledge plus the
# project's own technical domains. Each is a Wikipedia article title so the
# lookup resolves to a clean lead-section definition rather than a search miss.
WIKIPEDIA_LEARNING_TOPICS: tuple[str, ...] = (
    "Photosynthesis",
    "Telephone",
    "Marie Curie",
    "Gravity",
    "Electricity",
    "Democracy",
    "Volcano",
    "Antibiotic",
    "Photovoltaics",
    "Machine learning",
    "Neural network",
    "Encryption",
    "Compiler",
    "Virtual machine",
    "Hypertext Transfer Protocol",
    "JSON",
    "Git",
    "Linux",
    "Python (programming language)",
    "Graph (abstract data type)",
    "Knowledge graph",
    "Natural language processing",
    "Vaccine",
    "DNA",
    "Black hole",
    "Plate tectonics",
    "Renaissance",
    "Industrial Revolution",
    "Quantum mechanics",
    "Climate",
    "Ecosystem",
    "Immune system",
    "Algorithm",
    "Cryptography",
    "Relational database",
    "Operating system",
    "Internet",
    "Artificial intelligence",
    "Periodic table",
    "Evolution",
)

# A clean definition has real sentence shape, not a fragment or nav text.
_MIN_DEFINITION_WORDS = 8
# The CGSR ingestion verification gate rejects text >260 chars
# ("too_long_for_small_stage"), so definitions must be trimmed to fit while
# staying a complete sentence.
_MAX_DEFINITION_CHARS = 255


def _has_hangul(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text)


def _is_clean_definition(snippet: str) -> bool:
    text = (snippet or "").strip()

    if _has_hangul(text):
        return len(text) >= 16 and any(mark in text for mark in ("다.", "이다", "입니다", "은 ", "는 ", "."))
    if len(text.split()) < _MIN_DEFINITION_WORDS:
        return False
    # A real lead sentence ends a clause; bare keyword lists rarely do.
    return any(mark in text for mark in (". ", ".", " is ", " are ", " was ", " refers to "))


def _fit_for_ingestion(text: str, *, limit: int = _MAX_DEFINITION_CHARS) -> str:
    """Trim to a single complete sentence within the ingestion length cap.

    Wikipedia lead extracts run several sentences; the first one is the clean
    definition we want and almost always fits, so prefer it and only hard-cap on
    a word boundary if it is still too long."""

    text = " ".join((text or "").split())

    if _has_hangul(text):
        marker = text.find("다. ")
        first = (text[: marker + 2].strip() if marker != -1 else text.split(". ")[0].strip())
    else:
        first = text.split(". ")[0].strip()
        if first and not first.endswith("."):
            first = f"{first}."
    candidate = first if 12 <= len(first) <= limit else text
    if len(candidate) > limit:
        candidate = candidate[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "."
    return candidate


def _load_cursor() -> int:
    try:
        data = json.loads(_CURSOR_PATH.read_text(encoding="utf-8"))
        return int(data.get("cursor", 0)) % len(WIKIPEDIA_LEARNING_TOPICS)
    except Exception:
        return 0


def _save_cursor(cursor: int) -> None:
    try:
        _CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CURSOR_PATH.write_text(
            json.dumps({"cursor": cursor % len(WIKIPEDIA_LEARNING_TOPICS)}),
            encoding="utf-8",
        )
    except Exception:  # pragma: no cover - cursor persistence is best-effort
        pass


def next_topics(count: int, *, advance: bool = True) -> list[str]:
    """Return the next ``count`` topics from the rotating cursor."""

    total = len(WIKIPEDIA_LEARNING_TOPICS)
    count = max(0, min(int(count), total))
    start = _load_cursor()
    topics = [WIKIPEDIA_LEARNING_TOPICS[(start + offset) % total] for offset in range(count)]
    if advance and count:
        _save_cursor(start + count)
    return topics


def build_wikipedia_learning_payloads(topics: list[str]) -> list[LearningPayload]:
    """Resolve each topic to a clean Wikipedia definition ``LearningPayload``.

    Offline or rate-limited lookups return no usable snippet and are skipped, so
    this degrades to an empty list rather than fabricating rows.
    """

    payloads: list[LearningPayload] = []
    seen_urls: set[str] = set()
    for topic in topics:
        try:
            results = wikipedia_search(topic, count=2)
        except Exception:  # pragma: no cover - network failure never raises upward
            continue
        for result in results or []:
            snippet = str(result.get("snippet") or "").strip()
            title = str(result.get("title") or topic).strip()
            url = str(result.get("url") or "").strip()
            if not url or url in seen_urls or not _is_clean_definition(snippet):
                continue
            # Lead with the article title so CGSR anchors the concept on the real
            # subject, then carry one clean definition sentence within the cap.
            definition = _fit_for_ingestion(snippet)
            if title.lower() not in definition.lower():
                definition = _fit_for_ingestion(f"{title}: {definition}")
            text = definition
            payloads.append(
                payload_from_mapping(
                    {
                        "source_type": "wikipedia",
                        "source_id": url,
                        "source_url_or_path": url,
                        "text": text,
                        "language": "en",
                        "license_hint": "reference_only",
                    }
                )
            )
            seen_urls.add(url)
            break  # one clean definition per topic is enough
    return payloads


def ingest_web_result(
    results: list[dict[str, Any]],
    *,
    language: str = "en",
    max_nodes: int = 3,
    store_path: str | Path | None = None,
) -> dict[str, Any]:
    """Graft already-retrieved web results into the Cloud Brain on demand.

    Used by the chat web-grounding path: when a question is answered from the
    web, the cited result(s) become real ``source_type="wikipedia"`` concepts in
    the candidate store (same clean path as the autonomous loop), and the new
    node descriptors are returned so the Local Brain graph can show them lit up.
    """

    payloads: list[LearningPayload] = []
    nodes: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for result in results or []:
        if len(payloads) >= max_nodes:
            break
        snippet = str(result.get("snippet") or "").strip()
        title = str(result.get("title") or "").strip()
        url = str(result.get("url") or "").strip()
        if not title or not url or url in seen_urls or not _is_clean_definition(snippet):
            continue
        definition = _fit_for_ingestion(snippet)
        if title.lower() not in definition.lower():
            definition = _fit_for_ingestion(f"{title}: {definition}")
        payloads.append(
            payload_from_mapping(
                {
                    "source_type": "wikipedia",
                    "source_id": url,
                    "source_url_or_path": url,
                    "text": definition,
                    "language": language if language in {"ko", "en"} else "en",
                    "license_hint": "reference_only",
                }
            )
        )
        nodes.append({"id": url, "label": title, "kind": "web_new", "source_url": url, "definition": definition})
        seen_urls.add(url)
    if not payloads:
        return {"ingested": False, "reason": "no_grounded_payloads", "concepts_added": 0, "grafted_nodes": []}
    target = str(store_path or WIKIPEDIA_GROUNDED_STORE)
    config = BoundedLearningRunConfig(
        profile="interactive_safe",
        max_payloads=len(payloads),
        target_candidate_store=target,
        min_ram_free_gb=1.5,
        min_disk_free_gb=2.0,
        execute=True,
        dry_run=False,
    )
    result_summary = run_bounded_candidate_learning(config, payloads=payloads)
    return {
        "ingested": result_summary.state in {"completed", "paused"},
        "concepts_added": result_summary.concepts_added_candidate,
        "relations_added": result_summary.relations_added_candidate,
        "grafted_nodes": nodes,
        "candidate_store_path": target,
        "production_store_mutated": result_summary.production_store_mutated,
        "false_confident": result_summary.false_confident,
    }


def ingest_wikipedia_grounded_once(
    *,
    max_topics: int = 3,
    store_path: str | Path | None = None,
    advance_cursor: bool = True,
) -> dict[str, Any]:
    """Learn a small bounded batch of real concepts from Wikipedia.

    Builds clean ``source_type="wikipedia"`` payloads and runs them through the
    bounded candidate learner (candidate-only, production write blocked). Returns
    an honest summary; on no network / no clean snippet it reports that plainly
    instead of inventing growth.
    """

    topics = next_topics(max_topics, advance=advance_cursor)
    if not topics:
        return {"ingested": False, "reason": "no_topics", "concepts_added": 0}
    payloads = build_wikipedia_learning_payloads(topics)
    if not payloads:
        return {
            "ingested": False,
            "reason": "no_grounded_payloads",
            "topics_attempted": topics,
            "concepts_added": 0,
        }
    target = str(store_path or WIKIPEDIA_GROUNDED_STORE)
    # The interactive_safe profile's 8 GB RAM / 40 GB disk floors guard big 24h
    # runs; this is a 2-3 payload batch costing tens of MB, so use realistic
    # floors that still abort on a genuinely starved machine but don't refuse to
    # learn on an ordinarily-busy one.
    config = BoundedLearningRunConfig(
        profile="interactive_safe",
        max_payloads=len(payloads),
        target_candidate_store=target,
        min_ram_free_gb=1.5,
        min_disk_free_gb=2.0,
        execute=True,
        dry_run=False,
    )
    # Provenance/quality/mock gates are enforced inside the bounded loop, so
    # rejected rows never reach the candidate store.
    result = run_bounded_candidate_learning(config, payloads=payloads)
    return {
        "ingested": result.state in {"completed", "paused"},
        "state": result.state,
        "stop_reason": result.stop_reason,
        "topics_used": topics,
        "source_urls": [payload.source_url_or_path for payload in payloads],
        "payloads_accepted": result.payloads_accepted,
        "concepts_added": result.concepts_added_candidate,
        "relations_added": result.relations_added_candidate,
        "candidate_store_path": target,
        "production_store_mutated": result.production_store_mutated,
        "false_confident": result.false_confident,
    }
