# -*- coding: utf-8 -*-
"""Open-book MCQ — retrieve the real Wikipedia passage for the question's entity, then pick the option
best SUPPORTED by that passage. Un-hallucinatable: the choice is grounded in a real sentence the system
retrieved, not invented (see [[public-benchmark-open-book-strategy]]). This is the legitimate No-LLM
route to MMLU-style parity — the same thing a RAG system does, minus the LLM generator.

 passages = load_passages() # {title: lead_text}, built by harvest_wiki_passages
 r = answer_openbook(stem, choices, passages) # {choice_key, mode, confidence, basis} or None

Scoring is token SUPPORT over the RETRIEVED passage (the focused article), not over a noisy graph
neighbourhood — the option whose content words actually appear in the entity's real prose wins. For a
negated stem (' ?') the least-supported option is the odd one out. Returns None (not a
guess) when no passage is retrieved, so the caller's cascade can fall through to its own never-abstain.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Callable


_TOK = re.compile(r"[가-힣]+|[A-Za-z]{2,}|[0-9]+")
_JOSA = re.compile(r"(으로서|으로써|이라는|라는|에서|에게|으로|로서|처럼|보다|이란|란|인|은|는|이|가|을|를|의|에|와|과|도|만)$")
# English function / MCQ-frame words — the global (English-first) path needs these or 'the/which/
# following' hijack retrieval and scoring exactly as Korean josa would.
_EN_STOP = {"the", "a", "an", "of", "is", "are", "was", "were", "to", "in", "on", "for", "and", "or",
            "which", "what", "who", "whom", "whose", "when", "where", "why", "how", "following",
            "correct", "true", "false", "except", "best", "most", "least", "not", "all", "none",
            "that", "this", "these", "those", "with", "by", "as", "at", "from", "be", "been", "being",
            "has", "have", "had", "do", "does", "did", "it", "its", "their", "his", "her", "one",
            "about", "into", "than", "then", "also", "such", "each", "both", "some", "any", "will",
            "would", "can", "could", "may", "might", "statement", "statements", "term", "called"}
_STEM_STOP = {"다음", "중에서", "중", "옳은", "옳지", "않은", "것은", "것을", "무엇", "설명", "가장",
              "적절", "고르", "고른", "보기", "해당", "대한", "관한", "경우", "때문", "아닌", "것",
              "모두", "바르게", "바른", "틀린", "거리가", "먼", "이유", "특징"} | _EN_STOP
# ultra-common content words — they co-occur in almost any passage, so they can't DISCRIMINATE options.
# Dropped from support scoring so only distinctive tokens decide (raises precision on statement options).
_STOP_CONTENT = {"있다", "없다", "것", "수", "등", "및", "또는", "그리고", "이다", "한다", "하는", "되는",
                 "위해", "통해", "대한", "가장", "경우", "때문", "모든", "각각", "서로", "또한", "보다",
                 "이러한", "이런", "그런", "이것", "그것", "때", "일", "중", "및", "따라", "가지"} | _EN_STOP


_NEG_RE = re.compile(r"않은|않는|아닌|없는|없은|못한|못하는|틀린|잘못|적절하지\s*않|거리가\s*먼|"
                     r"해당하지\s*않|포함되지\s*않|맞지\s*않|바르지\s*않|관련\s*없|관계\s*없|옳지\s*않")


def _strip(t: str) -> str:
    s = _JOSA.sub("", t)
    return s if len(s) >= 2 else t


def _content(text: str) -> list[str]:
    return [_strip(t) for t in _TOK.findall(str(text or ""))]


@lru_cache(maxsize=1)
def load_passages(path: str | None = None) -> dict:
    """Load title->lead_text (built by harvest_wiki_passages). Cached. Empty dict if absent."""
    p = Path(path) if path else (Path(__file__).resolve().parents[2]
                                 / "data" / "graph_scale" / "wiki_passages" / "passages.tsv")
    out: dict[str, str] = {}
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                title, _, text = line.partition("\t")
                if title and text:
                    out[title.strip()] = text.rstrip("\n")
    except Exception:
        return {}
    return out


class ContentIndex:
    """Lean IDF-weighted inverted index over passage CONTENT (title+lead), so a question can retrieve
    the right passage even when it names no clean title — the recall lever past title-match's ~35%.
    Ultra-common tokens (>2% of docs) are dropped: they can't discriminate and they bloat the index."""

    def __init__(self, passages: dict):
        import math
        self.titles = list(passages)
        self.texts = [passages[t] for t in self.titles]
        post: dict[str, list[int]] = {}
        for i, t in enumerate(self.titles):
            for tok in {x for x in _content(t + " " + self.texts[i])
                        if len(x) >= 2 and x not in _STOP_CONTENT}:
                post.setdefault(tok, []).append(i)
        self.N = max(1, len(self.titles))
        cut = max(50, int(0.02 * self.N))                # drop hub tokens present in >2% of docs
        self.post = {k: v for k, v in post.items() if len(v) <= cut}
        self.idf = {k: math.log(self.N / len(v)) for k, v in self.post.items()}

    def search(self, query: str, min_score: float = 2.0) -> tuple[str, str] | None:
        got = self.search_topk(query, k=1, min_score=min_score)
        return got[0] if got else None

    def search_topk(self, query: str, k: int = 3, min_score: float = 2.0) -> list[tuple[str, str]]:
        """IDF-overlap top-k passages — the option-conditioned retrieval lever (+ )."""
        qt = {t for t in _content(query) if t in self.post and t not in _STEM_STOP}
        if not qt:
            return []
        scores: dict[int, float] = {}
        for tok in qt:
            w = self.idf[tok]
            for i in self.post[tok]:
                scores[i] = scores.get(i, 0.0) + w
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:k]
        return [(self.titles[i], self.texts[i]) for i, sc in ranked if sc >= min_score]


    def _postset(self, tok: str):
        ps = getattr(self, "_sets", None)
        if ps is None:
            ps = self._sets = {}
        s = ps.get(tok)
        if s is None:
            s = ps[tok] = set(self.post.get(tok, ()))
        return s

    def pmi(self, stem: str, option: str, max_q: int = 6, max_o: int = 4) -> float:
        """ PMI(, ) — ' '
 . log[N·df(q∧o)/(df(q)·df(o))]. 
 . ( )."""
        import math
        qts = sorted({t for t in _content(stem) if t in self.post and t not in _STEM_STOP},
                     key=lambda t: -self.idf[t])[:max_q]
        ots = sorted({t for t in _content(option) if t in self.post and t not in _STEM_STOP},
                     key=lambda t: -self.idf[t])[:max_o]
        if not qts or not ots:
            return 0.0
        total, pairs = 0.0, 0
        for ot in ots:
            oset = self._postset(ot)
            for qt in qts:
                co = len(self._postset(qt) & oset)
                pairs += 1
                if co:
                    total += max(0.0, math.log(co * self.N / (len(self.post[qt]) * len(self.post[ot]))))
        return total / pairs if pairs else 0.0


