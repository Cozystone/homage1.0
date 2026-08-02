from __future__ import annotations

import asyncio
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import json
from html import unescape
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus


# Local secrets loader: provider keys live in repo-root .env.local (gitignored), so the
# engine picks them up on any restart regardless of how the watchdog spawns it.
# PRECEDENCE: .env.local OVERRIDES the machine env (standard .env.local semantics — measured:
# a stale TAVILY key in the Windows user env shadowed the owner's fresh key and 432'd);
# plain .env is setdefault-only. Never raises.
def _load_local_env() -> None:
    try:
        from pathlib import Path
        root = Path(__file__).resolve().parents[4]   # apps/api/app/services/ → repo root
        for name, override in ((".env.local", True), (".env", False)):
            p = root / name
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k and v:
                    if override:
                        os.environ[k] = v
                    else:
                        os.environ.setdefault(k, v)
    except Exception:
        pass


_load_local_env()


# Wikimedia's User-Agent policy REQUIRES a descriptive agent with a real contact
# (URL or email). A generic / "contact: local" agent gets aggressively 429'd — that
# was the real cause of the recurring "web_unreachable": with a proper UA the same
# REST calls return 200 immediately. Override per-deployment via ATANOR_WEB_UA.
WEB_USER_AGENT = os.getenv("ATANOR_WEB_UA") or (
    "ATANOR-KnowledgeBot/0.2 (+https://github.com/ATANOR-Demo; ATANOR knowledge grounding)"
)

# Small TTL cache so repeated questions don't re-hit Wikipedia (cuts latency and
# avoids 429 rate-limiting). Keyed by request URL.
_WIKI_CACHE: dict[str, tuple[float, Any]] = {}
_WIKI_CACHE_TTL = 900.0  # 15 min


def _wiki_get_json(url: str, *, timeout: float = 2.5, retries: int = 1) -> Any:
    """GET + parse JSON from a bounded public Wikipedia endpoint, with a tiny TTL
    cache and one backoff retry on 429/5xx. Returns {} on failure (never raises).

    Timeout/retries are kept tight on purpose: a failing lookup must give up in a
    few seconds, not ~15s (3 attempts × 5s), which is what made the answer feel
    'too slow' / return web_unreachable after a long wait."""
    now = time.monotonic()
    cached = _WIKI_CACHE.get(url)
    if cached and now - cached[0] < _WIKI_CACHE_TTL:
        return cached[1]
    request = urllib.request.Request(url, headers={"User-Agent": WEB_USER_AGENT})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - bounded public API
                payload = json.loads(response.read().decode("utf-8"))
            _WIKI_CACHE[url] = (now, payload)
            return payload
        except urllib.error.HTTPError as exc:
            # 429 = rate-limited; an immediate retry just gets another 429, so give up
            # at once (fast fail) instead of sleeping. Only retry genuinely transient
            # 5xx server errors, and with a short backoff.
            if exc.code in (500, 502, 503) and attempt < retries:
                time.sleep(0.4 * (attempt + 1))
                continue
            return {}
        except Exception:
            return {}
    return {}


@dataclass
class WebSearchResult:
    id: str
    title: str
    url: str
    snippet: str
    provider: str
    source_type: str = "web_search"
    license_status: str = "reference_only"


DEFAULT_QUERY = "GraphRAG neuromorphic continual learning low power AI architecture"

STATIC_RESULTS = [
    WebSearchResult(
        id="web-static-001",
        title="Microsoft GraphRAG",
        url="https://github.com/microsoft/graphrag",
        snippet="Microsoft GraphRAG provides a graph-based retrieval augmented generation system with indexing and query workflows.",
        provider="static",
        source_type="repository_or_docs",
    ),
    WebSearchResult(
        id="web-static-002",
        title="Grounding with Bing Search tools with the agents API",
        url="https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/bing-tools",
        snippet="Microsoft Foundry agents can use Grounding with Bing Search to incorporate real-time public web data and cite sources.",
        provider="static",
        source_type="official_docs",
    ),
    WebSearchResult(
        id="web-static-003",
        title="Bing Search APIs retiring on August 11, 2025",
        url="https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement",
        snippet="Microsoft says Bing Search APIs retire on August 11, 2025 and recommends Grounding with Bing Search as part of Azure AI Agents.",
        provider="static",
        source_type="official_docs",
    ),
    WebSearchResult(
        id="web-static-004",
        title="MiroFish",
        url="https://github.com/666ghj/MiroFish",
        snippet="MiroFish demonstrates a console-style graph growth interface useful as a UI reference for ATANOR BakeBoard.",
        provider="static",
        source_type="repository_or_docs",
    ),
]


def _provider_from_env(provider: str | None = None) -> str:
    return (provider or os.getenv("WEB_SEARCH_PROVIDER") or "static").strip().lower()


FRESH_SEARCH_PATTERN = re.compile(
    "(\uC624\uB298|\uD604\uC7AC|\uCD5C\uC2E0|\uBC29\uAE08|\uC2E4\uC2DC\uAC04|\uC18D\uBCF4|\uB274\uC2A4|\uB0A0\uC528|\uC8FC\uAC00|\uD658\uC728|today|latest|recent|current|breaking|news|weather|stock|price)",
    re.IGNORECASE,
)
KNOWLEDGE_LOOKUP_PATTERN = re.compile(
    "(\uB204\uAD6C|\uB204\uAD6C\uC57C|\uBB50\uC57C|\uBB34\uC5C7|\uC815\uC758|\uC54C\uB824\uC918|\uC124\uBA85|\uC65C|\uC774\uC720|\uC6D0\uB9AC|\uC5B4\uB5BB\uAC8C"
    "|\uC5B8\uC81C|\uC5B4\uB514|\uC5B4\uB290|\uBC1C\uBA85|\uBC1C\uACAC|\uB9CC\uB4E0|\uC9C0\uC740|\uC4F4"  # \uC5B8\uC81C \uC5B4\uB514 \uC5B4\uB290 \uBC1C\uBA85 \uBC1C\uACAC \uB9CC\uB4E0 \uC9C0\uC740 \uC4F4
    r"|\bwho\b|\bwhat\b|\bwhen\b|\bwhere\b|\bwhich\b|\bwhom\b"
    r"|tell me about|define|explain|why|how"
    r"|invented|discovered|founded|created|located|capital of|author of)",
    re.IGNORECASE,
)


def is_fresh_search_query(query: str) -> bool:
    return bool(FRESH_SEARCH_PATTERN.search(query))


def is_knowledge_lookup_query(query: str) -> bool:
    return bool(KNOWLEDGE_LOOKUP_PATTERN.search(query))


def _provider_configured(provider: str) -> bool:
    if provider == "brave":
        return bool(os.getenv("BRAVE_SEARCH_API_KEY"))
    if provider == "serper":
        return bool(os.getenv("SERPER_API_KEY"))
    if provider == "tavily":
        return bool(os.getenv("TAVILY_API_KEY"))
    if provider in {"microsoft-grounding", "grounding-with-bing", "bing-grounding"}:
        return bool(os.getenv("FOUNDRY_PROJECT_ENDPOINT") and os.getenv("BING_PROJECT_CONNECTION_ID"))
    return provider == "static"


def _static_fixtures_allowed() -> bool:
    """The hardcoded STATIC_RESULTS are offline dev/CI fixtures — NEVER a production evidence
 source. Presenting a fixture as verified grounding (" …") is the exact
 No- violation. So fixtures surface ONLY when explicitly opted in: WEB_SEARCH_PROVIDER=static
 (tests set this) or ATANOR_ALLOW_STATIC_FIXTURES. With nothing configured, the search returns
 NO results and the answer path abstains honestly instead of grounding on a fixture."""
    raw = (os.getenv("WEB_SEARCH_PROVIDER") or "").strip().lower()
    flag = (os.getenv("ATANOR_ALLOW_STATIC_FIXTURES") or "").strip().lower()
    return raw == "static" or flag in {"1", "true", "yes", "on"}


def provider_status(provider: str | None = None) -> dict[str, Any]:
    selected = _provider_from_env(provider)
    return {
        "selected_provider": selected,
        "configured": _provider_configured(selected),
        "raw_result_providers": {
            "brave": bool(os.getenv("BRAVE_SEARCH_API_KEY")),
            "serper": bool(os.getenv("SERPER_API_KEY")),
            "tavily": bool(os.getenv("TAVILY_API_KEY")),
            "wikipedia": True,
            "static": True,
        },
        "microsoft_grounding_with_bing": {
            "configured": _provider_configured("microsoft-grounding"),
            "mode": "foundry_agent_tool",
            "native_homage_default": False,
            "reason": "Grounding with Bing is an Azure Foundry Agent tool that returns model responses with citations, not raw searchable chunks for ATANOR native synthesis.",
            "required_env": [
                "FOUNDRY_PROJECT_ENDPOINT",
                "FOUNDRY_MODEL_DEPLOYMENT_NAME",
                "BING_PROJECT_CONNECTION_ID",
                "AGENT_TOKEN or Azure credential",
            ],
        },
    }


def static_search(query: str, count: int = 5) -> list[dict[str, Any]]:
    terms = [term.lower() for term in query.split() if len(term) > 1]
    scored: list[tuple[int, WebSearchResult]] = []
    for result in STATIC_RESULTS:
        haystack = f"{result.title} {result.snippet} {result.url}".lower()
        score = sum(1 for term in terms if term in haystack)
        scored.append((score, result))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    # Only return entries that actually overlap the query. The static catalog is a
    # last-resort sample set; returning a score-0 entry (e.g. the GraphRAG sample for an
    # unrelated question like "who will be president in 2050") leaks an off-topic snippet
    # as if it were evidence. When nothing overlaps, return [] so the caller abstains
    # rather than surface garbage — "no relevant grounding → hold", not a canned answer.
    relevant = [(score, result) for score, result in scored if score > 0]
    return [asdict(result) | {"search_score": score} for score, result in relevant[: max(1, min(count, 10))]]


