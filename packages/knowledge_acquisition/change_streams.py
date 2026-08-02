# -*- coding: utf-8 -*-
"""The web tells us what changed, so the graph knows which of its own branches are rotting.

    from packages.knowledge_acquisition.change_streams import ChangeStreams
    for ev in ChangeStreams().listen(seconds=60):
        ...   # ev.entity changed at ev.at, according to ev.source

REAL-TIME IS NOT CRAWLING FASTER. It is knowing WHAT changed without asking. Publishers already announce
their own changes, on open standards nobody rate-limits, and measured 2026-07-31 while every SearXNG
upstream was suspended:

    Wikipedia EventStreams   a live edit reached us 8.1 seconds after it happened, SSE, no limit
    GDELT                    the global news index is published on a ~15 minute cadence
    RSS with conditional GET arstechnica and hnrss answer 304 Not Modified -- a poll costing no bytes
    RSS without ETag         bbc and nytimes re-send, but a feed is a few KB

That is the whole real-time layer, and none of it is a search API. What it gives is not answers; it is
NAMES -- this entity moved. The graph then decides whether it holds a fact about that entity, and only
then does anything get fetched.

WHY THIS IS THE LIVING PART. A general engine re-crawls by page popularity because it does not know what
it extracted from a page. ATANOR holds typed facts and knows which predicates the world changes -- price,
availability, ratingValue, startDate -- so it can re-fetch a fact at ITS OWN rate instead of re-crawling
the web at one rate. A stable fact is fetched once and never again. That asymmetry is not an optimisation;
it is the only reason a single machine can keep a live graph at all.

WHAT THIS DOES NOT DO. It does not discover entities ATANOR has never heard of -- a change event about
something unknown is dropped, because the alternative is following the whole news cycle. It does not
cover sources that publish no feed. And a stream saying an entity changed is not evidence of WHAT it
changed to: the fetch still happens, the extractor still runs, the consensus gate still decides.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Iterator

USER_AGENT = "atanor-research/0.1 (+local knowledge acquisition; polite)"
WIKI_STREAM = "https://stream.wikimedia.org/v2/stream/recentchange"
GDELT_LAST = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
DEFAULT_FEEDS = (
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://hnrss.org/frontpage",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_ITEM = re.compile(r"<(?:item|entry)\b.*?</(?:item|entry)>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class ChangeEvent:
    entity: str
    source: str          # wikipedia | rss:<host> | gdelt
    at: float
    detail: str = ""


@dataclass
class _FeedState:
    etag: str | None = None
    last_modified: str | None = None
    seen: set = field(default_factory=set)
    polls: int = 0
    not_modified: int = 0


@dataclass
class ChangeStreams:
    """Change NAMES from open feeds. Nothing here fetches a page or asserts a fact."""

    feeds: tuple[str, ...] = DEFAULT_FEEDS
    user_agent: str = USER_AGENT
    interested: Callable[[str], bool] | None = None   # e.g. `lambda e: e in property_table`
    feed_state: dict = field(default_factory=dict)
    stats: dict = field(default_factory=lambda: {"wikipedia": 0, "rss": 0, "gdelt": 0,
                                                 "dropped_uninteresting": 0, "bytes": 0,
                                                 "poll_304": 0, "polls": 0})

    # ---- the one filter that keeps this bounded -------------------------------------------------
    def _emit(self, ev: ChangeEvent) -> ChangeEvent | None:
        """An event about something ATANOR holds no fact about is dropped.

        Without this the loop becomes a news reader: Wikipedia alone edits several times a second and
        almost none of it touches anything in the graph. The filter is what turns a firehose into a
        staleness signal."""
        if self.interested is not None and not self.interested(ev.entity):
            self.stats["dropped_uninteresting"] += 1
            return None
        return ev

    # ---- wikipedia: genuinely live, 8 second lag measured ----------------------------------------
    def wikipedia(self, seconds: float = 30.0) -> Iterator[ChangeEvent]:
        req = urllib.request.Request(WIKI_STREAM, headers={"User-Agent": self.user_agent})
        deadline = time.time() + seconds
        try:
            with urllib.request.urlopen(req, timeout=max(5.0, seconds)) as r:
                buf = b""
                while time.time() < deadline:
                    chunk = r.read(4096)
                    if not chunk:
                        break
                    self.stats["bytes"] += len(chunk)
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.startswith(b"data: "):
                            continue
                        try:
                            d = json.loads(line[6:].decode("utf-8", "ignore"))
                        except Exception:
                            continue
                        if d.get("wiki") != "enwiki" or d.get("type") not in ("edit", "new"):
                            continue
                        title = str(d.get("title") or "").strip().lower()
                        if not title or ":" in title:      # namespaces are not things
                            continue
                        self.stats["wikipedia"] += 1
                        ev = self._emit(ChangeEvent(title, "wikipedia",
                                                    float(d.get("timestamp") or time.time()),
                                                    str(d.get("comment") or "")[:120]))
                        if ev:
                            yield ev
        except Exception:
            return

    # ---- rss: cheap when the server supports conditional GET --------------------------------------
    def poll_feeds(self) -> Iterator[ChangeEvent]:
        for url in self.feeds:
            st = self.feed_state.setdefault(url, _FeedState())
            headers = {"User-Agent": self.user_agent}
            if st.etag:
                headers["If-None-Match"] = st.etag
            elif st.last_modified:
                headers["If-Modified-Since"] = st.last_modified
            st.polls += 1
            self.stats["polls"] += 1
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                            timeout=20) as r:
                    body = r.read(400_000)
                    self.stats["bytes"] += len(body)
                    st.etag = r.headers.get("ETag") or st.etag
                    st.last_modified = r.headers.get("Last-Modified") or st.last_modified
            except urllib.error.HTTPError as exc:
                if exc.code == 304:
                    st.not_modified += 1
                    self.stats["poll_304"] += 1
                continue
            except Exception:
                continue
            host = urllib.parse.urlsplit(url).netloc
            for item in _ITEM.findall(body.decode("utf-8", "ignore")):
                m = _TITLE.search(item)
                if not m:
                    continue
                title = re.sub(r"\s+", " ", _TAG.sub("", m.group(1))).strip().lower()
                if not title or title in st.seen:
                    continue
                st.seen.add(title)
                self.stats["rss"] += 1
                ev = self._emit(ChangeEvent(title, f"rss:{host}", time.time()))
                if ev:
                    yield ev

    # ---- gdelt: the world news index, ~15 minute cadence -------------------------------------------
    def gdelt_slice(self) -> str | None:
        """The newest published slice id, or None. One tiny fetch; the slice itself is opt-in."""
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(GDELT_LAST, headers={"User-Agent": self.user_agent}),
                    timeout=20) as r:
                txt = r.read(4000).decode("utf-8", "ignore")
            m = re.search(r"/(\d{14})\.", txt)
            if m:
                self.stats["gdelt"] += 1
                return m.group(1)
        except Exception:
            pass
        return None

    # ---- one loop over everything ------------------------------------------------------------------
    def listen(self, seconds: float = 60.0) -> Iterator[ChangeEvent]:
        yield from self.poll_feeds()
        yield from self.wikipedia(seconds=seconds)

    def report(self) -> dict:
        s = dict(self.stats)
        s["feeds"] = {u: {"polls": v.polls, "not_modified": v.not_modified, "titles": len(v.seen)}
                      for u, v in self.feed_state.items()}
        s["kb"] = round(s.pop("bytes", 0) / 1024, 1)
        return s