@lru_cache(maxsize=1)
def load_content_index(path: str | None = None) -> "ContentIndex | None":
    p = load_passages(path)
    return ContentIndex(p) if p else None


class DiskContentIndex:
    """ContentIndex-compatible adapter over ATANOR Index's memmapped BM25 (packages/atanor_index).

    Why this exists (E6b, 2026-07-18): `ContentIndex` builds its postings dict in RAM, which is fine
    for the 685k Korean corpus but cannot span the 7.0M English one — so the English lane has only
    ever had TITLE-match retrieval, which fires on ~30% of stems (measured E6a: fire-rate 0.295 vs
    the Korean lane's 0.490). ATANOR Index already indexes that exact corpus on disk (~1.8GB, BM25 +
    title-canonicality rerank, ~20ms) with no RAM dict at all, so it is the only retrieval backend
    that scales here. Exposing .search/.search_topk/.idf means `retrieve()` and `answer_openbook()`
    need no changes — retrieval is swapped, scoring is untouched, so the measurement isolates one lever.

    `idf = None` is deliberate, not an oversight: DiskIndex uses BM25 idf internally for RANKING but
    does not export a per-token table, and E6a's English baseline also ran with idf=None. Keeping it
    None means E6b changes retrieval ONLY — adding option-scoring weights at the same time would make
    the result unattributable, which is the mistake E5/E5b were reverted for."""

    idf = None

    def __init__(self, index_dir=None):
        from packages.atanor_index.disk_index import DiskIndex
        if index_dir is None:
            from packages.atanor_index.retriever import _pick_dir
            index_dir = _pick_dir()
            if index_dir is None:
                raise FileNotFoundError("no built ATANOR Index directory")
        self._idx = DiskIndex(index_dir)
        self.dir = str(index_dir)

    def search(self, query: str, min_score: float = 0.0) -> tuple[str, str] | None:
        got = self.search_topk(query, k=1, min_score=min_score)
        return got[0] if got else None

    def search_topk(self, query: str, k: int = 3, min_score: float = 0.0) -> list[tuple[str, str]]:
        try:
            rows = self._idx.search_topk(query, k=k, min_score=min_score) or []
        except Exception:
            return []
        return [(r["title"], r["text"]) for r in rows]


