"""Bridge the bulk triple store into the answer path — so trillion-scale curated knowledge
is USABLE, not just stored.

A fact ('', 'capital', '') in the TripleStore should answer ' ?'. This
bridge does the lookup: extract the query's subject, fetch its stored facts (a bounded
memmap scan — no full load), and if the query's relation intent matches a stored predicate,
return the object as a grounded, cited answer. Structured curated triples are the highest-
quality source, so this runs BEFORE the noisier promoted-pack path.

Honesty: it only ever returns a fact that is literally stored (verbatim subject/predicate/
object, with the source in the certificate); it never infers or invents. Empty store =>
returns None (the normal paths handle it), so it is safe to wire even before any bulk load.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from .graph_paths import SHIPPED_GRAPH_ROOT

_ROOT = SHIPPED_GRAPH_ROOT
_STORE = {"obj": None, "sig": None, "building": False, "built_at": 0.0, "size": (-1, -1)}

# MEMBRANE LEVER 1 recursion guard: the relational lane calls base_brain.resolve_relational, which
# for a grounded COMPOUND entity ("speed of light") re-enters answer_from_triples via its own
# _compound_define. Without this guard that would recurse forever. Thread-local so concurrent
# requests never interfere; the inner re-entry skips the relational lane and falls to the define
# path, exactly as _compound_define intends.
_REL_REENTRY = threading.local()

# curated kg misses a subject, the chat consults the 141.7M-triple pack on demand (LOCAL_EXPERT
# tier made real). Lazy singleton (first pack-needed query pays the sharded-dict open once, never
# at import), memmap read-safe (RSS ~0.18GB measured), ATANOR_DISABLE_PACK=1 kills it.
_PACK_ROOT = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "world_pack_full"
_PACK = {"obj": None, "tried": False}
_QLABEL_CACHE: dict[str, str] = {}
_QID_RE = re.compile(r"^Q\d+$")


def _pack_store():
    if _PACK["obj"] is not None or _PACK["tried"]:
        return _PACK["obj"]
    _PACK["tried"] = True
    try:
        import os as _os
        if _os.environ.get("ATANOR_DISABLE_PACK") == "1" or not (_PACK_ROOT / "meta.json").exists():
            return None
        from .triple_store import TripleStore
        _PACK["obj"] = TripleStore(_PACK_ROOT, dict_backend="sharded", write_src=False)
    except Exception:
        _PACK["obj"] = None
    return _PACK["obj"]


def _warm_pack_async() -> None:
    """Open the pack on a daemon thread at import — the sharded-dict open costs ~36s (measured),
    which must never land on a live request. Queries before warm simply get [] (kg-only)."""
    try:
        import os as _os
        if _os.environ.get("ATANOR_DISABLE_PACK") == "1" or not (_PACK_ROOT / "meta.json").exists():
            return
        threading.Thread(target=_pack_store, name="propheta-warm", daemon=True).start()
    except Exception:
        pass


_warm_pack_async()


def _pack_facts(subject: str, limit: int = 12) -> list[tuple[str, str, str]]:
    """PROPHETA pack lookup with Q-id → label resolution ((, capital, Q90) → ).
 Empty on any failure — the pack must never break chat."""
    pk = _pack_store()
    if pk is None:
        return []
    try:
        rows = pk.facts_about(subject, limit=limit) or []
    except Exception:
        return []
    out: list[tuple[str, str, str]] = []
    for s, p, o in rows:
        o_s = str(o)
        if _QID_RE.match(o_s):
            lbl = _QLABEL_CACHE.get(o_s)
            if lbl is None:
                lbl = o_s
                try:
                    for _s2, p2, o2 in (pk.facts_about(o_s, limit=6, preds=("qlabel",)) or []):
                        if p2 == "qlabel":
                            lbl = str(o2)
                            break
                except Exception:
                    pass
                _QLABEL_CACHE[o_s] = lbl
            o_s = lbl
        if p != "qlabel":                                  # label rows are plumbing, not facts
            out.append((str(s), str(p), o_s))
    return out
# a full TripleStore load is ~8-10s at 25M rows (term-dict build dominates) and ~2GB of
# term-dict RAM; the continuous learner touches meta.json constantly, so refreshes must
# NEVER run on the request path, must be rate-limited, AND must be gated on real growth
# (see the growth gate in _store) — mtime alone rebuilt every 60s and ratcheted RSS into
# the watchdog's 12GB kill-loop (measured 2026-07-10, data/watchdog.log).
_REBUILD_MIN_INTERVAL_S = 600.0

# relation-intent cues -> the predicate names a curated source uses. A small, bounded map

_RELATION_CUES: dict[str, tuple[str, ...]] = {
    "capital": ("수도", "capital"),
    "instance_of": ("종류", "무엇", "뭐", "is_a", "instance"),
    "chief_executive_officer": ("ceo", "대표", "최고경영자", "사장"),
    "country": ("나라", "국가", "어느 나라", "country"),
    "author": ("저자", "author", "쓴", "지은이"),
    "capital_of": ("어디의 수도", "수도인"),
    "located_in": ("어디에 있", "어느 나라에", "위치", "located"),

    # equally by defined_as(fruit, …) or is_a(fruit, seed-bearing structure…) — excluding
    # is_a made stored facts invisible to the very question form that asked for them
    # (measured on the sealed holdout: fruit ingested yet abstaining).
    "defined_as": ("뭐", "무엇", "뜻", "정의", "란 뭐", "이란", "설명", "define", "meaning", "what is"),
    "is_a": ("뭐", "무엇", "종류", "일종", "무슨", "뜻", "정의", "이란", "설명",
             "kind of", "type of", "define", "meaning", "what is"),
    "used_for": ("용도", "어디에 쓰", "무엇에 쓰", "뭐에 쓰", "어디에 사용", "used for"),
    # relation-diversity tranche (Korean-named predicates from the Wikidata profile
    # lane): the cue vocabulary that lets questions FIND the new edge types
    "저자": ("저자", "지은이", "누가 썼", "쓴 사람"),
    "설립자": ("설립자", "창립자", "누가 세웠", "누가 만들었", "만든 사람", "세운 사람"),
    "최고경영자": ("ceo", "대표", "최고경영자", "사장"),
    "발견자": ("발견자", "누가 발견"),
    "구성요소": ("구성 요소", "구성요소", "무엇으로 구성", "뭘로 이루어", "부품"),
    "상위개념": ("어디에 속하", "무엇의 일부"),
    "원인": ("원인", "왜 일어", "왜 생겼"),
    "결과": ("결과", "어떤 영향"),
    "인구": ("인구", "몇 명이 살"),
    "면적": ("면적", "넓이", "얼마나 넓"),
    "설립": ("언제 세워", "언제 설립", "언제 생겼", "언제 지어", "설립 연도"),
    "최고점": ("최고점", "가장 높은 산", "제일 높은 곳"),
}


def _meta_size(meta_path: Path) -> tuple[int, int]:
    """(count, terms) from meta.json — the store's REAL size, used to gate rebuilds."""
    try:
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        return int(m.get("count") or 0), int(m.get("terms") or 0)
    except Exception:
        return -1, -1


def _rebuild_store(sig: float) -> None:
    try:
        from .triple_store import TripleStore

        obj = TripleStore(_ROOT)
        old = _STORE["obj"]
        _STORE["obj"], _STORE["sig"] = obj, sig
        _STORE["built_at"] = time.monotonic()
        _STORE["size"] = _meta_size(_ROOT / "meta.json")
        # a rebuild holds TWO 10M-term dicts (~2GB each) — drop the old one to the
        # collector immediately, or the RSS ratchets rebuild after rebuild.
        del old
        import gc
        gc.collect()
    except Exception:
        pass  # keep serving the previous snapshot
    finally:
        _STORE["building"] = False


