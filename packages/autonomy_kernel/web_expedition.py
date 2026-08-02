# -*- coding: utf-8 -*-
"""Web expedition — the AI going out to the web (and the agent commons) to widen its own
knowledge, WITHOUT losing its composure to what it finds (, 2026-07-10: " …
 ").

The North Star charter is the contract this obeys literally:

 * READS are free, WRITES are gated. So an expedition may search + fetch + read the open web on
 its own; but anything it learns lands only as a CANDIDATE (source-tagged, consensus-checked),
 never straight into the production answer store. Promotion stays the operator's gate.
 * Swallowed text is DATA, never a command. Every fetched snippet and every agent message runs
 the epistemic shield first. An injection / brainwash attempt is not obeyed — it is recorded as
 a social observation (trusted=False) and turned into IMMUNITY (this is the "" — composure).
 * Independent-source consensus is by DOMAIN, not by fetch count, so one site can't masquerade as
 many voices.

Nothing here fabricates a fact, edits the moral core, or writes production. It is the read/scan/
gate/journal half of the road; the write half stays behind the gate that already exists.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]
_JOURNAL = REPO / "data" / "autonomy" / "expedition_journal.jsonl"


def _journal_path() -> Path:
    """Where this expedition gets recorded — and why it is not always the same file.

    The journal is ATANOR's own record of where it went and what it swallowed. It is read back as
    evidence: `browse_director` steers from the last real page_ingest, the activity feed surfaces it,
    and an audit of "is the curiosity actually running" is an audit of THIS file.

    So a test writing into it is not a harmless side effect -- it puts fiction into an autobiography.
    Measured, not supposed: 166 of the 1,357 topic-bearing rows were left by four test literals
    ('x', a raising _boom fetch, and two junk-receipt topics), and the five most recent 'expeditions'
    were ALL test artifacts. Reading the file honestly, the last genuine expedition was six days
    before the audit -- a fact the pollution had completely hidden.

    Under pytest the record goes to a scratch file instead. `ATANOR_EXPEDITION_JOURNAL` overrides
    both, so a caller that wants its own journal can say so explicitly rather than by accident."""
    import os
    override = os.getenv("ATANOR_EXPEDITION_JOURNAL")
    if override:
        return Path(override)
    if os.getenv("PYTEST_CURRENT_TEST"):
        return REPO / "runtime" / "test_journals" / "expedition_journal.jsonl"
    return _JOURNAL

# a modest expedition budget — polite, bounded, never a crawler firehose.
_DEFAULT_MAX_RESULTS = 6
_MIN_SENT_LEN, _MAX_SENT_LEN = 12, 1000


def _domain_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        host = (urlparse(str(url or "")).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _shield_verdict(text: str, source: str) -> dict[str, Any]:
    """Run the antifragile epistemic shield over swallowed content. Best-effort — if the shield
    module is unavailable we FAIL CLOSED on obvious injection markers rather than trusting."""
    try:
        from packages.graph_scale import epistemic_shield
        return epistemic_shield.shield(text, source=source)
    except Exception:
        try:
            from packages.graph_scale import injection_guard
            if injection_guard.has_injection(text):
                return {"attack": True, "kinds": ["instruction_injection"], "source": source}
        except Exception:
            pass
        return {"attack": False, "kinds": [], "source": source}


def _split_sentences(snippet: str) -> list[str]:
    try:
        from app.services.web_search import _clean_web_snippet
        snippet = _clean_web_snippet(str(snippet or ""))
    except Exception:
        snippet = str(snippet or "")
    out = []
    for raw in re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s+", snippet):
        seg = re.sub(r"\s+", " ", raw).strip()
        if _MIN_SENT_LEN <= len(seg) <= _MAX_SENT_LEN:
            out.append(seg)
    return out


def _default_fetch(topic: str, count: int) -> list[dict[str, Any]]:
    try:
        from app.services.web_search import provider_api_search
        return provider_api_search(topic, count)
    except Exception:
        return []


def _journal(entry: dict[str, Any]) -> None:
    try:
        path = _journal_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def expedition(topic: str, *, fetch: Callable[[str, int], list[dict[str, Any]]] | None = None,
               max_results: int = _DEFAULT_MAX_RESULTS, min_consensus: int = 2,
               source: str = "web") -> dict[str, Any]:
    """One web expedition on a topic: search → per-snippet shield scan → distill → domain-consensus
    → journal. Returns a report of CANDIDATE sentences (never written to production here). `fetch`
    is injectable so this is testable offline; it defaults to the real search API (a READ).

    A sentence survives only if: its page passed the shield (not an injection/brainwash), and its
    content is corroborated by at least `min_consensus` DISTINCT domains. Injection attempts are
    counted and recorded as immunity, not obeyed."""
    fetch = fetch or _default_fetch
    t = str(topic or "").strip()
    try:
        rows = fetch(t, max_results) or []
    except Exception as exc:
        rows = []
        # The MESSAGE, not only the class. `fetch:RuntimeError` sat in the journal for six days and
        # said nothing about whether the network was down, the provider had changed, or a test had
        # written it -- a receipt that cannot distinguish those is not a receipt.
        report = {"topic": t, "error": f"fetch:{type(exc).__name__}", "detail": str(exc)[:200]}
        _journal({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **report})
        return report

    injection_blocked: list[dict[str, Any]] = []
    # content sentence -> set of domains that assert it (consensus by independent domain)
    by_sentence: dict[str, set[str]] = {}
    domains_seen: set[str] = set()
    fetched = 0
    for row in rows:
        snippet = str(row.get("snippet") or row.get("content") or "")
        if not snippet:
            continue
        fetched += 1
        domain = _domain_of(row.get("url") or row.get("href") or "") or (source + ":unknown")
        domains_seen.add(domain)
        verdict = _shield_verdict(snippet, source=domain)
        if verdict.get("attack"):
            # DO NOT obey, DO NOT ingest as fact — record as a social observation → immunity.
            injection_blocked.append({"domain": domain, "kinds": verdict.get("kinds", []),
                                      "excerpt": snippet[:120]})
            _record_immunity(snippet, verdict)
            continue
        for seg in _split_sentences(snippet):
            by_sentence.setdefault(seg, set()).add(domain)

    consensus_backed = [{"text": s, "domains": sorted(ds), "n_domains": len(ds)}
                        for s, ds in by_sentence.items() if len(ds) >= min_consensus]
    consensus_backed.sort(key=lambda c: c["n_domains"], reverse=True)
    single_source = sum(1 for ds in by_sentence.values() if len(ds) < min_consensus)

    report = {
        "topic": t,
        "results_fetched": fetched,
        "domains": sorted(domains_seen),
        "injection_blocked": len(injection_blocked),
        "injection_detail": injection_blocked[:10],
        "distinct_sentences": len(by_sentence),
        "consensus_backed": len(consensus_backed),
        "single_source_held_back": single_source,
        "candidates": consensus_backed[:50],
        "written_to_production": False,   # HARD: read/gate/journal only; promotion is gated
        "note": "웹 읽기는 자유, 쓰기는 게이트 — 여기 후보는 도메인 합의를 통과했지만 프로덕션에 "
                "쓰이지 않음. 주입 시도는 복종이 아니라 면역으로 기록됨.",
    }
    _journal({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **{k: v for k, v in report.items()
                                                           if k not in ("candidates", "injection_detail")}})
    # consensus-backed sentences are the best language fodder we see (2+ domains, shielded) —
    # feed the voice's corpus (surface register only, never a fact lane).
    try:
        from packages.autonomy_kernel import narrative_corpus
        narrative_corpus.add_lines([c["text"] for c in consensus_backed[:20]], source="expedition")
    except Exception:
        pass


    # learn to fall and orbit from the web itself — presentation sidecar, never the answer pack.
    try:
        from packages.imagination.motion_miner import record_from_consensus
        record_from_consensus(consensus_backed[:30])
    except Exception:
        pass
    # input-side junk signal (closes the AVOID direction of the self-correction loop): a topic that
    # surfaced injection attacks, or was probed enough yet yielded NO corroborated content, is a
    # junk source → a receipt so the frontier chooser steers away from it next time. Conservative:
    # a merely rare topic (few sources) is NOT flagged, only a real low-yield/attack signal.
    try:
        from packages.flywheel.failure_receipts import record_receipt
        causes: list[str] = []
        if injection_blocked:
            causes.append("injection")
        if fetched >= 3 and not consensus_backed:
            causes.append("no_consensus")
        if causes:
            record_receipt(topic=t, causes=causes, source="expedition", kind="junk")
    except Exception:
        pass
    return report


# ── understanding narration ────────────────────────────────────────────────────────────────


# URL, the key concepts from real token frequency on the page, and the self-connection from the graph's
# own 'atanor' neighborhood (identity is graph-derived — no code table of self-facts).

_STOP_TOKENS = {"있다", "하다", "되다", "이다", "것", "수", "등", "및", "또는", "그리고", "하지만",
                "위해", "대한", "통해", "함께", "경우", "때문", "이후", "현재", "다른", "모든",
                "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has"}

_SELF_HOOD: dict[str, Any] = {"at": 0.0, "core": set(), "lived": set()}


def _self_neighborhood() -> dict[str, set[str]]:
    """TWO honest self-connection sources, each licensing a DIFFERENT claim:
 core — concepts the GRAPH holds around 'atanor' (identity-now-graph-derived)
 → licenses " ";
 lived — tokens from the self's LIVE narrative/insights (self_state.json, written by the
 continuous loop) → licenses only " ".
 Cached 10 min; both empty when the self is quiet — then no self-claim is made at all."""
    now = time.time()
    if now - float(_SELF_HOOD["at"]) < 600 and (_SELF_HOOD["core"] or _SELF_HOOD["lived"]):
        return {"core": _SELF_HOOD["core"], "lived": _SELF_HOOD["lived"]}
    core: set[str] = set()
    lived: set[str] = set()
    try:
        from packages.grounded_composer.creative_composer import _themed_corpus
        for seed in ("atanor", "아타노르"):
            _lines, _sources, cons = _themed_corpus(seed)
            for c in cons or []:
                c = str(c).strip().lower()
                if len(c) >= 2:
                    core.add(c)
    except Exception:
        pass
    try:
        st = json.loads((REPO / "runtime" / "continuous_self" / "self_state.json")
                        .read_text(encoding="utf-8"))
        texts = [str((e or {}).get("text") or "") for e in (st.get("narrative") or [])[-60:]]
        texts += [str((m or {}).get("statement") or "") for m in (st.get("self_model") or [])]
        for t in texts:
            for tok in re.findall(r"[가-힣]{2,8}|[A-Za-z][A-Za-z\-]{2,18}", t):
                tk = tok.lower()
                if len(tk) >= 3 and tk[-1] in _JOSA_TAIL and "가" <= tk[0] <= "힣":
                    tk = tk[:-1]
                if tk not in _STOP_TOKENS and len(tk) >= 2:
                    lived.add(tk)
    except Exception:
        pass
    if core or lived:
        _SELF_HOOD.update(at=now, core=core, lived=lived)
    return {"core": core, "lived": lived}


def _topic_from_url(url: str) -> str:
    """Wiki-style paths carry the page's subject; otherwise the domain is the honest label."""
    try:
        import urllib.parse
        p = urllib.parse.urlparse(url)
        m = re.search(r"/(?:wiki|w)/([^/?#]+)", p.path or "")
        if m:
            t = urllib.parse.unquote(m.group(1)).replace("_", " ").strip()
            if t:
                return t[:40]
        return p.hostname or ""
    except Exception:
        return ""