def load_disk_index(index_dir=None) -> "DiskContentIndex | None":
    """Best-effort DiskContentIndex; None when the index isn't built (caller falls back to titles)."""
    try:
        return DiskContentIndex(index_dir)
    except Exception:
        return None


_PMI_SOLVERS: dict[int, "PMISolver"] = {}


def get_pmi_solver(passages: dict) -> "PMISolver | None":
    """Cached PMISolver over a passage dict. Built lazily (a few minutes over 685k leads) and only
    when the exam cascade actually reaches the PMI stage, so interactive answering never pays it."""
    if not passages:
        return None
    k = id(passages)
    s = _PMI_SOLVERS.get(k)
    if s is None:
        s = _PMI_SOLVERS[k] = PMISolver(passages)
    return s


class PMISolver:
    """PMI — ContentIndex ** **. 2% 
 (mitochondria/chloroplast 0), PMI . 
 df∈[2, 40%N] ( + ). 0, Aristo 2016 ."""

    def __init__(self, passages: dict, hi_frac: float = 0.40):
        import math
        titles = list(passages)
        self.N = max(1, len(titles))
        post: dict[str, set] = {}
        for i, t in enumerate(titles):
            for tok in {x for x in _content(t + " " + passages[t]) if len(x) >= 2}:
                post.setdefault(tok, set()).add(i)
        hi = int(hi_frac * self.N)
        self.post = {k: v for k, v in post.items() if 2 <= len(v) <= hi}
        self.idf = {k: math.log(self.N / len(v)) for k, v in self.post.items()}

    def pmi(self, stem: str, option: str, max_q: int = 8, max_o: int = 5) -> float:
        import math
        qts = sorted({t for t in _content(stem) if t in self.post and t not in _STEM_STOP},
                     key=lambda t: -self.idf[t])[:max_q]
        ots = sorted({t for t in _content(option) if t in self.post and t not in _STEM_STOP},
                     key=lambda t: -self.idf[t])[:max_o]
        if not qts or not ots:
            return 0.0
        total, pairs = 0.0, 0
        for ot in ots:
            oset = self.post[ot]
            for qt in qts:
                co = len(self.post[qt] & oset)
                pairs += 1
                if co:
                    total += max(0.0, math.log(co * self.N / (len(self.post[qt]) * len(oset))))
        return total / pairs if pairs else 0.0

    def solve(self, stem: str, choices: dict, *, negated: bool | None = None,
              min_margin_ratio: float = 0.20) -> dict | None:
        if not choices:
            return None
        if negated is None:
            negated = bool(_NEG_RE.search(str(stem or "")))
        scored = {k: self.pmi(stem, v) for k, v in choices.items()}
        ranked = sorted(scored.values(), reverse=True)
        if not ranked or ranked[0] <= 0.0:
            return None
        margin = ranked[0] - (ranked[1] if len(ranked) > 1 else 0.0)
        if margin / max(ranked[0], 1e-9) < min_margin_ratio:
            return None
        pick = (min if negated else max)(scored, key=scored.get)
        return {"choice_key": pick, "mode": "pmi", "confidence": 0.45,
                "basis": f"corpus PMI (top {ranked[0]:.2f}, margin {margin:.2f})"}