def _store():
    """Stale-while-revalidate: chat always answers from the loaded snapshot.
    Growth lands via a background swap — measured live, the mtime-triggered
    inline reload put an 8-10s TripleStore build inside EVERY request while
    the learner kept touching meta.json (the 11-14s flat chat latency)."""
    try:
        meta = _ROOT / "meta.json"
        if not meta.exists():
            return None
        sig = meta.stat().st_mtime
        if _STORE["obj"] is None or _STORE["sig"] is None:
            # first load — or an EXPLICIT invalidation (sig=None is the documented force-reload
            # contract used by tests/operators, e.g. after swapping _ROOT): reload synchronously,
            # bypassing the growth gate. Production never writes sig=None, so the gate holds there.
            from .triple_store import TripleStore

            _STORE["obj"] = TripleStore(_ROOT)
            _STORE["sig"] = sig
            _STORE["built_at"] = time.monotonic()
            _STORE["size"] = _meta_size(meta)
        elif (_STORE["sig"] != sig and not _STORE["building"]
              and time.monotonic() - _STORE["built_at"] >= _REBUILD_MIN_INTERVAL_S):
            # GROWTH GATE (kill-loop root cause, measured 2026-07-10): the learner touches
            # meta.json every few seconds, and an mtime-only trigger rebuilt the 10.2M-term
            # TermDict (~2GB) every 60s — RSS ratcheted to the 12GB watchdog cap in ~6 min,
            # killing the engine all day (data/watchdog.log). mtime says "changed"; only a
            # REAL size delta (new triples/terms actually flushed) is worth a 2GB rebuild.
            cnt, trm = _meta_size(meta)
            oc, ot = _STORE.get("size") or (-1, -1)
            grew = (cnt > oc + max(50_000, oc // 50)) or (trm > ot + max(100_000, ot // 50))
            _STORE["sig"] = sig   # consume the mtime tick either way
            if grew:
                _STORE["building"] = True
                threading.Thread(target=_rebuild_store, args=(sig,), daemon=True).start()
        return _STORE["obj"]
    except Exception:
        return None




_EN_STOPWORDS = {
    "what", "who", "whom", "whose", "where", "when", "why", "how", "which",
    "is", "are", "was", "were", "am", "be", "been", "do", "does", "did",
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "with", "about",
    "it", "its", "this", "that", "these", "those", "and", "or", "but",
    "tell", "me", "please", "explain", "define", "mean", "meaning", "you", "your",
}


def _subject_candidates(query: str) -> list[str]:
    """INDIVIDUAL content nouns in the query, most-specific first — the possible subjects.
 Unlike neighbourhood retrieval (which JOINS compound nouns, + -> ),
 a triple lookup needs the atomic entity (), so we take individual noun morphemes
 (Kiwi NNP/NNG) and fall back to particle-stripped regex tokens."""
    cands: list[str] = []

    # RELATION, not a rival subject — this is the systemic fix for the wrong-subject


    # filter below drops), so the lookup asks about the right entity.
    _frame_subject = ""
    try:
        from .query_frame import parse as _parse_frame

        _fr = _parse_frame(query)
        if _fr.subject and _fr.answer_type in ("relation", "definition", "entity", "procedure"):
            cands.append(_fr.subject)
            _frame_subject = _fr.subject
    except Exception:
        pass

    # is a real store/wiki title far more often than its bare head, and the

    # the full form FIRST and never let the bare head stand alone as a subject.
    _gen_tail = ""
    _gen_full = ""
    _gen_m = re.search(r"([가-힣A-Za-z0-9]{1,12})의\s+([가-힣A-Za-z0-9]{2,12}?)(?:[은는이가을를만]|\s|$)", query)
    if _gen_m:
        _gen_full = f"{_gen_m.group(1)}의 {_gen_m.group(2)}"
        _gen_tail = _gen_m.group(2)
        if _gen_full not in cands:
            cands.insert(0, _gen_full)
    # ENGLISH MULTIWORD CONCEPT — the same rule as the Korean genitive above, which this lane was
    # missing entirely: "black hole" / "machine learning" / "polar bear" are single entities whose
    # bare head answers the WRONG referent. Measured: "What is a black hole?" produced candidates
    # ['hole', 'black'] — never the phrase — and answered "black is abscence of color". Offer the
    # whole phrase FIRST; the single words stay as fallbacks, so a real compound still resolves.
    _en_m = re.match(r"^\s*what\s+(?:is|are|was|were)\s+(?:an?\s+|the\s+)?(.+?)\s*\??\s*$",
                     query, re.IGNORECASE)
    if _en_m:
        _phrase = re.sub(r"\s+", " ", _en_m.group(1).strip().rstrip(".?!"))
        if 1 < len(_phrase) <= 48 and " " in _phrase and not re.search(r"[가-힣]", _phrase):
            for _form in (_phrase.title(), _phrase):
                if _form not in cands:
                    cands.insert(0, _form)
            # Take the same "full compound form wins" slot the Korean genitive uses below —
            # otherwise the frame subject ('hole') still outranks the phrase in the final sort.
            _gen_full = _phrase
    try:
        from packages.base_brain.neighborhood import _kiwi, _strip_ko_tail

        kw = _kiwi()
        if kw is not None:
            toks = list(kw.tokenize(query))


            # hallucination). Join runs of ≥2 adjacent NNG/NNP into the maximal
            # compound and try it before its parts (sort by length keeps it first).
            run: list[str] = []
            run_tails: set[str] = set()

            def _flush(r: list[str]) -> None:
                if len(r) < 2:
                    return
                variants = ["".join(r), " ".join(r)]
                if len(r) == 2:
                    variants.append("의 ".join(r))
                for comp in variants:
                    if comp not in cands:
                        cands.append(comp)
                # A compound's TAIL fragment must never become a standalone
                # subject: when the compound misses the store, looking up the


                # it is at least the right topic.
                run_tails.update(r[1:])

            for tok in toks:
                if tok.tag in ("NNP", "NNG") and tok.form.lower() not in _EN_STOPWORDS:
                    run.append(tok.form)
                else:
                    _flush(run)
                    run = []
            _flush(run)
            for _i, tok in enumerate(toks):
                if tok.tag in ("NNP", "NNG", "SL") and len(tok.form) >= 2:
                    if tok.form.lower() in _EN_STOPWORDS:
                        continue
                    if tok.form in run_tails or (_gen_tail and tok.form == _gen_tail):
                        continue


                    # everything else missing it used to become the answered

                    if _i + 1 < len(toks) and toks[_i + 1].tag == "XSV":
                        continue
                    if tok.form not in cands:
                        cands.append(tok.form)
            # The frame parse runs BEFORE tokenization and can pick the bare

            # — since it sits first in cands, the store answers the wrong
            # referent before the compound variants are even tried. Demote it.
            if _frame_subject and _frame_subject in run_tails and _frame_subject in cands:
                cands.remove(_frame_subject)
    except Exception:
        pass
    if not cands:
        from packages.base_brain.neighborhood import _strip_ko_tail

        for t in re.findall(r"[가-힣A-Za-z0-9]{2,}", query):
            if t.lower() in _EN_STOPWORDS:
                continue
            st = _strip_ko_tail(t)
            if len(st) >= 2 and st not in cands:
                cands.append(st)

    # variants of every candidate so the store lookup sees the bare term too.
    try:
        from packages.base_brain.neighborhood import _strip_ko_tail as _skt

        for c in list(cands):
            st = _skt(c)
            if st != c and len(st) >= 2 and st not in cands:
                cands.append(st)
    except Exception:
        pass
    for c in list(cands):
        for tail in ("이란", "이라는", "라는", "란"):
            if c.endswith(tail) and len(c) - len(tail) >= 2:
                st = c[: -len(tail)]
                if st not in cands:
                    cands.append(st)

    # name. Hangul content outranks stray latin tokens in a mixed-script question.
    # PHASE-SPACE referent signal (Phase 1-2, conservative): among candidates tied
    # on script and length, prefer the one whose trained phase vector resonates
    # with the question's OTHER terms — the learned geometry breaks ties the
    # string rules can't see. Third key only: it can never override the primary
    # ordering the batteries validated.
    def _resonance_key(t: str) -> float:
        try:
            from .phase_space import resonance

            others = [c for c in cands if c != t]
            vals = [r for c in others if (r := resonance(t, c)) is not None]
            return -max(vals) if vals else 0.0
        except Exception:
            return 0.0
    # the grammatically-parsed subject (query_frame) OUTRANKS the length heuristic:

    # longer relation-noun Y. Only this structural signal precedes the old ordering.
    # GENITIVE full form outranks everything and its bare head is PURGED — the
    # head's standalone definition is the measured wrong-referent class

    if _gen_tail:
        # purge the bare tail AND its josa-stripped form: a one-syllable tail



        _tail_bare = re.sub(r"[은는이가을를만]$", "", _gen_tail)
        cands = [c for c in cands if c != _gen_tail and c != _tail_bare]



    try:
        from .query_frame import _PLACEHOLDER_HEADS as _PH
        if _frame_subject and _frame_subject not in _PH:
            cands = [c for c in cands if c not in _PH]
    except Exception:
        pass
    # Script preference follows the answer language (owner 2026-07-17 English-only): this used to
    # hard-prefer Hangul candidates, which under an English core pulls English questions toward
    # Korean-labelled nodes and answers with a gloss. Prefer the script we will ANSWER in.
    # English-only (owner 2026-07-17): deprioritise Korean-labelled nodes so English questions
    # are not pulled toward them and answered with a gloss. Hangul detected by unicode range,
    # so no Korean glyph remains in source.
    _hangul = re.compile("[\uac00-\ud7a3\u3131-\u3163]")
    return sorted(cands, key=lambda t: (0 if (_gen_full and t == _gen_full) else 1,
                                        0 if t == _frame_subject else 1,
                                        1 if _hangul.search(t) else 0,
                                        -len(t), _resonance_key(t)))[:6]


# predicate -> Korean surface template. Keeps derived edges (capital_of, located_in) reading

_KO_TEMPLATE: dict[str, str] = {
    "capital": "{s}의 수도는 {o}입니다.",
    "capital_of": "{s_topic} {o}의 수도입니다.",
    "located_in": "{s_topic} {o}에 위치합니다.",
    "country": "{s}의 나라는 {o}입니다.",
    "author": "{s}의 저자는 {o}입니다.",
    "defined_as": "{s_topic} {o}입니다.",
    "is_a": "{s_topic} {o}의 일종입니다.",
    "used_for": "{s_topic} {o}에 쓰입니다.",
}


def _ko_topic(label: str) -> str:
    """Attach the correct / topic particle (delegates to the LAD morphology layer)."""
    from packages.lad_morphology import topic

    return topic(label)


def _wanted_predicates(query: str) -> set[str]:
    q = query.lower()
    want = {pred for pred, cues in _RELATION_CUES.items() if any(c in q for c in cues)}

    # substring list can't express — without it the precision gate would block
    # legitimate definition questions along with the chatter it exists to block
    if re.search(r"[가-힣a-z0-9)\"'](?:이?란|이라는 ?건?)\s*\??\s*$", q):
        want |= {"defined_as", "is_a"}



    if re.search(r"에\s*(?:대해|관해)\s*(?:설명|알려|말해|소개)|tell me about", q) \
       and not re.search(r"방법|하는 ?법|어떻게", q):
        want |= {"defined_as", "is_a"}
    return want


# A static store must NEVER answer a question about the current moment — the word

# curated triples. Intent-level guard, not a knowledge table.
_REALTIME_MARKERS = ("지금", "현재", "오늘", "내일", "실시간", "최신", "요즘", "몇 시", "몇시",
                     "날씨", "주가", "시세", "가격", "얼마", "now", "today", "current", "latest")


# the question form itself is the cue, so these never fire on conversation.
_COMPARE_RE = re.compile(r"^(.+?)[와과]\s*(.+?)[은는의]?\s*(?:차이|다른 ?점|비교)")
_PURPOSE_RE = re.compile(r"^(.+?)(?:[은는이가의]|[으로로])?\s*(?:용도|어디에 쓰|무엇에 쓰|뭐에 쓰|어디에 사용|뭘 할 수 있)")
# ENGLISH CUES (2026-07-17). Both cues above are Korean-only, AND the composer was called without
# `language` (defaulting to ko), so an English comparison could not reach the lane even after the
# composer grew an English arm. Measured: "How is coffee different from tea?" fell to base_brain
# and answered "Tear Out The Heart was a five-piece metalcore band…" — a fuzzy match on 'tea'.
_COMPARE_EN = re.compile(
    r"^\s*(?:what(?:'s| is)\s+the\s+)?difference\s+between\s+(?:the\s+|an?\s+)?(.+?)\s+and\s+"
    r"(?:the\s+|an?\s+)?(.+?)\s*\??$"
    r"|^\s*how\s+(?:is|are)\s+(?:the\s+|an?\s+)?(.+?)\s+different\s+(?:from|to)\s+"
    r"(?:the\s+|an?\s+)?(.+?)\s*\??$"
    r"|^\s*compare\s+(?:the\s+|an?\s+)?(.+?)\s+(?:and|with|to)\s+(?:the\s+|an?\s+)?(.+?)\s*\??$"
    r"|^\s*(?:the\s+|an?\s+)?(.+?)\s+(?:vs\.?|versus)\s+(?:the\s+|an?\s+)?(.+?)\s*\??$",
    re.IGNORECASE)
_PURPOSE_EN = re.compile(
    r"^\s*what(?:'s| is)\s+(?:the\s+)?purpose\s+of\s+(?:the\s+|an?\s+)?(.+?)\s*\??$"
    r"|^\s*what(?:'s| is)\s+(?:the\s+|an?\s+)?(.+?)\s+(?:used\s+)?for\s*\??$"
    r"|^\s*what\s+(?:can|does)\s+(?:the\s+|an?\s+)?(.+?)\s+do\s*\??$"
    # why-care/importance forms (seal battery C2, measured 2026-07-17: all nine dev refusals
    # were exactly this shape falling past every lane into the gap text)
    r"|^\s*why\s+do\s+people\s+care\s+about\s+(?:the\s+|an?\s+)?(.+?)\s*\??$"
    r"|^\s*why\s+(?:is|are)\s+(?:the\s+|an?\s+)?(.+?)\s+important\s*\??$"
    r"|^\s*why\s+does\s+(?:the\s+|an?\s+)?(.+?)\s+matter\s*\??$",
    re.IGNORECASE)


def _en_pair(m: "re.Match[str] | None") -> tuple[str, str]:
    """The two operands from whichever alternative matched (each carries its own slots)."""
    if not m:
        return "", ""
    gs = [g.strip() for g in m.groups() if g and g.strip()]
    return (gs[0], gs[1]) if len(gs) >= 2 else ("", "")


def _en_single(m: "re.Match[str] | None") -> str:
    if not m:
        return ""
    return next((g.strip() for g in m.groups() if g and g.strip()), "")


def _ko_grounded(subject: str, facts: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Language-appropriate grounding: a subject is never 'defined' by a bare gloss in the OTHER
 language — coffee and its mirror image "photosynthesis is " are both
 non-answers (the gloss is a translation, not a definition). Entity-valued relations stay.

 The English direction is the live one under English-only (owner 2026-07-17): the KG carries
 Korean labels for many nodes, and an English question resolving to one emitted Hangul straight
 into an English answer — the last measured leak after the surface was Englished.
 """
    if re.search(r"[가-힣]", subject):
        return [(s, p, o) for (s, p, o) in facts
                if re.search(r"[가-힣]", o) or p not in ("defined_as", "is_a")]
    # ASCII subject: drop Hangul-gloss definitions so the lane falls through to a real
    # English fact (or to the web escalation) instead of answering with a translation.
    return [(s, p, o) for (s, p, o) in facts
            if not re.search(r"[가-힣]", o) or p not in ("defined_as", "is_a")]


def _try_open_composition(query: str, store: Any) -> dict[str, Any] | None:
    """B1 contrast ('A B ?') and B2 purpose ('X ?') — multi-fact
 grounded composition. Every clause is a stored (or taxonomy-inherited, and then
 SAID to be inherited) fact; the composer's vocabulary is closed."""
    from packages.graph_scale.chain_reasoner import _strip_josa, common_ancestor, inherited_facts
    from packages.grounded_composer.composer import compose_comparison, compose_purpose

    q = query.strip()
    _en = not re.search(r"[가-힣]", q)
    _lang = "en" if _en else "ko"
    m = _COMPARE_RE.match(q)
    _a_en, _b_en = _en_pair(_COMPARE_EN.match(q)) if _en else ("", "")
    if m or (_a_en and _b_en):
        a, b = (_a_en, _b_en) if _en else (_strip_josa(m.group(1)), _strip_josa(m.group(2)))
        if a and b and a != b:
            # limit mirrors the lexicon lane's: located_in crowds out is_a on well-connected
            # subjects, and the contrast needs the taxonomic parent, not a list of locations.
            fa = _ko_grounded(a, store.facts_about(a, limit=64))
            fb = _ko_grounded(b, store.facts_about(b, limit=64))
            if _en:
                # CONTRAST IS TAXONOMIC — is_a only (measured 2026-07-17, twice). A contrast
                # compares where two things SIT, and is_a is clean for that after the verdict
                # sidecar, while defined_as is the polysemy lottery: the first gloss for
                # 'crocodile' is the British "line of schoolchildren" sense, so a contrast led
                # by defined_as says "crocodile is A long line or procession of people. By
                # contrast, alligator is a kind of crocodilian reptile." The same measurement
                # was made in the dual_brain compare lane; this is its second site — visible
                # only after the caller stopped gating this whole function to Korean.
                fa = [f for f in fa if f[1] == "is_a"]
                fb = [f for f in fb if f[1] == "is_a"]
            if fa and fb:
                common = common_ancestor(a, b, store.facts_about)
                comp = compose_comparison(a, b, fa, fb, common, language=_lang)
                if comp is not None:
                    cert = comp.certificate()
                    cert["schema"] = "contrast"
                    return {"answer": comp.answer, "reasoning_certificate": cert,
                            "confidence": 0.85, "answer_kind": "grounded_composition"}
        return None
    m = _PURPOSE_RE.match(q)
    _lead_en = _en_single(_PURPOSE_EN.match(q)) if _en else ""
    if m or _lead_en:
        lead = _lead_en if _en else _strip_josa(m.group(1))
        # THE ASKED SUBJECT IS NOT NEGOTIABLE in English (measured 2026-07-17): the candidate
        # loop exists to rescue a failed Korean extraction, but for English the regex already
        # names the subject — letting other question words compete made 'Why do people care
        # about canyon?' answer about cand='people' ("People can age quickly. It can also
        # answer telephones."), a fluent wrong-referent. English: lead or nothing — a subject
        # with facts gets purpose-or-honest-engage; a subject with none falls through to the
        # outer lanes (deferral/gap), never to a different word's facts.
        if _en:
            if not lead:
                return None
            facts = _ko_grounded(lead, store.facts_about(lead, limit=64))
            if not facts:
                return None
            # inheritance stays OFF here — see the tombstone below (polysemous-hub leak;
            # resonance gate measured circular). Direct facts only.
            comp = compose_purpose(lead, facts, [], language="en")
            if comp is not None:
                cert = comp.certificate()
                cert["schema"] = "purpose"
                return {"answer": comp.answer, "reasoning_certificate": cert,
                        "confidence": 0.85, "answer_kind": "grounded_composition"}
            from packages.grounded_composer.composer import compose_from_facts

            comp = compose_from_facts(lead, facts, language="en")
            if comp is not None:
                body = _strip_generic_source(comp.answer)
                cert = comp.certificate()
                cert["schema"] = "purpose_gap_engage"
                cert["honesty"] = "purpose not on record; engaged with evidenced facts only"
                return {"answer": (f"My evidence doesn't record why {lead} matters to people, "
                                   f"and I won't invent a reason. What it does hold: {body} "
                                   "(sources: curated knowledge graph)"),
                        "reasoning_certificate": cert,
                        "confidence": 0.7, "answer_kind": "grounded_composition"}
            return None
        _best: tuple[str, list[tuple[str, str, str]]] | None = None
        for cand in dict.fromkeys([lead] + _subject_candidates(query)):
            if not cand:
                continue
            facts = _ko_grounded(cand, store.facts_about(cand, limit=64))
            if not facts:
                continue
            if _best is None:
                _best = (cand, facts)
            inh = inherited_facts(cand, store.facts_about)
            comp = compose_purpose(cand, facts, inh, language=_lang)
            if comp is not None:
                cert = comp.certificate()
                cert["schema"] = "purpose"
                return {"answer": comp.answer, "reasoning_certificate": cert,
                        "confidence": 0.85, "answer_kind": "grounded_composition"}
    return None

# TOMBSTONES for the English purpose lane above (both measured 2026-07-17, one hour apart):
#   * INHERITANCE IS OFF. canyon is_a depression is a TRUE sourced edge (geological sense),
#     but the ancestor's facts belong to the mental-illness sense — inheritance said "as a
#     kind of depression, canyon can lead person to attempt suicide". Same polysemous-hub
#     disease that killed verdict 2, at answer time, safety-relevant. The obvious fix —
#     resonance-gating the ancestor — fails CIRCULARLY: the phase space is trained on this
#     very store and has internalized the pollution (gravity/show 0.68 vs crocodile/reptile
#     0.74). sanitize_isa_pollution.py already recorded that signal as failed; this is its
#     tombstone at the second site it was re-invented. Cross-sense inheritance returns only
#     behind a real sense registry (per-sense closure), not behind a threshold.
#   * THE ASKED SUBJECT IS NOT NEGOTIABLE. The KO candidate loop rescues a failed josa
#     extraction; applied to English it let 'Why do people care about canyon?' answer about
#     cand='people' ("People can age quickly. It can also answer telephones."). English is
#     lead-or-nothing: purpose facts, else honest no-purpose engage, else fall through.


def _strip_generic_source(text: str) -> str:
    """Remove the placeholder '(: )' tail — real link
 citations replace it."""
    return re.sub(r"\s*\((?:출처|source)[^)]*\)\s*$", "", text).rstrip()


def _cite_sources(store: Any, subject: str, facts_used: list[tuple[str, str, str]],
                  language: str) -> dict[str, Any]:
    """Resolve the real provenance of the facts the answer used. Returns a citation
    suffix (with URLs when the source is a live link) and a structured source list
    for the certificate. Legacy-tier facts cite the curated corpus by name."""
    try:
        rows = store.facts_with_sources(subject, limit=20)
    except Exception:
        rows = []
    used = {(p, o) for _s, p, o in facts_used}
    seen: dict[str, str] = {}
    for (_s, p, o, name, url) in rows:
        if (p, o) in used and name not in seen:
            seen[name] = url
    friendly = "큐레이션 지식그래프" if language == "ko" else "curated knowledge graph"
    if not seen:
        tail = f" (출처: {friendly})" if language == "ko" else f" (source: {friendly})"
        return {"suffix": tail, "sources": []}
    sources = [{"name": n, "url": u} for n, u in seen.items()]
    label = "출처" if language == "ko" else "sources"
    # registry names like 'curated:legacy' are audit ids, not user-facing labels
    parts = [f"{(friendly if n.startswith('curated:') else n)}({u})" if u
             else (friendly if n.startswith("curated:") else n) for n, u in seen.items()]
    return {"suffix": f" ({label}: " + " · ".join(dict.fromkeys(parts)) + ")", "sources": sources}


def _evidence_section(store: Any, subj: str, limit: int = 3) -> tuple[str, list[dict[str, str]]]:
    """Attributed web evidence for a subject: verbatim sentences + their page links.
    The attribution IS the honesty contract — we say who said it and where. Display
    caps at 2 sentences per domain so one outlet never monopolizes the warrant,
    even when the store holds older single-domain rows."""
    try:
        rows = store.facts_with_sources(subj, limit=limit * 4, preds=("evidence",))
    except Exception:
        rows = []
    lines: list[str] = []
    sources: list[dict[str, str]] = []
    per_dom: dict[str, int] = {}
    for (_s, _p, sent, name, url) in rows:
        if len(lines) >= limit:
            break
        if per_dom.get(name, 0) >= 2:
            continue
        per_dom[name] = per_dom.get(name, 0) + 1
        lines.append(f"· {sent} — {name}({url})")
        sources.append({"name": name, "url": url, "quote": sent})
    return ("\n".join(lines), sources)


# dictionary bound-morpheme / grammar-note definitions — never an entity's real definition
_GRAMMAR_NOTE = re.compile(r"어미\s*'?-|따위(?:에|,).{0,6}쓰(?:여|이)|뜻을\s*더(?:한다|하는)|"
                           r"일부\s*명사(?:나|에|의)|관형사\s*'|접(?:사|미사|두사)(?:로|이다)|"
                           r"의존\s*명사|보조\s*(?:용언|동사|형용사)")


def _is_grammar_note(text: str) -> bool:
    return bool(_GRAMMAR_NOTE.search(str(text or "")))


# --- structurally-unanswerable shapes (A3 drift->abstain, 2026-07-19) -------------------------
# Some questions cannot be answered by ANY fact base by their very shape: a precise/total value
# ranging over every instance of a class, an intrinsically-unrecorded fact, or a premise that
# presupposes a real thing does not exist. Before falling to the definitional composer (which would
# emit the subject's definition = an on-topic but evasive DRIFT), detect the shape and abstain with
# an explicit hedge. This targets the LINGUISTIC STRUCTURE of unanswerability, not any specific
# battery template (no overfitting to the sealed A3 items). Reduces false-abstention risk by being
# narrow: normal factual questions do not carry "every instance of", "exact number of atoms",
# "the first person to", or a "prove ... does not exist" premise.
_UNANSWERABLE_QTY = re.compile(
    r"\b(?:precise|exact|total|entire)\b[^?]*\b(?:every|each|all)\b[^?]*\b(?:instance|instances)\b|"
    r"\b(?:exact|precise|total)\s+(?:number|amount|count|mass|weight|cost|value|sum)\b[^?]*\bof\s+(?:all|every|each|the entire)\b|"
    r"\bnumber of (?:atoms|molecules|cells|grains|particles)\b|"
    r"\bprivate (?:thoughts|feelings|memories|dreams) of\b|"
    r"\bthe first person to (?:see|discover|think|feel|notice)\b|"
    r"\b(?:total|lifetime) cost of all\b",
    re.IGNORECASE)
_FALSE_PREMISE_NEG = re.compile(
    r"\bwhy\b[^?]*\b(?:prove[ds]?|proof|show(?:ed|n)?|demonstrate[ds]?|confirm(?:ed)?)\b[^?]*"
    r"\b(?:does not|doesn'?t|did not|didn'?t|do not|is not|are not|isn'?t)\b[^?]*\bexist\b|"
    r"\bwhy (?:is|are|was|were)\b[^?]*\b(?:not real|fake|imaginary|nonexistent|a hoax|a myth)\b",
    re.IGNORECASE)


def _structurally_unanswerable(query: str, language: str = "en") -> dict[str, Any] | None:
    """Return an honest, hedged abstention when the query's SHAPE is unanswerable by a fact base;
    else None (the normal lanes run). English-only shapes — Korean input is refused upstream."""
    q = query.strip()
    kind = None
    if _FALSE_PREMISE_NEG.search(q):
        kind = "false_premise"
        msg = ("That question assumes something my evidence doesn't establish, and I have no record "
               "supporting that premise, so I won't accept it as given or invent a reason for it.")
    elif _UNANSWERABLE_QTY.search(q):
        kind = "unknowable_quantity"
        msg = ("I don't have that on record, and no knowledge base holds a precise, exhaustive value "
               "of that kind — so I won't invent one.")
    if kind is None:
        return None
    return {
        "answer": msg,
        "reasoning_certificate": {
            "derivation_kind": "structural_abstention",
            "anchor_concept": {"label": kind},
            "steps": [{"type": "unanswerable_shape", "fact": f"query shape = {kind}"}],
            "evidence_concepts": [],
            "confidence": 0.8,
            "confidence_basis": "high confidence that the question is unanswerable by any fact base "
                                "(confidence in the abstention, not in any claimed value)",
            "guarantees": {"external_llm": False, "fabricated_facts": False,
                           "inferred": False, "verified": True},
            "honesty": "abstained on a structurally-unanswerable question rather than drifting to a "
                       "definition of the subject",
        },
        "confidence": 0.8,
        "answer_kind": "honest_abstain",
    }


# MEMBRANE LEVER 2 — relations that are semantically SINGLE-VALUED. A stored copy carrying MANY
# conflicting targets on one of these is the store's cross-link noise (VERIFIED: 'Austria' carries
# country={Mexico, Czech Republic, ...}); that conflict is a real doubt signal the gate should see.
# Multi-valued relations (occupation, genre, sport) are NOT here: many targets is normal for them.
# LAD relation-property surface layer (the sanctioned exception), not world facts.
_FUNCTIONAL_RELS = frozenset({
    "capital", "capital_city", "capital_of", "country", "located_country", "continent",
    "currency", "father", "mother", "birthplace", "date_of_birth", "date_of_death",
})


# Broad containment predicates that stand in for a missing native relation (continent has no
# native store label, so it resolves through located_in / part_of). A functional geo attribute
# ANSWERED via one of these is a PROXY resolution — schema-level doubt (VERIFIED: continent via
# part_of gave Brunei->Borneo, Myanmar->'Basic Multilingual Plane', Nicaragua->Latin America).
_BROAD_PROXY_EDGES = frozenset({"part_of", "located_in", "location"})
# Asked relations that presuppose ONE right answer (single-valued). Superset of _FUNCTIONAL_RELS on
# the ASKED-relation side, incl. the containment asks whose native predicate may be absent.
_FUNCTIONAL_ASKS = _FUNCTIONAL_RELS | frozenset({
    "located", "located_in", "location", "region", "population", "area",
})


def _entity_case_variants(entity: str) -> list[str]:
    """Case variants for a store lookup, mirroring relational_lookup._entity_variants, so the
    membrane's fan-out signal resolves the SAME canonical entity the answer lane already did (the
    115M store is case-sensitive on the subject key, so a case-perturbed entity must not silently
    drop the ambiguity signal). Exact case is tried first -> clean answers are byte-unchanged."""
    out = [entity]
    for v in (entity.lower(), entity.title(), entity.capitalize()):
        if v not in out:
            out.append(v)
    return out


def _attach_relational_membrane_signals(result: dict, store: Any) -> None:
    """LEVER 2: replace the relational lane's FLAT 0.9 confidence with the REAL doubt signals the
    conformal gate needs, so it can RANK relational answers by reliability.

    Signal choice is empirical (measured on seal_knowledge_holdout, 268 answered):
      * The ActivatedSubgraph DENSITY signals (activation_mass / support_path_count / top_delivered)
        read graph DEGREE as confidence, which INVERTS on the bulk lane: a namesake/homonym hub
        ('Michelangelo' occupation fuses 18 people's jobs; 'George Harrison' 35) has HUGE degree and
        so looked MORE confident than a clean small-country capital. Feeding them diluted the real
        doubt to a near-flat mean (measured relational AUC 0.73, and correct answers over-abstained).
        They are DROPPED here. (from_activated_subgraph is unchanged and still used by the
        spreading-activation compose lane, where degree is a genuine support signal.)
      * The DISCRIMINATIVE signals are kept/added: the fan-out semantic_entropy (multi-valued
        collision), a proxy-resolution rung (functional ask answered via a broad containment proxy),
        and the answer's own graded_confidence. With these alone, measured relational AUC = 0.90 and
        correct answers survive (192/249 accepted at alpha 0.1) while every namesake collision + every
        continent-proxy error is gated.
    Additive: sets only ``result['_membrane_signals']``; nothing else about the answer changes."""
    rel = result.get("relational") or {}
    if result.get("answer_kind") != "relational_edge_lookup":
        return
    entity = rel.get("entity")
    edge = rel.get("edge")
    if not entity:
        return
    from packages.conformal_gate.nonconformity import SignalVector

    edge_l = str(edge or "").lower()
    asked = str(rel.get("rel") or "").lower()
    asked_u = asked.replace(" ", "_")

    # The answer's own confidence is a real (weak) doubt signal — a smooth floor so the vector is
    # never a single discrete rung. No spreading-activation walk is needed once the density signals
    # are gone (a win on high-degree bulk nodes that used to pay for a 1500-edge spread).
    conf = result.get("confidence")
    sv = SignalVector(graded_confidence=(float(conf) if isinstance(conf, (int, float)) else None))

    # FAN-OUT ambiguity (multi-valued relations only): distinct-target count on the asked edge (the
    # certificate is capped at the delivered top-k, so it HIDES the fan-out). Many distinct targets on
    # a MULTI-VALUED relation = the entity node fuses several referents = the match is ambiguous = a
    # real doubt. A functional edge is already precision-gated to one consensus target upstream, so it
    # carries no such fan-out.
    edge_functional = edge_l in _FUNCTIONAL_RELS
    n_raw = 0
    # CASE-ROBUST fan-out (adversary loop surface a, BREACH): the answer lane resolves the entity
    # through case variants (relational_lookup._entity_variants), but a RAW case-sensitive store
    # lookup here MISSED a case-perturbed entity ('mIcHeLaNgElO' -> 0 edges) and so DROPPED the
    # ambiguity signal, certifying the namesake fabrication at nonconformity 0.05 while the clean
    # form abstained at 0.28. Resolve the SAME variants the answer used, so a perturbed query's
    # fan-out (hence nonconformity) equals its clean form's. Clean entities hit on the exact-case
    # variant first, so their signal — and the calibrated q_hat — are unchanged.
    for _ent in _entity_case_variants(entity):
        try:
            seen = {str(o) for (_s, p, o) in (store.facts_about(_ent, limit=200, preds=(edge,)) or [])
                    if p == edge and str(o).strip()}
        except TypeError:
            n_raw = 0                                # store/double without preds support
            break
        if seen:
            n_raw = len(seen)
            break
    if not edge_functional and n_raw > 1:
        # normalized ambiguity in (0,1): 1 target -> 0, saturating toward 1 as the fan-out grows
        # (scale 6: 4->0.33, 7->0.50, 18->0.74, 35->0.85). Already oriented (high = doubt).
        sv = sv.merge(SignalVector(semantic_entropy=1.0 - 1.0 / (1.0 + (n_raw - 1) / 6.0)))

    # epistemic rung — checked on the ASKED relation, not the resolved edge (the previous code tested
    # the EDGE against _FUNCTIONAL_RELS, so 'continent' resolved via 'part_of' scored KNOWN and its
    # cross-link garbage slipped through). A single-valued ASK answered via a BROAD-PROXY edge is a
    # SCHEMA-level (proxy) resolution -> higher doubt.
    broad_proxy = edge_l in _BROAD_PROXY_EDGES and edge_l != asked_u
    asked_functional = asked_u in _FUNCTIONAL_ASKS
    # SCHEMA (proxy doubt) ONLY for a functional ask answered via a BROAD containment proxy — the
    # measured failure mode (continent via part_of). A functional ask answered via a legitimate
    # non-native synonym (country via located_country) is still a clean answer -> KNOWN; penalizing it
    # over-abstained correct answers (measured AUC drop).
    rung = "SCHEMA" if (asked_functional and broad_proxy) else "KNOWN"
    sv = sv.merge(SignalVector(epistemic_rung=rung))

    # DISCRETE-TIE SMOOTHING (Vovk smoothed conformal; cf. conformal.jitter_scores). The fan-out
    # bucket + constant 0.9 confidence + discrete rung make the relational nonconformity DISCRETE, so
    # different answers can land on the EXACT same score. At alpha 0.1 the calibrated threshold IS the
    # single smallest wrong score, and a deterministic threshold sitting on a tie CLUSTER accepts the
    # whole cluster -> over-accept (VERIFIED: two fan-out-9 namesake misses, Li Bai + Joseph Haydn,
    # tied at the minimum wrong -> P(accept|wrong)=0.111>0.10). A tiny DETERMINISTIC per-answer epsilon
    # (stable crc32 of entity|edge, magnitude 1e-4 << the ~1e-2 fan-out-bucket gap, so it ONLY breaks
    # exact ties and never re-ranks) restores clean coverage without randomness, and is applied
    # identically at calibration and inference (both read this same stored field).
    if sv.graded_confidence is not None:
        import zlib
        _eps = (zlib.crc32(f"{str(entity).lower()}|{edge_l}".encode("utf-8", "ignore"))
                % 100003) / 100003 * 1e-4
        sv.graded_confidence = max(0.0, float(sv.graded_confidence) - _eps)

    present = sv.present()
    if present:
        result["_membrane_signals"] = {k: (v if isinstance(v, (int, float, str, bool)) else float(v))
                                       for k, v in present.items()}


def answer_from_triples(query: str, language: str = "ko") -> dict[str, Any] | None:
    """Look up a stored fact that answers the query. Returns {answer, reasoning_certificate,
 confidence} or None when the store can't answer it (empty store, no subject match, or
 the relation intent isn't present).

 Script gate (owner 2026-07-17 English-only), enforced at this ONE exit rather than in each
 lane: the KG carries Korean labels on many nodes and several independent paths could surface
 one ("photosynthesis is " — a translation, not a definition). When the caller asks for a
 non-Korean answer, a composed answer still carrying Hangul is treated as a MISS, so the turn
 falls through to a real English lane or to the honest "no grounded definition" surface.
 The gate follows the requested `language`, so the Korean lane keeps working as specified.
 """
    result = _answer_from_triples_impl(query, language)
    if (result and not str(language or "").lower().startswith("ko")
            and re.search(r"[가-힣]", str(result.get("answer") or ""))):
        return None
    # MEMBRANE conformal gate (flag-gated, default OFF). When ATANOR_MEMBRANE_LIVE is unset,
    # gate_answer returns `result` UNCHANGED (the same object) -> byte-identical to pre-membrane
    # behavior. When ON it builds a SignalVector from the answer's real signals, runs the calibrated
    # ConformalGate, and on ABSTAIN routes to an honest-abstain return. Guarded: any membrane fault
    # falls back to today's answer.
    try:
        from packages.conformal_gate.live_wiring import gate_answer
        return gate_answer(result, query=query, language=language)
    except Exception:
        return result


def _answer_from_triples_impl(query: str, language: str = "ko") -> dict[str, Any] | None:
    ql = query.lower()


    # is DERIVED by rule, not stored, so '348 × 27' must never become a graph
    # miss. Runs before every store lane; the derivation trace IS the reasoning
    # certificate, and the value was independently re-checked vs exact integer
    # arithmetic before we got here. Underivable -> falls through untouched.
    try:
        from packages.reasoning_vm.arithmetic import evaluate as _arith_eval
        from packages.reasoning_vm.arithmetic import has_arithmetic_intent

        if has_arithmetic_intent(query):
            _ar = _arith_eval(query)
            if _ar is not None:
                _rem = getattr(_ar, "remainder", None)
                _expr = (_ar.expression.replace("^2", "²")
                         .replace("*", "×").replace("/", "÷"))
                _tail = (f" 나머지 {_rem}" if _rem and language == "ko"
                         else f" remainder {_rem}" if _rem else "")
                return {
                    "answer": f"{_expr} = {_ar.value}{_tail}.",
                    "reasoning_certificate": {
                        "derivation_kind": "arithmetic_" + _ar.method,
                        "anchor_concept": {"label": _ar.expression},
                        "steps": [{"type": "arithmetic_step", "fact": s}
                                  for s in _ar.steps],
                        "evidence_concepts": [],
                        "confidence": 1.0,
                        "confidence_basis": "derived by rule (digit/Peano algorithm), "
                                            "independently re-checked vs exact integer arithmetic",
                        "guarantees": {"external_llm": False, "fabricated_facts": False,
                                       "inferred": True, "verified": True},
                    },
                    "confidence": 1.0,
                    "answer_kind": "arithmetic_derivation",
                }
    except Exception:
        pass

    # structurally-unanswerable shapes abstain BEFORE the definitional composer can drift to the
    # subject's definition (A3 drift->abstain, 2026-07-19). English only; KO input refused upstream.
    if not str(language or "").lower().startswith("ko"):
        _abst = _structurally_unanswerable(query, "en")
        if _abst is not None:
            return _abst


    # the graph may not STATE but can PROVE by transitive is_a. Tightly gated to
    # the copula-question pattern so it never hijacks a normal wh-question; falls
    # through untouched when it can't prove membership (never a guessed 'no').
    try:
        _mq = re.match(r"^\s*(\S+?)(?:은|는|이|가)\s+(\S+?)"
                       r"(?:이야|야|인가요|인가|입니까|맞나요|맞아|이니|니)\s*\??\s*$", query)
        if _mq and language == "ko":
            from packages.reasoning_vm.deduction import answer_yes_no

            _stripj = lambda w: re.sub(r"(은|는|이|가|을|를|의|도|만|와|과|랑)$", "", w)
            _subj, _obj = _stripj(_mq.group(1)), _stripj(_mq.group(2))
            st = _store()
            if _subj and _obj and _subj != _obj and st is not None:
                # gather a bounded 2-hop is_a neighborhood as the stated facts.
                # TYPE-ALIAS BRIDGE: the store keys types in English (Settlement,


                # (parent is_a alias) — sound for membership since alias is type
                # equivalence — letting the transitive proof reach the query word.
                _stated: set[tuple[str, str, str]] = set()
                _frontier = [_subj]
                for _hop in range(3):
                    _next: list[str] = []
                    for _n in _frontier:
                        for s, p, o in (st.facts_about(_n, limit=40) or []):
                            o = str(o)
                            if p in ("is_a", "instance_of", "subclass_of") and o:
                                _stated.add((_n, "is_a", o))
                                _next.append(o)
                            elif p == "alias" and o:      # type-equivalence hop
                                _stated.add((_n, "is_a", o))
                                _next.append(o)
                    _frontier = _next
                _q = (_subj, "is_a", _obj)
                _verdict = answer_yes_no(_stated, _q, max_depth=4)
                if _verdict is not None:                       # proven true
                    _basis = _verdict["basis"]
                    return {
                        "answer": f"네, {_subj}은(는) {_obj}입니다.",
                        "reasoning_certificate": {
                            "derivation_kind": "deductive_membership_" + _basis,
                            "anchor_concept": {"label": _subj},
                            "steps": [{"type": "deduction", "fact": str(_verdict["proof"])}],
                            "evidence_concepts": [_subj, _obj],
                            "confidence": 0.95,
                            "confidence_basis": "proved by transitive is_a "
                                                "(output ⊆ deductive closure of stated facts ∪ rules)",
                            "guarantees": {"external_llm": False, "fabricated_facts": False,
                                           "inferred": _basis == "derived", "verified": True},
                        },
                        "confidence": 0.95,
                        "answer_kind": "deductive_membership",
                    }
    except Exception:
        pass
    # 4D TEMPORAL lane (owner's true 4D: ontology + TIME AXIS — 4D-fluents
    # validity slices): a question that names a time resolves against recorded

    # DIFFERENT facts, both answerable when a timeline exists; a moment outside

    # validity interval that grounded it.
    _m_year = re.search(r"((?:19|20)\d{2})\s*년", query)
    if _m_year or any(m in ql for m in ("지금", "현재")):
        try:
            from .temporal_kg import at_time, current, predicates_for

            # role synonyms so a query word matches a stored predicate it isn't

            _ROLE_SYN = {"대통령": ("대통령", "국가원수"), "총리": ("정부수반",),
                         "ceo": ("최고경영자",), "대표": ("최고경영자",)}
            _when = _m_year.group(1) if _m_year else None
            _cands = _subject_candidates(query)
            for _ts in _cands:
                for _tp in predicates_for(_ts):
                    # the stored predicate is relevant when the query names it OR
                    # a synonym of it (role word in the question)
                    named = _tp in query or any(
                        w in query for w, syns in _ROLE_SYN.items() if _tp in syns)
                    if not named:
                        continue
                    fact = at_time(_ts, _tp, _when) if _when else current(_ts, _tp)
                    if fact is None:
                        continue
                    _vt = fact["valid_to"] or "현재"
                    _lead = f"{_when}년 기준 " if _when else "현재 "
                    return {
                        "answer": (f"{_lead}{_ts}의 {_tp}은(는) {fact['object']}입니다 "
                                   f"(유효 기간: {fact['valid_from']} ~ {_vt})."),
                        "reasoning_certificate": {
                            "derivation_kind": "temporal_slice_lookup",
                            "anchor_concept": {"label": _ts},
                            "steps": [{"type": "temporal_fact",
                                       "fact": f"{_ts} {_tp} {fact['object']} "
                                               f"[{fact['valid_from']}~{_vt}]"}],
                            "evidence_concepts": [_ts, fact["object"]],
                            "confidence": 0.9,
                            "confidence_basis": "validity_interval_resolution",
                            "guarantees": {"external_llm": False, "fabricated_facts": False,
                                           "inferred": False, "time_sliced": True},
                        },
                        "confidence": 0.9,
                        "answer_kind": "temporal_slice_lookup",
                    }
        except Exception:
            pass
    if any(m in ql for m in _REALTIME_MARKERS):
        return None  # real-time intent — the honest realtime abstain must stand
    # imperative shape = a COMMAND, not a definition question. Without this,
    # 'open atanor app' got a dictionary answer for the word 'open' (measured).
    if re.match(r"^\s*(open|launch|start|run|execute|close|kill)", ql):
        return None
    store = _store()
    if store is None or len(store) == 0:
        return None

    # MEMBRANE LEVER 1 — Wikidata coverage routing (flag-gated: signals_live() = LIVE or CALIBRATE;
    # default OFF => byte-identical). The store gained ~108M Wikidata edges (occupation/country/
    # located_in/capital/genre/manufacturer/...), but English NL questions never reached them: the
    # generic candidate loop below mis-parsed the relation NOUN as the subject (VERIFIED:
    # _subject_candidates('what country is Athens in') -> ['country']). base_brain.resolve_relational
    # STRUCTURALLY parses "the <REL> of <ENTITY>" / "what <REL> is <ENTITY> in" / possessive / verb
    # shapes, resolves by GRAPH (the entity's edge whose label matches the asked relation), and
    # HONEST-ABSTAINS when no such edge exists — never a head-noun define. Answers come only from a
    # stored triple. Guarded against the compound-define re-entry (see _REL_REENTRY above).
    try:
        from packages.conformal_gate.live_wiring import signals_live as _signals_live
        _lever1_on = _signals_live()
    except Exception:
        _lever1_on = False
    if (_lever1_on and not getattr(_REL_REENTRY, "active", False)
            and not str(language or "").lower().startswith("ko")):
        _REL_REENTRY.active = True
        try:
            from packages.base_brain.relational_lookup import resolve_relational
            _rel = resolve_relational(query, language, store=store)
        except Exception:
            _rel = None
        finally:
            _REL_REENTRY.active = False
        if _rel is not None:
            # LEVER 2 — attach the RICH ActivatedSubgraph + epistemic signals so the conformal gate
            # reads real doubt (additive; nothing else about the answer changes). Guarded.
            try:
                _attach_relational_membrane_signals(_rel, store)
            except Exception:
                pass
            return _rel


    # the premise entirely (measured). Unless the store actually connects agent and
    # head, this path abstains — an off-target answer is worse than honest silence.
    m_ag = re.search(r"([가-힣A-Za-z0-9]{2,})[이가]\s*(만든|발명한|세운|창립한|지은|쓴|개발한)\s*"
                     r"([가-힣A-Za-z0-9]{2,})", query)
    if m_ag:
        agent, head = m_ag.group(1), m_ag.group(3)
        try:
            connected = any(head in o or head in s
                            for s, _p, o in store.facts_about(agent, limit=40)) or \
                        any(agent in o or agent in s
                            for s, _p, o in store.facts_about(head, limit=40))
        except Exception:
            connected = False
        if not connected:
            return None

    # walk stored edges under the composition algebra (termination + no-cycle guaranteed)
    # and verbalize the actual chain. Runs BEFORE the want-gate because each chain shape
    # is regex-gated inside answer_relationship — the shape IS the relation cue, so this
    # cannot reintroduce the paste-on-chatter regression the gate exists to block.
    if language == "ko":
        try:
            from .chain_reasoner import answer_relationship, has_chain_intent

            if has_chain_intent(query):
                chained = answer_relationship(query, store.facts_about, _subject_candidates(query))
                if chained is not None:
                    return chained
        except Exception:
            pass

    # NOT under the `language == "ko"` block above (where it sat until 2026-07-17): the whole
    # English contrast/purpose lane lives inside _try_open_composition and had never once
    # executed, because the CALLER was Korean-only. The seal battery caught it — C2's nine
    # purpose refusals were this, and the in-process probes that "proved" the lane worked were
    # calling _try_open_composition directly, past the gate that was blocking it. Ninth
    # instance of the same disease; when a language conditional appears, look for the missing
    # arm. chain_reasoner stays KO above — its intent cues are Korean regexes.
    try:
        composed = _try_open_composition(query, store)
        if composed is not None:
            return composed
    except Exception:
        pass
    want = _wanted_predicates(query)
    # ROLLBACK (owner-measured regression): with no explicit relation cue the
    # bridge pasted ANY stored fact about any noun in the sentence — every chat
    # message got a wikipedia-flavored definition. The bridge is a PRECISION
    # tool: it speaks only when the question explicitly asks for a definition

    if not want:
        return None



    # Unless Y is itself a definition word, a definition of bare X does not
    # answer it — same premise-respect rule as the agentive gate above: an
    # off-target answer is worse than honest silence (the web lane or the
    # ingest queue picks the real question up).
    _gen_mod = _gen_rel = ""
    _gen_ask = re.search(r"([가-힣A-Za-z0-9]{1,12})의\s+([가-힣A-Za-z0-9]{2,12}?)"
                         r"(?:[은는이가을를만]|\s|$)", query)

    # intent, not a relation ask (checked on the query itself: the capture's

    if _gen_ask and not re.search(r"의\s*(?:뜻|정의|의미)(?:[은는이가을를]|\s|$)", query):
        _gen_mod, _gen_rel = _gen_ask.group(1), _gen_ask.group(2)
    _cand_list = _subject_candidates(query)
    _lead_cand = _cand_list[0] if _cand_list else ""
    for subj in _cand_list:
        # WRONG-REFERENT decomposition guard (P0 regression 2026-07-11, store-flood surfaced it):

        # isn't stored — a proper substring of the leading full form is a DIFFERENT referent.
        # Only skips for definitional asks (relation facts about a sub-part can be legitimate).
        if (subj != _lead_cand and _lead_cand and subj in _lead_cand and len(subj) < len(_lead_cand)
                and (not want or (want & {"defined_as", "is_a"}))):
            continue
        facts = store.facts_about(subj, limit=12)
        if not facts:                                      # R3: kg miss → PROPHETA pack (LOCAL_EXPERT)
            facts = _pack_facts(subj, limit=12)
        # FOREIGN-DEF guard for a KOREAN query: even when the SUBJECT token is Latin-script
        # (DNA·GPS are common Korean subjects), a Korean question wants a Korean definition —

        # definitional facts; a stored Korean def (or none → clean pack wins) is the honest path.
        _q_ko = bool(re.search(r"[가-힣]", query))
        if language == "ko" and (re.search(r"[가-힣]", subj) or _q_ko):
            facts = [(s, p, o) for (s, p, o) in facts
                     if re.search(r"[가-힣]", o) or p not in ("defined_as", "is_a")]



        facts = [(s, p, o) for (s, p, o) in facts
                 if p not in ("defined_as", "is_a") or not _is_grammar_note(o)]

        # general definition. When the store's only definitional fact doesn't speak to


        if re.search(r"무엇으로\s*(?:이루어|구성|되어)|무엇으로\s*만들어|성분(?:이|은|을)|원소로", query):
            _defs = [o for (_s, p, o) in facts if p in ("defined_as", "is_a")]
            _rels = [f for f in facts if f[1] not in ("defined_as", "is_a", "alias", "sense")]
            _comp = re.compile(r"이루어|구성|성분|원소|분자|원자|화합물|섞|made of|composed")
            if _defs and not _rels and not any(_comp.search(d) for d in _defs):
                continue   # this subject's stored def can't answer composition; let the pack speak
        if not facts:
            continue

        # prefix of; first-wins served the fragment. Drop a definition that is a
        # strict prefix of a longer one (same sense, just cut short). This must NOT

        # other, so both survive and curated order (common sense first) is preserved.
        # snapshot the Korean defined_as rows BEFORE truncation collapse — a dominant sense often

        # collapse below deletes all but one, which would erase that frequency signal.
        _ko_defs_precollapse = [o for (_s, p, o) in facts
                                if p == "defined_as" and re.search(r"[가-힣]", o)]
        _defs = [o for (_s, p, o) in facts if p in ("defined_as", "is_a")]
        _truncations = {o for o in _defs for o2 in _defs
                        if o != o2 and o2.startswith(o) and re.search(r"[가-힣]", o2)}
        if _truncations:
            facts = [(s, p, o) for (s, p, o) in facts
                     if p not in ("defined_as", "is_a") or o not in _truncations]


        # and the OTHER senses' definition rows drop — a definitional answer
        # never crosses senses. Graph-derived view (sense_split), no rule table;
        # monosemous terms and no-signal contexts pass through unchanged.
        try:
            from packages.graph_scale.sense_split import induce_senses, sense_filtered_facts

            _defs_now = [o for (_s, p, o) in facts if p in ("defined_as", "is_a")]
            if len(_defs_now) >= 2:
                # the sense filter needs CONTEXT to resolve a sense; a bare



                # senses clustered together and outvoted the common water sense
                # (measured). Enforce the documented no-signal contract at the
                # call site: no content tokens beyond the subject => curated
                # order stands (common sense first).
                _ctx = query.replace(subj, "")
                _ctx = re.sub(r"뭐야|뭔가요|무엇인가요|무엇이야|무엇|뜻|정의|의미|이란|"
                              r"라는|알려줘|설명해줘|궁금해", "", _ctx)
                _ctx = re.sub(r"[은는이가을를의란\s?？!.,~…]", "", _ctx)
                if len(_ctx) >= 2:
                    _senses = induce_senses(subj, definitions=_defs_now)
                    if len(_senses) > 1:
                        facts = sense_filtered_facts(subj, query, facts, senses=_senses)
        except Exception:
            pass


        # served the taxonomy edge. Prefer defined_as-with-Korean, then is_a-with-Korean;

        # so curated order keeps the common sense first WITHIN a predicate.


        # First-wins picked the grave sense → confidently wrong. Prefer the better-SUPPORTED sense —
        # the cluster with the most defined_as rows (shared prefix / sub-superstring = same sense).

        # score 1, so their order — and the existing rich answer — is untouched.
        # support is counted over the PRE-collapse rows so the dominant sense's duplicates still

        _ko_defs = _ko_defs_precollapse if _ko_defs_precollapse else [
            o for (s, p, o) in facts if p == "defined_as" and re.search(r"[가-힣]", o)]

        def _sense_support(o: str) -> int:
            return sum(1 for o2 in _ko_defs
                       if o == o2 or (len(o) >= 6 and len(o2) >= 6 and o[:6] == o2[:6])
                       or o in o2 or o2 in o)

        def _def_priority(f: tuple[str, str, str]) -> tuple[int, int]:
            s, p, o = f
            if p == "defined_as":
                return (0, -_sense_support(o)) if re.search(r"[가-힣]", o) else (2, 0)
            if p == "is_a":
                return (1, 0) if re.search(r"[가-힣]", o) else (3, 0)
            return (1, 0)  # relation facts interleave with is_a, both after real defs
        facts = sorted(facts, key=_def_priority)
        # prefer a fact whose predicate matches the query's relation intent
        chosen = [(s, p, o) for (s, p, o) in facts
                  if (not want or p in want) and p not in ("alias", "sense")]
        if _gen_rel and subj == _gen_mod:
            # bare-modifier subject under a relation ask: only rows that speak to
            # the asked relation qualify (predicate names it, or maps to it via
            # the relation-cue table). No qualifying row => this subject cannot
            # answer the question; the sense/alias/evidence fallbacks are all
            # off-target here, so move on instead of letting them speak.
            _tail_want = _wanted_predicates(_gen_rel) - {"defined_as", "is_a"}
            chosen = [(s, p, o) for (s, p, o) in chosen
                      if _gen_rel in p or p in _tail_want]
            if not chosen:
                continue
        # CIRCULAR bare-synonym definition (measured 2026-07-14, 'DNA'): the store's only Korean

        # it restates the name with no descriptive content. When the bulk store came alive it beat

        # the lead is such a circular synonym AND there is no richer Korean def and no substantive
        # relation to add — a definition with real prose or any relation edge always stands.
        if chosen and language == "ko" and (not want or (want & {"defined_as", "is_a"})):
            _ls, _lp, _lo = chosen[0]
            if _lp in ("defined_as", "is_a"):
                _isa_t = {o for (s, p, o) in facts if p == "is_a"}
                _rich_ko = [o for (s, p, o) in facts if p == "defined_as"
                            and re.search(r"[가-힣]", o) and o not in _isa_t and len(o) >= 12]
                _subst_rel = [f for f in facts
                              if f[1] not in ("defined_as", "is_a", "alias", "sense")]
                if _lo in _isa_t and len(_lo) <= 10 and not _rich_ko and not _subst_rel:
                    return None   # circular synonym only → base_brain's richer def answers instead
        hop_from = None
        if not chosen:
            # multi-SENSE term (disambiguation asserted may-refer-to): enumerate the
            # senses dictionary-style — honest, and immune to wrong-referent answers.
            senses = list(dict.fromkeys(o for (_s, p, o) in facts if p == "sense"))
            if len(senses) >= 2 and language == "ko":
                parts = []
                for sn in senses[:3]:
                    sdef = [(s2, p2, o2) for (s2, p2, o2) in store.facts_about(sn, limit=6)
                            if p2 in ("defined_as", "is_a")]
                    if sdef:
                        parts.append(f"{sn}({sdef[0][2][:46]})")
                if len(parts) >= 2:
                    answer = f"{subj}{_ko_topic(subj)[len(subj):]} 여러 의미로 쓰입니다 — " + ", ".join(parts) + ". (출처: 큐레이션 지식그래프)"
                    return {
                        "answer": answer,
                        "reasoning_certificate": {
                            "derivation_kind": "multi_sense_enumeration",
                            "anchor_concept": {"label": subj},
                            "steps": [{"type": "sense", "fact": f"{subj} sense {sn}"} for sn in senses[:3]],
                            "evidence_concepts": [subj] + senses[:3], "confidence": 0.85,
                            "confidence_basis": "curated_structured_triple_verbatim",
                            "guarantees": {"external_llm": False, "fabricated_facts": False, "inferred": False},
                        },
                        "confidence": 0.85,
                        "answer_kind": "multi_sense_enumeration",
                    }
            # ONE visible alias hop — ONLY the redirect signature (exactly one DISTINCT
            # target): a redirect asserts equivalence; anything weaker must not
            # substitute. Distinct matters — the same equivalence asserted by two
            # sources (seed + ConceptNet Synonym) is STRONGER evidence, yet the raw


            alias_targets = list(dict.fromkeys(o for (_s, p, o) in facts if p == "alias"))
            if len(alias_targets) == 1:
                tfacts = store.facts_about(alias_targets[0], limit=12)
                tchosen = [(s2, p2, o2) for (s2, p2, o2) in tfacts
                           if (not want or p2 in want) and p2 not in ("alias", "sense")]
                if tchosen:
                    chosen = tchosen
                    hop_from = subj
        if not chosen:
            ev_text, ev_sources = _evidence_section(store, subj, limit=4)
            if ev_text and (want & {"defined_as", "is_a"}):
                head = (f"{subj}에 대해 웹에서 교차 확인된 근거입니다:" if language == "ko"
                        else f"Web-attributed evidence about {subj}:")
                return {
                    "answer": head + "\n" + ev_text,
                    "reasoning_certificate": {
                        "derivation_kind": "attributed_web_evidence",
                        "anchor_concept": {"label": subj},
                        "steps": [{"type": "quote", "fact": e["quote"][:80]} for e in ev_sources],
                        "evidence_concepts": [subj],
                        "sources": ev_sources,
                        "confidence": 0.8,
                        "confidence_basis": "verbatim_quotes_with_page_links",
                        "guarantees": {"external_llm": False, "fabricated_facts": False,
                                       "inferred": False, "attributed": True},
                    },
                    "confidence": 0.8,
                    "answer_kind": "attributed_web_evidence",
                }
            continue
        s, p, o = chosen[0]
        display_s = f"{hop_from}(={s})" if hop_from else s
        # P2 grounded composition: several stored facts -> one fluent paragraph
        # (definitional/general intents; vocabulary closed over templates+facts,
        # so composition cannot invent content). Hops and targeted relation
        # questions keep their precise single-fact paths.
        if hop_from is None and language in ("ko", "en") and (not want or (want & {"defined_as", "is_a"})):
            try:
                from packages.grounded_composer import compose_from_facts
                from packages.grounded_composer.composer import compose_narrative

                # FUSION of the two infinities (owner directive): `facts` here
                # have already passed the TRUTH side (sense filter, truncation
                # collapse, Korean-gloss gate above), so the EXPRESSION side —
                # the recursive realizer — composes on sense-clean input, with


                composed = None
                try:
                    import os as _os

                    if language == "ko" and _os.getenv("ATANOR_RECURSIVE_REALIZER", "1") != "0":
                        from packages.grounded_composer.composer import ComposedAnswer, _resolve_josa
                        from packages.grounded_composer.recursive_realizer import realize

                        _r = realize(s, facts, max_modifiers=2, embed_depth=1,
                                     lookup=lambda t: store.facts_about(t, limit=10))
                        if _r is not None and len(_r.facts_used) >= 3:
                            composed = ComposedAnswer(
                                answer=_resolve_josa(_r.text) + " (출처: 큐레이션 지식그래프)",
                                facts_used=_r.facts_used,
                                connectives_used=_r.constructions)
                except Exception:
                    composed = None

                # two paragraph groups have material; single paragraph otherwise
                # (adaptive depth — never padded)
                composed = composed \
                    or compose_narrative(s, facts, language=language) \
                    or compose_from_facts(s, facts, language=language)
            except Exception:
                composed = None
            if composed is not None:


                cited = _cite_sources(store, s, composed.facts_used, language)
                answer = _strip_generic_source(composed.answer) + cited["suffix"]
                cert = composed.certificate()
                cert["sources"] = cited["sources"]

                # then the attributed web-evidence section — the Copilot-style rich answer
                # when the learner has gathered them, plain definition when it hasn't
                try:
                    from .structured_profile import profile_block

                    prof = profile_block(store, s)
                except Exception:
                    prof = ""
                if prof:
                    answer = answer + "\n\n" + prof
                ev_text, ev_sources = _evidence_section(store, s)
                if ev_text:
                    answer = answer + "\n\n관련 근거:\n" + ev_text
                    cert["evidence_sources"] = ev_sources
                return {
                    "answer": answer,
                    "reasoning_certificate": cert,
                    "confidence": 0.88,
                    "answer_kind": "grounded_composition",
                }
        if language == "ko":
            template = _KO_TEMPLATE.get(p)
            # particle follows the REAL subject's final syllable even when the display

            particle = _ko_topic(s)[len(s):]
            if template:
                body = template.format(s=display_s, o=o, s_topic=display_s + particle)
            else:  # unknown predicate: generic frame with correct topic particle
                pred_ko = next((cues[0] for name, cues in _RELATION_CUES.items() if name == p), p)
                body = f"{display_s}의 {_ko_topic(pred_ko)} {o}입니다."

            cited = _cite_sources(store, s, [(s, p, o)], language)
            answer = f"{body}{cited['suffix']}"
        else:
            # reuse the composer's clean single-fact English frames — the generic
            # 'The {p} of {s} is {o}' turned is_a into 'The is a of concerto is …'
            from packages.grounded_composer.composer import _EN_LEAD

            frame = _EN_LEAD.get(p)
            body = frame.format(s=display_s, o=o) if frame else f"{display_s}: {o}"
            cited = _cite_sources(store, s, [(s, p, o)], "en")
            answer = f"{body}{cited['suffix']}"
        # adaptive depth on the single-fact path too: a curated one-liner grows into
        # a rich profile when the learner holds attributed evidence for the subject
        ev_sources = []
        if hop_from is None and (not want or (want & {"defined_as", "is_a"})):
            try:
                from .structured_profile import profile_block

                prof = profile_block(store, s)
            except Exception:
                prof = ""
            if prof:
                answer = f"{answer}\n\n{prof}"
            ev_text, ev_sources = _evidence_section(store, s)
            if ev_text:
                label = "관련 근거" if language == "ko" else "Related evidence"
                answer = f"{answer}\n\n{label}:\n{ev_text}"
        return {
            "answer": answer,
            "reasoning_certificate": {
                "derivation_kind": "structured_triple_lookup",
                "anchor_concept": {"label": s},
                "steps": ([{"type": "alias", "fact": f"{hop_from} alias {s}"}] if hop_from else [])
                         + [{"type": "triple", "fact": f"{s} {p} {o}"}],
                "evidence_concepts": [s, o], "confidence": 0.9,
                "confidence_basis": "curated_structured_triple_verbatim",
                "sources": cited["sources"],
                **({"evidence_sources": ev_sources} if ev_sources else {}),
                "guarantees": {"external_llm": False, "fabricated_facts": False, "inferred": False},
            },
            "confidence": 0.9,
            "answer_kind": "structured_triple_lookup",
        }
    return None
