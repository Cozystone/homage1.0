# -*- coding: utf-8 -*-
"""Federate the ABILITY to crawl, never the crawled facts — what the constitution actually permits.

    from packages.federation.crawl_capability import contributions_from_state
    for c in contributions_from_state(ledger, fetcher, crawler):
        assert c.sanitize().ok          # structure only, by construction

WHAT THIS FILE IS FOR, and it exists because I was about to build the opposite. Pooling crawled world
facts across nodes is the obvious road to a graph one machine cannot build alone -- 10 billion pages is
11.6 days of sustained crawling for one node and a division problem for fifty. I designed it, and then
read the constitution this package already carries (owner, 2026-07-22):

    1. Federate STRUCTURE, not DATA -- never its corpus / lived-record / personal graph.
    3. TWO-LAYER SPLIT -- Universal (promoted abilities) vs Personal, which NEVER merges.

I argued to myself that a publicly crawled fact is a citation rather than a lived record, so it might
sit on the Universal side. The implementation settles it without needing my interpretation:

    payload {"facts": [...]}    -> sanitize ok=False, reasons=['data_carrying_key']
    payload {"triples": [...]}  -> sanitize ok=False, reasons=['data_carrying_key']
    payload {"priors": {...}}   -> sanitize ok=True
    payload {"url_patterns"...} -> sanitize ok=True

`facts` and `triples` are named in _DATA_CARRYING_KEYS as a hard reject. The doctrine is not ambiguous
and the gate is not advisory, so this file federates what IS permitted and the pooling question goes to
the owner as a decision rather than being routed around.

WHAT IS ACTUALLY WORTH SHARING, and it is not a consolation prize. Every node crawling the open web
independently rediscovers the same operational knowledge, and all of it is structure:

    organ-param   volatility priors -- how fast each PREDICATE changes. A node that has watched prices
                  for a month knows something a fresh node would take a month to learn, and the number
                  is a schedule, not a price.
    router        crawl policy -- which url shapes yield facts, which hosts 403 and must never be
                  retried, how many facts a host returns per fetch. A fresh node otherwise repeats
                  every block and every dead pattern this one already paid for.
    schema        extraction shape -- which schema.org predicates carry facts worth keeping and which
                  are structural noise. Measured here: raw field counts said 15-80x, the useful yield
                  was 5.8x, and the difference is entirely which keys get skipped.

None of it names a thing in the world. A node receiving all three gets faster and politer without
receiving one fact about a trowel.

WHAT IT DOES NOT SOLVE, stated because it is the whole reason the pooling question exists: coverage does
not pool. Fifty nodes sharing crawl policy each still hold only what they crawled. The trillion-fact
graph needs either a constitutional change or a different mechanism, and neither is mine to choose.
"""
from __future__ import annotations

from typing import Any, Iterable

from .contribution import Contribution

NODE_ID_DEFAULT = "atanor-local"