_LOWER_CACHE: dict[int, dict] = {}   # id(passages) → {lower_title: title}; passages kept alive by lru_cache


def _lower_index(passages: dict) -> dict:
    """Case-folded title lookup. English Wikipedia titles are Capitalized ('Photosynthesis') but MCQ
    stems say 'photosynthesis' — without this, English title-match misses ~96% of the time."""
    k = id(passages)
    idx = _LOWER_CACHE.get(k)
    if idx is None:
        idx = {}
        for t in passages:
            lk = t.lower()
            if lk not in idx:                            # first (usually canonical) title wins
                idx[lk] = t
        _LOWER_CACHE[k] = idx
    return idx


def retrieve(query: str, passages: dict, index: "ContentIndex | None" = None) -> tuple[str, str] | None:
    """Find the passage the question is about: TITLE match (case-insensitive) on a stem term OR
 adjacent bigram (multi-word titles 'United States'/' '), longest candidate first. Falls
 back to the CONTENT index (IDF overlap) when no title matches — the recall lever."""
    if not passages:
        return None
    raw = _TOK.findall(str(query or ""))
    cands: set[str] = set()
    for t in raw:
        if t in _STEM_STOP:
            continue
        cands.add(t)
        cands.add(_strip(t))
    for a, b in zip(raw, raw[1:]):                        # adjacent bigrams for multi-word titles
        if a in _STEM_STOP or b in _STEM_STOP:
            continue
        cands.add(f"{a} {b}")
        cands.add(f"{a} {_strip(b)}")
        cands.add(a + b)
    low = _lower_index(passages)
    matched: dict[str, str] = {}                          # title -> passage (deduped)
    for cand in (c for c in cands if c and len(c) >= 2):
        if cand in passages:
            matched[cand] = passages[cand]
        else:
            t = low.get(cand.lower())                     # case-insensitive (English titles)
            if t is not None:
                matched[t] = passages[t]
    if matched:
        if len(matched) == 1:
            (t, txt), = matched.items()
            return t, txt
        # RELEVANCE RANK: among title matches, pick the passage whose CONTENT best overlaps the whole
        # question — not the longest token. A long word that happens to be a title is usually the wrong
        # entity; the right one is whichever passage actually talks about the question's other terms.
        q = {w for w in _content(query) if w not in _STOP_CONTENT and w not in _STEM_STOP}
        best = max(matched.items(), key=lambda it: (len(q & set(_content(it[1]))), len(it[0])))
        return best
    if index is not None:                                 # no title hit → content retrieval
        return index.search(query)
    return None


def _support(option: str, passage_text: str, idf: dict | None = None) -> float:
    """Weighted fraction of the option's DISTINCTIVE content tokens that appear in the passage. SUBSTRING
 match (Korean agglutination tolerated: ''→' '). Each token is weighted by IDF when available
 (a rare 'chlorophyll' match decides; common words shared by all options barely count) — else by length.
 This is the scoring-precision lever: token OVERLAP scored ≈ guessing; DISTINCTIVENESS separates options."""
    toks = [t for t in _content(option) if t not in _STOP_CONTENT]
    if not toks:
        return 0.0

    def w(t: str) -> float:
        return idf.get(t, 4.0) if idf is not None else float(len(t))   # 4.0 ≈ log(55): a moderately-rare default

    hit = sum(w(t) for t in toks if t and t in passage_text)
    tot = sum(w(t) for t in toks)
    return hit / tot if tot else 0.0


