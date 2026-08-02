# -*- coding: utf-8 -*-
"""The shared fetcher: parallel ACROSS hosts, one-at-a-time WITHIN a host.

    from packages.knowledge_acquisition.polite_fetch import PoliteFetcher
    f = PoliteFetcher()
    for url, status, body in f.fetch_many(urls):     # yields as they arrive, nothing accumulates
        ...

WHY IT IS SHARED. Two very different jobs need exactly this and nothing more: the fact harvester wants
HTML to extract from, and the perception corpus wants images and their captions. Building the politeness,
the robots handling and the blocked-host memory twice is how this repository ends up with a hundred and
thirty-three of everything, so it is built once and both import it.

THE THROUGHPUT IDENTITY, which is the whole design:

    pages per second = number of DISTINCT HOSTS  x  1 request per second per host

Parallelism comes from host DIVERSITY, not from request rate. Fifty hosts is fifty pages a second while
every individual server sees one polite request a second. That matters twice over, because the consensus
gate also counts distinct domains -- the thing that makes the crawl fast is the same thing that makes a
fact verifiable. One lever, two requirements.

MEASURED AND CORRECTED, 2026-07-31. A first test pulled 40 pages across 5 hosts in 3.9 s and called it
10 pages/second. Per host that was 2.03 requests/second, which is over the floor this module promises:
pages came back in 0.44 s median, so a single worker per host was enough to exceed it. The fix is explicit
spacing rather than trusting the worker count, and `stats()` reports the achieved per-host rate so the
violation is visible instead of inferred.

ROBOTS IS FETCHED WITH OUR OWN USER AGENT, and that correction is load-bearing.
`RobotFileParser.read()` uses Python's default agent; a site that 403s that agent makes the parser report
DISALLOW EVERYTHING, which is documented, safe, and in our case simply wrong -- all six reference domains
allow these paths when robots.txt is asked for politely. Reading the false result nearly got Wikipedia
recorded as uncrawlable. A robots.txt that genuinely cannot be read is treated as DISALLOWED; it is never
guessed at.

A 403 or 429 shuts a host for the run. Retrying a closed door is abuse, not persistence.

NOTHING IS ACCUMULATED. `fetch_many` is a generator: the caller consumes each body and lets it go. The
architecture this serves keeps EXTRACTED STRUCTURE and discards pages -- 396,657 facts occupy 16 MB where
the pages behind them are hundreds of gigabytes -- so a fetcher that buffered its results would defeat
the reason it exists.
"""
from __future__ import annotations

import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Iterable, Iterator

USER_AGENT = "atanor-research/0.1 (+local knowledge acquisition; polite, robots-respecting)"
MIN_INTERVAL_S = 1.0
TIMEOUT_S = 15.0
MAX_BYTES = 500_000


@dataclass
class HostState:
    """Everything the run learned about one host, so it is never rediscovered."""

    delay: float = MIN_INTERVAL_S
    robots: urllib.robotparser.RobotFileParser | None = None
    robots_readable: bool = False
    blocked: bool = False
    requests: int = 0
    ok: int = 0
    first_request: float = 0.0
    last_request: float = 0.0

    def rate(self) -> float:
        span = self.last_request - self.first_request
        return (self.requests - 1) / span if span > 0 and self.requests > 1 else 0.0


