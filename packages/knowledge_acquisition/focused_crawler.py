# -*- coding: utf-8 -*-
"""A crawler whose frontier is scored by IGNORANCE, and whose index is the fact table.

    from packages.knowledge_acquisition.focused_crawler import FocusedCrawler
    c = FocusedCrawler(deficit={"trowel", "kiosk", ...})
    for page in c.crawl(seeds, max_pages=2000):
        ...            # page.facts is kept; page.html was already discarded

WHY THIS IS NOT A WORKAROUND. Common Crawl and sitemaps are somebody else's crawl. This one walks the
link graph itself, the way a crawler has always worked -- seeds, then the links on the page, then the
links on those. Nobody's index is consulted, so nobody's index can be taken away.

WHAT MAKES IT TRACTABLE ON ONE MACHINE, and it is three separate reversals of the usual pipeline.

    1  THE INDEX IS THE FACT TABLE. A general engine stores pages because it must answer FUTURE UNKNOWN
       queries. ATANOR knows its query set, so a page is read, extracted, and dropped. Measured:
       396,657 facts occupy 16 MB where the pages behind them are hundreds of gigabytes. Storage
       scales with KNOWLEDGE, not with the web, and that is what removes the 200-terabyte problem.

    2  CONSENSUS REPLACES RANKING. Ranking exists for a person who reads the top three results. ATANOR
       needs the same fact from DISTINCT DOMAINS, so more results is better and ordering them is work
       nobody reads. No PageRank is needed; the gate that already exists does that job.

    3  THE FRONTIER IS SCORED BY WHAT IS MISSING. A general crawler must go breadth-first because it
       does not know what it needs. This one has the deficit map -- 8,848 words ATANOR can say and
       cannot describe -- so every discovered link is scored by whether its anchor text or url slug
       names something unknown. That is a focused crawl (Chakrabarti et al. 1999) with an unusually
       good focus signal, and it means the crawl TERMINATES: a general crawler never finishes, this
       one stops when the deficit is covered.

    SCALE, from the deficit rather than from the web:
        8,848 words x ~30 pages each = ~265,000 pages, not 4 billion
        at 50 distinct hosts x 1 req/s = ~1.5 hours

POLITENESS AND ROBOTS ARE NOT THIS MODULE'S BUSINESS. PoliteFetcher owns them, and it owns them once:
one request per second per host, robots.txt fetched with our own agent, a 403 shutting a host for the
run. This module only decides WHERE to go.

WHAT IT CANNOT REACH, said plainly: anything no crawled page links to, and anything drawn only by
JavaScript. The second is where a real browser belongs -- for the few pages that need rendering, not for
throughput.
"""
from __future__ import annotations

import heapq
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from .polite_fetch import PoliteFetcher

_A = re.compile(rb'<a\s[^>]*href=["\']([^"\'#>]+)["\'][^>]*>(.{0,160}?)</a>', re.I | re.S)
_TAG = re.compile(rb"<[^>]+>")
_WORD = re.compile(r"[a-z]{3,20}")
_SKIP_EXT = re.compile(r"\.(jpg|jpeg|png|gif|svg|webp|pdf|zip|gz|mp4|mp3|css|js|ico|xml|json)$", re.I)
_SKIP_PATH = re.compile(r"/(login|signin|signup|cart|checkout|account|privacy|terms|contact|"
                        r"advertise|subscribe|donate)\b", re.I)

# A NON-ENGLISH MIRROR SCORES EXACTLY LIKE THE ENGLISH ONE, because the slug is the same word. That
# is how host-balancing found 41 hosts and collapsed the harvest: mg.wiktionary.org, sw.wiktionary.org
# and th.wiktionary.org are perfect host diversity and zero English facts. Measured: 8.93 pages/second
# with 6 facts, against 1.94 pages/second with 73. Throughput bought with irrelevant hosts is not
# throughput. ATANOR has been English-only since 2026-07-18, so the language belongs in the frontier
# rather than being discovered again downstream.
_LANG_SUB = re.compile(r"^([a-z]{2,3})\.(wik|m\.wik)", re.I)


def _english_host(host: str) -> bool:
    m = _LANG_SUB.match(host)
    return not m or m.group(1).lower() == "en"


@dataclass(order=True)
class _Link:
    neg_score: float
    depth: int = field(compare=False)
    url: str = field(compare=False)
    why: str = field(compare=False, default="")


@dataclass
class Page:
    url: str
    host: str
    depth: int
    score: float
    facts: list = field(default_factory=list)          # (entity, relation, object)
    links_found: int = 0
    words_hit: tuple = ()