_SENT = re.compile(r"(?<=[.!?])\s+")
_NUM = re.compile(r"\d+(?:\.\d+)?")
# polarity pairs — a wrong MCQ option often FLIPS a relation the passage states (increase↔decrease).
# Detecting the flip is a real No-LLM entailment signal that bag-of-words is blind to.
_POS = {"increase", "increases", "increased", "increasing", "rise", "rises", "higher", "high", "more",
        "greater", "greatest", "larger", "positive", "gain", "gains", "up", "faster", "stronger", "hot",
        "hotter", "attract", "attracts", "acidic", "activate", "activates", "promote", "promotes"}
_NEG = {"decrease", "decreases", "decreased", "decreasing", "fall", "falls", "lower", "low", "less",
        "fewer", "smaller", "negative", "loss", "loses", "down", "slower", "weaker", "cold", "colder",
        "repel", "repels", "basic", "alkaline", "inhibit", "inhibits", "suppress", "suppresses"}


def _polarity(text: str) -> int | None:
    toks = set(re.findall(r"[a-z]+", str(text or "").lower()))
    p, n = bool(toks & _POS), bool(toks & _NEG)
    return 0 if p and not n else 1 if n and not p else None


def _order_sign(a: str, b: str, text: str) -> int:
    """+1 if a occurs before b in text, -1 if after, 0 if either absent. Used to catch subject↔object
    TRANSPOSITION: an option 'bonds break down glucose' vs a passage 'glucose breaks down into…' shares
    every word but reverses the two key nouns' order — a contradiction bag-of-words is blind to."""
    ia, ib = text.find(a), text.find(b)
    return 0 if ia < 0 or ib < 0 else (1 if ia < ib else -1)


def _entail_score(option: str, passage: str, idf: dict | None = None) -> float:
    """Beyond overlap: find the passage SENTENCE that best matches the option, then reward number,
    polarity, and subject-object ORDER agreement and punish CONTRADICTION. This is the discrimination
    lever token-overlap lacks — a distractor that says '46'/'decreases'/reverses the roles is driven down."""
    otoks = [t for t in _content(option) if t not in _STOP_CONTENT and t not in _EN_STOP]
    if not otoks:
        return 0.0
    onums, opol = set(_NUM.findall(option)), _polarity(option)

    def w(t: str) -> float:
        return idf.get(t, 4.0) if idf is not None else float(len(t))

    key2 = sorted(set(otoks), key=lambda t: -w(t))[:2]    # the two most-distinctive option nouns
    best = 0.0
    for sent in _SENT.split(passage):
        if not sent:
            continue
        hit = sum(w(t) for t in otoks if t in sent)
        tot = sum(w(t) for t in otoks) or 1.0
        overlap = hit / tot
        if overlap < 0.34:                                # this sentence isn't about the option — skip
            continue
        s = overlap
        snums = set(_NUM.findall(sent))
        if onums:
            s += 0.5 if (onums & snums) else (-0.5 if snums else 0.0)   # same number ✓ / different ✗
        spol = _polarity(sent)
        if opol is not None and spol is not None:
            s += 0.3 if opol == spol else -0.6            # polarity flip = contradiction
        if len(key2) == 2:                                # subject↔object transposition (Gemini ①)
            oo, so = _order_sign(key2[0], key2[1], option), _order_sign(key2[0], key2[1], sent)
            if oo and so:
                s += 0.25 if oo == so else -0.7           # reversed roles = contradiction
        best = max(best, s)
    # never underperform plain overlap: if no sentence qualified, fall back to passage-level support.
    return best if best > 0.0 else _support(option, passage, idf)


def _pick(scored: dict, negated: bool, desc: str) -> dict | None:
    """Turn per-option support scores into a marked pick, but ONLY when the passage genuinely
    SEPARATES the options (a real margin). No margin → None, so a guess is never dressed as grounded."""
    if not scored:
        return None
    ranked = sorted(scored.values(), reverse=True)
    lo, hi = min(scored.values()), max(scored.values())
    pick = (min if negated else max)(scored, key=scored.get)
    top = scored[pick]
    margin = (ranked[0] - ranked[1]) if len(ranked) >= 2 else ranked[0]
    ok = (negated and hi > 0.0 and lo < hi) or (not negated and top > 0.0 and margin >= 0.15)
    if ok:
        conf = 0.55 + min(0.3, abs(margin))
        return {"choice_key": pick, "mode": "openbook", "confidence": round(conf, 2),
                "basis": f"{desc} (support {top:.2f}, margin {margin:.2f})"}
    return None


