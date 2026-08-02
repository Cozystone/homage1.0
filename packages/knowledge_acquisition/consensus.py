# -*- coding: utf-8 -*-
"""Cross-domain consensus over extracted relational-fact candidates — the VERIFICATION GATE.

This is the fabrication-0 guard. It reuses the wild_web / web_knowledge_drain doctrine verbatim
(``a claim asserted by one page is a rumor; by >= 2 INDEPENDENT domains, evidence``): a mined
object value is promoted ONLY when >= MIN_DOMAINS DISTINCT domains independently state it. A
single-source object — however confidently extracted — is NEVER promoted (stays an honest gap).

Consensus key is the CANONICAL object (lowercased, article/punctuation-stripped) so surface
variants of the same value corroborate ("Paris" == "paris" == "the city of Paris" -> paris), but
DIFFERENT values do not. On a conflict (two different values each reach consensus) the higher
distinct-domain count wins; a genuine TIE abstains (never guess between equals).

Reuses ``wild_web.store.domain_of`` (registrable-ish domain = independent-stranger id) and
``wild_web.store.MIN_DOMAINS`` (the shared consensus floor), so this gate and the register/causal
gates share ONE definition of "independent source".
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from packages.wild_web.store import MIN_DOMAINS, domain_of


def canonical_object(obj: str) -> str:
    """Canonical consensus key for an object value: lowercased, leading article + surrounding
    punctuation stripped, whitespace collapsed. Surface-only (no world knowledge)."""
    o = re.sub(r"\s+", " ", str(obj or "").strip().lower())
    o = re.sub(r"^(?:the|a|an)\s+", "", o)
    o = o.strip(" ,.;:'\"-)(")
    o = re.sub(r"^(?:city\s+of|town\s+of)\s+", "", o)   # "city of Paris" -> "paris"
    return o.strip()


@dataclass
class ConsensusResult:
    obj: str                                   # verbatim winning surface form (for injection)
    domains: list[str]                         # distinct domains that attest it (provenance)
    urls: list[str]                            # one evidence url per domain (provenance)
    n_domains: int
    corroborated: bool                         # n_domains >= MIN_DOMAINS
    conflict: bool = False                     # another value also reached consensus (lower count)
    tie: bool = False                          # top two values tied on domain count -> abstain


@dataclass
class ConsensusTally:
    """Accumulate (object, source_url) sightings and decide consensus by DISTINCT DOMAIN count."""
    min_domains: int = MIN_DOMAINS
    # canonical_obj -> {domain -> first url}, and canonical_obj -> Counter(verbatim surface forms)
    _domains: dict[str, dict[str, str]] = field(default_factory=dict)
    _surface: dict[str, Counter] = field(default_factory=dict)

    def add(self, obj: str, source_url: str) -> None:
        canon = canonical_object(obj)
        if not canon:
            return
        dom = domain_of(source_url)
        if not dom or dom == "unknown":
            return
        self._domains.setdefault(canon, {}).setdefault(dom, source_url)
        self._surface.setdefault(canon, Counter())[obj.strip()] += 1

    def add_pairs(self, pairs: Iterable[tuple[str, str]]) -> None:
        for obj, url in pairs:
            self.add(obj, url)

    def _ranked(self) -> list[tuple[str, int]]:
        """(canonical_obj, distinct_domain_count) sorted by count desc, then key for stability."""
        return sorted(((c, len(d)) for c, d in self._domains.items()),
                      key=lambda kv: (-kv[1], kv[0]))

    def resolve(self) -> ConsensusResult | None:
        """The consensus verdict. None if NOTHING reached the domain floor (honest gap). On a tie
        for the top spot at/above the floor, returns a result flagged ``tie=True`` and
        ``corroborated=False`` (ambiguous -> the caller abstains, never guesses)."""
        ranked = self._ranked()
        if not ranked:
            return None
        top_canon, top_n = ranked[0]
        if top_n < self.min_domains:
            return None                                    # no object crossed the floor
        tie = len(ranked) > 1 and ranked[1][1] == top_n
        conflict = len(ranked) > 1 and self.min_domains <= ranked[1][1] < top_n
        dom_map = self._domains[top_canon]
        # verbatim surface: the most common attested spelling of the winning value
        obj = self._surface[top_canon].most_common(1)[0][0]
        return ConsensusResult(
            obj=obj,
            domains=sorted(dom_map),
            urls=[dom_map[d] for d in sorted(dom_map)],
            n_domains=top_n,
            corroborated=not tie,
            conflict=conflict,
            tie=tie,
        )
