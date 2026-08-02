"""Drain the abstain queue into the curated store — the automated half of the
abstain-to-ingest loop. Callable from the CLI script AND the continuous-learning daemon
tick, so coverage grows with usage without an operator. Conservative by construction:
only clean copular definitions become facts; contradictions are judge-quarantined."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from . import abstain_queue
from .corpus_adapters import extract_definition_triple
from .curated_judge import filter_candidates
from .graph_paths import (
    ABSTAIN_PROPOSAL_FRAGMENT_ROOT,
    SHIPPED_GRAPH_ROOT,
)
from .triple_store import TripleStore

PROPOSAL_FRAGMENT_ROOT = ABSTAIN_PROPOSAL_FRAGMENT_ROOT
_UA = ("ATANOR-KG/1.0 (https://github.com/Cozystone/ATANOR; blueyjkim@gmail.com) "
       "urllib/3 abstain-queue-feeder")


def _rest_summary(host: str, term: str) -> str:
    return _summary2(host, term)[0]


def _summary2(host: str, term: str) -> tuple[str, bool]:
    """(extract, is_disambiguation) — a disambiguation page is a SENSE INDEX, not
    an empty result; the caller can expand it."""
    url = f"https://{host}/api/rest_v1/page/summary/{urllib.parse.quote(term)}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    if data.get("type") == "disambiguation":
        return "", True
    return (data.get("extract") or "").strip(), False


def _disambig_links(host: str, term: str, limit: int = 8) -> list[str]:
    """Article links of a disambiguation page (ns=0) — the senses the page asserts."""
    url = (f"https://{host}/w/api.php?action=query&prop=links&titles="
           f"{urllib.parse.quote(term)}&format=json&pllimit={limit}&plnamespace=0")
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        pages = list((data.get("query") or {}).get("pages", {}).values())
        return [l["title"] for l in (pages[0].get("links") or [])][:limit] if pages else []
    except Exception:
        return []


def _term_lang(term: str) -> str:
    """Route by script — an English term on ko.wikipedia is a guaranteed 404 (the
    holdout drain measured 7/20 fetch failures from exactly this)."""
    return "ko" if any("가" <= ch <= "힣" for ch in term) else "en"


def _wiki_summary(term: str, lang: str | None = None) -> str:
    """Wikipedia first; Wiktionary as the fallback for dictionary-class words
 (, … live there, not in the encyclopedia). Same conservative extractor
 downstream either way — a source change never loosens the honesty gate."""
    lang = lang or _term_lang(term)
    try:
        extract = _rest_summary(f"{lang}.wikipedia.org", term)
    except Exception:
        extract = ""
    if extract:
        return extract
    try:
        return _rest_summary(f"{lang}.wiktionary.org", term)
    except Exception:
        return ""


def _wiki_allowed() -> bool:
    """HARD RULE (owner, twice now): the source is the SEARCH API, never
    wikipedia-centric scraping. Wiki lanes exist only behind an explicit
    opt-in; the default drain never touches them."""
    import os

    return os.getenv("ATANOR_ALLOW_WIKI", "") == "1"


def _tavily_definitions(term: str) -> list[str]:
    """PRIMARY source lane: real web search — the search-API CASCADE (Tavily,
    then the self-hosted SearXNG metasearch when Tavily is quota-dead; HTTP 432
    measured live). Returns candidate definitional sentences from the top
    results' cleaned content — the same conservative extractor and judge gate
    run downstream, so a source change never loosens honesty."""
    import sys as _sys
    from pathlib import Path as _Path

    api_dir = str(_Path(__file__).resolve().parents[2] / "apps" / "api")
    if api_dir not in _sys.path:
        _sys.path.insert(0, api_dir)
    from app.services.web_search import searxng_search, tavily_search  # noqa: E402

    lang = _term_lang(term)
    q = f"{term}이란 무엇인가" if lang == "ko" else f"what is {term}"
    rows = tavily_search(q, count=5) or searxng_search(q, count=6)
    sentences: list[str] = []
    for row in rows:
        text = str(row.get("snippet") or row.get("content") or "")
        for s in re.split(r"(?<=다\.)\s+|(?<=[.?!])\s+", text):
            s = s.strip()
            if term.lower() in s.lower() and 8 <= len(s) <= 240:
                sentences.append(s)
        if len(sentences) >= 6:
            break
    return sentences[:6]


def _wiktionary_defs(term: str, lang: str) -> list[str]:
    """Dictionary lane: wiktionary DEFINITIONS are '#' list items inside language
 sections — invisible to the REST summary, whose lead is empty for most entries
 (measured: // EXIST on ko.wiktionary yet drained as no-definition).
 Parses the wikitext, scopes to the section when present, strips markup,
 and returns gloss heads normalized exactly like the dump adapter."""
    url = (f"https://{lang}.wiktionary.org/w/api.php?action=parse&prop=wikitext"
           f"&format=json&page={urllib.parse.quote(term)}")
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    text = ((data.get("parse") or {}).get("wikitext") or {}).get("*") or ""
    if not text:
        return []
    # STRICT on-language section scoping: a wiktionary page stacks many languages'
    # sections, and page-wide '#' lines asserted junk ('is defined_as she' came from
    # another language's pronoun list). No on-language section => nothing to assert.
    section = {"ko": "한국어", "en": "English"}.get(lang)
    if section:
        m = re.search(rf"^==\s*{section}\s*==\s*$(.*?)(?=^==[^=]|\Z)", text, re.M | re.S)
        if not m:
            return []
        text = m.group(1)
    heads: list[str] = []
    for line in text.splitlines():
        dm = re.match(r"^#\s*(?![:*#])(.+)$", line)
        if not dm:
            continue
        gloss = dm.group(1)
        gloss = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]|]+)\]\]", r"\1", gloss)   # [[a|b]] -> b
        gloss = re.sub(r"\{\{[^}]*\}\}", "", gloss)                        # drop templates
        gloss = gloss.replace("'''", "").replace("''", "").strip()
        head = re.split(r"[,.;(]|이다|입니다|를 말한다|을 말한다", gloss, maxsplit=1)[0].strip()
        head = re.sub(r"^(?:하나의|일종의|어떤)\s+", "", head)
        if 2 <= len(head) <= 40 and head != term and head not in heads:
            heads.append(head)
        if len(heads) >= 3:
            break
    return heads


def _wikidata_label(term: str) -> str | None:
    """ENTITY lane resolver: acronyms and proper nouns (AGN, Lusatia) often have no
 dictionary entry but ARE curated Wikidata items whose Korean label carries the
 real name (AGN -> ). EXACT label/alias match only — the search also
 returns 'Agnes' for 'AGN', and a fuzzy hit here would be a wrong-referent bug."""
    url = ("https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json"
           "&language=ko&uselang=ko&type=item&limit=5&search=" + urllib.parse.quote(term))
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    tl = term.lower()
    for hit in data.get("search", []):
        matched = str((hit.get("match") or {}).get("text") or "").lower()
        label = (hit.get("label") or "").strip()
        if matched == tl and label and label.lower() != tl:
            return label
    return None


def _definition_sentences(term: str, extract: str) -> list[str]:

    # was split at the birth-year '?' and the definition never survived as one sentence.
    masked = re.sub(r"\([^)]*\)", lambda m: m.group(0).replace(".", "·").replace("?", "·").replace("!", "·"), extract)
    spans, start = [], 0
    for m in re.finditer(r"(?<=다\.)\s+|(?<=[.?!])\s+", masked):
        spans.append((start, m.start())); start = m.end()
    spans.append((start, len(masked)))
    sents = [extract[a:b].strip() for a, b in spans if extract[a:b].strip()]
    tl = term.lower()
    return [s for s in sents[:3] if term in s or tl in s.lower()]


_UMS_CACHE: dict[str, Any] = {}


def _urimalsaem_module():
    """scripts/ is not a package — load the drain module by path, once."""
    if "m" not in _UMS_CACHE:
        import importlib.util
        from pathlib import Path as _P

        path = _P(__file__).resolve().parents[2] / "scripts" / "urimalsaem_drain.py"
        spec = importlib.util.spec_from_file_location("urimalsaem_drain", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _UMS_CACHE["m"] = mod
    return _UMS_CACHE["m"]


def _learn_evidence(
    term: str,
    query: str,
    store: TripleStore,
    reference_store: TripleStore,
                    log: Any = print) -> int | None:
    """v2 knowledge-learner hook: QUESTION-level attributed web evidence for the
    subject (verbatim sentences + page links, 2/domain, whole-web search). Runs
    when a real user query hit the abstain queue, so the next ask gets a linked
    answer even when no clean definitional triple exists. Returns None on the
    cheap skip (subject already holds evidence) so the caller's per-drain web
    budget only counts actual searches."""
    try:
        if (
            reference_store.facts_with_sources(
                term,
                limit=1,
                preds=("evidence",),
            )
            or store.facts_with_sources(
                term,
                limit=1,
                preds=("evidence",),
            )
        ):
            return None
    except Exception:
        pass
    gained = 0

    try:
        from .structured_profile import fetch_profile

        gained += int(
            fetch_profile(
                term,
                store=store,
                reference_store=reference_store,
                log=log,
            ).get("stored", 0)
        )
    except Exception:
        pass
    try:
        from .web_knowledge_drain import learn_from_question

        c = learn_from_question(
            query or f"{term}이란?",
            subject_hint=term,
            store=store,
            reference_store=reference_store,
            log=log,
        )
        gained += int(c.get("evidence", 0)) + int(c.get("stored", 0))
    except Exception:
        pass
    return gained


def drain(
    limit: int = 5,
    dry_run: bool = False,
    log: Any = print,
    *,
    proposal_store: TripleStore | None = None,
    reference_store: TripleStore | None = None,
) -> dict[str, int]:
    """Process up to `limit` pending terms. Returns counters; never raises (each term's
    failure is recorded on the queue and skipped)."""
    counters = {
        "terms": 0,
        "detected": 0,
        "fragment_written": 0,
        # Reserved for a sealed immutable GraphMutationBatch.
        "proposed": 0,
        # Reserved for a fully materialized and verified sibling candidate.
        "staged": 0,
        # Reserved for a COMMITTED operator-signed shipped-store swap.
        "applied": 0,
        # Present in a fragment is not present in the signed shipped graph.
        "ingested": 0,
        "quarantined": 0,
        "no_definition": 0,
        "failed": 0,
        "evidence": 0,
    }
    records = abstain_queue.pending_records(limit)
    if not records:
        return counters
    store = proposal_store or TripleStore(PROPOSAL_FRAGMENT_ROOT)
    reference = reference_store or TripleStore(SHIPPED_GRAPH_ROOT)
    web_learns = 0  # at most 2 question-level web learns per drain call (bounded tick)
    for rec in records:
        term = str(rec.get("term") or "")
        counters["terms"] += 1
        lang = _term_lang(term)
        sentences: list[str] = []
        candidates: list[tuple[str, str, str]] = []
        saw_disambig = False

        # lexicography beats any web snippet; exact-headword gate inside).
        # This is the lane that resolved the whole blocked Sino-Korean class.
        if lang == "ko":
            try:
                _ums = _urimalsaem_module()
                defs = _ums.definitions(term, _ums._key())
                candidates = [(term, "defined_as", d) for d in defs]
                if candidates:
                    log(f"  {term}: 우리말샘 lane -> {len(candidates)} definition(s)")
            except Exception:
                candidates = []
        # then the search API cascade (hard rule — never wikipedia-centric). Same
        # conservative extractor + subject-relevance + judge gate downstream.
        if not candidates:
            try:
                sentences = _tavily_definitions(term)
            except Exception:
                sentences = []
            candidates = [t for s in sentences if (t := extract_definition_triple(s))]
            tl0 = term.lower()
            candidates = [c for c in candidates if tl0 in c[0].lower() or c[0].lower() in tl0]
            if candidates:
                log(f"  {term}: search-api lane -> {len(candidates)} candidate(s)")
        # wiki lanes: OPT-IN ONLY (ATANOR_ALLOW_WIKI=1); the default drain skips them
        for host in ((f"{lang}.wikipedia.org", f"{lang}.wiktionary.org") if (_wiki_allowed() and not candidates) else ()):
            try:
                extract, is_dab = _summary2(host, term)
            except Exception:
                continue
            saw_disambig = saw_disambig or is_dab
            if not extract:
                continue
            sentences = _definition_sentences(term, extract)
            candidates = [t for s in sentences if (t := extract_definition_triple(s))]
            # subject relevance: this drain answers THIS term — a true sentence about a
            # different subject on the same page (planet -> 'best available theory of
            # planet formation') must not be stored as the answer to this query.
            tl = term.lower()
            candidates = [c for c in candidates
                          if tl in c[0].lower() or c[0].lower() in tl]
            if not candidates and not sentences:
                # REDIRECT sense: the term never appears because the summary IS the

                # different subject + the redirect's own assertion of equivalence give
                # two verbatim facts: the target's definition and (term, alias, target).
                first = re.split(r"(?<=다\.)\s+|(?<=[.?!])\s+", extract)[0].strip()
                trip = extract_definition_triple(first)
                if trip and trip[0].lower() != tl:
                    candidates = [trip, (term, "alias", trip[0])]
                    log(f"  {term}: redirect sense -> {trip[0]}")
            if candidates:
                break
        # acronym alias: when the SOURCE SENTENCE itself asserts both names —
        # 'Automated machine learning (AutoML) is …' — the fact is stored under the
        # queried name too. Verbatim-grounded: only if '(term)' literally appears.
        for s in sentences:
            for subj, pred, obj in list(candidates):
                if (term.lower() != subj.lower()
                        and re.search(r"\(\s*" + re.escape(term) + r"\s*[),]", s)
                        and (term, pred, obj) not in candidates):
                    candidates.append((term, pred, obj))
        if not candidates and _wiki_allowed():
            # DICTIONARY lane (wikitext '#' senses) — OPT-IN, same judge gate.
            try:
                defs = _wiktionary_defs(term, lang)
            except Exception:
                defs = []
            for head in defs:
                trip = (term, "defined_as", head)
                if trip not in candidates:
                    candidates.append(trip)
            if defs:
                log(f"  {term}: wiktionary dictionary lane -> {len(defs)} sense(s)")
        if not candidates:
            # WIKIDATA ENTITY lane: resolve to the curated Korean label, then define
            # via that label's own encyclopedia summary — two verbatim facts (the
            # label's definition + the term->label alias), judge-gated like the rest.
            wd_label = None
            # NAME-shaped terms only: Wikidata resolves entity NAMES (AGN, Colobus,
            # Lusatia). An all-lowercase English word is dictionary material — the
            # country-code alias turned 'is' into Iceland (retracted, guarded).
            if not re.fullmatch(r"[a-z0-9 ]+", term):
                try:
                    wd_label = _wikidata_label(term)
                except Exception:
                    wd_label = None
            if wd_label:
                extract = ""
                if _wiki_allowed():
                    try:
                        extract, _dab = _summary2("ko.wikipedia.org", wd_label)
                    except Exception:
                        extract = ""
                if extract:
                    first = re.split(r"(?<=다\.)\s+|(?<=[.?!])\s+", extract)[0].strip()
                    trip = extract_definition_triple(first)
                    if trip and (wd_label.lower() in trip[0].lower()
                                 or trip[0].lower() in wd_label.lower()):
                        candidates = [trip, (term, "alias", trip[0])]
                        log(f"  {term}: wikidata entity -> {wd_label}")
        if not candidates and saw_disambig:
            # SENSE EXPANSION: the disambiguation page asserts these senses. Ingest each
            # sense's own definition under the SENSE title, plus (term, alias, sense) —
            # both verbatim from the source, judge-gated like everything else.
            links = [ti for ti in _disambig_links(f"{lang}.wikipedia.org", term)
                     if term.lower() in ti.lower()]

            for title in links[:4]:
                try:
                    s_extract, s_dab = _summary2(f"{lang}.wikipedia.org", title)
                except Exception:
                    continue
                if s_dab or not s_extract:
                    continue
                for sent in _definition_sentences(title, s_extract):
                    trip = extract_definition_triple(sent)
                    if trip and (title.lower() in trip[0].lower() or trip[0].lower() in title.lower()):
                        candidates.append(trip)
                        # disambiguation asserts MAY-REFER-TO, not equivalence: store
                        # `sense` (the bridge ENUMERATES senses, never substitutes).
                        sense = (term, "sense", trip[0])
                        if sense not in candidates:
                            candidates.append(sense)
                        break
            if candidates:
                log(f"  {term}: disambiguation expanded to {sorted({c[0] for c in candidates if c[1] != 'alias'})}")
        if not candidates:
            abstain_queue.mark(term, "no_definition")
            counters["no_definition"] += 1
            log(f"  {term}: no clean definition (honest gap, stays visible)")
            # no definitional triple != nothing to say — the knowledge learner can
            # still gather attributed evidence (quotes + links) for this subject
            if web_learns < 2 and not dry_run and rec.get("query"):
                got = _learn_evidence(
                    term,
                    str(rec.get("query") or ""),
                    store,
                    reference,
                    log,
                )
                if got is not None:
                    web_learns += 1
                    counters["evidence"] += got
            # mine tomorrow's frames from today's real rejections (data, not intuition)
            try:
                rejects = (
                    PROPOSAL_FRAGMENT_ROOT.parent
                    / "extractor_rejects.jsonl"
                )
                with rejects.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"term": term, "sentences": sentences[:2]},
                                        ensure_ascii=False) + "\n")
            except Exception:
                pass
            continue
        # INJECTION boundary (threat model §1): a web-swallowed candidate whose

        # is refused before it can become knowledge. Observed content is DATA.
        try:
            from .injection_guard import gate_triple as _inj_gate

            _clean, _blocked = [], 0
            for c in candidates:
                if _inj_gate(c[0], c[1], c[2])["allowed"]:
                    _clean.append(c)
                else:
                    _blocked += 1
            if _blocked:
                counters["injection_blocked"] = counters.get("injection_blocked", 0) + _blocked
                log(f"  {term}: BLOCKED {_blocked} injection-bearing candidate(s)")
            candidates = _clean
        except Exception:
            pass
        if not candidates:
            continue
        verdicts = filter_candidates(candidates, reference)
        counters["detected"] += len(verdicts["promotable"])
        counters["quarantined"] += len(verdicts["quarantined"])
        for q in verdicts["quarantined"]:
            log(f"  {term}: QUARANTINED {q['fact']} — curated evidence {q['evidence']}")
        if dry_run:
            log(f"  {term}: detected candidate facts {verdicts['promotable']}")
            continue
        r = store.bulk_ingest(verdicts["promotable"])
        counters["fragment_written"] += r["added"]
        abstain_queue.mark(
            term,
            "proposal_fragment_written",
            f"{r['added']} unsealed candidate facts",
        )
        for s, p, o in verdicts["promotable"]:
            log(f"  {term}: + {s} | {p} | {o}")
        # enrich answered subjects too: the definition is the lead, attributed

        if web_learns < 2 and rec.get("query"):
            got = _learn_evidence(
                term,
                str(rec.get("query") or ""),
                store,
                reference,
                log,
            )
            if got is not None:
                web_learns += 1
                counters["evidence"] += got
        # Do not credit routing success here. Staging is a mechanism firing;
        # only a later signed promotion receipt can establish shipped lift.
    return counters
