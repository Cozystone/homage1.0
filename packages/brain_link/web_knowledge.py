# -*- coding: utf-8 -*-
"""Source-weighted web knowledge — stop over-mining Wikipedia; the web is huge.

Owner (2026-07-21): "wikipedia 작작 써라. 찾을 곳이 웹에 무지하게 많은데 왜 매번 백과사전만 뒤지냐.
검색 가중치로 wikipedia 말고 다른 것들 더 적극적으로 찾게 해."

SearXNG (:8888) already AGGREGATES many engines — one query returns ~20 results across many domains
(native-languages.org, britannica, wikiwand, primary sites, …); the old lane just picked Wikipedia
every time. This module ranks those results by a SOURCE WEIGHT that:
  - PENALIZES encyclopedic mirrors (wikipedia, wikiwand, handwiki, grokipedia, ...) so they win only
    when nothing better exists — never first by default,
  - REWARDS domain DIVERSITY across a session (a domain already used this session is down-weighted,
    so answers spread across the web instead of hammering one site),
  - REWARDS topical/primary/specialist domains (.edu/.gov/.org specialists, official sites).
Honesty preserved: whatever wins is quoted with its source URL; nothing invented. Falls back to the
Wikipedia REST summary ONLY if SearXNG is unreachable (so the lane still works offline-of-SearXNG).
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections import Counter

_UA = {"User-Agent": "ATANOR-BrainLink/1 (research)"}

# encyclopedic mirrors — allowed, but never the default first pick
_ENCYCLOPEDIC = ("wikipedia.org", "wikiwand.com", "handwiki.org", "grokipedia.com",
                 "wikidata.org", "dbpedia.org", "wikimedia.org", "wiki2.org")
# low-value / noisy domains to push down (video/social/aggregators for factual queries)
_LOW_VALUE = ("douyin.com", "tiktok.com", "pinterest.", "youtube.com", "facebook.com",
              "instagram.com", "twitter.com", "x.com", "quora.com", "reddit.com",
              "amazon.", "ebay.", "aliexpress.", ".shop", "shopletter")
# specialist / authoritative signals to lift
_AUTHORITATIVE = (".edu", ".gov", "britannica.com", ".ac.", "nature.com", "sciencedirect.com",
                  "native-languages.org", "stanford.edu", "nasa.gov")


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.replace("www.", "").lower()


_CJK = re.compile(r"[　-鿿가-힣぀-ヿ]")   # CJK / Hangul / Kana


def _is_english(text: str) -> bool:
    """English-only doctrine: reject snippets with CJK/Hangul or too few ASCII letters."""
    if _CJK.search(text) and sum(1 for c in text if c.isascii() and c.isalpha()) < 24:
        return False
    ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
    return ascii_letters >= 8


def _anchors_query(term: str, title: str, content: str) -> bool:
    """Relevance gate ([[web-rescue-relevance-gate]]): the result must actually be ABOUT the query —
    a content word of the term appears in the title/snippet. 'deep south' must not match 'DeepSeek'."""
    hay = (title + " " + content).lower()
    words = [w for w in re.findall(r"[a-z]{3,}", term.lower())]
    if not words:
        return True
    return all(w in hay for w in words) or (len(words) > 1 and sum(w in hay for w in words) >= 2)


def _source_weight(url: str, used_domains: Counter) -> float:
    """Higher = preferred. Encyclopedic penalized; diversity + authority rewarded."""
    d = _domain(url)
    w = 1.0
    if any(e in d for e in _ENCYCLOPEDIC):
        w -= 0.6                                  # wiki-family: only wins if nothing better
    if any(x in d for x in _LOW_VALUE):
        w -= 0.9
    if any(a in d for a in _AUTHORITATIVE):
        w += 0.4
    w -= 0.25 * used_domains.get(d, 0)            # spread across the web (session diversity)
    return w


def searxng_ranked(query: str, base: str, used_domains: Counter,
                   timeout: float = 8.0) -> list[dict]:
    """Query SearXNG JSON, return results sorted by source weight (best first)."""
    url = f"{base.rstrip('/')}/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return []
    out = []
    for res in data.get("results", []):
        u = res.get("url", "")
        if not u or not res.get("title"):
            continue
        out.append({"url": u, "title": res["title"], "content": res.get("content", ""),
                    "domain": _domain(u), "weight": _source_weight(u, used_domains)})
    out.sort(key=lambda r: -r["weight"])
    return out


def _wiki_fallback(term: str, timeout: float = 8.0) -> tuple[str, str] | None:
    t = urllib.parse.quote(term.strip().replace(" ", "_"))
    try:
        req = urllib.request.Request(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{t}", headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if not d.get("extract") or d.get("type") == "disambiguation":
        return None
    gloss = re.split(r"(?<=[.!?])\s", d["extract"].strip())[0]
    if _is_nonanswer(gloss):                           # the stub gate holds on the fallback too
        return None
    return gloss, d.get("content_urls", {}).get("desktop", {}).get("page", "")


# definitional query variants — the ITERATIVE search loop (Claude's web tool does 1-3+ progressive
# searches). A bare noun like 'coffee' pulls commercial junk; '"coffee" definition' pulls glosses.
# When CONTEXT is given (recent conversation concepts), a context-anchored variant leads: the
# Chinese-room 맥락 결여 lesson made mechanical — an ambiguous term is resolved BY its discourse
# context ('United' amid a geography talk => 'United states country', not the airline).
def _query_variants(term: str, context: list[str] | None = None) -> list[str]:
    t = term.strip()
    base = [f'"{t}" definition', f"what is {t}", f"{t} meaning", t]
    if context:
        ctx = " ".join(w for w in context[:2] if w and w.lower() != t.lower())
        if ctx:
            return [f"{t} {ctx}", f'"{t}" definition {ctx}'] + base
    return base


def _looks_definitional(term: str, snippet: str) -> bool:
    """Dynamic-filter test (Claude's filtering step): keep a result only if it reads like a DEFINITION
    of the term, not an ad/listing. Rewards 'X is/are/was a ...' and copular openers; rejects
    marketing verbs and dateline/price noise."""
    s = snippet.strip().lower()
    t = term.strip().lower()
    if re.search(r"\b\d+\s*(followers|posts|reviews|\$|USD|% off|sale)\b", s):
        return False
    if s.startswith(("we ", "our ", "shop ", "buy ", "get ", "sign up", "welcome to")):
        return False
    # a definitional opener: "<term> is/are/was/refers to/is a ..." (the frame of an encyclopedic gloss)
    if re.search(rf"\b{re.escape(t)}\b\s+(is|are|was|were|refers to|means|denotes|is a|is an)\b", s):
        return True
    # or any copular within the first clause (generic definitional shape)
    return bool(re.match(r"^[a-z][\w '\-,]{2,60}\s+(is|are|was|were|refers to)\s+", s))


# a snippet can be English, anchored, AND still say nothing — a disambiguation stub or a word-list
# dump. These are worse than no answer (they read as confident but carry zero meaning), so they must
# be rejected outright, never kept as the best_nondef fallback. (Overnight defect: "what is state?"
# -> "Topics referred to by the same term"; "what is letter?" -> "a - accent - acute - all the best…")
_NONANSWER = re.compile(
    r"topics referred to by the same term|may refer to:|may also refer to|"
    r"disambiguation|is a surname|is a given name|redirects here|for other uses",
    re.I)


def _is_nonanswer(snippet: str) -> bool:
    s = snippet.strip()
    if _NONANSWER.search(s):
        return True
    # word-list dump: many ' - '/' · ' separators and very few sentence stops => a glossary index,
    # not a definition ("a - accent - acute - all the best - alpha - B - best …").
    seps = s.count(" - ") + s.count(" · ") + s.count(" | ")
    stops = s.count(". ") + s.count("? ") + s.count("! ")
    return seps >= 4 and stops <= 1


def _acceptable_fallback(term: str, snippet: str) -> bool:
    """GPT-5.4's game-film coaching (2026-07-21), implemented: before ACCEPTING a retrieved reply,
    check it matches the requested semantic role. A what-is question deserves text ABOUT the term —
    not a sales pitch ('We present ... our wide range of quality auto parts') and not a page that
    merely mentions the term in passing ('Another quirk is Intel mobile CPUs ... letter'). Those two
    were live failures the coach quoted from the overnight transcript. Applies to the best_nondef
    fallback lane; abstaining beats a confidently-wrong sense."""
    s = snippet.strip().lower()
    if s.startswith(("we ", "our ", "shop", "buy ", "get ", "sign up", "welcome",
                     "find the latest", "discover ", "explore ", "browse ")):
        return False                                  # a pitch answers no what-is question
    return term.strip().lower() in s[:40]             # term in SUBJECT position, not incidental


def learn_from_web(term: str, base: str, used_domains: Counter,
                   context: list[str] | None = None) -> tuple[str, str, str] | None:
    """Resolve a concept from the DIVERSE web, source-weighted + ITERATIVE + dynamically FILTERED
    (Claude's web-tool loop applied to No-LLM): try definitional query variants in turn; per result
    require English + query-anchor + a DEFINITIONAL shape before it reaches us. `context` (recent
    discourse concepts) both anchors the queries AND boosts results that mention it — so an
    ambiguous term resolves to the sense the CONVERSATION is about. Returns (gloss, url, domain)
    or None; records the winning domain so the next query spreads elsewhere."""
    ctx_words = [w.lower() for w in (context or []) if w]
    best_nondef: tuple[str, str, str] | None = None      # anchored+English but not clearly a def
    for q in _query_variants(term, context):              # progressive re-search across variants
        ranked = searxng_ranked(q, base, used_domains)
        if ctx_words:                                     # context boost: the discourse picks the sense
            for r in ranked:
                hay = (r["title"] + " " + r["content"]).lower()
                if any(w in hay for w in ctx_words):
                    r["weight"] += 0.45
            ranked.sort(key=lambda r: -r["weight"])
        for r in ranked:
            snippet = (r["content"] or r["title"]).strip()
            if len(snippet) < 25 or not _is_english(snippet):
                continue
            if _is_nonanswer(snippet):                       # disambiguation stub / word-list => skip
                continue
            if not _anchors_query(term, r["title"], r["content"]):
                continue
            gloss = re.split(r"(?<=[.!?])\s", snippet)[0][:280]
            if _looks_definitional(term, snippet):        # dynamic filter: definitional wins now
                used_domains[r["domain"]] += 1
                return gloss, r["url"], r["domain"]
            if best_nondef is None and _acceptable_fallback(term, snippet):
                best_nondef = (gloss, r["url"], r["domain"])   # decent fallback; keep searching
    if best_nondef:                                       # no clean definition found across variants
        used_domains[best_nondef[2]] += 1
        return best_nondef
    fb = _wiki_fallback(term)                              # SearXNG down / dry -> encyclopedic last
    if fb:
        used_domains["en.wikipedia.org"] += 1
        return fb[0], fb[1], "en.wikipedia.org"
    return None