@dataclass
class PoliteFetcher:
    user_agent: str = USER_AGENT
    min_interval_s: float = MIN_INTERVAL_S
    timeout_s: float = TIMEOUT_S
    max_bytes: int = MAX_BYTES
    obey_robots: bool = True
    hosts: dict[str, HostState] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ---- per-host bookkeeping ------------------------------------------------------------------
    def _state(self, host: str) -> HostState:
        with self._lock:
            st = self.hosts.get(host)
            if st is None:
                st = self.hosts[host] = HostState(delay=self.min_interval_s)
            return st

    def _load_robots(self, host: str, st: HostState) -> None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(f"https://{host}/robots.txt",
                                         headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                rp.parse(r.read(400_000).decode("utf-8", "ignore").splitlines())
            st.robots_readable = True
            d = rp.crawl_delay(self.user_agent)
            st.delay = max(self.min_interval_s, float(d) if d else 0.0)
        except Exception:
            st.robots_readable = False        # unreadable -> disallowed, never guessed
        st.robots = rp

    def allowed(self, url: str) -> bool:
        if not self.obey_robots:
            return True
        host = urllib.parse.urlsplit(url).netloc
        st = self._state(host)
        if st.robots is None:
            self._load_robots(host, st)
        if not st.robots_readable:
            return False
        try:
            return bool(st.robots.can_fetch(self.user_agent, url))
        except Exception:
            return False

    # ---- one request, spaced explicitly --------------------------------------------------------
    def fetch(self, url: str) -> tuple[str, object, bytes]:
        host = urllib.parse.urlsplit(url).netloc
        st = self._state(host)
        if st.blocked:
            return url, "blocked", b""
        if not self.allowed(url):
            return url, "robots", b""
        # EXPLICIT spacing. Relying on one-worker-per-host is what let the first measurement run at
        # 2.03 req/s against a 1.0 floor: a fast server simply answers before the next tick.
        wait = st.delay - (time.time() - st.last_request)
        if st.last_request and wait > 0:
            time.sleep(wait)
        if not st.first_request:
            st.first_request = time.time()
        st.last_request = time.time()
        st.requests += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                body = r.read(self.max_bytes)
            st.ok += 1
            return url, 200, body
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                st.blocked = True             # a shut door stays shut for this run
            return url, exc.code, b""
        except Exception as exc:
            return url, type(exc).__name__, b""

    # ---- many requests, one worker per host ----------------------------------------------------
    def fetch_many(self, urls: Iterable[str], *, max_hosts: int = 64) -> Iterator[tuple]:
        """Yield (url, status, body) as they arrive. A generator on purpose: nothing is buffered.

        Work is partitioned BY HOST and each host gets exactly one worker, so within a host requests
        are serial and spaced, while across hosts they overlap. Throughput therefore scales with how
        many distinct hosts the caller supplies, which is the property the whole design rests on."""
        by_host: dict[str, list[str]] = {}
        for u in urls:
            by_host.setdefault(urllib.parse.urlsplit(u).netloc, []).append(u)
        out: queue.Queue = queue.Queue()
        hosts = list(by_host)[:max_hosts]
        overflow = [u for h in list(by_host)[max_hosts:] for u in by_host[h]]

        def work(host: str) -> None:
            try:
                for u in by_host[host]:
                    out.put(self.fetch(u))
            finally:
                out.put(("__done__", host, b""))

        threads = [threading.Thread(target=work, args=(h,), daemon=True) for h in hosts]
        for t in threads:
            t.start()
        done = 0
        while done < len(hosts):
            item = out.get()
            if item[0] == "__done__":
                done += 1
                continue
            yield item
        for u in overflow:                     # hosts past the cap, served after the parallel set
            yield self.fetch(u)

    # ---- what the run learned -------------------------------------------------------------------
    def stats(self) -> dict:
        """Per-host outcome AND achieved request rate, so a politeness violation is visible.

        `worst_rate` above `min_interval_s` means this fetcher broke its own promise, which is the
        failure the first measurement made and did not notice."""
        per = {h: {"requests": s.requests, "ok": s.ok, "blocked": s.blocked,
                   "robots_readable": s.robots_readable, "delay_s": round(s.delay, 2),
                   "achieved_req_per_s": round(s.rate(), 3)}
               for h, s in self.hosts.items()}
        rates = [v["achieved_req_per_s"] for v in per.values() if v["requests"] > 1]
        return {"hosts": per, "n_hosts": len(per),
                "worst_req_per_s": max(rates) if rates else 0.0,
                "politeness_floor": 1.0 / self.min_interval_s,
                "within_floor": (max(rates) if rates else 0.0) <= (1.0 / self.min_interval_s) + 1e-6}