def _strip_html(value: str) -> str:
    text = unescape(unescape(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_lookup_query(query: str) -> str:
    cleaned = re.sub(r"[?!.,]", " ", query)
    cleaned = re.sub(
        "(\uC5D0\\s*\uB300\uD574|\uC5D0\\s*\uB300\uD55C|\uC5D0\\s*\uAD00\uD574|\uC5D0\\s*\uAD00\uD55C|\uAD00\uB828\uD574|\uB204\uAD6C\uC57C|\uB204\uAD6C\uB2C8|\uB204\uAD6C|\uBB50\uC57C|\uBB34\uC5C7\uC774\uC57C|\uBB34\uC5C7|\uC54C\uB824\uC918|\uC124\uBA85\uD574\uC918|\uC124\uBA85|\uC18C\uAC1C\uD574\uC918|\uC815\uC758|who is|what is|tell me about|define|explain)",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Strip question scaffolding around a fact so the ENTITY remains and the
    # encyclopedia search hits the right page ("who invented the telephone" ->
    # "the telephone"). English verbs + Korean equivalents.
    cleaned = re.sub(
        r"\b(who|when|where|which)\b\s*(was|were|is|are|did)?\s*"
        r"(invented|discovered|made|created|founded|wrote|built|designed|painted|born|located|the\s+author\s+of|the\s+capital\s+of)?",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        "(누가\\s*(발명|발견|만든|지은|쓴|세운|그린)(한|했어|했나|했지)?|언제\\s*(발명|발견|만들|생겼)|"
        "발명한|발견한|만든|지은|쓴|언제|어디(에|서|야)?|어느|수도(가|는)?)",
        " ",
        cleaned,
    )



    cleaned = re.sub(
        r"(창립자|설립자|창업자|공동\s*창업자|발명자|발견자|저자|작곡가|작가|감독|창시자|설계자|개발자)\s*(은|는|이|가|를|을)?",
        " ",
        cleaned,
    )

    cleaned = re.sub(
        r"(그린|세운|설립한|창립한|창업한|작곡한|감독한|건설한|개발한|창시한|설계한)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s(사람|인물|이름)\b", " ", cleaned)
    cleaned = re.sub(
        r"(그건|그게|그거|그것|이건|이게|이거|이것|왜\s*그런가요|왜\s*그래|왜|이유|원리|어떻게|how|why)",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    tokens = [token for token in re.split(r"\s+", cleaned.strip()) if token]
    trimmed = [_strip_korean_lookup_particle(token) for token in tokens]
    return " ".join(token for token in trimmed if token).strip() or query.strip()


def _strip_korean_lookup_particle(token: str) -> str:
    token = token.strip()
    if len(token) <= 1:
        return token
    # Strip only common lookup particles from Korean noun tokens. This turns

    return re.sub(r"(\uC740|\uB294|\uC774|\uAC00|\uC744|\uB97C|\uC758|\uC5D0|\uC5D0\uC11C|\uC73C\uB85C|\uB85C|\uACFC|\uC640|\uB3C4|\uB9CC)$", "", token)


def _lookup_terms(lookup: str) -> list[str]:
    terms: list[str] = []
    for token in re.split(r"\s+", lookup.lower()):
        token = re.sub(r"[^0-9a-zA-Z\uAC00-\uD7A3]+", "", token)
        if len(token) >= 2:
            terms.append(token)
    return terms


VISUAL_EVENT_CUE_RE = re.compile(
    r"(떨어|낙하|앉|나무|사과|머리|발견|관찰|움직|이동|회전|충돌|흐르|"
    r"fall|fell|falling|drop|dropped|tree|apple|sat|sitting|head|discover|observ|move|motion|orbit)",
    re.IGNORECASE,
)


def _split_source_sentences(text: str, *, max_len: int = 420) -> list[str]:
    cleaned = _strip_html(text)
    if not cleaned:
        return []
    # Keep sentence boundaries simple and deterministic; this is evidence
    # extraction for visual affordances, not generative summarization.
    rough = re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s+|[\n\r]+", cleaned)
    sentences: list[str] = []
    for item in rough:
        sentence = re.sub(r"\s+", " ", item).strip()
        if len(sentence) < 18:
            continue
        if len(sentence) > max_len:
            sentence = sentence[:max_len].rstrip(" ,;:") + "..."
        sentences.append(sentence)
    return sentences


def extract_visual_event_sentences(text: str, *, limit: int = 3) -> list[str]:
    """Return source-local visual/motion sentences without topic templates."""

    results: list[str] = []
    seen: set[str] = set()
    for sentence in _split_source_sentences(text):
        if not VISUAL_EVENT_CUE_RE.search(sentence):
            continue
        key = sentence.casefold()
        if key in seen:
            continue
        seen.add(key)
        results.append(sentence)
        if len(results) >= max(1, limit):
            break
    return results


def _wikipedia_extract_for_page(title: str) -> str:
    page_slug = quote(title.replace(" ", "_"), safe="")
    page_url = (
        "https://ko.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&exintro=0"
        f"&format=json&titles={page_slug}"
    )
    request = urllib.request.Request(page_url, headers={"User-Agent": WEB_USER_AGENT})
    with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310 - bounded public API endpoint
        body = json.loads(response.read().decode("utf-8"))
    pages = (body.get("query", {}) or {}).get("pages", {}) or {}
    for page in pages.values():
        extract = str(page.get("extract") or "").strip()
        if extract:
            return extract
    return ""


_INFOBOX_FIELDS = {
    "founded": ("설립자", "창립자", "창업자", "공동 창립자", "공동창립자", "founder", "founders", "founded by"),
    "invented": ("발명자", "발명가", "inventor", "inventors"),
    "directed": ("감독", "director"),
    "composed": ("작곡", "작곡가", "composer"),
}


def wikipedia_infobox_people(title: str, *, host: str, relation_key: str) -> str | None:
    """Read the named people from an article's infobox (e.g. a company's 
 field) via the parse API. The extracts API strips infoboxes, so founders that
 live only in the infobox are invisible to prose scraping — this recovers them.
 Returns a comma-joined name string, or None. Deterministic, no LLM."""
    fields = _INFOBOX_FIELDS.get(relation_key)
    if not fields:
        return None
    api = f"https://{host}/w/api.php?action=parse&format=json&prop=wikitext&redirects=1&page={quote(title, safe='')}"
    body = _wiki_get_json(api)
    parse = (body or {}).get("parse", {}) or {}
    wikitext = parse.get("wikitext", {})
    wt = wikitext.get("*", "") if isinstance(wikitext, dict) else str(wikitext or "")
    if not wt:
        return None
    for field in fields:
        m = re.search(rf"\|\s*{re.escape(field)}\s*=\s*(.+)", wt)
        if not m:
            continue
        value = m.group(1)
        # Prefer [[wikilink]] display names; reject ref/citation noise.
        names = [n.split("|")[0].strip() for n in re.findall(r"\[\[([^\]]+)\]\]", value)]
        names = [n for n in names if n and "=" not in n and "{" not in n and 2 <= len(n) <= 24 and not re.search(r"\d", n)]
        if names:
            return ", ".join(dict.fromkeys(names[:5]))  # de-dup, cap at 5
    return None


def _wikipedia_visual_event_results(base_results: list[dict[str, Any]], *, limit: int = 2) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for result in base_results[:2]:
        title = str(result.get("title") or "").strip()
        if not title:
            continue
        try:
            extract = _wikipedia_extract_for_page(title)
        except Exception:
            continue
        for sentence_index, sentence in enumerate(extract_visual_event_sentences(extract, limit=2), start=1):
            enriched.append(
                {
                    "id": f"{result.get('id') or 'wikipedia'}-visual-{sentence_index}",
                    "title": f"{title} visual event evidence",
                    "url": result.get("url", ""),
                    "snippet": sentence,
                    "provider": "wikipedia",
                    "source_type": "encyclopedia_visual_event_extract",
                    "license_status": "reference_only",
                    "search_score": int(result.get("search_score") or 0) - sentence_index,
                    "query_terms_matched": int(result.get("query_terms_matched") or 0),
                    "normalized_query": result.get("normalized_query"),
                    "visual_evidence_enrichment": True,
                    "enrichment_basis": "source_page_sentence_visual_motion_cues",
                    "topic_scene_templates": False,
                    "renderer_may_infer_topic": False,
                    "particle_text": False,
                }
            )
            if len(enriched) >= max(0, limit):
                return enriched
    return enriched


def _wiki_host_for_query(query: str) -> str:
    # Use the Wikipedia edition that matches the query language. A Korean query
    # hits ko.wikipedia; an otherwise-Latin query hits en.wikipedia (searching
    # ko.wikipedia for "Eiffel Tower" returns irrelevant pages).
    return "ko.wikipedia.org" if re.search(r"[가-힣]", query or "") else "en.wikipedia.org"


def _norm_title(title: str) -> str:
    return re.sub(r"[\s_]+", "", str(title or "").lower())


def _wiki_rest_summary(term: str, host: str) -> dict[str, Any] | None:
    """Direct REST summary for an exact page title. Catches entities the action
 search misses (e.g. '' resolves to the ' ' page) and is the most
 rate-limit-friendly Wikipedia endpoint. Returns a result row or None."""
    term = (term or "").strip()
    if not term:
        return None
    slug = quote(term.replace(" ", "_"), safe="")
    summary = _wiki_get_json(f"https://{host}/api/rest_v1/page/summary/{slug}", timeout=3.0)
    if not isinstance(summary, dict) or not summary:
        return None
    if str(summary.get("type") or "") == "disambiguation":
        return None
    extract = _strip_html(str(summary.get("extract") or ""))
    if not extract:
        return None
    title = _strip_html(str(summary.get("title") or term))
    page_url = (summary.get("content_urls", {}) or {}).get("desktop", {}).get("page") or f"https://{host}/wiki/{slug}"
    return {
        "id": "wikipedia-direct",
        "title": title,
        "url": page_url,
        "snippet": extract,
        "provider": "wikipedia",
        "source_type": "encyclopedia_summary",
        "license_status": "reference_only",
        "search_score": 250,
        "query_terms_matched": 2,
        "normalized_query": term,
    }


def _wiktionary_definition(term: str, *, korean: bool) -> dict[str, Any] | None:
    """A free DICTIONARY source (different content type from the encyclopedia) for
 plain definitional 'X ' queries — real source diversity beyond Wikipedia
 while staying on a keyless, language-aware endpoint."""
    term = (term or "").strip()
    if not term:
        return None
    host = "ko.wiktionary.org" if korean else "en.wiktionary.org"
    slug = quote(term.replace(" ", "_"), safe="")
    body = _wiki_get_json(f"https://{host}/api/rest_v1/page/definition/{slug}", timeout=3.0)
    if not isinstance(body, dict) or not body:
        return None
    lang_key = "ko" if korean else "en"
    entries = body.get(lang_key) or next((v for v in body.values() if isinstance(v, list)), [])
    for entry in entries or []:
        for definition in entry.get("definitions", []) or []:
            text = _strip_html(str(definition.get("definition") or "")).strip()
            if len(text) >= 6:
                return {
                    "id": "wiktionary-1",
                    "title": term,
                    "url": f"https://{host}/wiki/{slug}",
                    "snippet": text,
                    "provider": "wiktionary",
                    "source_type": "dictionary_definition",
                    "license_status": "reference_only",
                    "search_score": 180,
                    "query_terms_matched": 1,
                    "normalized_query": term,
                }
    return None


_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


_EMOJI_RE = re.compile(
    "[" "\U0001f000-\U0001faff" "\U00002600-\U000027bf" "\U0001f1e6-\U0001f1ff" "←-⇿" "✀-➿" "]",
    flags=re.UNICODE,
)
_FLUFF_MARKERS = ("참고하십시오", "문서를 참고", "더보기", "바로가기", "구독", "좋아요", "본문 바로가기", "이 글은", "출처 :", "기자 =", "subscribers", "likes", "views", "구독자", "조회수", "앵커멘트", "subscribe")


def _ko_has_batchim(ch: str) -> bool:
    """True if a Hangul syllable carries a final consonant (). Pure morphology:
 the syllable block is 0xAC00..0xD7A3 and the index is (code-0xAC00) % 28."""
    o = ord(ch) if ch else 0
    return 0xAC00 <= o <= 0xD7A3 and (o - 0xAC00) % 28 != 0


def _is_ko_predicate_final(left: str) -> bool:
    """Does `left` end on a Korean declarative predicate (so a period-less join can be cut
 here)? A sentence-final - terminates a CONJUGATED predicate — the copula /, or a
 verb/adjective stem carrying a (·······). A Sino-Korean noun
 that merely ends in the syllable with a vowel-final stem (=最多) has no and is NOT
 a boundary, so ' ' stays one clause. Segmentation morphology, not a knowledge rule."""
    left = left.rstrip()
    if not left.endswith("다"):
        return False
    if left.endswith("이다") or left.endswith("아니다"):
        return True
    return _ko_has_batchim(left[-2]) if len(left) >= 2 else False


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    # Primary boundaries: sentence-final punctuation.
    parts: list[str] = []
    for part in re.split(r"(?<=[.!?。])\s+", text):
        # Secondary: search snippets sometimes drop the period between declarative sentences



        start = 0
        for m in re.finditer(r"다\s+(?=[가-힣A-Z])", part):
            cut = m.start() + 1
            if _is_ko_predicate_final(part[start:cut]):
                parts.append(part[start:cut])
                start = m.end()
        parts.append(part[start:])
    return [p.strip() for p in parts if p and p.strip()]


_KO_PREDICATE = re.compile(r"(다|요|음|함|됨|이며|이고|이다|입니다|한다|된다|했다|였다|이었|로 알려|에 위치|에 본사)[.\s)\"']*$|(이다|입니다|한다|된다|했다|였다|이며|로 알려)")


_COMMON_EN_WORDS = {
    "the", "is", "a", "of", "and", "to", "in", "was", "for", "on", "with", "as",
    "by", "at", "an", "it", "that", "are", "be", "from", "or", "this", "which",
    "has", "had", "its", "not", "were", "but", "have", "he", "she", "they",
}


def _sentence_reads_as_language(s: str) -> bool:
    if re.search(r"[가-힣぀-ヿ㐀-䶿一-鿿]", s):
        return True
    words = re.findall(r"[A-Za-z]+", s)
    if len(words) < 6:
        return True                      # too short to judge — don't block
    window = [w.lower() for w in words[:60]]
    hits = sum(1 for w in window if w in _COMMON_EN_WORDS)
    return hits >= max(1, len(window) // 12)


def looks_like_natural_language(text: str) -> bool:
    """Data-quality gate: does this text read as REAL language (Korean/CJK, or
 English with a plausible function-word ratio)? Pronounceable-nonsense pages
 (bot walls, lorem generators, garbled encodings) once flowed through the web
 path, got ANSWERED, then got MEMORIZED into web_fact_memory — poisoning every
 later recall of that topic. Judged per-SENTENCE by majority: a poisoned text
 can smuggle one Korean fragment (its own '(: …)' tail quoted the user's
 Korean query) while every body sentence is nonsense — whole-text checks pass
 it, a sentence majority does not. Gibberish has essentially zero common
 English function words; real English can't avoid them; Hangul/CJK passes."""
    t = (text or "").strip()
    if len(t) < 8:
        return True
    sents = [s.strip() for s in re.split(r"(?<=[.!?다])\s+", t) if len(s.strip()) >= 20]
    if not sents:
        return _sentence_reads_as_language(t)
    bad = sum(1 for s in sents if not _sentence_reads_as_language(s))
    return bad * 2 <= len(sents)


def _is_fluff_sentence(s: str) -> bool:
    if len(s) < 16 or len(s) > 320:
        return True
    if not looks_like_natural_language(s):   # gibberish never becomes evidence
        return True
    if any(m in s for m in _FLUFF_MARKERS):
        return True
    if s.count("|") >= 2 or s.count("·") >= 5 or s.count("/") >= 3:
        return True
    if _EMOJI_RE.search(s):
        return True
    if s.rstrip().endswith("?") or "뭘까요" in s or "무엇일까" in s:  # question-form, not an answer
        return True
    # Korean sentence with no predicate ending is a title/fragment (e.g. a namuwiki
    # family-tree run-on); require some verb/copula signal for Hangul-heavy sentences.
    if re.search(r"[가-힣]", s) and not _KO_PREDICATE.search(s):
        return True
    # Truncated fragments: an unbalanced quote/bracket means the sentence was cut


    for _o, _c in (("(", ")"), ("[", "]"), ("“", "”"), ("‘", "’"), ("《", "》"), ("「", "」"), ("«", "»")):
        if s.count(_o) != s.count(_c):
            return True
    if s.count('"') % 2 == 1:
        return True
    return False


def retrieval_budget(query: str) -> dict[str, Any]:
    """Proportional retrieval: scale search effort to the question's complexity
 instead of one fixed depth. A short entity/fact lookup reads a few results;
 an open question (///…) or a long multi-part query earns a
 wider sweep and a fuller composition. Structural signals only."""
    q = str(query or "")
    open_marker = bool(re.search(
        r"요약|설명해|비교|정리해|자세히|역사|과정|차이|추천|어떻게|왜\b|원리|장단점|영향|전망"
        r"|explain|compare|summar|history|why|how", q, re.IGNORECASE))
    content_tokens = len(re.findall(r"[가-힣A-Za-z0-9]{2,}", q))
    if open_marker or content_tokens >= 6:
        return {"top_k": 8, "max_supporting": 4, "deep": True}
    return {"top_k": 3, "max_supporting": 2, "deep": False}



# An unverified single-source web claim must NOT surface as a confident fact. This grades the
# composed lead by how many INDEPENDENT sources corroborate it, then the surface form is forced
# to match the tier: verified→assert, single-source→hedge, nothing→withhold. This is the k-source
# consensus machine finally on the LIVE web path (it existed in packages but idled here).
_AUTHORITATIVE_BASE_DOMAINS = frozenset({
    "wikipedia.org",
    "namu.wiki",
    "britannica.com",
    "terms.naver.com",
    "doopedia.co.kr",
    "stdict.korean.go.kr",
    "nih.gov",
    "who.int",
    "nature.com",
})
_AUTHORITATIVE_PUBLIC_SUFFIXES = (".gov", ".go.kr", ".edu", ".ac.kr")
_WEB_HEDGE_KO = "한 곳에서 확인한 내용이라 교차검증은 아직인데, 참고로 전해드리면 — "
_WEB_HEDGE_EN = "I could only confirm this from a single source (not cross-checked): "


def _row_url_host(row: dict[str, Any]) -> str:
    """Return the canonical HTTP(S) hostname carried by the result URL."""
    raw = str(row.get("url") or row.get("link") or row.get("source_url") or "").strip()
    if not raw:
        return ""
    try:
        parsed = urllib.parse.urlsplit(raw)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return ""
        return parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except (UnicodeError, ValueError):
        return ""


def _is_authoritative_host(host: str) -> bool:
    """Match only an exact trusted hostname or a DNS-label-bounded subdomain."""
    value = str(host or "").lower().rstrip(".")
    if not value:
        return False
    if value.endswith(_AUTHORITATIVE_PUBLIC_SUFFIXES):
        return True
    return any(
        value == base or value.endswith("." + base)
        for base in _AUTHORITATIVE_BASE_DOMAINS
    )


def _row_domain(row: dict[str, Any]) -> str:
    """Return only URL-bound provenance eligible for independence counting."""
    return _row_url_host(row)


def _claim_shingles(s: str) -> set[str]:
    t = re.sub(r"[^가-힣a-z0-9]", "", s.lower())
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else {t}


def grade_web_evidence(entity: str, lead: str, rows: list[dict[str, Any]],
                       key_terms: list[str]) -> dict[str, Any]:
    """Tier a composed web lead by INDEPENDENT-source corroboration.
      verified       — an authoritative source, or >=2 distinct domains, carry the same claim
      single_source  — only one domain does (the lead's own) -> the surface must hedge
      withhold       — nothing corroborates the claim -> do not voice it as fact
    Independence = distinct domain; a claim 'corroborates' if the source mentions the entity's
    key terms AND its snippet shares >=30% of the lead's character-bigrams (same fact, not just
    same page)."""
    lead_sh = _claim_shingles(lead)
    kt = [t.lower() for t in (key_terms or []) if len(t) >= 2]
    corroborating: dict[str, float] = {}
    authoritative = False
    has_unbound_source = False
    for row in rows or []:
        snippet = str(row.get("snippet") or "")
        low = snippet.lower()
        if kt and not any(t in low for t in kt):
            continue
        overlap = len(lead_sh & _claim_shingles(snippet)) / max(1, len(lead_sh))
        if overlap < 0.30:
            continue
        dom = _row_domain(row)
        if not dom:
            # URL-less evidence may remain visible as a tainted single-source
            # hedge, but caller metadata cannot manufacture a corroborating
            # domain or combine with a real URL to reach the two-source gate.
            has_unbound_source = True
            continue
        corroborating[dom] = max(corroborating.get(dom, 0.0), overlap)
        if _is_authoritative_host(dom):
            authoritative = True
    n = len(corroborating)
    if (authoritative and n >= 1) or n >= 2:
        tier, conf = "verified", (0.82 if authoritative else 0.72)
    elif n == 1 or has_unbound_source:
        tier, conf = "single_source", 0.5
    else:
        tier, conf = "withhold", 0.0
    return {"tier": tier, "n_sources": n, "domains": list(corroborating)[:4],
            "authoritative": authoritative, "confidence": conf}


def compose_web_answer(query: str, rows: list[dict[str, Any]], *, language: str = "ko", max_supporting: int = 4, allow_partial: bool = False) -> dict[str, Any] | None:
    """Turn retrieved results into an ORGANIZED answer instead of pasting a raw snippet:
    split the top results into clean sentences, then EXTRACTIVELY select + arrange a
    definitional lead about the queried entity plus a couple of non-redundant supporting
    facts. No LLM generation, no rule table — selection is by referent resonance + the
    query's own key terms. Returns {answer, lead, sources} or None."""
    try:
        from packages.cgsr.cgsr.referent_resonance import (
            answer_is_about_entity,
            infer_evidence_type,
            query_expected_type,
            query_subject_entity,
            resonance,
        )
        entity = query_subject_entity(query)
        expected = query_expected_type(query)
    except Exception:  # pragma: no cover
        return None
    key_terms = [t for t in _lookup_terms(_normalize_lookup_query(query)) if len(t) >= 2]

    # 1) gather clean candidate sentences from the top results
    cands: list[tuple[str, dict[str, Any]]] = []
    seen_norm: set[str] = set()
    for row in rows[:8]:
        for sentence in _split_sentences(_clean_web_snippet(str(row.get("snippet") or ""))):
            if _is_fluff_sentence(sentence):
                continue
            norm = re.sub(r"\s+", "", sentence)[:60]
            if norm in seen_norm:
                continue
            seen_norm.add(norm)
            cands.append((sentence, row))
    if not cands:
        return None

    def about(s: str) -> bool:
        return answer_is_about_entity(entity, s) if len(entity) >= 2 else True

    def term_hits(s: str) -> int:
        low = s.lower()
        return sum(1 for t in key_terms if t.lower() in low)

    def is_def(s: str) -> bool:
        return bool(re.search(r"(은|는|이|가)\s.{4,}?(이다|입니다|이며|로 알려|를 말한다|를 뜻한다|에 위치|에 본사)", s) or re.search(r"\bis (a|an|the)\b", s.lower()))

    # The candidates are already in referent-ranked order (the rows/facts were ranked
    # upstream). RESPECT that order — do NOT globally re-rank, or a low-ranked junk
    # sentence (a fly, a family-tree line) can win. The LEAD is the first sentence that
    # is genuinely ABOUT the entity (defines it); fall back to the first definitional,
    # then the first candidate.
    # Coverage guard: the lead MUST contain the query's own key content terms. Without this,
    # when the search returns only off-topic pages (no candidate is about the entity), the
    # is_def fallback pastes any definitional sentence — e.g. "What is a black hole?" grabs



    def covers(s: str) -> bool:
        if not key_terms:
            return True
        low = s.lower()
        present = [t for t in key_terms if t.lower() in low]
        # STRICT (default, entity lookups): every key term must be present — "Black is a
        # color" is rejected for "black hole" (missing 'hole'). RELAXED (orchestrated open
        # questions, 3+ terms): a natural question spreads its terms across sentences, so
        # require the topic head (longest term) + a MAJORITY — enough to stay on-referent
        # without demanding one sentence carry the whole question.
        if allow_partial and len(key_terms) >= 3:
            head = max(key_terms, key=len).lower()
            return head in low and len(present) >= (len(key_terms) + 1) // 2
        return len(present) == len(key_terms)

    is_who_query = bool(re.search(r"누구|누가|\bwho\b", query.lower()))

    def subject_lead(s: str) -> bool:
        # The lead must be TOPIC'd on the query's entity — the subject phrase before the first

        # question, so a Korean noun compound resolves correctly:


        #    thing) is rejected.



        # Anchor the lead on the ENTITY (South Korea), NOT the longest query term — which for a
        # "PROPERTY of ENTITY" question is the PROPERTY ("capital"), letting the property's own page
        # ("Capital punishment is a legal penalty in South Korea") win the lead. English-core.
        _ent_terms = [t for t in _lookup_terms(entity) if len(t) >= 2] if entity else []
        head = ((max(_ent_terms, key=len) if _ent_terms else (max(key_terms, key=len) if key_terms else ""))).lower()
        if not head:
            return True
        match = re.match(r"^(.{1,40}?)(은|는|이|가|께서)\s", s)
        topic = re.sub(r"\([^)]*\)", "", (match.group(1) if match else s[:24])).strip().lower()
        topic = re.sub(r"^(a|an|the)\s+", "", topic).strip()
        if not topic:
            return False
        if is_who_query:
            return topic.split()[-1].startswith(head)
        return topic.startswith(head)

    # Lead selection leans on covers()+subject_lead()+is_def() rather than about(): about()

    # so it fires inconsistently. covers (every key term present) + subject_lead (entity is the
    # sentence's topic) + is_def (definitional) is a cleaner, stronger anchor for the lead.
    # English "PROPERTY of ENTITY → value" lead (e.g. "capital of South Korea"): the answer's SUBJECT
    # is the VALUE ("Seoul"), not the entity, so subject_lead (which anchors on the entity) can never
    # find it and the polysemy distractor "Capital punishment is a legal penalty in South Korea" wins
    # covers() instead. Prefer a candidate that states the RELATION — "<property> of … is <value>" or
    # "<value> is (the) <property> …" — which structurally excludes "capital punishment" (no 'capital
    # of' / 'is the capital'). Gated to the English property pattern, so 'what is ENTITY' is untouched.
    _prop_m = re.match(r"^\s*(?:what|which)\s+(?:is|are|was|were)\s+(?:the\s+)?([a-z][a-z ]{2,24}?)\s+of\s",
                       query, re.IGNORECASE)
    lead_idx = None
    if _prop_m:
        _prop = _prop_m.group(1).strip().lower()
        _rel = re.compile(rf"\b{re.escape(_prop)}\s+of\b|\bis\s+(?:the\s+)?{re.escape(_prop)}\b", re.IGNORECASE)
        lead_idx = next((i for i, (s, _) in enumerate(cands) if _rel.search(s) and covers(s)), None)
        if lead_idx is None:      # atanor's "capital of Korea is Seoul" lacks 'south' → relax covers
            lead_idx = next((i for i, (s, _) in enumerate(cands) if _rel.search(s)), None)
    if lead_idx is None:
        lead_idx = next((i for i, (s, _) in enumerate(cands) if covers(s) and subject_lead(s) and is_def(s)), None)
    if lead_idx is None:
        lead_idx = next((i for i, (s, _) in enumerate(cands) if covers(s) and subject_lead(s)), None)
    if lead_idx is None:
        lead_idx = next((i for i, (s, _) in enumerate(cands) if covers(s) and is_def(s)), None)
    if lead_idx is None:
        lead_idx = next((i for i, (s, _) in enumerate(cands) if covers(s)), None)
    if lead_idx is None:
        # nothing covers the query's key terms -> abstain rather than paste an off-topic fact
        return None
    lead_sentence, lead_row = cands[lead_idx]

    def _shingles(s: str) -> set[str]:
        # Character bigrams (spaces/punct stripped): robust to Korean agglutination —

        # DIFFERENT tokens, so paraphrases of the same fact are recognized as redundant
        # where token-overlap was fooled and let three near-identical definitions through.
        t = re.sub(r"[^가-힣a-z0-9]", "", s.lower())
        return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else {t}

    lead_tokens = _shingles(lead_sentence)

    # 2) supporting facts: in order, about the entity, share terms, NOT redundant.
    supporting: list[tuple[str, dict[str, Any]]] = []
    # Non-redundancy is checked against EVERYTHING already chosen (the lead AND every
    # supporting sentence picked so far) — not just the lead. Two paraphrases of the same

    # lead to pass a lead-only check, then both land and the answer repeats itself. Pairwise
    # against all chosen sentences drops the second copy.
    chosen_token_sets: list[set[str]] = [lead_tokens]
    for index, (sentence, row) in enumerate(cands):
        if index == lead_idx:
            continue
        toks = _shingles(sentence)
        # A supporting fact is kept if it is a CONTINUATION from the lead's own source paragraph
        # (row is lead_row — follow-on sentences elaborate the subject via pronoun/ellipsis,

        # cross-source fact that both COVERS the query terms AND is HEAD-topic'd on the entity



        if not ((row is lead_row) or (covers(sentence) and subject_lead(sentence))):
            continue
        # Char-bigram overlap (Korean-robust): a paraphrase of the same definition shares
        # most of its bigrams with one already chosen, so it is dropped and a genuinely
        # new fact is picked instead. 0.55 on bigrams ≈ "says mostly the same thing".
        if any(len(toks & chosen) / max(1, len(toks)) > 0.55 for chosen in chosen_token_sets):
            continue  # too similar to the lead or an already-selected supporting fact
        supporting.append((sentence, row))
        chosen_token_sets.append(toks)
        if len(supporting) >= max_supporting:
            break

    body = lead_sentence
    if supporting:
        body += " " + " ".join(s for s, _ in supporting)




    # every fact stays VERBATIM (bones), only the connective discourse is generated
    # (flesh), so the answer READS composed while staying hallucination-safe. A simple

    open_q = bool(re.search(
        r"왜\b|어떻게|어째서|차이|비교|장단점|방법|추천|무엇을|어떤|영향|이유|과정|원리"
        r"|왜냐|괜찮|얼마나|몇\s|어디|언제|해야|할까|될까|좋을까|알려줘"
        r"|why|how|compare|difference|should|recommend", str(query), re.IGNORECASE))
    woven = None
    if open_q and supporting:  # need ≥2 grounded facts for flesh to have bones
        try:
            from packages.base_brain.grounded_generation import synthesize
            facts = [{"name": None, "description": s} for s in
                     [lead_sentence, *[s for s, _ in supporting]]]
            syn = synthesize(query, facts, language, min_facts=2, max_facts=5)
            if syn and str(syn.get("answer") or "").strip():
                woven = str(syn["answer"]).strip()
        except Exception:
            woven = None
    if woven:
        body = woven

    sources = []
    for _, row in [(lead_sentence, lead_row), *supporting]:
        title = str(row.get("title") or "")
        if title and title not in sources:
            sources.append(title)

    # Follow-up topics: prefer clean related-page TITLES over token extraction — Korean word

    # not topics. Page titles are already clean named entities. Drop titles that contain a query

    # a Tesla-the-company answer), keep genuinely-related different-titled pages. Empty when the
    # evidence carries no titles (a fact-bound path) — better none than particle-garbage chips.
    kt_low = {t.lower() for t in key_terms}
    follow_ups: list[str] = []
    for row in rows[:8]:
        title = _clean_web_title(str(row.get("title") or "")).strip()
        if len(title) < 3 or title in follow_ups:
            continue
        if any(t in title.lower() for t in kt_low):
            continue
        follow_ups.append(title)
        if len(follow_ups) >= 5:
            break
    # ── TRUTH GATE: force the surface form to match the evidence tier ──────────────────────
    _verify = grade_web_evidence(entity, lead_sentence, rows, key_terms)
    _body = body.strip()
    if _verify["tier"] == "withhold":
        # nothing independently corroborates the claim — silence beats an unverified assertion
        return None
    if _verify["tier"] == "single_source":
        _body = (_WEB_HEDGE_KO if language == "ko" else _WEB_HEDGE_EN) + _body
    return {"answer": _body, "lead": lead_sentence, "sources": sources[:3],
            "follow_ups": follow_ups, "verification": _verify,
            "answer_kind": ("web_single_source_hedged" if _verify["tier"] == "single_source"
                            else "grounded_synthesis" if woven else "extractive")}


# Korean particles are BOUND morphemes — they attach to the preceding word with no

# space-separated particle to the preceding Hangul word is morphology (LAD), not a
# knowledge rule. The particle must be delimited on the right (space/punct/end) so a

_KO_PARTICLES = sorted(
    [
        "으로부터", "이라는", "이라고", "에서는", "에게서", "으로서", "으로써", "이라도", "조차도",
        "에서", "에게", "한테", "께서", "으로", "이랑", "라는", "라고", "처럼", "보다", "만큼",
        "까지", "부터", "마다", "조차", "마저", "밖에", "이나", "이란", "라도",
        "은", "는", "이", "가", "을", "를", "와", "과", "에", "의", "로", "도", "만", "랑", "란",
    ],
    key=len,
    reverse=True,
)
_KO_PARTICLE_RX = re.compile(
    r"([가-힣])\s+(" + "|".join(_KO_PARTICLES) + r")(?=[\s.,;:!?)\]}\"'」』·]|$)"
)


def _reattach_korean_particles(text: str) -> str:
    prev = None
    s = str(text or "")
    while prev != s:
        prev = s
        s = _KO_PARTICLE_RX.sub(r"\1\2", s)
    return s


def _clean_web_snippet(text: str) -> str:
    """Strip the cruft a real search API returns (markdown tables/headers from Namuwiki
 infoboxes, '[·]' toggles, source-name title suffixes) so the answer is clean
 prose, not '# | [·] | --- | **** …'."""
    s = _strip_html(str(text or ""))
    s = re.sub(r"\[[^\]]*?(?:펼치기|접기|편집|edit)[^\]]*?\]", " ", s)
    s = re.sub(r"\[\d+\]", "", s)                        # wiki citation markers [3][4] → drop
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)  # markdown links/images → label
    s = re.sub(r"[#*`>]+", " ", s)                      # headers / bold / code / quotes
    s = re.sub(r"\s*\|\s*", " ", s)                     # table pipes
    s = re.sub(r"-{2,}", " ", s)                        # table rules ---
    s = re.sub(r"\s+", " ", s).strip()
    s = _reattach_korean_particles(s)
    return s


def _clean_web_title(title: str) -> str:
    """Drop the trailing site name a search result title carries (' - ',
 '… : ', '… | 24')."""
    t = _strip_html(str(title or ""))
    t = re.sub(r"\s*[-:|]\s*(나무위키|위키백과|네이버\s*블로그|티스토리|예스24|YouTube|유튜브|브런치|다음|Daum|Wikipedia)\b.*$", "", t, flags=re.IGNORECASE)
    return t.strip()


_SEARXNG_URL = os.getenv("SEARXNG_URL", "http://127.0.0.1:8888").rstrip("/")
_SEARXNG_OK: dict[str, Any] = {"checked": 0.0, "up": False}


def _searxng_reachable() -> bool:
    """Cache a reachability probe — a self-hosted SearXNG is unlimited but may be down."""
    now = time.monotonic()
    if now - float(_SEARXNG_OK["checked"]) < 60.0:
        return bool(_SEARXNG_OK["up"])
    up = False
    try:
        req = urllib.request.Request(_SEARXNG_URL + "/healthz", headers={"User-Agent": WEB_USER_AGENT})
        with urllib.request.urlopen(req, timeout=2) as resp:  # nosec B310 - local instance
            up = resp.status == 200
    except Exception:
        up = False
    _SEARXNG_OK.update({"checked": now, "up": up})
    return up


def searxng_search(query: str, count: int = 6) -> list[dict[str, Any]]:
    """Query a self-hosted SearXNG metasearch instance (unlimited, keyless, diverse —
    aggregates Google/Bing/DuckDuckGo/Namuwiki/blogs/news). The agreed primary web
    source. Returns title/url/snippet rows; empty when the instance is down."""
    query = (query or "").strip()
    if not query:
        return []
    # general+news: the whole-web mandate includes newspapers/outlets — news-category
    # engines (naver news, bing news, reuters…) join every query, not just !bangs
    url = _SEARXNG_URL + "/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "language": "ko", "categories": "general,news"})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": WEB_USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:  # nosec B310 - local instance
            payload = json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception:  # pragma: no cover - network/optional
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("results", []) or [], start=1):
        snippet = _clean_web_snippet(str(item.get("content") or ""))
        if not snippet:
            continue
        url_ = str(item.get("url") or "")
        domain = re.sub(r"^https?://(www\.)?", "", url_).split("/")[0]
        rows.append(
            {
                "id": f"searxng-{index}",
                "title": _clean_web_title(str(item.get("title") or "")),
                "url": url_,
                "snippet": snippet,
                "provider": f"searxng:{domain}",
                "source_type": "metasearch",
                "license_status": "reference_only",
                "search_score": max(1, count - index + 1),
                "normalized_query": query,
            }
        )
        if len(rows) >= max(1, min(count, 12)):
            break
    return rows


def brave_search(query: str, count: int = 6) -> list[dict[str, Any]]:
    """Real multi-source web search via the Brave Search API (a full web index, the way
    ChatGPT/Perplexity retrieve). Keyed by BRAVE_SEARCH_API_KEY (free tier ~2000/mo).
    Returns title/url/snippet rows; the referent-resonance gate downstream picks the
    best. Empty list when unconfigured or on error (caller falls back to Wikipedia)."""
    key = os.getenv("BRAVE_SEARCH_API_KEY")
    query = (query or "").strip()
    if not key or not query:
        return []
    url = (
        "https://api.search.brave.com/res/v1/web/search?"
        f"q={quote_plus(query)}&count={max(1, min(count, 10))}&search_lang=ko&country=KR"
    )
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "X-Subscription-Token": key, "User-Agent": WEB_USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:  # nosec B310 - configured API
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # pragma: no cover - network/optional
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate((payload.get("web", {}) or {}).get("results", []) or [], start=1):
        snippet = _clean_web_snippet(str(item.get("description") or ""))
        if not snippet:
            continue
        url_ = str(item.get("url") or "")
        domain = re.sub(r"^https?://(www\.)?", "", url_).split("/")[0]
        rows.append(
            {
                "id": f"brave-{index}",
                "title": _clean_web_title(str(item.get("title") or "")),
                "url": url_,
                "snippet": snippet,
                "provider": f"brave:{domain}",
                "source_type": "web_search_api",
                "license_status": "reference_only",
                "search_score": (count - index + 1),
                "normalized_query": query,
            }
        )
    return rows


def tavily_search(query: str, count: int = 6) -> list[dict[str, Any]]:
    """Real web search via the Tavily API (LLM-optimized: returns clean page content).
    Keyed by TAVILY_API_KEY (free tier). Empty when unconfigured/on error."""
    key = os.getenv("TAVILY_API_KEY")
    query = (query or "").strip()
    if not key or not query:
        return []
    body = json.dumps(
        {"api_key": key, "query": query, "max_results": max(1, min(count, 10)), "search_depth": "basic"}
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.tavily.com/search", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:  # nosec B310 - configured API
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # pragma: no cover - network/optional
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("results", []) or [], start=1):
        snippet = _clean_web_snippet(str(item.get("content") or ""))
        if not snippet:
            continue
        url_ = str(item.get("url") or "")
        domain = re.sub(r"^https?://(www\.)?", "", url_).split("/")[0]
        rows.append(
            {
                "id": f"tavily-{index}",
                "title": _clean_web_title(str(item.get("title") or "")),
                "url": url_,
                "snippet": snippet,
                "provider": f"tavily:{domain}",
                "source_type": "web_search_api",
                "license_status": "reference_only",
                "search_score": (count - index + 1),
                "normalized_query": query,
            }
        )
    return rows


_WEB_WALL_BUDGET_S = 11.0   # per-answer web ceiling — an answer's chained retrieval calls must
#                            not run it to 30-60s (that timed out the caller = a false miss).



# Free tier = 1000 credits/month. We keep a local per-month spend counter so the code can refuse
# to burn the allowance on routine searches: search stays a thin-coverage fallback, and a RESERVE
# is kept for firecrawl_scrape (deep research / Ring-1 harvest), which is where Firecrawl is
# uniquely valuable. Ledger is process-local + on disk (data/ops/firecrawl_budget.json), so it
# survives engine restarts; it counts API CALLS (conservative lower bound on credits).
_FIRECRAWL_MONTHLY_CAP = int(os.environ.get("FIRECRAWL_MONTHLY_CAP", "900"))   # keep 100 safety
_FIRECRAWL_SCRAPE_RESERVE = int(os.environ.get("FIRECRAWL_SCRAPE_RESERVE", "400"))
_FIRECRAWL_LEDGER = Path(__file__).resolve().parents[4] / "data" / "ops" / "firecrawl_budget.json"
_FIRECRAWL_STATE: dict[str, Any] = {"month": None, "used": 0, "loaded": False}
_FIRECRAWL_LOCK = threading.RLock()   # reentrant: budget_status holds it while calling budget_ok


def _firecrawl_month() -> str:
    import time as _t
    return _t.strftime("%Y-%m")


def _firecrawl_load() -> None:
    if _FIRECRAWL_STATE["loaded"]:
        return
    _FIRECRAWL_STATE["loaded"] = True
    try:
        row = json.loads(_FIRECRAWL_LEDGER.read_text(encoding="utf-8"))
        if row.get("month") == _firecrawl_month():
            _FIRECRAWL_STATE["month"] = row["month"]
            _FIRECRAWL_STATE["used"] = int(row.get("used") or 0)
    except Exception:
        pass
    if _FIRECRAWL_STATE["month"] != _firecrawl_month():
        _FIRECRAWL_STATE["month"] = _firecrawl_month()
        _FIRECRAWL_STATE["used"] = 0


def _firecrawl_spend(n: int = 1) -> None:
    with _FIRECRAWL_LOCK:
        _firecrawl_load()
        if _FIRECRAWL_STATE["month"] != _firecrawl_month():    # month rollover
            _FIRECRAWL_STATE["month"] = _firecrawl_month()
            _FIRECRAWL_STATE["used"] = 0
        _FIRECRAWL_STATE["used"] += n
        try:
            _FIRECRAWL_LEDGER.parent.mkdir(parents=True, exist_ok=True)
            _FIRECRAWL_LEDGER.write_text(json.dumps(
                {"month": _FIRECRAWL_STATE["month"], "used": _FIRECRAWL_STATE["used"],
                 "cap": _FIRECRAWL_MONTHLY_CAP}), encoding="utf-8")
        except Exception:
            pass


def _firecrawl_budget_ok(*, for_scrape: bool = False) -> bool:
    """SEARCH may spend only the share above the scrape reserve; SCRAPE may spend up to the cap."""
    with _FIRECRAWL_LOCK:
        _firecrawl_load()
        if _FIRECRAWL_STATE["month"] != _firecrawl_month():
            return True
        used = int(_FIRECRAWL_STATE["used"])
    limit = _FIRECRAWL_MONTHLY_CAP if for_scrape else (_FIRECRAWL_MONTHLY_CAP - _FIRECRAWL_SCRAPE_RESERVE)
    return used < limit


def firecrawl_budget_status() -> dict[str, Any]:
    """Ops surface: how much of the monthly Firecrawl allowance is spent."""
    with _FIRECRAWL_LOCK:
        _firecrawl_load()
        return {"month": _FIRECRAWL_STATE["month"], "used": int(_FIRECRAWL_STATE["used"]),
                "cap": _FIRECRAWL_MONTHLY_CAP, "scrape_reserve": _FIRECRAWL_SCRAPE_RESERVE,
                "search_allowed": _firecrawl_budget_ok(), "scrape_allowed": _firecrawl_budget_ok(for_scrape=True)}


def firecrawl_search(query: str, count: int = 6) -> list[dict[str, Any]]:
    """Web search via Firecrawl /v2/search (owner-provisioned key 2026-07-16). Returns the same
    row shape as the other providers. Empty when unconfigured/on error."""
    key = os.getenv("FIRECRAWL_API_KEY")
    query = (query or "").strip()
    if not key or not query:
        return []
    if not _firecrawl_budget_ok():          # search share of the monthly allowance is exhausted
        return []
    body = json.dumps({"query": query, "limit": max(1, min(count, 10))}).encode("utf-8")
    request = urllib.request.Request(
        "https://api.firecrawl.dev/v2/search", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        _firecrawl_spend(1)                 # count the call even on failure (the API may bill it)
        with urllib.request.urlopen(request, timeout=12) as response:  # nosec B310 - configured API
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # pragma: no cover - network/optional
        return []
    data = payload.get("data") or {}
    web = data.get("web") if isinstance(data, dict) else data
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(web or [], start=1):
        snippet = _clean_web_snippet(str(item.get("description") or item.get("markdown") or ""))
        url = str(item.get("url") or "")
        if not snippet or not url:
            continue
        domain = _row_domain({"url": url})
        rows.append({"id": f"firecrawl-{index}", "title": str(item.get("title") or "")[:160],
                     "snippet": snippet[:800], "url": url, "provider": f"firecrawl:{domain}"})
    return rows


def firecrawl_scrape(url: str, timeout: float = 20.0) -> str:
    """Deep-read one page via Firecrawl /v2/scrape → clean markdown text ('' on any failure).
    The deep-research lever: snippets say THAT a page answers; scrape reads WHAT it says.
    Also the ATANOR Index Ring-1 harvest primitive."""
    key = os.getenv("FIRECRAWL_API_KEY")
    if not key or not str(url or "").startswith("http"):
        return ""
    if not _firecrawl_budget_ok(for_scrape=True):   # scrape may draw on the reserve, up to the cap
        return ""
    body = json.dumps({"url": url, "formats": ["markdown"]}).encode("utf-8")
    request = urllib.request.Request(
        "https://api.firecrawl.dev/v2/scrape", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        _firecrawl_spend(1)
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
        return str((payload.get("data") or {}).get("markdown") or "")[:40000]
    except Exception:  # pragma: no cover - network/optional
        return ""


def provider_api_search(query: str, count: int = 6) -> list[dict[str, Any]]:
    """Real multi-source web search. PRIMARY = self-hosted SearXNG (unlimited, keyless,
    diverse metasearch) — the agreed source; then Tavily/Brave if a key is set.
    PER-ANSWER WALL BUDGET: once this answer has already spent _WEB_WALL_BUDGET_S in flight,
    skip further web and return [] — the 'uniform 100%' guard so no single answer stalls into a
    caller timeout (the 6 __err__ battery misses were the engine hanging past the 60s harness)."""
    try:
        from packages.graph_scale.load_signal import request_elapsed
        if request_elapsed() > _WEB_WALL_BUDGET_S:
            return []
    except Exception:
        pass

    # PARALLEL and merge (URL-deduped) — SearXNG (multi-engine roster) + keyed Tavily/Firecrawl/
    # Brave. Parallel matters: serial fan-out cost ~7-9s and blew the rescue budget (measured:
    # Seoul regressed to the weak local answer via a MISS-cached timeout). Wall ≈ slowest provider.
    tasks: list[tuple[str, Any]] = []

    # Stable-order merge below keeps its hits ahead of external providers on ties; external still runs
    # so freshness/coverage never regress while the self-index is small (V0). ATANOR_DISABLE_LOCAL_INDEX=1.
    if os.environ.get("ATANOR_DISABLE_LOCAL_INDEX") != "1":
        try:
            from packages.atanor_index.retriever import local_search as _atanor_local
            tasks.append(("atanor_index", lambda: _atanor_local(query, count)))
        except Exception:
            pass
    if _searxng_reachable():
        tasks.append(("searxng", lambda: searxng_search(query, count)))
    if os.getenv("TAVILY_API_KEY"):
        tasks.append(("tavily", lambda: tavily_search(query, count)))
    if os.getenv("BRAVE_SEARCH_API_KEY"):   # Brave free tier discontinued — slot kept for later
        tasks.append(("brave", lambda: brave_search(query, count)))

    # credits/month). It joins as a SECOND WAVE below only when the free providers came back thin,
    # so credits are spent exactly where they add coverage — and firecrawl_scrape (deep research /
    # Ring 1 harvest) keeps a reserved share of the monthly budget.
    if not tasks and not (os.getenv("FIRECRAWL_API_KEY") and _firecrawl_budget_ok()):
        return []
    results: dict[str, list[dict[str, Any]]] = {}

    def _run(task_list: list[tuple[str, Any]]) -> None:
        if not task_list:
            return
        if len(task_list) == 1:
            name, fn = task_list[0]
            try:
                results[name] = fn() or []
            except Exception:
                results[name] = []
            return
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=len(task_list)) as ex:
            futs = {ex.submit(fn): name for name, fn in task_list}
            for fut in _cf.as_completed(futs, timeout=14):
                try:
                    results[futs[fut]] = fut.result() or []
                except Exception:
                    results[futs[fut]] = []

    _run(tasks)
    # Web coverage after the free wave (the self-index is offline evidence, not web coverage).
    web_rows = sum(len(v) for k, v in results.items() if k != "atanor_index")
    if web_rows < 3 and os.getenv("FIRECRAWL_API_KEY") and _firecrawl_budget_ok():
        tasks.append(("firecrawl", None))
        _run([("firecrawl", lambda: firecrawl_search(query, count))])

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name, _fn in tasks:                                # stable provider order for determinism
        for row in results.get(name, []):
            key = str(row.get("url") or row.get("title") or "")[:200]
            if key and key not in seen:
                seen.add(key)
                merged.append(row)
    return merged


def has_search_api() -> bool:
    return bool(_searxng_reachable() or os.getenv("TAVILY_API_KEY") or os.getenv("BRAVE_SEARCH_API_KEY"))

# DuckDuckGo Lite rate-limits aggressive use, so cache results and back off after a
# block. The chat path is low-volume; sustained crawler-scale collection needs a real
# search API key (Brave/Serper) — env WEB_SEARCH_PROVIDER + key — not this endpoint.
_GENWEB_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_GENWEB_CACHE_TTL = 1800.0  # 30 min
_GENWEB_BACKOFF_UNTIL = 0.0


def general_web_search(query: str, count: int = 6) -> list[dict[str, Any]]:
    """Roam the OPEN web (not just Wikipedia) via DuckDuckGo Lite — a keyless, no-JS
    endpoint that returns diverse Korean+global sources (Naver blogs, Tistory, Namuwiki,
    news, Wikipedia). Returns title/url/snippet rows; the caller selects the best one by
    referent resonance + relevance, so a messy source is filtered out on our end."""
    global _GENWEB_BACKOFF_UNTIL
    query = (query or "").strip()
    if not query:
        return []
    now = time.monotonic()
    cached = _GENWEB_CACHE.get(query)
    if cached and now - cached[0] < _GENWEB_CACHE_TTL:
        return cached[1]
    if now < _GENWEB_BACKOFF_UNTIL:
        return []  # recently blocked → don't hammer; the caller falls back to Wikipedia
    try:
        body = urllib.parse.urlencode({"q": query}).encode("utf-8")
        request = urllib.request.Request(
            "https://lite.duckduckgo.com/lite/",
            data=body,
            headers={"User-Agent": _BROWSER_UA, "Accept-Language": "ko,en;q=0.8"},
        )
        with urllib.request.urlopen(request, timeout=6) as response:  # nosec B310 - public lite search
            html = response.read().decode("utf-8", "ignore")
    except Exception:  # pragma: no cover - network/optional
        _GENWEB_BACKOFF_UNTIL = now + 120.0
        return []
    links = re.findall(r"href=\"(https?://[^\"]+)\"\s+class='result-link'>(.*?)</a>", html, re.S)
    if not links:
        _GENWEB_BACKOFF_UNTIL = now + 120.0  # blocked / unexpected page → back off
    snippets = re.findall(r"class='result-snippet'>(.*?)</td>", html, re.S)
    rows: list[dict[str, Any]] = []
    for index, (url, title_html) in enumerate(links[: max(1, min(count, 10))]):
        if "duckduckgo.com" in url:
            continue
        title = _strip_html(title_html)
        snippet = _strip_html(snippets[index]) if index < len(snippets) else ""
        if not snippet:
            continue
        domain = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        rows.append(
            {
                "id": f"web-{index + 1}",
                "title": title,
                "url": url,
                "snippet": snippet,
                "provider": f"web:{domain}",
                "source_type": "open_web_search",
                "license_status": "reference_only",
                "search_score": (count - index),
                "normalized_query": query,
            }
        )
    if rows:
        _GENWEB_CACHE[query] = (now, rows)
    return rows


_TRUSTED_DOMAINS = ("wikipedia.org", "namu.wiki", "namuwiki", "terms.naver.com", "doopedia", "britannica", "dbpedia")


def _rank_web_rows(query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pick the best answer from a set of web rows by referent resonance + relevance,
    so 'our side filters the best out' no matter how noisy the sources are: the answer
    must be ABOUT the queried entity, share its terms, and prefer trusted/definitional
    sources. This is the quality filter that the raw DuckDuckGo merge lacked."""
    try:
        from packages.cgsr.cgsr.referent_resonance import query_subject_entity, answer_is_about_entity
        entity = query_subject_entity(query)
    except Exception:  # pragma: no cover
        entity, answer_is_about_entity = "", None  # type: ignore


    lookup_terms = (_lookup_terms(entity) if len(entity) >= 2 else []) or _lookup_terms(_normalize_lookup_query(query))
    try:
        from packages.cgsr.cgsr.referent_resonance import infer_evidence_type
    except Exception:  # pragma: no cover
        infer_evidence_type = None  # type: ignore

    def score(row: dict[str, Any]) -> tuple:
        snippet = str(row.get("snippet", ""))
        text = f"{row.get('title','')} {snippet}".lower()
        about = 1
        if answer_is_about_entity is not None and len(entity) >= 2:
            about = 1 if answer_is_about_entity(entity, snippet) else 0


        title_norm = _norm_title(str(row.get("title") or ""))
        exact = 1 if title_norm == _norm_title(entity) else 0
        term_hits = sum(1 for t in lookup_terms if t and t.lower() in text)
        url = str(row.get("url", "")).lower()
        trust = 1 if any(d in url for d in _TRUSTED_DOMAINS) else 0
        looks_def = 1 if re.search(r"(이다|입니다|란\s|라고도|를 말한다|를 뜻한다|를 의미|is a|are )", snippet) else 0
        length_ok = 1 if 40 <= len(snippet) <= 600 else 0
        return (about, exact, term_hits, trust, looks_def, length_ok)

    return sorted(rows, key=score, reverse=True)


def _merge_web_candidates(query: str, count: int) -> list[dict[str, Any]]:
    """Best-of across sources: gather DIVERSE open-web rows (DDG → Naver/Tistory/Namu/
 news/Wikipedia) AND the precise Wikipedia entity page, then SELECT the best by
 on-topic terms, definition shape, source trust, and entity-anchoring — so a messy
 or off-topic source (the song '' for ' ', a random movie list) is
 filtered out on our end. Searches the SUBJECT ENTITY (''), not the raw question,
 so an exact title-collision ('' the song) doesn't win. Falls back to
 Wikipedia-only when the open web is rate-limited."""
    try:
        from packages.cgsr.cgsr.referent_resonance import query_subject_entity, answer_is_about_entity
        entity = query_subject_entity(query) or query
    except Exception:  # pragma: no cover
        entity = query
        answer_is_about_entity = None  # type: ignore
    search_term = entity if 2 <= len(entity) <= 20 else query
    general = general_web_search(search_term, count + 2)
    wiki = wikipedia_search(query, count)  # keeps entity resolution / direct summary
    lookup_terms = _lookup_terms(_normalize_lookup_query(query)) or _lookup_terms(entity)

    def score(row: dict[str, Any]) -> tuple:
        snippet = str(row.get("snippet", ""))
        text = f"{row.get('title','')} {snippet}".lower()
        term_hits = sum(1 for t in lookup_terms if t and t.lower() in text)
        about = 1
        if answer_is_about_entity is not None and len(entity) >= 2:
            about = 1 if answer_is_about_entity(entity, snippet) else 0
        url = str(row.get("url", "")).lower()
        trust = 2 if any(d in url for d in _TRUSTED_DOMAINS) else (1 if row.get("provider") == "wikipedia" else 0)
        looks_def = 1 if re.search(r"(이다|입니다|란\s|라고도|를 말한다|를 뜻한다|를 의미)", snippet) else 0
        length_ok = 1 if len(snippet) >= 40 else 0
        return (about, term_hits, trust, looks_def, length_ok)

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(general + wiki, key=score, reverse=True):
        key = _norm_title(str(row.get("title") or ""))[:30] + str(row.get("snippet") or "")[:30]
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
        if len(merged) >= count:
            break
    return merged


def _resolve_entity_by_type(entity: str, expected_type: str, host: str) -> dict[str, Any] | None:
    """Disambiguate an ambiguous name by surfing diversely: gather several candidate
 pages (action search) and pick the one whose TYPE matches what the question implies
 — '' + a founder question (→ ORG) resolves to ' ()', not ' '.
 This is the crawler-like breadth the user asked for, used for selection, not paste."""
    try:
        from packages.cgsr.cgsr.referent_resonance import infer_evidence_type
    except Exception:  # pragma: no cover - optional
        return None
    entity = (entity or "").strip()
    if not entity or expected_type in ("", "unknown"):
        return None
    api = (
        f"https://{host}/w/api.php?action=query&list=search&format=json&utf8=1"
        f"&srlimit=6&srsearch={quote_plus(entity)}"
    )
    body = _wiki_get_json(api)
    titles = [_strip_html(it.get("title") or "") for it in (body.get("query", {}).get("search", []) or [])][:6]
    if entity not in titles:
        titles.insert(0, entity)
    first_valid: dict[str, Any] | None = None
    for title in titles[:6]:
        row = _wiki_rest_summary(title, host)
        if not row:
            continue
        if first_valid is None:
            first_valid = row
        if infer_evidence_type(row["snippet"]) == expected_type:
            return row  # first type-matching candidate wins
    return first_valid


def _diverse_fallback_rows(query: str, lookup: str, lookup_terms: list[str], primary_host: str) -> list[dict[str, Any]]:
    """When the action search finds nothing, harvest from several keyless sources
    (direct Wikipedia summary in both language editions + Wiktionary) so a query
    isn't dead just because the strict title search missed."""
    korean = primary_host.startswith("ko")
    other_host = "en.wikipedia.org" if korean else "ko.wikipedia.org"
    # Candidate page titles: the cleaned lookup, plus each multi-char term.
    candidates: list[str] = []
    for cand in [lookup, *lookup_terms, query.strip()]:
        cand = (cand or "").strip()
        if cand and cand not in candidates:
            candidates.append(cand)
    rows: list[dict[str, Any]] = []
    for host in (primary_host, other_host):
        for cand in candidates[:4]:
            row = _wiki_rest_summary(cand, host)
            if row:
                rows.append(row)
                break
        if rows:
            break
    if not rows:
        for cand in candidates[:2]:
            wk = _wiktionary_definition(cand, korean=korean)
            if wk:
                rows.append(wk)
                break
    return rows


_WIKI_CACHE: dict[tuple[str, int], tuple[float, list[dict[str, Any]]]] = {}
_WIKI_CACHE_TTL = 300.0  # seconds


def wikipedia_search(query: str, count: int = 5) -> list[dict[str, Any]]:
    """TTL-memoized wrapper. A single chat request fans out several wikipedia_search
    calls (search_web's internal fetch, the outer fallback, and claim verification),
    often for the SAME term — each was a fresh ~1.5s network round-trip. Caching them
    for 5 min collapses the duplicates and makes a re-ask instant, without changing what
    is retrieved."""
    key = (str(query), int(count))
    hit = _WIKI_CACHE.get(key)
    now = time.time()
    if hit and (now - hit[0]) < _WIKI_CACHE_TTL:
        return hit[1]
    rows = _wikipedia_search_impl(query, count)
    _WIKI_CACHE[key] = (now, rows)
    if len(_WIKI_CACHE) > 512:  # bounded: drop the oldest quarter
        for k, _v in sorted(_WIKI_CACHE.items(), key=lambda kv: kv[1][0])[:128]:
            _WIKI_CACHE.pop(k, None)
    return rows


def _wikipedia_search_impl(query: str, count: int = 5) -> list[dict[str, Any]]:
    lookup = _normalize_lookup_query(query)
    lookup_terms = _lookup_terms(lookup)
    bounded_count = max(1, min(count, 10))
    wiki_host = _wiki_host_for_query(query)
    api_url = (
        f"https://{wiki_host}/w/api.php?action=query&list=search&format=json&utf8=1"
        f"&srlimit={max(bounded_count, 8)}&srsearch={quote_plus(lookup)}"
    )
    body = _wiki_get_json(api_url)
    results: list[dict[str, Any]] = []
    for index, item in enumerate((body.get("query", {}).get("search", []) or [])[: max(bounded_count, 8)], start=1):
        title = _strip_html(item.get("title") or lookup)
        page_slug = quote(title.replace(" ", "_"), safe="")
        page_url = f"https://{wiki_host}/wiki/{page_slug}"
        snippet = _strip_html(item.get("snippet") or "")
        if index <= 2:
            summary_url = f"https://{wiki_host}/api/rest_v1/page/summary/{page_slug}"
            summary = _wiki_get_json(summary_url)
            if isinstance(summary, dict) and summary:
                snippet = _strip_html(summary.get("extract") or snippet)
                page_url = summary.get("content_urls", {}).get("desktop", {}).get("page") or page_url
        if title and snippet:
            haystack = f"{title} {snippet}".lower()
            term_hits = sum(1 for term in lookup_terms if term in haystack)
            results.append(
                {
                    "id": f"wikipedia-{index}",
                    "title": title,
                    "url": page_url,
                    "snippet": snippet,
                    "provider": "wikipedia",
                    "source_type": "encyclopedia_search",
                    "license_status": "reference_only",
                    "search_score": (term_hits * 100) + (bounded_count - min(index, bounded_count) + 1),
                    "query_terms_matched": term_hits,
                    "normalized_query": lookup,
                }
            )
    results.sort(key=lambda result: (-int(result.get("query_terms_matched") or 0), -int(result.get("search_score") or 0), str(result.get("title") or "")))
    primary_limit = bounded_count - 1 if bounded_count >= 3 else bounded_count
    bounded_results = results[:primary_limit]
    enrichment_budget = 1 if bounded_count >= 3 else 0
    if enrichment_budget:
        for enriched in _wikipedia_visual_event_results(bounded_results, limit=enrichment_budget):
            if len(bounded_results) >= bounded_count:
                break
            bounded_results.append(enriched)
    if len(bounded_results) < bounded_count:
        for result in results[primary_limit:bounded_count]:
            if len(bounded_results) >= bounded_count:
                break
            bounded_results.append(result)
    # Precision + disambiguation: the action search ranks by term frequency, so a

    # fly). The exact-title REST summary is the authoritative page; and when the


    # by surfing several candidates. Prepend the result so it wins, deduped.
    try:
        from packages.cgsr.cgsr.referent_resonance import query_entity_type as _qet
        _entity_type = _qet(query)
    except Exception:  # pragma: no cover - optional
        _entity_type = "unknown"
    direct = None
    if _entity_type not in ("", "unknown"):
        direct = _resolve_entity_by_type(lookup, _entity_type, wiki_host)
    if not direct:
        direct = _wiki_rest_summary(lookup, wiki_host) or (
            _wiki_rest_summary(lookup_terms[0], wiki_host) if lookup_terms else None
        )
    if direct:
        seen_titles = {_norm_title(direct["title"])}
        merged = [direct]
        for row in bounded_results:
            if _norm_title(str(row.get("title") or "")) not in seen_titles:
                merged.append(row)
                seen_titles.add(_norm_title(str(row.get("title") or "")))
        bounded_results = merged[:bounded_count]
    # Diversity + robustness: if the strict action search found nothing (title
    # mismatch, or it was 429'd), harvest from direct summaries (both language
    # editions) and Wiktionary so the query still gets a real, cited source.
    if not bounded_results:
        bounded_results = _diverse_fallback_rows(query, lookup, lookup_terms, wiki_host)
    return bounded_results


def news_rss_search(query: str, count: int = 5) -> list[dict[str, Any]]:
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=ko&gl=KR&ceid=KR:ko"
    request = urllib.request.Request(url, headers={"User-Agent": WEB_USER_AGENT})
    with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310 - bounded public RSS endpoint
        xml = response.read()
    root = ET.fromstring(xml)
    results: list[dict[str, Any]] = []
    for index, item in enumerate(root.findall(".//item")[: max(1, min(count, 10))], start=1):
        title = (item.findtext("title") or "News result").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = _strip_html(item.findtext("description") or "")
        if not link:
            continue
        results.append(
            {
                "id": f"news-rss-{index}",
                "title": title,
                "url": link,
                "snippet": f"{pub_date} - {description}" if pub_date else description,
                "provider": "news-rss",
                "source_type": "news_search",
                "license_status": "reference_only",
                "search_score": count - index + 1,
            }
        )
    return results


async def search_web(query: str | None = None, count: int = 5, provider: str | None = None) -> dict[str, Any]:
    selected = _provider_from_env(provider)
    clean_query = (query or DEFAULT_QUERY).strip() or DEFAULT_QUERY
    bounded_count = max(1, min(int(count or 5), 10))
    if selected in {"microsoft-grounding", "grounding-with-bing", "bing-grounding"}:
        return {
            "provider": "microsoft-grounding",
            "query": clean_query,
            "results": [],
            "configured": _provider_configured("microsoft-grounding"),
            "bing_query_url": f"https://www.bing.com/search?q={quote_plus(clean_query)}",
            "status": "metadata_only",
            "message": "Grounding with Bing is configured through Azure Foundry Agents and does not expose raw result chunks to this native ATANOR harvest path.",
            "provider_status": provider_status(selected),
        }

    # The Python local companion keeps network calls conservative. Raw-result
    # providers are wired in the deployable Next route; local FastAPI exposes
    # the same contract and falls back to deterministic reference results.
    if is_fresh_search_query(clean_query) and selected == "static":
        try:
            results = news_rss_search(clean_query, bounded_count)
            if results:
                return {
                    "provider": "news-rss",
                    "query": clean_query,
                    "results": results,
                    "configured": True,
                    "bing_query_url": f"https://www.bing.com/search?q={quote_plus(clean_query)}",
                    "status": "ok",
                    "provider_status": provider_status(selected),
                }
        except Exception:
            pass
    if not is_fresh_search_query(clean_query) and is_knowledge_lookup_query(clean_query):
        # Multi-source via a real search API (Tavily/Brave) — a full web index, the way
        # ChatGPT/Perplexity retrieve — ranked by referent resonance so the best answer
        # is filtered out on our end. Falls back to the precise, type-resolved Wikipedia
        # path when no API key is configured (a single-endpoint DDG scrape was tried and
        # reverted — too noisy without a strong ranker).
        try:



            # clean entity.
            try:
                from packages.cgsr.cgsr.referent_resonance import query_subject_entity, is_definitional_question
                _ent = query_subject_entity(clean_query)
                _search_term = _ent if (2 <= len(_ent) <= 24 and is_definitional_question(clean_query)) else clean_query
            except Exception:
                _search_term = clean_query
            # PRIMARY = real multi-source search whenever available: SearXNG (keyless — aggregates
            # Google/Bing/DuckDuckGo/Namuwiki/news/blogs, the agreed diverse source, NOT just a
            # static encyclopedia) or a configured key (Tavily/Brave). provider_api_search prefers
            # SearXNG when reachable. Only when NEITHER is available do we fall to keyless
            # Wikipedia. This is what makes news/articles actively feed the answer.
            use_real_search = _searxng_reachable() or selected in {"brave", "serper", "tavily"}
            api_rows = (
                await asyncio.to_thread(provider_api_search, _search_term, bounded_count + 2)
                if use_real_search
                else []
            )
            if api_rows:
                # Merge the clean, precise Wikipedia entity page so an encyclopedic bio

                # result, while the open web still covers topics Wikipedia lacks.
                wiki_rows: list[dict[str, Any]] = []
                try:
                    wiki_rows = await asyncio.to_thread(wikipedia_search, _search_term, 3)
                except Exception:
                    wiki_rows = []
                ranked = _rank_web_rows(clean_query, api_rows + wiki_rows)[:bounded_count]
                return {
                    "provider": "search-api",
                    "query": clean_query,
                    "results": ranked,
                    "configured": True,
                    "bing_query_url": f"https://www.bing.com/search?q={quote_plus(clean_query)}",
                    "status": "ok",
                    "provider_status": provider_status(selected),
                }
        except Exception:
            pass
        try:
            results = await asyncio.to_thread(wikipedia_search, clean_query, bounded_count)
            if results:
                return {
                    "provider": "wikipedia",
                    "query": clean_query,
                    "results": results,
                    "configured": True,
                    "bing_query_url": f"https://www.bing.com/search?q={quote_plus(clean_query)}",
                    "status": "ok",
                    "provider_status": provider_status(selected),
                }
        except Exception:
            pass
    if _static_fixtures_allowed():
        return {
            "provider": selected if _provider_configured(selected) else "static",
            "query": clean_query,
            "results": static_search(clean_query, bounded_count),
            "configured": _provider_configured(selected),
            "bing_query_url": f"https://www.bing.com/search?q={quote_plus(clean_query)}",
            "status": "ok" if selected == "static" else "fallback_static",
            "provider_status": provider_status(selected),
        }
    # No real source and fixtures are NOT opted in → return nothing so the answer path abstains

    return {
        "provider": "none",
        "query": clean_query,
        "results": [],
        "configured": False,
        "bing_query_url": f"https://www.bing.com/search?q={quote_plus(clean_query)}",
        "status": "no_grounded_source",
        "provider_status": provider_status(selected),
    }


def web_results_to_evidence(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    for index, result in enumerate(results, start=1):
        evidence.append(
            {
                "doc_id": result.get("id") or f"web-{index:03d}",
                "chunk_id": f"{result.get('id') or f'web-{index:03d}'}#search",
                "path": result.get("url", ""),
                "url": result.get("url", ""),
                "score": round(0.72 + min(index, 5) * 0.03, 3),
                "snippet": result.get("snippet", ""),
                "title": result.get("title", "Web result"),
                "retrieval_signals": {"web_search": 1, "provider": result.get("provider", "static")},
                "source_type": result.get("source_type", "web_search"),
                "visual_evidence_enrichment": bool(result.get("visual_evidence_enrichment")),
                "enrichment_basis": result.get("enrichment_basis"),
                "topic_scene_templates": bool(result.get("topic_scene_templates", False)),
                "renderer_may_infer_topic": bool(result.get("renderer_may_infer_topic", False)),
                "particle_text": bool(result.get("particle_text", False)),
            }
        )
    return evidence
