# -*- coding: utf-8 -*-
"""The PUBLIC scope: crawled world facts may travel, and a peer can never become a source.

    from packages.federation.world_facts import WorldFactContribution, merge_into_tally
    c = WorldFactContribution.from_table(table, node_id="atanor-pc", limit=5000)
    c.sanitize()                       # provenance required, PII refused, personal refused
    merge_into_tally(tally, c)         # counts ORIGINAL domains, never the peer

CONSTITUTIONAL AMENDMENT, owner-authorised 2026-07-31. The federation constitution of 2026-07-22 reads
"federate STRUCTURE, not DATA", and `_DATA_CARRYING_KEYS` enforces it by rejecting any payload with a
`facts` or `triples` key. I proposed pooling crawled facts, the gate refused it, and the owner was asked
rather than routed around. The owner chose to add a PUBLIC SCOPE.

WHAT THE AMENDMENT DOES AND DOES NOT OPEN. It opens one lane, explicitly named, for facts that are
already public and can prove it. It does not touch the capability lane, which still rejects
`facts`/`triples`, and it does not touch layer 3 of the constitution: Personal -- subjectivity, felt
state, lived record, local grounding -- still NEVER merges. A fact about a trowel is a citation of a
public page. A fact about what this node did, felt, or was told is not, and the difference is provable
rather than intended: a public fact carries the DOMAINS that assert it, and one that cannot is refused.

THE INVARIANT THAT MAKES THIS SAFE, and everything else here exists to protect it:

    a receiving node counts ORIGINAL SOURCE DOMAINS, never peer identities

Five peers sending "trowel used_for spreading, seen at en.wiktionary.org" is ONE domain, not five. So a
ring of cooperating nodes cannot manufacture consensus, and a compromised node cannot promote its
inventions by repetition -- it can only ever contribute what its sources already said, and those sources
are named and checkable. That is the same domain-keyed property that already makes the local property
table safe to merge into ConsensusTally; federation inherits it rather than inventing a trust model.

WHAT A RECEIVER STILL DOES FOR ITSELF. It applies its OWN consensus floor, its own PII and harm gates,
and its own promotion gate. A federated fact arrives as evidence, exactly like a fetched page: it is not
promoted because a peer promoted it. Nothing here writes to a store.

WHAT THIS DOES NOT SOLVE. It does not verify that the peer actually read what it claims to have read --
provenance is a citation, not a proof, and a lying peer can cite a real domain for a fact that domain
never asserted. The defence is that the citation is CHECKABLE: a receiver that cares can re-fetch the
named url, and a peer whose citations fail re-check is a peer to stop reading. Building that reputation
loop is not done here and is named as missing rather than implied.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

PUBLIC_FACT_KIND = "world-fact"
MAX_FACTS_PER_CONTRIBUTION = 50_000
MAX_LEN = 200

# Predicates that describe the NODE rather than the world. These are the lived record the constitution
# protects, and they are refused in the public lane no matter how they are labelled.
PERSONAL_PREDICATES = frozenset({
    "felt", "feeling", "mood", "hormone", "self_relevance", "believed", "remembered", "intended",
    "decided", "experienced", "observed_by_me", "my", "owner", "operator", "user", "session",
    "conversation", "diary", "journal", "private", "local_grounding", "personhood",
})
_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$")


@dataclass(frozen=True)
class PublicFact:
    """One crawled fact WITH the domains that assert it. Provenance is not optional here."""

    subject: str
    predicate: str
    object: str
    source_domains: tuple[str, ...]
    observed_at: float = 0.0
    volatile: bool = False

    def key(self) -> tuple[str, str]:
        return (self.subject, self.predicate)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SanitizeReport:
    ok: bool
    kept: int
    dropped: dict[str, int] = field(default_factory=dict)
    sample_dropped: list = field(default_factory=list)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _domains_ok(domains: Iterable[str]) -> tuple[str, ...]:
    out = []
    for d in domains or ():
        d = _clean(d)
        if d.startswith(("http://", "https://")):
            d = urllib.parse.urlsplit(d).netloc
        if d and _DOMAIN.match(d) and d not in out:
            out.append(d)
    return tuple(out)


@dataclass
class WorldFactContribution:
    """Public facts offered to the federation. Sanitized before it travels, re-gated on arrival."""

    node_id: str
    facts: list = field(default_factory=list)
    made_at: float = field(default_factory=time.time)

    # ---- construction -----------------------------------------------------------------------------
    @staticmethod
    def from_table(table, node_id: str, limit: int = 10_000,
                   corpus_url=None) -> "WorldFactContribution":
        """Read a PropertyTable into public facts, mapping each corpus to the domain that asserts it.

        The corpus->domain mapping is imported, never re-declared: if the two ever disagreed about what
        domain a corpus is, a receiver would count one source as two and the floor would silently
        become one."""
        if corpus_url is None:
            from packages.atanor_index.retriever import corpus_url as _cu
            corpus_url = _cu
        facts: list[PublicFact] = []
        keys = getattr(table, "_keys", [])
        n = min(int(limit), len(keys))
        # the table is keyed by hash, so iterate its value arrays rather than trying to invert it
        for pos in range(n):
            try:
                rows = table._rows_at(pos)
            except Exception:
                continue
            by_obj: dict[str, list[str]] = {}
            for obj, corpus in rows:
                url = corpus_url(corpus, "")
                dom = urllib.parse.urlsplit(url).netloc if url else ""
                if dom:
                    by_obj.setdefault(obj, []).append(dom)
            for obj, doms in by_obj.items():
                facts.append(PublicFact("", "", obj, _domains_ok(doms)))
        return WorldFactContribution(node_id=node_id, facts=facts)

    @staticmethod
    def from_triples(node_id: str, triples: Iterable[tuple]) -> "WorldFactContribution":
        """(subject, predicate, object, domains[, observed_at, volatile]) -> a contribution."""
        out = []
        for t in triples:
            s, p, o, doms = t[0], t[1], t[2], t[3]
            at = float(t[4]) if len(t) > 4 else 0.0
            vol = bool(t[5]) if len(t) > 5 else False
            out.append(PublicFact(_clean(s), _clean(p), _clean(o), _domains_ok(doms), at, vol))
        return WorldFactContribution(node_id=node_id, facts=out)

    # ---- the gate ----------------------------------------------------------------------------------
    def sanitize(self) -> SanitizeReport:
        """Keep only facts that are public, attributed, and not about this node.

        Every rejection reason is counted rather than silently dropped, because a lane that quietly
        discards most of what it is given looks identical to one that is working."""
        from packages.wild_web import is_harmful, is_pii

        kept: list[PublicFact] = []
        dropped: dict[str, int] = {}
        sample: list = []

        def drop(reason: str, f: PublicFact) -> None:
            dropped[reason] = dropped.get(reason, 0) + 1
            if len(sample) < 8:
                sample.append({"reason": reason, "fact": [f.subject, f.predicate, f.object]})

        for f in self.facts[:MAX_FACTS_PER_CONTRIBUTION]:
            if not f.subject or not f.predicate or not f.object:
                drop("incomplete", f)
                continue
            if len(f.subject) > MAX_LEN or len(f.object) > MAX_LEN:
                drop("too_long", f)
                continue
            if not f.source_domains:
                # THE core rule: a fact that cannot say who asserts it is indistinguishable from an
                # invention, and it is exactly what the constitution kept out
                drop("no_provenance", f)
                continue
            if f.predicate in PERSONAL_PREDICATES or any(
                    f.predicate.startswith(p + "_") for p in PERSONAL_PREDICATES):
                drop("personal_predicate", f)
                continue
            blob = f"{f.subject} {f.object}"
            if is_pii(blob) or is_harmful(blob):
                drop("pii_or_harm", f)
                continue
            kept.append(f)
        self.facts = kept
        return SanitizeReport(ok=bool(kept), kept=len(kept), dropped=dropped, sample_dropped=sample)

    def digest(self) -> str:
        canon = json.dumps([[f.subject, f.predicate, f.object, list(f.source_domains)]
                            for f in self.facts], sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {"kind": PUBLIC_FACT_KIND, "node_id": self.node_id, "made_at": self.made_at,
                "digest": self.digest(),
                "facts": [f.as_dict() for f in self.facts]}

    @staticmethod
    def from_dict(d: dict) -> "WorldFactContribution":
        c = WorldFactContribution(node_id=str(d.get("node_id") or ""),
                                  made_at=float(d.get("made_at") or 0.0))
        c.facts = [PublicFact(_clean(x.get("subject")), _clean(x.get("predicate")),
                              _clean(x.get("object")), _domains_ok(x.get("source_domains") or ()),
                              float(x.get("observed_at") or 0.0), bool(x.get("volatile")))
                   for x in (d.get("facts") or [])]
        return c


# ---- the receiving side -------------------------------------------------------------------------
def merge_into_tally(tally, contribution: "WorldFactContribution", *, entity: str = "",
                     predicate: str = "") -> dict:
    """Add a peer's facts to a local ConsensusTally as their ORIGINAL DOMAINS. Never as the peer.

    This function is the whole safety argument in code. The tally keys evidence by domain, so feeding
    it `https://<original domain>/` means N peers asserting the same sourced fact collapse to the
    number of DISTINCT SOURCES they cite -- which is what the floor was always counting."""
    added = 0
    peers_seen = set()
    for f in contribution.facts:
        if entity and f.subject != entity:
            continue
        if predicate and f.predicate != predicate:
            continue
        for dom in f.source_domains:
            tally.add(f.object, f"https://{dom}/")
            added += 1
        peers_seen.add(contribution.node_id)
    return {"sightings_added": added, "peers": sorted(peers_seen),
            "note": "domains counted, peers not"}


def peer_flood_check(tally_factory, fact: tuple, n_peers: int, floor: int = 2) -> dict:
    """Prove the invariant instead of asserting it: N peers citing ONE domain must not reach the floor.

    Kept as a callable rather than only a test so the property can be re-checked wherever the merge is
    used, the same way reject_reason_for_facts keeps the old boundary executable."""
    s, p, o, dom = fact
    doms = list(dom) if isinstance(dom, (list, tuple)) else [dom]   # a list, wrapped once, not twice
    tally = tally_factory()
    for i in range(n_peers):
        c = WorldFactContribution.from_triples(f"peer-{i}", [(s, p, o, doms)])
        c.sanitize()
        merge_into_tally(tally, c)
    verdict = tally.resolve()
    # COUNT FROM THE TALLY, NOT THE VERDICT. `resolve()` returns None below the floor, so reading
    # n_domains off the verdict reports 0 for exactly the case this check exists to prove -- the
    # property held and the instrument said nothing, which is how a safety check becomes decorative.
    ranked = tally._ranked()
    n_domains = ranked[0][1] if ranked else 0
    return {"peers": n_peers, "distinct_domains": n_domains, "floor": floor,
            "reached_floor": bool(verdict and verdict.corroborated),
            "safe": not (verdict and verdict.corroborated) if n_peers >= floor else True}