def answer_openbook(stem: str, choices: dict, passages: dict,
                    *, negated: bool | None = None, index: "ContentIndex | None" = None) -> dict | None:
    """Pick the option the retrieved real prose supports. Two retrieval patterns:
 B the STEM names an entity → score each (statement) option's support in the entity's passage.
 A the OPTIONS are entities → retrieve EACH option's passage, score the STEM's terms in it
 (' ? /…' → 's passage contains ).
 `index` (optional) enables content retrieval when no title matches — higher recall.
 None (not a guess) when nothing retrieves or no option is separated — the caller's cascade decides."""
    if not choices:
        return None
    if negated is None:
        negated = bool(_NEG_RE.search(str(stem or "")))
    _idf = getattr(index, "idf", None)                   # IDF-weighted option scoring when available

    # Pattern B — stem entity's passage scores the options. Statement options are scored by ENTAILMENT
    # (sentence match + number/polarity consistency), not bag-of-words — the discrimination lever.
    got = retrieve(stem, passages, index)
    if got is not None:
        title, text = got
        b = _pick({k: _entail_score(v, text, _idf) for k, v in choices.items()}, negated, f"stem passage '{title}'")
        if b:
            return b

    # Pattern A — entity options (all short): each option's own passage, scored by STEM-term support.
    # Title-match only here (content search on a bare entity would drift); Pattern A is for named entities.
    if choices and max(len(str(v)) for v in choices.values()) <= 12:
        stem_terms = " ".join(t for t in _content(stem)
                              if t not in _STOP_CONTENT and t not in _STEM_STOP)
        scored_a, any_p = {}, False
        for k, opt in choices.items():
            g = retrieve(opt, passages)
            if g is None:
                scored_a[k] = 0.0
                continue
            any_p = True
            scored_a[k] = _support(stem_terms, g[1], _idf)
        if any_p:
            a = _pick(scored_a, negated, "option passages vs stem")
            if a:
                return a




    import os as _os
    if index is not None and _os.environ.get("ATANOR_OC") == "1":
        scored_oc, any_hit = {}, False
        for k, opt in choices.items():
            pool = index.search_topk(f"{stem} {opt}", k=3)
            if not pool:
                scored_oc[k] = 0.0
                continue
            any_hit = True
            scored_oc[k] = max(_entail_score(opt, txt, _idf) for _t, txt in pool)
        if any_hit:
            oc = _pick(scored_oc, negated, "option-conditioned passages")
            if oc:
                oc["mode"] = "openbook-oc"
                return oc
    return None


def answer_pmi(stem: str, choices: dict, index: "ContentIndex | None",
               *, negated: bool | None = None, min_margin_ratio: float = 0.25) -> dict | None:
    """PMI (Aristo , 0) — . ·
 ( ). : 1 2 ."""
    if index is None or not choices:
        return None
    if negated is None:
        negated = bool(_NEG_RE.search(str(stem or "")))
    scored = {k: index.pmi(stem, v) for k, v in choices.items()}
    ranked = sorted(scored.values(), reverse=True)
    if not ranked or ranked[0] <= 0.0:
        return None
    margin = ranked[0] - (ranked[1] if len(ranked) > 1 else 0.0)
    if margin / max(ranked[0], 1e-9) < min_margin_ratio:
        return None
    pick = (min if negated else max)(scored, key=scored.get)
    if negated and min(scored.values()) <= 0.0 and ranked[0] <= 0.0:
        return None
    return {"choice_key": pick, "mode": "pmi", "confidence": 0.45,
            "basis": f"corpus PMI (top {ranked[0]:.2f}, margin {margin:.2f})"}
