"""Semantic-neighborhood gathering — so probabilistic synthesis can answer from the
CONSTELLATION of related grounded facts, not only an exact-match concept.

The gap that made the engine abstain far too often: retrieval is name/token based, so a
Korean query (" ?") finds NOTHING even when the pack holds 16 facts ABOUT AI
(AI , , …) — different words, so no token match. An LLM answers such a
question by composing from everything it knows around the topic; it doesn't need a node
literally named . This module gives the No-LLM engine the same reach WITHOUT
fabrication: it gathers the genuinely-related grounded facts (the neighborhood) so the
grounded-constrained generator can weave them into an honest, composed answer.

Three ways a concept enters the neighborhood (ADDITIVE, all grounded):
 1. NAME/LABEL/ALIAS match (what plain retrieval already does).
 2. DESCRIPTION-content match — a concept whose verbatim description shares the query's
 content words (finds -related facts for a query even if unnamed).
 3. DOMAIN BRIDGE — a small, bounded language-equivalence map (LAD layer, like the
 particle/ rules) for high-frequency terms whose cross-lingual / synonym form
 never appears literally in any description (→AI//, →
 happiness/ …). This is language equivalence, NOT knowledge; the KNOWLEDGE still
 comes only from the matched concepts' verbatim descriptions.

The relevance bar stays honest: a concept joins only on a real lexical/bridge overlap
with the query, and the synthesis is framed as " " so
it never masquerades as a definition it doesn't have.
"""
from __future__ import annotations

import re
from typing import Any

_HANGUL = re.compile(r"[가-힣]")