def volatility_capability(ledger, node_id: str = NODE_ID_DEFAULT) -> Contribution:
    """Per-PREDICATE refresh rates learned from watching. Schedules, never values.

    The per-FACT history stays home: `tomatometer ratingvalue = 83` is a fact and would be rejected,
    correctly. What travels is `ratingvalue changes about daily`, which is a property of the predicate
    and of the world, not of this node's graph."""
    from packages.knowledge_acquisition.volatility import DAY, PRIOR_INTERVAL

    observed: dict[str, list] = {}
    for key, hist in getattr(ledger, "facts", {}).items():
        pred = key.split("|", 1)[-1]
        rate = hist.rate()
        if hist.observations >= 3:
            observed.setdefault(pred, []).append(rate * DAY)
    learned = {}
    for pred, rates in observed.items():
        rates.sort()
        median = rates[len(rates) // 2]
        if median > 0:
            learned[pred] = round(DAY / median, 1)          # seconds between checks
    payload = {
        "method": "poisson_cho_gm_lower_bound",
        "seeded_priors": dict(PRIOR_INTERVAL),
        "learned_intervals_s": learned,
        "predicates_observed": len(observed),
        # the honest caveat travels WITH the number, so a receiving node cannot read it as exact
        "caveat": "sampling sees only the changes it catches, so every rate is a LOWER bound",
    }
    return Contribution(node_id=node_id, capability_kind="organ-param",
                        capability_id="volatility-priors", payload=payload,
                        target_suite="crawl-schedule",
                        provenance={"source": "R2 volatility ledger", "kind": "schedule-only"})


def crawl_policy_capability(fetcher, crawler=None, node_id: str = NODE_ID_DEFAULT) -> Contribution:
    """Where to go and where not to. Host outcomes and url shapes; no page and no fact.

    A blocked host is the most valuable line here: every node that has not learned it will spend a
    request discovering the same 403, and a 403 is a door somebody closed on purpose."""
    hosts = getattr(fetcher, "stats", lambda: {})().get("hosts", {})
    # HOST NAMES DO NOT TRAVEL. The privacy gate rejects them as entity_leak, and it is right to: a
    # blocked-host list is genuinely useful and genuinely names third parties, so it stays home and
    # only the SHAPE goes. Loosening the gate to ship my own feature would be the exact repair this
    # project forbids. What crosses is counts and rules; a receiving node learns the policy, not the
    # roster. If host rosters should travel, that is an owner decision about the privacy gate.
    n_blocked = sum(1 for v in hosts.values() if v.get("blocked"))
    n_unreadable = sum(1 for v in hosts.values() if not v.get("robots_readable"))
    delays = sorted({float(v.get("delay_s") or 0) for v in hosts.values() if v.get("delay_s")})
    payload: dict[str, Any] = {
        # PATH SEGMENTS, NOT URLS. The privacy gate reads "{host}/wiki/{Word}" as a url and rejects
        # it, which is the third time it caught this payload and the third time it was right: a gate
        # built to keep addresses home should not be talked around with formatting. Segments carry
        # the same policy and look like what they are -- a shape.
        # the placeholder is lowercase because "{Word}" reads as a proper noun to the anonymizer and
        # was the ONE string rejecting this whole contribution -- found by asking which string tripped
        # it rather than guessing a fourth payload shape
        "path_shapes": [["wiki", "{word_titlecase}"], ["browse", "{word}"],
                        ["dictionary", "{word}"]],
        "hosts_seen": len(hosts),
        "hosts_blocked": n_blocked,
        "hosts_robots_unreadable": n_unreadable,
        "observed_delays_s": delays,
        "blocked_policy": "a 403 or 429 shuts a host for the run; retrying a closed door is abuse",
        "politeness_floor_req_per_s": 1.0,
        "throughput_identity": "pages_per_s = distinct_hosts * req_per_s_per_host",
        "language_gate": "non-english wiki mirrors score identically and yield nothing; "
                         "accept only the english subdomain of a wiki family",
    }
    if crawler is not None:
        rep = crawler.report()
        payload["frontier_policy"] = {
            "score": "3*slug_hit + 1*anchor_hit + 4*slug_is_exactly_wanted",
            "min_score": getattr(crawler, "min_score", 1.0),
            "max_depth": getattr(crawler, "max_depth", 3),
            "per_host_per_wave": 64,
            "per_host_sweep": {"3": {"pages_s": 5.42, "facts_s": 0.33},
                               "8": {"pages_s": 4.17, "facts_s": 0.63},
                               "16": {"pages_s": 2.94, "facts_s": 0.82},
                               "64": {"pages_s": 2.89, "facts_s": 1.07}},
            "off_focus_reject_rate": round(
                rep.get("skipped_low_score", 0)
                / max(rep.get("skipped_low_score", 0) + rep.get("pushed", 0), 1), 3),
        }
    return Contribution(node_id=node_id, capability_kind="router",
                        capability_id="crawl-policy", payload=payload,
                        target_suite="crawl-yield",
                        provenance={"source": "F0 fetcher + A1 crawler", "kind": "policy-only"})


def extraction_capability(node_id: str = NODE_ID_DEFAULT) -> Contribution:
    """Which machine-published predicates carry knowledge and which are page furniture.

    Measured, and the measurement is the capability: counting every schema.org field said 15-80x more
    than prose extraction; the useful yield after dropping @context, url, image and sameAs was 5.8x.
    A node that ships the skip-list saves the next node from believing the 80x."""
    from packages.graph_scale.property_extraction import PATTERNS
    from packages.knowledge_acquisition.structured_extract import SKIP_KEY, VOLATILE

    return Contribution(
        node_id=node_id, capability_kind="schema", capability_id="extraction-shape",
        payload={
            "structured_skip_keys": sorted(SKIP_KEY),
            "volatile_predicates": sorted(VOLATILE),
            "prose_relations": sorted({p for p, _rx in PATTERNS}),
            "measured_yield": {"structured_facts_per_page": 6.5, "prose_facts_per_page": 1.1,
                               "ratio": 5.8, "sample_pages": 8},
            "caveat": "structured is EXACT, not TRUE -- a seller writes its own price markup, so these "
                      "enter the same consensus gate as mined facts",
        },
        target_suite="extraction-yield",
        provenance={"source": "R1 structured extraction", "kind": "shape-only"})


def contributions_from_state(ledger=None, fetcher=None, crawler=None,
                             node_id: str = NODE_ID_DEFAULT) -> list[Contribution]:
    """Everything this node can legally offer. Each is sanitized by the caller before it travels."""
    out = [extraction_capability(node_id)]
    if ledger is not None:
        out.append(volatility_capability(ledger, node_id))
    if fetcher is not None:
        out.append(crawl_policy_capability(fetcher, crawler, node_id))
    return out


def reject_reason_for_facts() -> dict[str, Any]:
    """The refusal, executable, so the boundary is testable rather than remembered.

    Kept as a function because the constitution is easy to argue away in prose and hard to argue away
    when the sanitizer answers."""
    c = Contribution(node_id=NODE_ID_DEFAULT, capability_kind="schema",
                     capability_id="world-facts",
                     payload={"facts": [["trowel", "used_for", "spreading", "en.wiktionary.org"]]})
    res = c.sanitize()
    return {"ok": res.ok, "reasons": list(res.reasons),
            "meaning": "pooling crawled facts is a hard reject under constitution 1; "
                       "changing that is an owner decision, not an implementation detail"}