def _slug_words(url: str) -> set[str]:
    path = urllib.parse.urlsplit(url).path.lower()
    return set(_WORD.findall(path.replace("_", " ").replace("-", " ").replace("/", " ")))


def _anchor_words(anchor: bytes) -> set[str]:
    txt = _TAG.sub(b" ", anchor).decode("utf-8", "ignore").lower()
    return set(_WORD.findall(txt))


class FocusedCrawler:
    """Link-graph traversal with a deficit-scored frontier. Keeps facts, discards pages."""

    def __init__(self, deficit: Iterable[str], *, fetcher: PoliteFetcher | None = None,
                 min_score: float = 1.0, max_depth: int = 3, max_frontier: int = 200_000,
                 relations: tuple[str, ...] = ("used_for", "capable_of", "made_of")):
        self.deficit = {w.strip().lower() for w in deficit if w and w.strip()}
        self.covered: set[str] = set()
        self.fetcher = fetcher or PoliteFetcher()
        self.min_score = float(min_score)
        self.max_depth = int(max_depth)
        self.max_frontier = int(max_frontier)
        self.relations = relations
        self.seen: set[str] = set()
        self._heap: list[_Link] = []
        self.stats = {"pushed": 0, "skipped_low_score": 0, "skipped_seen": 0,
                      "skipped_shape": 0, "skipped_language": 0, "fetched": 0,
                      "facts": 0, "hosts": set()}

    # ---- the frontier ---------------------------------------------------------------------------
    def score(self, url: str, anchor_words: set[str]) -> tuple[float, str]:
        """How much does this link smell of something ATANOR cannot describe?

        A slug that IS a deficit word is the strongest signal a reference site can give -- that is
        literally the page about the thing. Anchor mentions are weaker and additive. A link that
        names nothing unknown scores zero and is not followed, which is what keeps the crawl from
        becoming a general one."""
        slug = _slug_words(url)
        want = self.deficit - self.covered
        hits_slug = slug & want
        hits_anchor = anchor_words & want
        s = 3.0 * len(hits_slug) + 1.0 * len(hits_anchor)
        # the last path segment being exactly a wanted word is the reference-page shape
        last = urllib.parse.urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1].lower()
        if last in want:
            s += 4.0
        why = ",".join(sorted(hits_slug | hits_anchor)[:4])
        return s, why

    def push(self, url: str, depth: int, anchor_words: set[str] | None = None) -> bool:
        if depth > self.max_depth or len(self._heap) >= self.max_frontier:
            return False
        url, _frag = urllib.parse.urldefrag(url)
        if not url.startswith(("http://", "https://")):
            self.stats["skipped_shape"] += 1
            return False
        if _SKIP_EXT.search(url) or _SKIP_PATH.search(url) or len(url) > 300:
            self.stats["skipped_shape"] += 1
            return False
        if not _english_host(urllib.parse.urlsplit(url).netloc):
            self.stats["skipped_language"] += 1
            return False
        if url in self.seen:
            self.stats["skipped_seen"] += 1
            return False
        s, why = self.score(url, anchor_words or set())
        if s < self.min_score:
            self.stats["skipped_low_score"] += 1
            return False
        self.seen.add(url)
        heapq.heappush(self._heap, _Link(-s, depth, url, why))
        self.stats["pushed"] += 1
        return True

    def seed(self, urls: Iterable[str]) -> int:
        """Seeds bypass the score floor: they are chosen, not discovered."""
        n = 0
        for u in urls:
            u, _ = urllib.parse.urldefrag(u)
            if u.startswith(("http://", "https://")) and u not in self.seen:
                self.seen.add(u)
                heapq.heappush(self._heap, _Link(-100.0, 0, u, "seed"))
                self.stats["pushed"] += 1
                n += 1
        return n

    # ---- the crawl -------------------------------------------------------------------------------
    def crawl(self, max_pages: int = 1000, wave: int = 64) -> Iterator[Page]:
        """Yield a Page per fetched url. `page.facts` is what persists; the html is already gone.

        FETCHED IN WAVES, AND THAT IS NOT A DETAIL. The first version popped one link, fetched it, and
        waited out the politeness delay before popping the next -- 0.87 pages/second no matter how many
        hosts were available, because a sequential caller makes a host-parallel fetcher pointless. It
        is the same built-but-not-wired failure this repository keeps producing, committed by the
        person who had just built the fetcher.

        A wave takes the top `wave` links by score, hands the whole set to `fetch_many`, and lets it
        partition by host. Throughput becomes hosts x 1 req/s as designed. Score order is preserved
        BETWEEN waves rather than within one, which is the right trade: a wave is small enough that the
        ordering barely differs, and the parallelism is worth orders of magnitude.

        Nothing accumulates: bodies are consumed inside the loop and dropped."""
        from packages.graph_scale.property_extraction import extract

        fetched = 0
        while self._heap and fetched < max_pages:
            batch = self._wave(min(wave, max_pages - fetched))
            if not batch:
                break
            by_url = {b.url: b for b in batch}
            for url, status, body in self.fetcher.fetch_many([b.url for b in batch]):
                link = by_url.get(url) or _Link(0.0, 0, url)
                fetched += 1
                self.stats["fetched"] += 1
                host = urllib.parse.urlsplit(url).netloc
                self.stats["hosts"].add(host)
                page = Page(url=url, host=host, depth=link.depth, score=-link.neg_score)
                if status != 200 or not body:
                    yield page
                    continue
                yield self._read(page, body, link, extract)

    def _wave(self, size: int, per_host: int = 64) -> list["_Link"]:
        """Take the next `size` links, optionally spread across hosts. The default barely spreads.

        A wave lasts as long as its most-loaded host, because within a host requests are serial, and
        link graphs are host-clustered -- a Wiktionary page links overwhelmingly back to Wiktionary.
        So capping links per host per wave raises PAGES per second, and I set the cap to 3 on that
        reasoning and measured the wrong number.

        The sweep, 100 pages per arm, identical seeds:

            per_host   pages/s   facts/s   hosts   facts   covered
            3            5.42      0.33      31       6        6
            8            4.17      0.63      17      15       12
            16           2.94      0.82       5      28       14
            64           2.89      1.07       4      37       17

        facts/second rises monotonically as the balancing is RELAXED. Value is concentrated: a few
        reference sites hold almost every page worth reading, so a wave spread over 31 hosts spends 29
        of its slots on academic landing pages and app-store listings. Pages per second was never the
        goal; it was the proxy I reached for, and it pointed the opposite way.

        The mechanism stays because it should pay off later -- once the crawl has discovered many
        reference-QUALITY hosts, spreading costs nothing and parallelises. It is off by default until a
        measurement says otherwise. Links not taken stay on the heap with their scores."""
        taken: list[_Link] = []
        held: list[_Link] = []
        counts: dict[str, int] = {}
        while self._heap and len(taken) < size:
            link = heapq.heappop(self._heap)
            host = urllib.parse.urlsplit(link.url).netloc
            if counts.get(host, 0) < per_host:
                counts[host] = counts.get(host, 0) + 1
                taken.append(link)
            else:
                held.append(link)
                if len(held) > size * 8:      # the heap is one host deep; stop scanning for diversity
                    break
        for link in held:
            heapq.heappush(self._heap, link)
        return taken

    def _read(self, page: "Page", body: bytes, link: "_Link", extract) -> "Page":
        """Links out, facts in, page gone. Split out so `crawl` reads as the schedule it is."""
        url = page.url
        # 1) links out, scored and pushed. Anchor text is the cheapest relevance signal there is.
        for m in _A.finditer(body):
            href = m.group(1).decode("utf-8", "ignore")
            nxt = urllib.parse.urljoin(url, href)
            page.links_found += 1
            self.push(nxt, link.depth + 1, _anchor_words(m.group(2)))
        # 2) facts in, page out. The entity is taken from the url slug: on a reference site the
        #    page IS about its slug, which is the same assumption the direct-address fetcher makes.
        slug = urllib.parse.urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
        entity = re.sub(r"[_\-]+", " ", urllib.parse.unquote(slug)).strip().lower()
        if entity and re.fullmatch(r"[a-z][a-z ]{1,40}", entity):
            text = _TAG.sub(b" ", body).decode("utf-8", "ignore")
            text = re.sub(r"\s+", " ", text)
            hits = []
            for sentence in re.split(r"(?<=[.!?]) ", text):
                if entity not in sentence.lower() or len(sentence) > 400:
                    continue
                for rel, obj in extract(entity, sentence):
                    if rel in self.relations:
                        hits.append((entity, rel, obj))
            page.facts = hits[:40]
            self.stats["facts"] += len(page.facts)
            if page.facts:
                self.covered.add(entity)          # shrinks `want`, so the frontier re-scores down
            page.words_hit = tuple(sorted({f[0] for f in page.facts}))
        del body                                       # explicit: the page does not outlive the wave
        return page

    def report(self) -> dict:
        s = dict(self.stats)
        s["hosts"] = sorted(s["hosts"])
        s["n_hosts"] = len(s["hosts"])
        s["frontier_remaining"] = len(self._heap)
        s["deficit_total"] = len(self.deficit)
        s["deficit_covered"] = len(self.covered & self.deficit)
        s["fetcher"] = self.fetcher.stats()
        return s
