# -*- coding: utf-8 -*-
"""Evidence with NO search API: the entity IS the address.

    from packages.knowledge_acquisition.direct_fetch import DirectFetchEvidence
    DirectFetchEvidence().documents("trowel", "used for")   # -> [(url, text), ...]

WHY THIS EXISTS, and it is the gap the owner named. A precomputed table over frozen dumps is retrieval,
not acquisition: it answers faster from what ATANOR already has and gets nothing new. If the only path to
new knowledge is a search API, and search APIs suspend us inside an hour of continuous querying -- which
they measurably did on 2026-07-31 -- then the whole apparatus is one blocked provider away from useless.

THE THING THAT SEPARATES IS THAT SEARCH AND FETCH ARE DIFFERENT RESOURCES. A search API is a scarce,
commercially defended index; a page is a URL that its owner serves to anyone polite. What search buys is
DISCOVERY -- which url answers this question -- and that is precisely the part ATANOR does not need,
because the shape parser has already produced the entity. Reference sites address their content by
headword, so the entity IS the address:

    trowel -> en.wiktionary.org/wiki/trowel, dictionary.com/browse/trowel, merriam-webster.com/dictionary/trowel

Measured while every SearXNG upstream was suspended, no search API touched: six independent domains
answered directly. Three of them are outside Wikimedia, which matters because the consensus floor counts
distinct sources and Wikipedia plus Wiktionary are two works in one ecosystem.

    open (200)     en.wikipedia.org  en.wiktionary.org  commons.wikimedia.org
                   dictionary.com    merriam-webster.com  vocabulary.com
    blocked (403)  thefreedictionary.com  collinsdictionary.com  britannica.com (partly)

THE 403s ARE THE HONEST HALF. "Unlimited" is false: some doors are shut and stay shut, and a fetcher that
retried them would be abuse rather than persistence. A blocked domain is recorded and never retried in
the same run.

ROBOTS IS A HARD RULE HERE, and getting it right took a correction worth keeping. `RobotFileParser.read()`
fetches robots.txt with Python's default user agent, and a site that 403s that agent makes the parser
report DISALLOW EVERYTHING -- documented behaviour, safe, and in our case simply wrong: all six domains
allow these paths when robots.txt is fetched with our own agent. So robots.txt is fetched with the same
UA the crawl uses, and a robots.txt that genuinely cannot be read is treated as DISALLOWED rather than
guessed at.

Politeness is per-domain and unconditional: one request at a time, a floor between requests to the same
host, robots' own crawl-delay honoured when it is larger, and an identifying user agent. This is not a
crawler that walks the web; it fetches the few pages that address one known headword.
"""
from __future__ import annotations

import re
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field

USER_AGENT = "atanor-research/0.1 (+local knowledge acquisition; polite, robots-respecting)"
MIN_INTERVAL_S = 1.0            # per host, and never lowered by anything a site says
TIMEOUT_S = 12.0
MAX_BYTES = 400_000

# headword -> url, for sites that address content BY headword. No search step exists in this table;
# that is the whole point. Wikipedia/Wiktionary/Commons are one ecosystem and count as such.
URL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("en.wikipedia.org", "https://en.wikipedia.org/wiki/{Title}"),
    ("en.wiktionary.org", "https://en.wiktionary.org/wiki/{word}"),
    ("www.dictionary.com", "https://www.dictionary.com/browse/{word}"),
    ("www.merriam-webster.com", "https://www.merriam-webster.com/dictionary/{word}"),
    ("www.vocabulary.com", "https://www.vocabulary.com/dictionary/{word}"),
)

_TAG = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
_ANY_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _visible_text(html: str) -> str:
    return _WS.sub(" ", _ANY_TAG.sub(" ", _TAG.sub(" ", html))).strip()


@dataclass
class _HostState:
    last_request: float = 0.0
    robots: urllib.robotparser.RobotFileParser | None = None
    readable: bool = False
    blocked: bool = False           # a 403/429 seen this run; never retried
    delay: float = MIN_INTERVAL_S


@dataclass
class DirectFetchEvidence:
    """An EvidenceSource that constructs urls from the entity and fetches them. No search provider."""

    patterns: tuple[tuple[str, str], ...] = URL_PATTERNS
    user_agent: str = USER_AGENT
    min_interval_s: float = MIN_INTERVAL_S
    body_sentences: int = 8
    _hosts: dict = field(default_factory=dict)
    _lock: object = field(default_factory=threading.Lock)

    def _state(self, host: str) -> _HostState:
        with self._lock:
            if host not in self._hosts:
                self._hosts[host] = _HostState()
            return self._hosts[host]

    def _robots_ok(self, host: str, url: str) -> bool:
        """True only when robots.txt was READ and permits this path. Unreadable means no."""
        st = self._state(host)
        if st.robots is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                req = urllib.request.Request(f"https://{host}/robots.txt",
                                             headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                    rp.parse(r.read().decode("utf-8", "ignore").splitlines())
                st.readable = True
            except Exception:
                st.readable = False          # cannot read -> treat as disallowed, never guess
            st.robots = rp
            if st.readable:
                d = rp.crawl_delay(self.user_agent)
                st.delay = max(self.min_interval_s, float(d) if d else 0.0)
        if not st.readable:
            return False
        try:
            return bool(st.robots.can_fetch(self.user_agent, url))
        except Exception:
            return False

    def _wait(self, host: str) -> None:
        st = self._state(host)
        gap = time.time() - st.last_request
        if gap < st.delay:
            time.sleep(st.delay - gap)
        st.last_request = time.time()

    def _fetch(self, host: str, url: str) -> str:
        st = self._state(host)
        if st.blocked or not self._robots_ok(host, url):
            return ""
        self._wait(host)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                return r.read(MAX_BYTES).decode("utf-8", "ignore")
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                # a shut door stays shut for this run. Retrying is abuse, not persistence.
                st.blocked = True
            return ""
        except Exception:
            return ""

    def documents(self, entity: str, rel_norm: str, query: str = "") -> list[tuple[str, str]]:
        from .evidence import _clean_live_document

        word = re.sub(r"\s+", "_", entity.strip().lower())
        title = word[:1].upper() + word[1:]
        if not re.fullmatch(r"[a-z0-9_\-]{2,60}", word):
            return []
        out: list[tuple[str, str]] = []
        for host, pattern in self.patterns:
            url = pattern.format(word=word, Title=title)
            html = self._fetch(host, url)
            if not html:
                continue
            text = _clean_live_document("", _visible_text(html)[:MAX_BYTES], entity,
                                        self.body_sentences)
            if text:
                out.append((url, text))
        return out

    def report(self) -> dict:
        """What the run learned about each host — which is data the next run should not rediscover."""
        return {h: {"robots_readable": s.readable, "blocked": s.blocked, "delay_s": s.delay}
                for h, s in self._hosts.items()}
