# -*- coding: utf-8 -*-
"""Wild-web session — the ONLY network-touching module: SearXNG search (forum-preferring, wiki last
resort) + honest urllib fetch, robots-lite + per-domain rate limit, then hand extracted segments to
the channel router. `searcher`/`fetcher` are injectable so tests run fully offline (no network).

Doctrine notes:
  * Forums/discussion boards are the TARGET register (wild human communication), so the ranker
    INVERTS the factual-lane weighting from brain_link.web_knowledge: forums are boosted, wiki is
    demoted to last resort (per the wiki-last-resort doctrine).
  * Honest crawler: UA 'ATANOR-research', 8s timeout, public pages only (skip login/paywall URLs,
    honor obvious <meta robots noindex>), >= 5s between fetches of the SAME domain.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from collections import Counter
from typing import Any, Callable

from . import store as S
from . import transforms as T
from .channels import process_segments

SEARXNG_BASE = "http://127.0.0.1:8888"
_UA = {"User-Agent": "ATANOR-research"}
_DEFAULT_TOPIC = "how do people fix a bicycle flat tire"
_RATE_LIMIT_S = 5.0
_MAX_BYTES = 2_000_000

# forum / discussion / Q&A cues — the wild-communication sources we PREFER
_FORUM = ("reddit.com", "stackexchange.com", "stackoverflow.com", "superuser.com",
          "serverfault.com", "askubuntu.com", "quora.com", "news.ycombinator.com",
          "bikeforums.net", "discourse", "community.", "forum", "discuss", "board", "answers.",
          "zhihu.com", "bbs.")
# junk for TEXT human-communication: video / app-store / social / shopping / login (no readable
# wild text — SearXNG on this box floods these for NL queries, so demote hard)
_JUNK = ("youtube.com", "youtu.be", "music.youtube", "play.google.com", "apps.apple.com",
         "accounts.google", "facebook.com", "instagram.com", "tiktok.com", "twitter.com", "x.com",
         "pinterest.", "amazon.", "ebay.", "aliexpress.", "tradeinn.com", "google.com/maps",
         "linkedin.com")
# corporate support / official docs — coherent prose but NOT wild communication (demote, not junk)
_CORPORATE = ("support.microsoft.com", "docs.microsoft.com", "learn.microsoft.com",
              "support.apple.com", "support.google.com", "docs.", "developer.", "help.", "kb.")
# encyclopedic mirrors — allowed, but only when nothing better exists (wiki last resort)
_ENCYCLOPEDIC = ("wikipedia.org", "wikiwand.com", "britannica.com", "handwiki.org",
                 "dbpedia.org", "wikidata.org", "wikimedia.org", "namu.wiki")
# login-walled / paywalled / non-public — skipped pre-fetch (robots-lite, public pages only)
_LOGIN_WALL = ("/login", "/signin", "/sign-in", "/account", "/subscribe", "/checkout",
               "/register", "/auth", "/paywall", "accounts.google", "facebook.com/login",
               "instagram.com/accounts", "linkedin.com/login")

_NOINDEX = re.compile(
    r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', re.IGNORECASE)


def _wild_weight(domain: str) -> float:
    """Higher = preferred. Forums/Q&A boosted; junk (video/social/shop) and corporate docs demoted;
    wiki last resort. Domain diversity is enforced separately (per-domain page cap in wild_session)."""
    w = 1.0
    if any(f in domain for f in _FORUM):
        w += 0.7
    if any(j in domain for j in _JUNK):
        w -= 1.2
    if any(c in domain for c in _CORPORATE):
        w -= 0.5
    if any(e in domain for e in _ENCYCLOPEDIC):
        w -= 0.6
    return w


def _query_variants(topic: str) -> list[str]:
    """Discussion-biased query variants (the doctrine prefers forum/discussion sources). A bare NL
    query on this SearXNG floods video/app junk; a 'forum'/'discussion' hint surfaces boards."""
    t = topic.strip()
    return [f"{t} forum", f"{t} discussion", t, f"{t} how to"]


def wild_search(query: str, base: str = SEARXNG_BASE, timeout: float = 8.0,
                extra: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Query SearXNG JSON for ONE query; return results ranked (forum-first, junk/wiki demoted).
    `extra` steers SearXNG at the SOURCE — e.g. {'engines': 'lemmy posts,lemmy comments'} or
    {'categories': 'q&a'} to hit the discussion-bearing engines directly instead of the general web
    category (which this box floods with SEO/dictionary/app-store pages for NL queries)."""
    # language=en biases the SearXNG aggregation to English at the SOURCE (English-only doctrine),
    # cutting the CJK/localized noise this box's index otherwise floods in.
    params = {"q": query, "format": "json", "language": "en"}
    if extra:
        params.update(extra)
    url = base.rstrip("/") + "/search?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for res in data.get("results", []):
        u = res.get("url", "")
        if not u or not res.get("title"):
            continue
        d = S.domain_of(u)
        content = res.get("content", "") or ""
        out.append({"url": u, "title": res.get("title", ""), "content": content,
                    "domain": d, "weight": _wild_weight(d),
                    "quality": T.discussion_density(f"{res.get('title', '')} . {content}")})
    out.sort(key=lambda r: -(r["weight"] + r["quality"]))
    return out