# LAD-layer language/synonym bridge for high-frequency query heads whose equivalent
# never appears literally in the (often English) descriptions. Bounded + honest: it
# only decides WHICH grounded concepts are topically relevant, never supplies content.
_DOMAIN_BRIDGE: dict[str, tuple[str, ...]] = {
    "인공지능": ("ai", "artificial intelligence", "기계학습", "머신러닝", "신경망", "딥러닝", "추론", "학습"),
    "ai": ("인공지능", "artificial intelligence", "신경망", "기계학습"),
    "머신러닝": ("machine learning", "기계학습", "학습", "신경망", "ai"),
    "기계학습": ("machine learning", "머신러닝", "학습", "신경망"),
    "딥러닝": ("deep learning", "신경망", "neural", "학습"),
    "컴퓨터": ("computer", "cpu", "gpu", "연산", "프로세서"),
    "인터넷": ("internet", "network", "네트워크", "웹", "http"),
    "행복": ("happiness", "만족", "즐거움", "긍정", "감정", "웰빙"),
    "리더십": ("leadership", "리더", "지도자", "이끄는", "관리", "통솔"),
    "리더": ("leader", "지도자", "이끄는", "통솔"),
    "민주주의": ("democracy", "선거", "시민", "정치", "자유"),
    "경제": ("economy", "economic", "시장", "금융", "무역"),
    "우주": ("universe", "cosmos", "은하", "행성", "항성", "천체"),
    "생명": ("life", "생물", "세포", "유기체"),
    "언어": ("language", "문법", "단어", "의미", "표현"),
    "예술": ("art", "예술가", "작품", "미술", "음악"),
    "역사": ("history", "역사적", "시대", "과거"),
    "과학": ("science", "scientific", "연구", "실험", "이론"),
    "철학": ("philosophy", "사상", "존재", "인식", "윤리"),
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()


# Trailing Korean particles/endings to strip so a query token matches the bare concept

_KO_TAIL = ("이란", "으로", "에서", "에게", "이라고", "라고", "은", "는", "이", "가", "을", "를",
            "에", "의", "도", "만", "과", "와", "란", "이나", "나", "로", "께", "이야", "야")


def _strip_ko_tail(token: str) -> str:
    for p in _KO_TAIL:
        if token.endswith(p) and len(token) - len(p) >= 2:
            return token[: -len(p)]
    return token


_STOP = {"무엇", "뭐야", "뭔가", "이란", "란", "인가", "대해", "설명", "알려", "어떻게", "왜",
         "무슨", "설명해", "알려줘", "되려면", "the", "what", "is", "are", "a", "an", "of",
         "about", "how", "why", "것", "게", "거"}

# SCOPE/SUPERLATIVE qualifiers — real words, but as a query ANCHOR they are almost


# They may still SCORE, but a concept must hit a NON-scope term to join the neighborhood.
_SCOPE_GENERIC = {"세계", "세상", "전세계", "지구", "나라", "제일", "가장", "최고", "최대", "최소",
                  "최장", "최단", "으뜸", "종류", "세계에서", "world", "most", "best", "largest",
                  "longest", "biggest", "highest", "smallest", "kind", "type", "널리"}

# Kiwi (morphological analyser) is OPTIONAL: when installed it gives robust Korean noun

# when absent we fall back to the regex. Lazy singleton — the ~1s init happens once, and
# warm throughput is ~30k queries/sec, so it never slows the retrieval hot path. It does

_KIWI = None
_KIWI_TRIED = False


def _kiwi():
    """RETIRED (owner 2026-07-18, BINDING ' . Kiwi '): ATANOR is
 English-only. Korean input is refused at the I/O boundary, so Korean morphology never runs on a
 user turn. This loader now always returns None; every caller already treats None as 'no Korean
 analyser' and falls back to the Latin word-boundary path. Kept as a null seam so the ~10 import
 sites need not each be touched to disable the Kiwi lane."""
    return None


def _kiwi_noun_phrases(text: str) -> set[str]:
    """Compound-preserving noun extraction: JOIN adjacent noun morphemes so + ->
 (not split), while particles/endings are dropped by the analyser. Returns an
 empty set if Kiwi is unavailable (caller falls back to the regex)."""
    kw = _kiwi()
    if kw is None:
        return set()
    out: set[str] = set()
    cur = ""
    try:
        for tok in kw.tokenize(text):
            if tok.tag in ("NNG", "NNP", "SL"):
                cur += tok.form
            else:
                if len(cur) >= 2:
                    out.add(cur.lower())
                cur = ""
        if len(cur) >= 2:
            out.add(cur.lower())
    except Exception:
        return set()
    return {t for t in out if t not in _STOP}


def _en_function_words() -> frozenset[str]:
    """The ONE vetted English function-word list (lexicon_lane), shared not copied — the same
    consolidation engage.py made. _STOP below is Korean-shaped with eight English words bolted
    on, which let 'do', 'care' and 'people' anchor relevance (measured below)."""
    try:
        from packages.graph_scale.lexicon_lane import _FUNCTION_WORDS
        return frozenset(_FUNCTION_WORDS)
    except Exception:
        return frozenset()


def _content_tokens(text: str) -> set[str]:
    latin = set(re.findall(r"[a-z0-9]{2,}", _norm(text)))
    latin -= _en_function_words()
    # prefer Kiwi's morphological nouns; fall back to particle-stripped regex tokens.
    korean = _kiwi_noun_phrases(str(text or ""))
    if not korean:
        korean = {_strip_ko_tail(t) for t in re.findall(r"[가-힣]{2,}", str(text or ""))}
    return {t for t in (latin | korean) if t not in _STOP and len(t) >= 2}


def _hits(terms: set[str], text: str) -> set[str]:
    """Term hits with a WORD BOUNDARY for Latin; Korean keeps substring matching.

 Measured 2026-07-17 — the English face of this project's oldest chronic bug ('' inside
 '', which pack_loader fixed with _named_with_boundary). Raw `t in text` made
 'Why do people care about free nerve ending?' pull:
 free inside Freedom of religion / Topfreedom / freestyle skier
 do inside Freedom / Donald / Indonesia
 ending inside defending champions
 and the neighbourhood synthesis then answered a question about nerve endings with
 "Freedom of religion is enshrined in the constitution" — fluent, hedged, and about nothing
 the user asked. It cost 5.5s (the seal battery's p99 tail) to produce that.

 Korean is agglutinative and written without spaces, so substring is right there; English
 words have boundaries and must use them. One rule per language, not one rule for both.
 """
    out: set[str] = set()
    for t in terms:
        if not t:
            continue
        if t.isascii():
            if re.search(r"\b%s\b" % re.escape(t), text):
                out.add(t)
        elif t in text:
            out.add(t)
    return out


def _subject_str(query: str) -> str:
    """The query's grammatical SUBJECT (its topic) as a raw string. Best-effort: any failure
    returns "". Parsed ONCE per gather and threaded down, so the fallback path parses one time."""
    try:
        from packages.graph_scale.query_frame import parse
        return str(getattr(parse(query), "subject", None) or "")
    except Exception:
        return ""


def _latin_head(subject: str) -> str:
    """The HEAD token of a MULTI-WORD Latin subject (English is head-final: 'free nerve ENDING').
    Empty for single-word or Korean subjects. Lets the neighbourhood reject modifier-only matches:
    'free nerve ending' has ZERO pack coverage for its head ('nerve','ending' both DF=0, measured
    2026-07-18), yet the gratis-sense modifier 'free' (DF=12: Free Fire, free software) would
    otherwise be the sole anchor and the synthesis would answer a nerve question with a game. A
    compound is ABOUT its head; a match on only a modifier is a different topic."""
    lat = [t for t in re.findall(r"[a-z0-9]{2,}", str(subject).lower())
           if t not in _STOP and t not in _SCOPE_GENERIC and t not in _en_function_words()]
    return lat[-1] if len(lat) >= 2 else ""


def _subject_tokens(query: str) -> set[str]:
    """Content tokens of the query's grammatical SUBJECT — kept as a thin wrapper for callers that
    only need the token set. See _subject_str for why the subject anchors the neighbourhood."""
    subj = _subject_str(query)
    return _content_tokens(subj) if subj else set()


def _expand_query_terms(query: str, subject: str | None = None) -> tuple[set[str], set[str]]:
    """Return (all_terms, primary_terms). primary = the query's OWN content tokens + their
    bridge equivalents that are specific enough (>= 2 Korean chars / >= 3 Latin) to anchor
    relevance. A concept joins the neighbourhood only if it hits a PRIMARY term, so a weak
    incidental 2-gram never drags in an off-topic concept. `subject` may be supplied to avoid a
    second parse when the caller already extracted it."""
    toks = _content_tokens(query)

    # count toward the score but can't by themselves anchor an off-topic concept.
    anchor = {t for t in toks if t not in _SCOPE_GENERIC}
    # …and it must hit a SUBJECT token, not the question's framing — same demotion as scope words
    # (framing tokens stay in all_terms so they still SCORE, they just can't ANCHOR alone). Falls
    # back to the full anchor set when subject extraction is empty or disjoint, never worse.
    subj = _content_tokens(subject) if subject else (set() if subject == "" else _subject_tokens(query))
    if subj:
        subj_anchor = anchor & subj
        if subj_anchor:
            anchor = subj_anchor
    if not anchor:
        anchor = set(toks)
    all_terms: set[str] = set(toks)
    primary: set[str] = set(anchor)
    for t in anchor:
        for bridged in _DOMAIN_BRIDGE.get(t, ()):
            b = _norm(bridged)
            if (b.isascii() and len(b) >= 3) or (not b.isascii() and len(b) >= 2):
                primary.add(b)
                all_terms.add(b)
    return all_terms, primary


def _concept_text(concept: dict[str, Any]) -> str:
    labels = concept.get("labels") or {}
    return " ".join([
        str(concept.get("canonical_name") or ""),
        *[str(v) for v in labels.values()],
        *[str(a) for a in (concept.get("aliases") or [])],
        str(concept.get("short_description") or ""),
    ])


def gather_neighborhood(
    query: str, concepts: list[dict[str, Any]], *, limit: int = 6, min_overlap: int = 1
) -> list[dict[str, Any]]:
    """Return grounded concepts topically related to the query — by name/label, by
    description-content overlap, or via the domain bridge — each with a `neighbor_score`.
    Only concepts with a real description are eligible (they must carry a fact to weave)."""
    subject = _subject_str(query)
    terms, primary = _expand_query_terms(query, subject=subject)
    if not terms:
        return []
    # A MULTI-WORD Latin subject must be matched on its HEAD (or >=2 of its own tokens); a match on
    # only a modifier is a different topic ('free' in 'free nerve ending' → Free Fire). Empty for
    # single-word / Korean / bridged subjects, which keep the current behaviour.
    head = _latin_head(subject)
    subj_toks = _content_tokens(subject) if subject else set()
    scored: list[tuple[float, dict[str, Any]]] = []
    for c in concepts:
        desc = str(c.get("short_description") or "").strip()
        if len(desc) < 15:
            continue
        text = _norm(_concept_text(c))
        hits = _hits(terms, text)
        # relevance REQUIRES a primary-term hit — an incidental short 2-gram alone never

        phits = hits & primary
        if not phits:
            continue
        # min_overlap: a neighbour must hit at least this many PRIMARY terms. At the default 1 this is
        # the historical behaviour; callers weaving a definition for a bare SINGLE-word subject pass 2
        # so a lone name-collision ('dog' in the TV show 'Greatest American Dog') no longer qualifies
        # as related evidence — those cases fall to the honest hedge instead of a fluent junk list.
        if len(phits) < min_overlap:
            continue
        if head and head not in phits and len(phits & subj_toks) < 2:
            continue
        name_text = _norm(str(c.get("canonical_name") or "") + " " + " ".join(str(v) for v in (c.get("labels") or {}).values()))
        name_hits = len(_hits(hits, name_text))
        score = len(hits) + name_hits * 1.5
        scored.append((score, c))
    scored.sort(key=lambda it: (-it[0], len(str(it[1].get("short_description") or ""))))
    return [c for _, c in scored[:limit]]
