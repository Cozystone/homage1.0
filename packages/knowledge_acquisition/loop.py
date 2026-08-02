# -*- coding: utf-8 -*-
"""The autonomous knowledge-acquisition CLOSED LOOP (R2 / M4 substrate lever).

    knowledge question ABSTAINS  ->  mine the web for the missing fact  ->  VERIFY (source +
    consensus >= 2 independent domains)  ->  inject into the graph (no-retrain)  ->  re-answer.

This is FUSION glue — every heavy organ is reused, nothing re-implemented:
  * abstain-detect + shape-parse + re-answer : ``base_brain.relational_lookup`` (resolve_relational
    returns ``honest_abstain_relational`` when the graph holds no matching edge; the SAME call after
    injection returns the grounded answer).
  * safety floors (a mined sentence is DATA)  : ``wild_web`` (is_harmful / is_pii / has_injection).
  * verification gate (fabrication-0)         : ``consensus.ConsensusTally`` (>= 2 DISTINCT domains,
    the wild_web / web_knowledge_drain doctrine).
  * relational OBJECT extraction (the one new organ) : ``relation_extract``.
  * no-retrain graph write with provenance    : ``inject.inject_fact`` (TripleStore append, EXCLUDE
    guard, idempotent, single-writer sanity).

Constitution (BINDING):
  * Fabrication 0 — a fact enters the graph ONLY through the consensus gate. No consensus -> NOT
    injected -> the question stays HONESTLY abstained. A guess is never written.
  * Provenance — every injected edge carries its consensus source(s); the re-answer cites grounding.
  * Neuro-budget — facts live in the GRAPH, never in weights. No model here (0 learned params).
  * Scoped writes — the loop writes to the ``store_root`` it is given; the sealed gate passes an
    ephemeral store, never the shipped one. (Live persistent writes remain behind the operator /
    candidate-promotion gate at the daemon layer — this module only writes where told.)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from packages.base_brain.relational_lookup import (
    REL_SYNONYMS,
    parse_relational_shape,
    resolve_relational,
)
from packages.graph_scale.triple_store import TripleStore

from .consensus import ConsensusTally
from .evidence import EvidenceSource
from .inject import inject_fact
from .relation_extract import extract_from_documents


def graph_predicate(rel_norm: str) -> str:
    """The GRAPH predicate label to write for an asked relation, chosen deterministically from the
    LAD relation lexicon so the relational lane's ``_predicate_targets`` finds it on re-answer:
    prefer the underscored form of the asked relation if it is a known label, else the
    lexicographically-first synonym, else the underscored asked relation. (Relation NAMES, not
    world facts.)"""
    target = rel_norm.replace(" ", "_")
    labels = REL_SYNONYMS.get(rel_norm)
    if labels:
        return target if target in labels else sorted(labels)[0]
    return target


@dataclass
class AcquisitionResult:
    status: str                 # not_relational | already_grounded | abstained_insufficient_consensus
    #                             | excluded_test_locked | injected | acquired | write_refused
    question: str
    entity: str = ""
    rel_norm: str = ""
    predicate: str = ""
    before_kind: str = ""       # answer_kind before acquisition
    after_kind: str = ""        # answer_kind after  acquisition
    answer: str = ""
    object: str = ""
    domains: list[str] | None = None
    urls: list[str] | None = None
    candidates: int = 0         # (object, url) sightings extracted
    neutralized: int = 0        # docs whose prompt-injection was disarmed (sanitize_injection on)
    dropped: int = 0            # docs dropped by a content-safety floor (harm/PII/residual-injection)
    fired: bool = False         # abstention -> correct grounded answer (the payoff signal)
    tiers_run: list[str] | None = None   # cascade tiers actually consulted, in order
    settled_by: str = ""        # the tier at which the floor was met; "" if it never was
    detail: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        return d


def _abstains(core: dict[str, Any] | None) -> bool:
    return bool(core) and core.get("answer_kind") == "honest_abstain_relational"


def _evidence_tiers(evidence) -> list[tuple[str, Any]]:
    """One source, or an ordered cascade. Named so the log and the result say WHICH tier answered.

    A caller may pass a bare EvidenceSource (the original contract, unchanged), a sequence of them,
    or a sequence of (name, source) pairs when it wants the names to be meaningful."""
    if evidence is None:
        return []
    if isinstance(evidence, (list, tuple)):
        out = []
        for i, item in enumerate(evidence):
            if isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], str):
                out.append((item[0], item[1]))
            else:
                out.append((f"tier{i + 1}", item))
        return out
    return [(type(evidence).__name__.replace("Evidence", "").lower() or "evidence", evidence)]


def _screen_documents(docs, *, sanitize_injection, is_harmful, is_pii, has_injection):
    """Page-level safety screen. Unchanged behaviour, lifted out so every cascade tier gets it.

    A tier that skipped this would be a hole in the floor rather than a faster path."""
    safe: list[tuple[str, str]] = []
    dropped = 0
    neutralized = 0
    for url, text in docs:
        if sanitize_injection:
            # disarm the command spans in fetched content (a poisoned page must not hijack the
            # answer) — the factual residual survives to face consensus. Uses the shipped guard.
            from packages.graph_scale.injection_guard import strip as _ig_strip
            text, contaminated = _ig_strip(text)
            if contaminated:
                neutralized += 1
            # harm + residual-injection are PAGE-level floors (a harmful page informs nothing).
            # PII is NOT a page-drop in the live READ lane: we extract a factual OBJECT (a place /
            # name), never the page's contact details, so an encyclopedic page carrying big numbers
            # (population/coordinates) or a footer phone must still inform the fact. PII is enforced
            # at the OBJECT level after extraction instead.
            floored = is_harmful(text) or has_injection(text)
        else:
            # legacy fail-closed default (the offline sealed gate): a harmful/PII/injection page is
            # inert DATA, dropped whole.
            floored = is_harmful(text) or is_pii(text) or has_injection(text)
        if floored:
            dropped += 1
            continue
        safe.append((url, text))
    return safe, dropped, neutralized


def acquire(question: str, evidence: EvidenceSource, store_root: Path | str, *,
            language: str = "en", retrieved_at: str | None = None,
            sanitize_injection: bool = False, property_table=None,
            log: Callable[..., None] = lambda *a, **k: None) -> AcquisitionResult:
    """Run the closed loop for ONE question against ``store_root``. Never raises on evidence
    failure — an empty/failed mine simply leaves the question honestly abstained.

    ``sanitize_injection`` (default off — preserves the legacy fail-closed contract): when ON,
    a mined document's prompt-injection command spans are NEUTRALIZED via the shipped
    ``injection_guard.strip`` (the command is disarmed so a poisoned page cannot hijack the
    answer) and its FACTUAL residual still faces the >= 2-domain consensus gate — so a poisoned
    page can INFORM a fact but never enshrine one alone. When OFF, an injection-bearing document
    is dropped whole (the original behavior the offline sealed gate encodes)."""
    store_root = Path(store_root)

    # 1) ABSTAIN-DETECT — ask the relational lane against the scoped store.
    store = TripleStore(store_root)
    core = resolve_relational(question, language=language, store=store)
    if core is None:
        return AcquisitionResult("not_relational", question,
                                 detail={"note": "not a relational-shape question"})
    before_kind = str(core.get("answer_kind") or "")
    if not _abstains(core):
        # already grounded (this is also the re-answer success check when called again)
        return AcquisitionResult("already_grounded", question, before_kind=before_kind,
                                 after_kind=before_kind, answer=str(core.get("answer") or ""),
                                 detail={"note": "graph already holds the edge"})

    shape = parse_relational_shape(question)
    if not shape:                                    # abstained but unparyable shape (defensive)
        return AcquisitionResult("not_relational", question, before_kind=before_kind)
    entity, rel_norm, kind = shape["entity"], shape["rel_norm"], shape["kind"]
    predicate = graph_predicate(rel_norm)

    # 2) MINE — gather candidate documents, (optionally) NEUTRALIZE prompt-injection, drop DATA
    #    that trips a content-safety floor, extract objects.
    from packages.wild_web import is_harmful, is_pii  # lazy: keep network module out of import path
    from packages.wild_web.transforms import has_injection

    # 2+3) MINE AND VERIFY AS A CASCADE — each tier only runs if the floor is not met yet.
    #
    # Evidence ACCUMULATES into one tally and the verdict is checked AFTER EACH TIER, so the loop
    # stops the moment two sources agree. That is the whole point: the tiers differ by three orders
    # of magnitude in cost, and the expensive one has a hard external limit.
    #
    #   tier 0  property table   ~2 microseconds, precomputed, no retrieval at all
    #   tier 1  local corpora    ~2 milliseconds, BM25 over 8.25M owned passages, no network
    #   tier 2  the web          ~2 seconds, and measured 2026-07-31 to get every upstream search
    #                            engine to suspend us inside an hour of continuous querying
    #
    # A cheap tier that settles the question means the expensive one is never asked, which is not an
    # optimisation here but the difference between a loop that can run unattended and one that gets
    # cut off. What each tier CANNOT do is lower the bar: they all add sightings to the same
    # ConsensusTally under the same floor, and a tier that finds nothing simply passes the question
    # down. Ordering evidence by cost cannot change what counts as evidence.
    tally = ConsensusTally()
    pairs: list[tuple[str, str]] = []
    dropped = 0
    neutralized = 0
    tiers_run: list[str] = []
    settled_by: str | None = None

    def _settled() -> bool:
        v = tally.resolve()
        return v is not None and v.corroborated

    # TIER 0 — the property table. Facts, not documents, which is why it joins at the consensus
    # layer rather than as an EvidenceSource: handing it to `documents` would mean synthesising text
    # and re-extracting from it, which is lossy and circular.
    #
    # DOUBLE COUNTING IS THE RISK AND THE EXISTING DESIGN ALREADY FORBIDS IT. ConsensusTally keys its
    # evidence by DOMAIN (`_domains[canon][dom]`), so a fact the table read out of Wikipedia and a
    # fact extracted from a fetched en.wikipedia.org page collapse to one domain instead of reaching
    # the floor between them. That holds only while both sides agree what domain a corpus is, so the
    # mapping lives once in `retriever.corpus_url` and is imported, never copied.
    if property_table is not None:
        table_pairs: list[tuple[str, str]] = []
        try:
            from packages.atanor_index.retriever import corpus_url
            for obj, corpus in property_table.lookup(entity, predicate):
                url = corpus_url(corpus, entity)
                if url:
                    table_pairs.append((obj, url))
        except Exception as exc:                     # a missing table must never break the loop
            log(f"  {entity} [{rel_norm}]: property table unavailable ({exc})")
        if sanitize_injection:
            table_pairs = [(o, u) for (o, u) in table_pairs
                           if not (is_pii(o) or is_harmful(o) or has_injection(o))]
        if table_pairs:
            tiers_run.append("table")
            pairs += table_pairs
            tally.add_pairs(table_pairs)
            log(f"  {entity} [{rel_norm}]: tier=table {len(table_pairs)} precomputed sightings from "
                f"{len({u.split('/')[2] for _o, u in table_pairs})} corpora")
            if _settled():
                settled_by = "table"

    # TIERS 1..n — retrieval, in the order the caller gave them. `evidence` accepts one source (the
    # original contract) or a sequence, so existing callers are unaffected.
    if settled_by is None:
        for tier_name, src in _evidence_tiers(evidence):
            docs = src.documents(entity, rel_norm, question) or []
            safe_docs, d, n = _screen_documents(docs, sanitize_injection=sanitize_injection,
                                                is_harmful=is_harmful, is_pii=is_pii,
                                                has_injection=has_injection)
            dropped += d
            neutralized += n
            tier_pairs = extract_from_documents(safe_docs, entity, rel_norm, kind)
            if sanitize_injection:
                # object-level safety net: a mined OBJECT that is itself PII / harm / injection
                # never promotes
                tier_pairs = [(o, u) for (o, u) in tier_pairs
                              if not (is_pii(o) or is_harmful(o) or has_injection(o))]
            tiers_run.append(tier_name)
            pairs += tier_pairs
            tally.add_pairs(tier_pairs)
            log(f"  {entity} [{rel_norm}]: tier={tier_name} {len(safe_docs)} docs -> "
                f"{len(tier_pairs)} object sightings ({d} floored, {n} injection-neutralized)")
            if _settled():
                settled_by = tier_name
                break

    verdict = tally.resolve()
    if verdict is None or not verdict.corroborated:
        reason = ("no object reached the 2-domain floor" if verdict is None
                  else "top values tied across domains — ambiguous")
        log(f"  {entity} [{rel_norm}]: NO consensus ({reason}) -> stays abstained")
        return AcquisitionResult("abstained_insufficient_consensus", question, entity=entity,
                                 rel_norm=rel_norm, predicate=predicate, before_kind=before_kind,
                                 after_kind=before_kind, answer=str(core.get("answer") or ""),
                                 candidates=len(pairs), neutralized=neutralized, dropped=dropped,
                                 fired=False, tiers_run=tiers_run, settled_by=settled_by or "",
                                 detail={"reason": reason,
                                         "top": None if verdict is None else
                                         {"object": verdict.obj, "n_domains": verdict.n_domains,
                                          "tie": verdict.tie}})

    # 4) INJECT — no-retrain graph write with consensus provenance (respects EXCLUDE_PAIRS).
    audit = inject_fact(store_root, entity, predicate, verdict.obj,
                        verdict.domains, verdict.urls, retrieved_at=retrieved_at)
    if audit.get("reason") == "excluded_test_locked":
        log(f"  {entity} [{rel_norm}]: consensus reached but pair is test-locked -> not injected")
        return AcquisitionResult("excluded_test_locked", question, entity=entity, rel_norm=rel_norm,
                                 predicate=predicate, before_kind=before_kind, after_kind=before_kind,
                                 answer=str(core.get("answer") or ""), object=verdict.obj,
                                 domains=verdict.domains, urls=verdict.urls, candidates=len(pairs),
                                 neutralized=neutralized, dropped=dropped,
                                 fired=False, tiers_run=tiers_run, settled_by=settled_by or "",
                                 detail=audit)
    if not audit.get("injected"):
        return AcquisitionResult("write_refused", question, entity=entity, rel_norm=rel_norm,
                                 predicate=predicate, before_kind=before_kind, after_kind=before_kind,
                                 answer=str(core.get("answer") or ""), object=verdict.obj,
                                 domains=verdict.domains, urls=verdict.urls, candidates=len(pairs),
                                 neutralized=neutralized, dropped=dropped,
                                 fired=False, tiers_run=tiers_run, settled_by=settled_by or "",
                                 detail=audit)

    # 5) RE-ANSWER — reopen the store (reads the freshly-written columns) and ask again.
    store2 = TripleStore(store_root)
    core2 = resolve_relational(question, language=language, store=store2)
    after_kind = str((core2 or {}).get("answer_kind") or "")
    answer2 = str((core2 or {}).get("answer") or "")
    fired = bool(core2) and not _abstains(core2) and core2.get("relational", {}).get("resolved")
    log(f"  {entity} [{rel_norm}]: injected {verdict.obj} "
        f"({verdict.n_domains} domains {verdict.domains}) -> re-answer: {answer2!r}")
    return AcquisitionResult("acquired" if fired else "injected", question, entity=entity,
                             rel_norm=rel_norm, predicate=predicate, before_kind=before_kind,
                             after_kind=after_kind, answer=answer2, object=verdict.obj,
                             domains=verdict.domains, urls=verdict.urls, candidates=len(pairs),
                             neutralized=neutralized, dropped=dropped,
                             # THE SUCCESS RETURN NEEDS THESE MOST, and the first version omitted
                             # exactly here: a run reported "queued 2, settled by {}" because the
                             # only results carrying a tier were the ones that never reached one.
                             fired=fired, tiers_run=tiers_run, settled_by=settled_by or "",
                             detail={"inject": audit})


def acquire_batch(questions: list[str], evidence: EvidenceSource, store_root: Path | str,
                  **kwargs: Any) -> dict[str, Any]:
    """Run the loop for many questions; return the results plus the measured FIRE-RATE — of the
    questions that started ABSTAINED, how many became correctly grounded after acquisition. This is
    the payoff analogue of the fluency fire-rate (here expected to actually fire, since graph facts
    improve answers)."""
    results = [acquire(q, evidence, store_root, **kwargs) for q in questions]
    started_abstained = [r for r in results
                         if r.before_kind == "honest_abstain_relational"]
    fired = [r for r in started_abstained if r.fired]
    fire_rate = round(len(fired) / len(started_abstained), 4) if started_abstained else 0.0
    return {
        "results": results,
        "n_questions": len(questions),
        "n_started_abstained": len(started_abstained),
        "n_fired": len(fired),
        "fire_rate": fire_rate,
    }
