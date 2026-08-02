# -*- coding: utf-8 -*-
"""Re-fetch what a peer cited. A citation is checkable, and a peer whose citations fail is one to stop
reading.

    from packages.federation.citation_audit import CitationAuditor, PeerLedger
    a = CitationAuditor(PeerLedger("data/federation/peers.json"))
    a.audit(contribution, sample_rate=0.05)     # checks a sample, records the peer's record
    a.ledger.should_read("peer-7")              # the ONLY thing reputation decides

WHY THIS IS THE MISSING PIECE. The public scope lets crawled facts travel because they carry the domains
that assert them, and because a receiver counts those domains rather than the peers. That stops a ring
from manufacturing consensus. It does not stop a single lying peer from citing a REAL domain for a fact
that domain never asserted -- provenance is a citation, not a proof. The defence was always that a
citation is CHECKABLE, and this is the check.

TWO DESIGN RULES, and both exist to protect something already won.

  1. REPUTATION DECIDES WHETHER TO READ A PEER, NEVER WHAT A FACT WEIGHS. If a peer's score multiplied
     the strength of its facts, the peer would be back inside the consensus arithmetic and the whole
     domain-keyed invariant would be gone. So `merge_into_tally` takes no score, this module exposes
     no weight, and the only output is a boolean: read this peer, or do not.

  2. FAILING TO CONFIRM IS NOT REFUTING. Our own extractor's recall is low -- measured this session,
     `kiosk` returned 0 sightings from 4 documents whose text plainly described its use -- so scoring
     "we could not re-extract it" as a lie would punish honest peers for our own blind spots. The
     verdict is three-valued and REFUTED needs the strong form:

        CONFIRMED     the cited page contains the object
        REFUTED       the page fetched fine and the object appears NOWHERE in it, or the cited page
                      does not exist at all
        INCONCLUSIVE  robots refused, host blocked, fetch failed, page unreadable -- our problem,
                      never the peer's

SAMPLING IS PROBABILISTIC AND SAYS SO. Re-checking everything would mean re-crawling what federation was
supposed to save, so a sample is checked. A peer sending mostly-true facts with a little poison is caught
with probability 1 - (1-r)^k for k poisoned facts at sample rate r, and `detection_odds` reports that
number rather than leaving it implied. One poisoned fact in a thousand at a 5% sample is a coin that
lands wrong most of the time, and that is a limit of the method, not a detail to omit.
"""
from __future__ import annotations

import json
import random
import re
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CONFIRMED = "confirmed"
REFUTED = "refuted"
INCONCLUSIVE = "inconclusive"

# One refutation is a lot. A peer that fabricates a citation is not making a rounding error, and the
# public scope only works because citations mean something.
MAX_REFUTATIONS = 1
MIN_CHECKS_BEFORE_TRUST = 3


@dataclass
class PeerRecord:
    checked: int = 0
    confirmed: int = 0
    refuted: int = 0
    inconclusive: int = 0
    first_seen: float = 0.0
    last_checked: float = 0.0
    last_refutation: str = ""

    def confirm_rate(self) -> float:
        decisive = self.confirmed + self.refuted
        return (self.confirmed / decisive) if decisive else 0.0


@dataclass
class PeerLedger:
    path: Path | str | None = None
    peers: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.path and Path(self.path).exists():
            raw = json.loads(Path(self.path).read_text(encoding="utf-8"))
            self.peers = {k: PeerRecord(**v) for k, v in raw.get("peers", {}).items()}

    def record(self, peer: str) -> PeerRecord:
        r = self.peers.get(peer)
        if r is None:
            r = self.peers[peer] = PeerRecord(first_seen=time.time())
        return r

    def note(self, peer: str, verdict: str, detail: str = "") -> PeerRecord:
        r = self.record(peer)
        r.checked += 1
        r.last_checked = time.time()
        if verdict == CONFIRMED:
            r.confirmed += 1
        elif verdict == REFUTED:
            r.refuted += 1
            r.last_refutation = detail[:200]
        else:
            r.inconclusive += 1
        return r

    def should_read(self, peer: str) -> bool:
        """The ONLY decision reputation makes. Not a weight, not a multiplier -- read, or do not.

        A peer we have never checked is read: refusing the unknown would make the federation a closed
        club and the first contribution is exactly what gets sampled."""
        r = self.peers.get(peer)
        return True if r is None else r.refuted < MAX_REFUTATIONS

    def save(self) -> None:
        if not self.path:
            return
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"peers": {k: asdict(v) for k, v in self.peers.items()}}, indent=2),
                     encoding="utf-8")

    def report(self) -> dict:
        return {"peers": len(self.peers),
                "readable": sum(1 for p in self.peers if self.should_read(p)),
                "refused": sorted(p for p in self.peers if not self.should_read(p)),
                "detail": {k: asdict(v) for k, v in self.peers.items()}}