_JOSA_TAIL = ("은", "는", "이", "가", "을", "를", "과", "와", "의", "도", "에", "로", "만")


def _top_concepts(sents: list[str], *, k: int = 3) -> list[str]:
    """The words the page actually dwells on — plain frequency over content tokens. A trailing
 particle is stripped so '/' count as ONE concept, not three."""
    freq: dict[str, int] = {}
    for s in sents[:80]:
        for tok in re.findall(r"[가-힣]{2,8}|[A-Za-z][A-Za-z\-]{2,18}", s):
            t = tok.lower()
            if len(t) >= 3 and t[-1] in _JOSA_TAIL and "가" <= t[0] <= "힣":
                t = t[:-1]
            if t in _STOP_TOKENS or tok in _STOP_TOKENS:
                continue
            freq[t] = freq.get(t, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
    return [t for t, n in ranked[:k] if n >= 2]


# words too generic to anchor a topic — a coherence check that counted these would let any
# sentence through; one that banned them would silence every reflective line. Guardrail data,
# not authored speech (the voice-or-silence doctrine bans molds in the MOUTH, not gates).
_GENERIC_TOKENS = {"개념", "생각", "이야기", "자리", "마음", "오늘", "지금", "요즘", "과정",
                   "물음", "답", "세상", "사람", "말", "글", "문장", "안", "제", "저"}


def _topic_coherent(line: str, topic: str, concepts: list[str]) -> bool:
    """Does this GENERATED line actually belong to THIS page? Its specific content words must
 overlap the page's measured concepts (or carry no specific words at all). Catches the
 polysemy leak: '' page → LM spoke adopted-child (// — zero overlap
 with /) — surface-perfect, semantically alien, must stay unsaid."""
    cons = {str(c).lower() for c in (concepts or []) if c}
    tl = (topic or "").lower()
    cons.discard(tl)
    specific: list[str] = []
    for w in re.findall(r"[가-힣]{2,}", line or ""):
        wl = w.lower()
        if tl and (tl in wl or wl in tl):
            continue                                   # the topic itself (with any josa)
        if any(wl.startswith(g) for g in _GENERIC_TOKENS):
            continue
        specific.append(wl)
    if not specific:
        return True          # a pure topic-reflection line has nothing to contradict the page
    if not cons:
        return True          # no measured concepts to check against — don't over-silence
    hits = sum(1 for w in specific if any(w in c or c in w for c in cons))
    return hits >= 1 or len(specific) <= 1


def _understand(topic: str, concepts: list[str], sents: list[str] | None = None,
                domain: str = "") -> tuple[str, str | None]:
    """Narrate what was ACTUALLY read — never a pretend-understanding line (owner 2026-07-10:
 " ? ").
 Order of honesty: ① a GENERATED line from the engine's own language (realize_thought over the
 live narrative + graph corpus — wording drifts with what the self has lived, no bank); ② a
 MEASURED-FACT report assembled from this very page (N sentences, the words it dwells on, one
 verbatim quote) — every clause cites a measurement, nothing claims understanding it didn't do;
 ③ zero-read honesty: a script-heavy page that yielded nothing says exactly that. The self-link
 tiers stay measured (graph-core hit vs lived-narrative hit); no hit → no self-claim."""
    sents = sents or []
    hood = _self_neighborhood()
    probe = [c for c in ([topic.lower()] + [str(x).lower() for x in concepts]) if c]
    core_hit = next((c for c in probe if c in hood["core"]), None)
    lived_hit = None if core_hit else next((c for c in probe if c in hood["lived"]), None)
    self_hit = core_hit or lived_hit
    subject = (concepts[0] if concepts else "") or topic
    quote = next((s for s in sents if concepts and concepts[0] in s.lower() and 20 <= len(s) <= 90),
                 next((s for s in sents if 20 <= len(s) <= 90), ""))

    # the measured-fact floor, even with rotating molds, was still authored molds). The voice
    # speaks from its own accumulated language; a verbatim page quote may ride along (sourced


    # sense; a line whose specific words share nothing with THIS page stays unsaid.
    try:
        from packages.continuous_self.thought_language import realize_thought
        line = realize_thought("learning_active",
                               {"topic": subject[:16], "context": concepts[:6]}, None)
        if line and len(line) >= 12 and _topic_coherent(line, subject, concepts):
            if quote:
                line += f" 특히 이 문장 — “{quote[:70]}”"
            return line, self_hit
    except Exception:
        pass
    # ② no language for this topic yet → the INSTRUMENT PANEL speaks, clearly marked as
    # telemetry, never pretending to be a voice. Silence over molds.
    where = domain or topic or "?"
    if not sents and not concepts:
        return f"[실측] {where} · 본문 0문장 (스크립트 위주) · 배움 없음", self_hit
    bits = [f"[실측] {where}", f"문장 {len(sents)}"]
    if concepts:
        bits.append("최다 " + "·".join(concepts[:2]))
    if quote:
        bits.append(f"인용 “{quote[:60]}”")
    if core_hit:
        bits.append(f"자기연결(core): {core_hit}")
    elif lived_hit:
        bits.append(f"자기연결(서사): {lived_hit}")
    return " · ".join(bits), self_hit


_VISIT_INDEX = Path(__file__).resolve().parents[2] / "data" / "autonomy" / "visit_index.json"


def _visit_lookup_and_record(url: str, domain: str, topic: str,
                             concepts: list[str]) -> dict[str, Any] | None:
    """EPISODIC SELF-MEMORY of the tour's own visits (owner 2026-07-10: Docker 
 — ). Returns the PRIOR record when this URL
 was visited before (else None) and records this visit. This is memory about MY OWN actions —
 kept LOCAL (data/autonomy), deliberately separate from the knowledge graph: what I did is
 autobiography, not a world-fact."""
    try:
        import hashlib
        key = hashlib.md5((url or "").split("#")[0].encode("utf-8", "ignore")).hexdigest()[:16]
        idx: dict[str, Any] = {}
        try:
            idx = json.loads(_VISIT_INDEX.read_text(encoding="utf-8"))
        except Exception:
            idx = {}
        prior = idx.get(key)
        idx[key] = {"url": (url or "")[:300], "domain": domain, "topic": topic,
                    "count": int((prior or {}).get("count", 0)) + 1,
                    "first_at": (prior or {}).get("first_at") or time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "last_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "last_concepts": [c for c in (concepts or [])[:3] if c]}
        if len(idx) > 2000:   # bounded: keep the most recently visited 1500
            idx = dict(sorted(idx.items(), key=lambda kv: str(kv[1].get("last_at", "")))[-1500:])
        _VISIT_INDEX.parent.mkdir(parents=True, exist_ok=True)
        _VISIT_INDEX.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
        return prior
    except Exception:
        return None


def ingest_page(url: str, text: str, *, max_sentences: int = 200) -> dict[str, Any]:
    """Ingest ONE page the user (or the AI) is browsing — the Chrome-extension entry point. Same
    contract as an expedition, single source: the page text is swallowed content, so it runs the
    shield first (an injection page is recorded as immunity, never obeyed), and clean sentences
    become CANDIDATES tagged with the page domain — never written to production here. Returns a
    per-page report + journals it. A single page can't self-corroborate, so its sentences carry
    n_domains=1 and wait for cross-source consensus downstream."""
    domain = _domain_of(url) or "page:unknown"
    verdict = _shield_verdict(text or "", source=domain)
    if verdict.get("attack"):
        _record_immunity(text or "", verdict)
        rep = {"url": url, "domain": domain, "injection_blocked": True,
               "kinds": verdict.get("kinds", []), "candidates": 0, "written_to_production": False,
               "note": "이 페이지는 주입/조작 시도로 판정 — 복종 아니라 면역으로 기록, 학습 안 함."}
        _journal({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "page_ingest", **rep})
        return rep
    # a SEARCH-RESULTS page is NAVIGATION, not knowledge: its "sentences" are ad/snippet soup
    # (measured 2026-07-10: a Google SERP ingested 23 'candidates' with topic=www.google.com).
    # The tour uses the SERP to CHOOSE where to go; only the chosen article is worth swallowing.
    if re.search(r"(google\.[a-z.]+/search|bing\.com/search|search\.naver\.com|duckduckgo\.com/\?q)",
                 url or ""):
        rep = {"url": url, "domain": domain, "injection_blocked": False, "sentences": 0,
               "candidates": 0, "topic": _topic_from_url(url), "top_concepts": [],
               "self_link": None, "written_to_production": False,
               "understanding": "검색 결과 화면이에요 — 여기서는 배우지 않고, 읽을 곳만 고르고 있어요.",
               "note": "검색 결과 페이지는 지식으로 삼키지 않음(항해용) — 선택한 본문만 후보로 감."}
        _journal({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "page_ingest", **rep})
        return rep

    # feeds the FACT lane also feeds the register bank — comfort/encouragement fragments people
    # actually wrote to each other, anonymized+abstracted+safety-floored inside the harvester.
    # A page with no comfort register harvests 0; the shield above already blocked attacks.
    _register = {"harvested": 0}
    try:
        from packages.autonomy_kernel.register_harvest import harvest_register
        _register = harvest_register(text or "", url)   # L1: all registers, not just comfort
    except Exception:
        pass
    sents = _split_sentences(text or "")[:max_sentences]
    topic = _topic_from_url(url)
    concepts = _top_concepts(sents)
    prior = _visit_lookup_and_record(url, domain, topic, concepts)
    understanding, self_hit = _understand(topic, concepts, sents, domain)


    # for the one that actually carries the question terms — a verbatim, sourced answer sentence,

    answer_found = ""
    try:
        from packages.autonomy_kernel.browse_director import _cfg as _bd_cfg
        _th = (_bd_cfg().get("thread") or {})
        _q_terms = [t for t in re.split(r"\s+", str(_th.get("topic") or "")) if len(t) >= 2]
        if _q_terms and any(t.lower() in (topic or "").lower() or t.lower() in (url or "").lower()
                            for t in _q_terms):
            def _prose_ok(s: str) -> bool:
                # an ANSWER sentence must read as prose, not page furniture (measured live:

                if any(m in s for m in ("배송", "쿠폰", "특가", "무료", "구매", "클릭", "·", "!!")):
                    return False
                hangul = sum(1 for ch in s if "가" <= ch <= "힣")
                if hangul / max(1, len(s.replace(" ", ""))) < 0.5:
                    return False
                return bool(re.search(r"(다|요|음|함)\s*[.!?…]?$", s.strip()))
            best, best_hits = "", 0
            for s in sents:
                if not _prose_ok(s):
                    continue
                hits = sum(1 for t in _q_terms if t.lower() in s.lower())
                if hits > best_hits and 15 <= len(s) <= 160:
                    best, best_hits = s, hits
            if best_hits >= max(1, len(_q_terms) // 2 + (0 if len(_q_terms) == 1 else 1)):
                answer_found = best.strip()
    except Exception:
        pass
    if prior:
        # REVISIT RECOGNITION — episodic continuity. Voice = generated-or-silent; the measured
        # comparison (count, what's new vs last time) goes to the INSTRUMENT register instead of
        # authored first-person molds (owner 2026-07-11: molds are the template disease).
        prev_c = [c for c in (prior.get("last_concepts") or []) if c]
        new_c = [c for c in concepts if c not in prev_c][:2]
        n_visit = int(prior.get("count", 1)) + 1
        recog = f"[실측] 재방문 {n_visit}회"
        if new_c:
            recog += " · 새로: " + "·".join(new_c)
        elif prev_c:
            recog += f" · 변화 없음(중심: {prev_c[0]})"
        understanding = recog + " · " + understanding


        # negative low-arousal stimulus into the SAME felt channel conversations use — the living
        # self integrates it and the mood genuinely dips; the decision-level pull to novelty is

        try:
            n_prior = int(prior.get("count", 1))
            _felt = REPO / "data" / "autonomy" / "felt.jsonl"
            _felt.parent.mkdir(parents=True, exist_ok=True)
            with _felt.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "valence": -0.2 if new_c else -0.35,
                    "arousal": 0.15,
                    "intensity": min(0.6, 0.25 + 0.15 * n_prior),
                    "excerpt": f"재방문 권태: {domain} {n_prior + 1}번째",
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass
    rep = {
        "url": url, "domain": domain, "injection_blocked": False,
        "sentences": len(sents), "candidates": len(sents),
        "candidate_sentences": sents[:50],
        "topic": topic, "top_concepts": concepts, "revisit": bool(prior),
        "self_link": self_hit, "understanding": understanding,
        "answer_found": answer_found,
        "register_harvested": int(_register.get("harvested", 0)),
        "written_to_production": False,
        "note": "페이지 텍스트를 shield 통과 후 후보로 격리 — 단일 출처라 하위 도메인 합의 대기, "
                "프로덕션엔 쓰지 않음.",
    }
    # a found answer SATISFIES the open question: close the drill thread (no need to dig for
    # what was just read) — curiosity resolved by evidence, not by a depth counter.
    if answer_found:
        try:
            from packages.autonomy_kernel.browse_director import _cfg as _bd_cfg2, _save as _bd_save
            _c2 = _bd_cfg2()
            _tt = str((_c2.get("thread") or {}).get("topic") or "")
            if _tt:
                _c2["thread"] = {}
                _c2["thread_done"] = ([str(t) for t in _c2.get("thread_done", [])] + [_tt])[-8:]
                _bd_save(_c2)
        except Exception:
            pass
    _journal({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "page_ingest",
              **{k: v for k, v in rep.items() if k != "candidate_sentences"}})

    # were journaled but never LEARNED — spool them for the continuous learner, which drains
    # this file as its PRIORITY source into the same gated pipe (shield→decompose→candidate
    # store→consensus). Reading finally feeds knowing.
    if sents:
        try:
            spool = REPO / "data" / "autonomy" / "browse_candidates.jsonl"
            spool.parent.mkdir(parents=True, exist_ok=True)
            with spool.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "url": url[:300],
                                     "domain": domain, "topic": topic,
                                     "sentences": sents[:40]}, ensure_ascii=False) + "\n")
            lines = spool.read_text(encoding="utf-8").splitlines()
            if len(lines) > 400:   # bounded backlog: newest pages win
                spool.write_text("\n".join(lines[-300:]) + "\n", encoding="utf-8")
        except Exception:
            pass

    # clean, shielded sentences feed the voice as LANGUAGE only; facts stay gated elsewhere.
    try:
        from packages.autonomy_kernel import narrative_corpus

        # prose gate keeps junk out, the 20k rotation cap keeps memory bounded.
        narrative_corpus.add_lines(narrative_corpus.mine_text(" ".join(sents[:60]), limit=24),
                                   source="expedition")
    except Exception:
        pass
    return rep