def wild_search_variants(topic: str, base: str = SEARXNG_BASE) -> list[dict[str, Any]]:
    """Run discussion-biased variants, MERGE (dedup by url), rank. Stops early once enough
    forum/discussion hits (weight > 1.0) are gathered."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for q in _query_variants(topic):
        for r in wild_search(q, base):
            if r["url"] in seen:
                continue
            seen.add(r["url"])
            merged.append(r)
        if sum(1 for r in merged if r["weight"] > 1.0) >= 6:
            break
    merged.sort(key=lambda r: -(r["weight"] + r.get("quality", 0.0)))
    return merged


# ── SOURCE STEERING: hit the DISCUSSION-BEARING engines directly (the big lever) ─────────────────
# Measured on this box: the general web category returns SEO/dictionary/app-store pages ('keep' ->
# Google Keep, 'why' -> dictionary defs), so a session saw ~1 domain of real discussion and consensus
# never fired. But SearXNG here also exposes discussion engines whose results ARE wild human talk,
# each spanning MANY DISTINCT domains — exactly the cross-domain spread consensus needs:
#   * fediverse (Lemmy posts+comments): federated -> one topic naturally appears across dozens of
#     INDEPENDENT instances (lemmy.world, beehaw.org, sopuli.xyz, aussie.zone, ...). Literal
#     full-text search, so it gets SHORT 2-token content-noun queries (topic_keyword_windows).
#   * q&a (StackExchange family): real question/answer threads (stackoverflow, askubuntu, superuser).
# `general` (forum-biased variants) stays as the fallback lane. Channel provenance gives a discussion
# bonus in ranking so these lead over any general-web survivor.
_CHANNEL_BONUS = {"fediverse": 0.7, "qa": 0.7, "general": 0.0}
_FEDIVERSE = {"engines": "lemmy posts,lemmy comments"}   # federated: one topic -> many DISTINCT domains
_QA = {"categories": "q&a"}                               # StackExchange family: real Q/A threads


def wild_search_channels(topic: str, base: str = SEARXNG_BASE) -> list[dict[str, Any]]:
    """Query the discussion-bearing engines (fediverse + q&a) AND the general forum-biased lane, MERGE
    (dedup by url), tag channel provenance, and rank by domain weight + discussion quality + channel
    bonus. This is the default searcher — it deliberately surfaces multi-domain discussion so a single
    session can reach the >= 2 distinct domains that register/causal consensus requires. The fediverse
    lane issues several SHORT 2-token window queries (literal Lemmy search needs them) and merges."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []

    def take(results: list[dict[str, Any]], channel: str) -> None:
        for r in results:
            if r["url"] in seen:
                continue
            seen.add(r["url"])
            r["channel"] = channel
            merged.append(r)

    for q in (T.topic_keyword_windows(topic, size=2, max_windows=3) or [topic]):
        take(wild_search(q, base, extra=_FEDIVERSE), "fediverse")
    take(wild_search(topic, base, extra=_QA), "qa")
    take(wild_search_variants(topic, base), "general")          # general fallback lane

    merged.sort(key=lambda r: -(r["weight"] + r.get("quality", 0.0)
                                + _CHANNEL_BONUS.get(r.get("channel", "general"), 0.0)))
    return merged


def _skip_url(url: str) -> bool:
    u = (url or "").lower()
    return (not u.startswith(("http://", "https://"))) or any(w in u for w in _LOGIN_WALL)


def _has_noindex(html: str) -> bool:
    return bool(_NOINDEX.search(html or ""))


def fetch_page(url: str, timeout: float = 8.0) -> str | None:
    """Honest single-page fetch: UA 'ATANOR-research', 8s, HTML/text only, capped at 2MB."""
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ctype = (r.headers.get_content_type() or "")
            if "html" not in ctype and "text" not in ctype:
                return None
            raw = r.read(_MAX_BYTES)
            charset = r.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
    except Exception:
        return None


_YIELD_FILE = Path(__file__).resolve().parents[2] / "data" / "register_bank" / "domain_yield.json"