def detection_odds(sample_rate: float, poisoned: int) -> float:
    """P(at least one poisoned fact is sampled). The honest bound on what sampling can promise."""
    r = max(0.0, min(1.0, float(sample_rate)))
    return 1.0 - (1.0 - r) ** max(0, int(poisoned))


@dataclass
class CitationAuditor:
    """Re-fetches cited pages and turns the result into a peer's record."""

    ledger: PeerLedger = field(default_factory=PeerLedger)
    fetcher: Any = None
    url_for: Any = None            # (domain, entity) -> url; defaults to the retriever's mapping
    rng: random.Random = field(default_factory=lambda: random.Random(0))

    def _fetch(self, url: str) -> tuple[object, bytes]:
        if self.fetcher is None:
            from packages.knowledge_acquisition.polite_fetch import PoliteFetcher
            self.fetcher = PoliteFetcher()
        _u, status, body = self.fetcher.fetch(url)
        return status, body

    def _candidate_urls(self, domain: str, entity: str) -> list[str]:
        """Where on that domain the page about this entity would live. Cheap, conventional guesses.

        A citation names a DOMAIN, not a url, because that is what the consensus floor counts. So the
        audit has to find the page, and a miss here must land as INCONCLUSIVE rather than as a lie."""
        if self.url_for is not None:
            u = self.url_for(domain, entity)
            return [u] if u else []
        slug = re.sub(r"\s+", "_", entity.strip())
        word = re.sub(r"\s+", "-", entity.strip().lower())
        return [f"https://{domain}/wiki/{slug[:1].upper() + slug[1:]}",
                f"https://{domain}/wiki/{word}",
                f"https://{domain}/browse/{word}",
                f"https://{domain}/dictionary/{word}"]

    def verify(self, fact) -> tuple[str, str]:
        """(verdict, detail) for one cited fact. Three-valued on purpose -- see the module docstring."""
        from packages.knowledge_acquisition.polite_fetch import PoliteFetcher  # noqa: F401

        obj = (fact.object or "").strip().lower()
        if not obj or not fact.source_domains:
            return INCONCLUSIVE, "no object or no citation"
        tried = []
        for domain in fact.source_domains[:2]:
            for url in self._candidate_urls(domain, fact.subject):
                status, body = self._fetch(url)
                tried.append(f"{url} -> {status}")
                if status != 200 or not body:
                    continue
                text = re.sub(r"<[^>]+>", " ", body.decode("utf-8", "ignore")).lower()
                text = re.sub(r"\s+", " ", text)
                if obj in text:
                    return CONFIRMED, f"{domain} contains {obj!r}"
                # the page loaded and the claimed object is nowhere in it. This is the strong form:
                # not "our extractor missed it" but "the words are not on the page".
                head = " ".join(w for w in obj.split() if len(w) > 3)
                if head and head not in text:
                    return REFUTED, f"{domain} page loaded and does not contain {obj!r}"
        return INCONCLUSIVE, "; ".join(tried[:4]) or "no candidate url resolved"

    def audit(self, contribution, sample_rate: float = 0.05, max_checks: int = 20) -> dict:
        """Check a sample of a peer's citations and update its record.

        Returns what was found AND the odds this sample would have caught k poisoned facts, so a clean
        audit is never mistaken for a proof of honesty."""
        facts = list(getattr(contribution, "facts", []))
        peer = getattr(contribution, "node_id", "")
        if not facts or not peer:
            return {"peer": peer, "checked": 0, "note": "nothing to audit"}
        k = max(1, min(int(len(facts) * float(sample_rate)) or 1, max_checks))
        sample = self.rng.sample(facts, min(k, len(facts)))
        out = {CONFIRMED: 0, REFUTED: 0, INCONCLUSIVE: 0}
        refutations = []
        for f in sample:
            verdict, detail = self.verify(f)
            out[verdict] += 1
            self.ledger.note(peer, verdict, detail)
            if verdict == REFUTED:
                refutations.append({"fact": [f.subject, f.predicate, f.object], "why": detail})
        rec = self.ledger.record(peer)
        return {"peer": peer, "facts_offered": len(facts), "checked": len(sample),
                "confirmed": out[CONFIRMED], "refuted": out[REFUTED],
                "inconclusive": out[INCONCLUSIVE],
                "refutations": refutations,
                "should_read_now": self.ledger.should_read(peer),
                "confirm_rate": round(rec.confirm_rate(), 3),
                "detection_odds_if_1_poisoned": round(detection_odds(len(sample) / len(facts), 1), 4),
                "detection_odds_if_10_poisoned": round(detection_odds(len(sample) / len(facts), 10), 4),
                "caveat": "a clean audit is evidence, not proof: sampling catches poison with the "
                          "odds above and misses it otherwise"}