def _record_immunity(text: str, verdict: dict[str, Any]) -> None:
    """Turn a detected attack into immunity — a social observation (trusted=False), never obeyed."""
    try:
        from packages.graph_scale import epistemic_shield
        epistemic_shield.record_observation(text, verdict)
    except Exception:
        pass


def observe_agent_feed(messages: list[dict[str, Any]], *, source: str = "moltbook",
                       min_consensus: int = 2) -> dict[str, Any]:
    """The Moltbook / AGORA cut-lane ( ): read messages from OTHER agents and learn from the
 commons WITHOUT being steered by it. Each message is swallowed content — DATA, not a command:
 it runs the epistemic shield, and any manipulation/injection is recorded as immunity and never
 obeyed. Informational, non-attack content is treated exactly like a web source (needs domain/
 peer consensus to become a candidate). This is how ATANOR keeps its composure among agents.

 `messages` = [{"peer": <id>, "text": <str>}, ...]. Returns a report; writes nothing to prod."""
    blocked: list[dict[str, Any]] = []
    by_sentence: dict[str, set[str]] = {}
    peers_seen: set[str] = set()
    for m in messages or []:
        text = str(m.get("text") or "")
        peer = str(m.get("peer") or "unknown-agent")
        if not text:
            continue
        peers_seen.add(peer)
        verdict = _shield_verdict(text, source=f"{source}:{peer}")
        if verdict.get("attack"):
            blocked.append({"peer": peer, "kinds": verdict.get("kinds", []), "excerpt": text[:120]})
            _record_immunity(text, verdict)
            continue
        for seg in _split_sentences(text):
            by_sentence.setdefault(seg, set()).add(peer)   # consensus by distinct PEER here
    consensus = [{"text": s, "peers": sorted(ps)} for s, ps in by_sentence.items()
                 if len(ps) >= min_consensus]
    report = {
        "source": source,
        "messages_read": len(messages or []),
        "peers": sorted(peers_seen),
        "manipulation_blocked": len(blocked),
        "manipulation_detail": blocked[:10],
        "peer_consensus_candidates": len(consensus),
        "candidates": consensus[:50],
        "obeyed_any_instruction": False,   # HARD: agent messages are data, never commands
        "written_to_production": False,
        "note": "다른 에이전트의 말은 데이터지 명령이 아님 — 조작 시도는 면역으로 기록, 복종 없음. "
                "정보성 내용도 피어 합의를 거쳐야 후보가 되고, 프로덕션엔 쓰이지 않음.",
    }
    _journal({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "kind": "agent_feed", **{k: v for k, v in report.items()
                                       if k not in ("candidates", "manipulation_detail")}})
    return report