def _record_domain_yield(this_run: dict) -> dict:
    """Accumulate which domains actually produced speech, so the next roam can prefer them."""
    if not this_run:
        return {}
    try:
        cur = json.loads(_YIELD_FILE.read_text(encoding="utf-8")) if _YIELD_FILE.exists() else {}
    except Exception:
        cur = {}
    for dom, n in this_run.items():
        row = cur.get(dom) or {"pages": 0, "harvested": 0}
        row["pages"] = int(row.get("pages", 0)) + 1
        row["harvested"] = int(row.get("harvested", 0)) + int(n)
        cur[dom] = row
    try:
        _YIELD_FILE.parent.mkdir(parents=True, exist_ok=True)
        _YIELD_FILE.write_text(json.dumps(cur, indent=1, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return this_run


def preferred_domains(k: int = 8) -> list[str]:
    """Where speech has actually been found, best first — SOURCE SELECTION AS A MEASUREMENT.

    Not a list I wrote. A hand-picked roster of "good conversational sites" is the hand rule this
    project keeps removing, and it also cannot know which sites are reachable and readable from this
    machine: the first attempt at reading pages hit HTTPError on people.com, a login wall on a Korean
    portal, and zero segments from Facebook. What survives contact is the only reliable evidence, so
    the roster is whatever produced register per page read, and it updates itself every session."""
    try:
        cur = json.loads(_YIELD_FILE.read_text(encoding="utf-8")) if _YIELD_FILE.exists() else {}
    except Exception:
        return []
    scored = [(d, r.get("harvested", 0) / max(1, r.get("pages", 1)), r.get("harvested", 0))
              for d, r in cur.items() if r.get("harvested", 0) > 0]
    scored.sort(key=lambda x: (-x[1], -x[2], x[0]))
    return [d for d, _rate, _n in scored[:k]]


def wild_session(topic: str | None = None, max_pages: int = 3, *, base: str = SEARXNG_BASE,
                 pages_per_domain: int = 1,
                 searcher: Callable[[str], list[dict[str, Any]]] | None = None,
                 fetcher: Callable[[str], str | None] | None = None) -> dict[str, Any]:
    """Run ONE wild-web learning session.

    topic: given, else the next 'ungrounded' curiosity topic, else a benign default.
    pages_per_domain: cap pages fetched from any single domain (default 1) — spreads the session
    across DISTINCT domains, which is exactly what 2-domain register/causal consensus needs.
    The default searcher hits the discussion-bearing engines (fediverse + q&a) so ONE topic is pulled
    from MANY distinct domains in ONE session; the fetch plan is then ordered by the domain-diversity
    scheduler; already-harvested URLs (cross-session) and within-domain mirrors are skipped.
    Returns honest counts incl. distinct_domains, register_promoted, causal_corroborated,
    convergence_rate. searcher/fetcher injectable for tests (fully offline)."""
    search = searcher or (lambda q: wild_search_channels(q, base))
    fetch = fetcher or fetch_page
    topic = topic or S.next_ungrounded_topic() or _DEFAULT_TOPIC

    results = search(topic) or []
    # topical-relevance anchor: the content words of the topic (reuse realcity.extract_topics). A
    # harvested page must actually be ABOUT the topic — else the forum-boost drags in off-topic
    # boards (a French Facebook forum is human discourse, but not what we went looking for).
    topic_words = [w.lower() for w in T.extract_topics(topic, [])]
    need_words = min(2, len(topic_words))   # a page must share >=2 distinct topic words (not just
    #                                         one generic one like 'people') to count as on-topic

    # EFFICIENCY: drop junk/login URLs and URLs already harvested in a PAST session before ranking —
    # spend the fetch budget on NEW sources (novelty drive).
    eligible: list[dict[str, Any]] = []
    skipped_seen = 0
    for r in results:
        if not isinstance(r, dict):
            continue
        u = r.get("url", "")
        if not u or _skip_url(u):
            continue
        if S.already_seen(u):
            skipped_seen += 1
            continue
        eligible.append(r)

    # SOURCE STEERING + CONVERGENCE: order the fetch plan to MAXIMISE distinct-domain coverage (a
    # slightly larger candidate pool than max_pages so gate rejections still leave a diverse set).
    plan = T.schedule_by_domain_diversity(eligible, max(max_pages * 4, max_pages),
                                          pages_per_domain) or eligible

    dom_pages: Counter = Counter()
    last_fetch: dict[str, float] = {}
    pages: list[str] = []
    pairs: list[tuple[str, str]] = []
    harvested_domains: set[str] = set()
    off_topic = 0
    mirror_skipped = 0
    register_harvested = 0
    register_by: dict[str, int] = {}
    #: which domains actually YIELD conversational register. SOURCE SELECTION, measured rather than
    #: listed by me: a hand-picked source list is the hand-rule this project keeps removing, and it
    #: also cannot know which sites are readable from here. Recorded per session and read back by
    #: `preferred_domains`, so where the mind roams next is decided by where speech was actually found.
    domain_yield: dict[str, int] = {}

    for res in plan:
        if len(pages) >= max_pages:
            break
        url = res.get("url", "") if isinstance(res, dict) else ""
        if not url or _skip_url(url):
            continue
        dom = S.domain_of(url)
        if dom_pages[dom] >= pages_per_domain:      # distinct-domain spread (consensus needs it)
            continue
        # per-domain rate limit (>= 5s between fetches of the same domain)
        if dom in last_fetch:
            wait = _RATE_LIMIT_S - (time.time() - last_fetch[dom])
            if wait > 0:
                time.sleep(wait)
        last_fetch[dom] = time.time()

        html = fetch(url)
        if not html or _has_noindex(html):
            continue
        segs = T.extract_segments(html, url)
        if not segs:
            continue
        blob = " ".join(segs)
        if S.seen_content(url, blob):               # within-domain mirror/crosspost — no new signal
            mirror_skipped += 1
            continue
        if topic_words:
            present = {tw for s in segs for tw in topic_words if tw in s.lower()}
            if len(present) < need_words:           # on-topic pages only (relevance gate)
                off_topic += 1
                continue
        dom_pages[dom] += 1
        pages.append(url)
        harvested_domains.add(dom)
        pairs.extend((s, url) for s in segs)
        # THE REGISTER LANE, joined here because this is the only place page BODIES are read.
        #
        # The pieces were all present and none of them touched: `wild_session` reads pages politely
        # (robots-lite, per-domain rate limit, paywall skip) and was called by nothing outside its own
        # __main__; `register_harvest` banks how people talk and was fed only by a page path nothing
        # ran; `expedition` distils SEARCH SNIPPETS, which never contain a conversation. So the voice's
        # diet could not fill however well each part worked -- the ninth built-present-unread case
        # found in one day.
        #
        # Segments rather than raw HTML: the extractor has already stripped chrome, and what is banked
        # is then anonymised, abstracted to short fragments and consensus-gated inside the harvester.
        try:
            from packages.autonomy_kernel.register_harvest import harvest_register
            # NEWLINE-joined, not space-joined. `blob` exists for content-dedup hashing and joins
            # segments with a single space; handing that to the harvester produced ONE line of 5,810
            # characters, far outside the 12-120 window, so every real forum reply was dropped on a
            # length check. The segment boundaries are the reply boundaries and must survive.
            _reg = harvest_register("\n".join(segs), url)
            register_harvested += int(_reg.get("harvested") or 0)
            for _r, _n in (_reg.get("by_register") or {}).items():
                register_by[_r] = register_by.get(_r, 0) + int(_n)
            domain_yield[dom] = domain_yield.get(dom, 0) + int(_reg.get("harvested") or 0)
        except Exception:
            pass
        S.mark_visited(url, blob)                   # cross-session dedupe (URL + within-domain content)

    agg = process_segments(pairs)
    # CONVERGENCE RATE: of the distinct register/fragment/causal signals harvested this session, what
    # share was attested across >= 2 DISTINCT domains (promoted/corroborated) vs still stuck at 1
    # domain (staged). FRAGMENT promotions are the W2 lever — whole-segment templates almost never
    # converge, so fragment_promoted is where genuine register consensus now fires.
    converged = agg["register_promoted"] + agg["fragment_promoted"] + agg["causal_corroborated"]
    below = (agg["register_staged"] + max(0, agg["fragment_candidates"] - agg["fragment_promoted"])
             + max(0, agg["causal_candidates"] - agg["causal_corroborated"]))
    convergence_rate = round(converged / max(1, converged + below), 3)
    summary = {
        "topic": topic,
        "pages_visited": len(pages),
        "distinct_domains": len(harvested_domains),
        "urls_skipped_already_seen": skipped_seen,
        "off_topic_pages_skipped": off_topic,
        "mirror_pages_skipped": mirror_skipped,
        "pages": pages[:10],
        "segments": agg["segments"],
        "register_harvested": register_harvested,
        "register_by": register_by,
        "domain_yield": _record_domain_yield(domain_yield),
        "quarantined": agg["quarantined"],
        "register_staged": agg["register_staged"],
        "register_promoted": agg["register_promoted"],
        "register_duplicate": agg["register_duplicate"],
        "fragment_candidates": agg["fragment_candidates"],
        "fragment_promoted": agg["fragment_promoted"],
        "topics": agg["topics"],
        "causal_candidates": agg["causal_candidates"],
        "causal_corroborated": agg["causal_corroborated"],
        "convergence_rate": convergence_rate,
        "dropped": {k[len("dropped_"):]: v for k, v in agg.items()
                    if k.startswith("dropped_") and v},
    }
    S.log_session(summary)
    return summary
