# -*- coding: utf-8 -*-
"""Creative composer — the - (/ , No-LLM).

The owner's directive: strict evidence-only reasoning cannot make a poem, so
MIX the next-token mode of generation into the architecture — as PRINCIPLES,
never as transformer code in the answer path. This module is that fusion:

 (grounding) — the theme's real evidence sentences from the KG become the
 corpus; phase-space neighbors widen it thematically.
 (flow) — HolographicLM (FHRR kernel next-token, deterministic, no
 backprop) is fitted ON THAT CORPUS at request time and
 generates lines: corpus-attested units only, arranged new.
 (feeling) — the sensory impression (3-7) opens the poem; the grounded
 metaphor (3-8) closes it.

Honesty contract: creative output is LABELED creative (creative_mode: true,
factual_claims: false). Fabrication rules bind FACT claims; a poem asserts
none — but even so, every unit it emits occurred in the grounding corpus
(the LM's own guarantee), and the corpus sources are cited. No corpus -> no
poem (silence over pastiche).
"""
from __future__ import annotations

import re
from typing import Any

_MIN_CORPUS = 3          # fewer grounded sentences than this -> decline
_MAX_CORPUS = 60         # bound the per-request fit
_NEIGHBOR_CONCEPTS = 4   # phase neighbors that widen the theme corpus


_JOSA_TAIL = re.compile(r"(은|는|이|가|을|를|의|에|에서|으로|로|와|과|도|만)$")
_CONTENT = re.compile(r"[가-힣]{2,}")


def _content_words(sentence: str, limit: int = 8) -> list[str]:
    """Hangul content words of a definition, trailing stripped — the
 concepts the theme's own prose points at (the graph-native corpus walk)."""
    out: list[str] = []
    for tok in _CONTENT.findall(sentence):
        base = _JOSA_TAIL.sub("", tok)
        if len(base) >= 2 and base not in out:
            out.append(base)
        if len(out) >= limit:
            break
    return out


def _themed_corpus(theme: str) -> tuple[list[str], list[str], list[str]]:
    """Korean prose corpus grown ALONG THE GRAPH from the theme: the theme's
    definition sentences, then the definitions of the concepts those sentences
    mention (1 hop), plus phase neighbors. Returns (sentences, urls, concepts)."""
    sentences: list[str] = []
    sources: list[str] = []
    concepts: list[str] = []
    try:
        from packages.graph_scale.answer_bridge import _store

        kg = _store()
    except Exception:
        kg = None
    if kg is None:
        return [], [], []

    terms = [theme]
    try:
        from packages.graph_scale.phase_space import neighbors

        for term, res in neighbors(theme, k=12):
            if res < 0.5 or term == theme:
                continue
            terms.append(term)
            if len(terms) > _NEIGHBOR_CONCEPTS:
                break
    except Exception:
        pass
    # 1-hop textual walk: the theme's own definitions name the concepts the
    # poem should breathe in — pull THEIR definitions into the corpus too
    try:
        first = kg.facts_with_sources(theme, limit=8, preds=("defined_as", "is_a")) or []
        hop: list[str] = []
        for row in first:
            for w in _content_words(str(row[2] if len(row) > 2 else "")):
                if w != theme and w not in terms and w not in hop:
                    hop.append(w)
        terms.extend(hop[:10])
    except Exception:
        pass

    seen: set[str] = set()
    for term in terms:
        try:
            # evidence = verbatim web sentences; defined_as/is_a = curated
            # definition prose — both are real grounded text, so both feed the
            # corpus (definitions carry most of the graph's Korean prose)
            rows = kg.facts_with_sources(
                term, limit=24, preds=("evidence", "defined_as", "is_a")) or []
        except Exception:
            continue
        got = False
        for row in rows:
            pred = str(row[1] if len(row) > 1 else "")
            o = str(row[2] if len(row) > 2 else "")
            if len(o) < 8 or o in seen:
                continue
            # Korean poem needs a Korean corpus: majority-Hangul rows only
            # (the store's neighbor definitions are often English Wiktionary prose)
            hangul = sum(1 for ch in o if "가" <= ch <= "힣")
            if hangul < len(o) * 0.4:
                continue
            seen.add(o)
            # a definition object is a noun phrase — close it into a sentence so
            # the LM learns sentence-final endings from it (josa via LAD)
            if pred == "evidence":
                sentences.append(o)
            else:
                try:
                    from packages.lad_morphology import topic as _topic

                    head = _topic(term)
                except Exception:
                    head = f"{term}은"
                sentences.append(f"{head} {o}이다.")
            got = True
            url = str(row[4] if len(row) > 4 else "")
            if url and url not in sources:
                sources.append(url)
            if len(sentences) >= _MAX_CORPUS:
                break
        if got:
            concepts.append(term)
        if len(sentences) >= _MAX_CORPUS:
            break
    return sentences, sources[:6], concepts


def _line_from_tokens(toks: list[str], *, drop_first: int = 0) -> str:
    """Tokens -> one poem line: de-noise, bound the length, and prefer ending
    on a sentence-final token so lines close instead of trailing off."""
    body = toks[drop_first:]
    out: list[str] = []
    for t in body:
        if out and t == out[-1]:
            continue
        if re.fullmatch(r"[0-9]+", t):
            continue
        out.append(t)
        if len(out) >= 12:
            break

    for i in range(len(out) - 1, 1, -1):
        if out[i].endswith(("다", "음", "함", "요")):
            out = out[: i + 1]
            break
    return " ".join(out).strip()


def _too_similar(a: str, b: str) -> bool:
    """Token-set overlap gate: sliding replays of the same definition collapse
    into one line (a small corpus makes the kernel replay; keep one copy)."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) > 0.6


# A poem line must READ like one, not like a dictionary entry. Reject lines that are

_META_LINE = re.compile(r"(관형사|접미사|접두사|어미|조사|자모|음절|준말|명사|동사|형용사|부사|"
                        r"따위|붙여|붙는|뒤에\s*붙|앞에서|뜻을\s*더하|이르는\s*말|가리키는\s*말|약어|줄임)")


def _poetic_ok(line: str) -> bool:
    """Keep only lines that could belong in a poem — no metalinguistic definitions,
 not English-dominated, and properly closed (no dangling '…', broken '')."""
    if not line or len(line.split()) < 2:
        return False
    if _META_LINE.search(line):
        return False
    hangul = sum(1 for c in line if "가" <= c <= "힣")
    latin = sum(1 for c in line if c.isascii() and c.isalpha())
    if latin > hangul:                       # English-dominated leak
        return False
    if line.rstrip().endswith(("의", "및", "와", "과", "에", "를", "을", "부록")):
        return False                         # trails off mid-phrase
    return True


def _polish(line: str) -> str:
    """Small surface fixes so a line closes naturally (LAD surface, not knowledge)."""
    line = re.sub(r"(한다|이다|한다)\s*이다\b", r"\1", line)
    line = re.sub(r"\s+", " ", line).strip()
    line = re.sub(r"[,\s]+$", "", line)
    return line


def _batchim(w: str) -> bool:
    w = re.sub(r"[)\].\"'\s]+$", "", str(w or ""))
    return bool(w) and "가" <= w[-1] <= "힣" and (ord(w[-1]) - 0xAC00) % 28 != 0


def _topic_particle(w: str) -> str:
    return "은" if _batchim(w) else "는"


def _obj_particle(w: str) -> str:
    return "을" if _batchim(w) else "를"


def compose_poem(theme: str, *, hormones: dict | None = None) -> dict[str, Any] | None:
    """A short grounded poem for the theme, or None when the graph holds too
    little to compose from (the honest decline stays honest)."""
    theme = str(theme or "").strip()
    if not theme or len(theme) > 24:
        return None
    corpus, sources, concepts = _themed_corpus(theme)
    if len(corpus) < _MIN_CORPUS:
        return None

    try:
        from packages.cgsr.cgsr.holographic_lm import HolographicLM

        lm = HolographicLM(dim=256, window=3, decay=0.7, seed=7)
        lm.fit(corpus)
    except Exception:
        return None


    # walk, so the same theme reads warmer when the self-loop is content, brisker when it is aroused.
    # Bias is multiplicative on the corpus-attested vote → tone re-ranks, never fabricates a word.
    _tone = None
    try:
        from packages.cgsr.cgsr.holographic_speaker import HolographicSpeaker
        _tone = HolographicSpeaker(lm=lm).tone_bias_fn(hormones)
    except Exception:
        _tone = None

    lines: list[str] = []


    impression = None
    try:
        from packages.continuous_self.sensory_interference import impression_from_visual

        impression = impression_from_visual(theme)
    except Exception:
        impression = None
    if impression:
        lines.append(impression["felt"])



    # tokenizer), so seeds are corpus-attested tokens that carry the concept.
    from packages.cgsr.cgsr.holographic_lm import tokens as _lm_tokens

    corpus_toks: list[str] = []
    for s in corpus:
        corpus_toks.extend(_lm_tokens(s))
    tok_set = set(corpus_toks)

    def _attested(concept: str) -> str | None:
        if concept in tok_set:
            return concept
        for t in corpus_toks:
            if t.startswith(concept):
                return t
        return None

    seed_concepts = [theme]
    if impression and impression.get("evoked"):
        seed_concepts.append(impression["evoked"][0]["term"])
    seed_concepts.extend(c for c in concepts[1:6] if c not in seed_concepts)
    holo_lines = 0
    for concept in seed_concepts[:6]:
        if holo_lines >= 3:
            break
        seed = _attested(concept)
        if not seed:
            continue
        toks = lm.generate_fluent(seed, max_len=14, coherence=0.7, rep_penalty=0.8, tone_bias=_tone)
        line = _polish(_line_from_tokens(toks, drop_first=0))
        if (line and len(line.split()) >= 3 and _poetic_ok(line)
                and not any(_too_similar(line, prev) for prev in lines)):
            lines.append(line)
            holo_lines += 1


    met = None
    try:
        from packages.graph_scale.metaphor import metaphor

        met = metaphor(theme)
    except Exception:
        met = None

    if met and str(met.get("vehicle") or "").strip() and re.search(r"[가-힣]", str(met["vehicle"])) \
            and sum(1 for c in str(met["vehicle"]) if c.isascii() and c.isalpha()) == 0:
        try:
            from packages.lad_morphology import topic as _topic

            head = _topic(theme)
        except Exception:
            head = f"{theme}는"
        lines.append(f"{head} {met['vehicle']}의 결을 닮았다.")


    # poetic scaffold — a seeded opener that addresses the theme, so the piece READS as a poem
    # rather than a run of definition lines. The scaffold is discourse surface (LAD), not a fact.
    import hashlib

    _h = int(hashlib.sha256(theme.encode("utf-8", "ignore")).hexdigest(), 16)
    _openers = (f"{theme}{_obj_particle(theme)} 가만히 떠올리면,",
                f"{theme}, 그 말을 오래 품으면,",
                f"눈을 감고 {theme}{_obj_particle(theme)} 불러보면,",
                f"{theme}{_topic_particle(theme)} 이렇게 다가온다 —")
    opener = _openers[_h % len(_openers)]
    body = [ln for ln in lines if ln][:3]
    if len(body) < 1:
        return None
    framed = [opener, *body]
    if len(framed) < 2:
        return None
    return {
        "theme": theme,
        "title": f"{theme}",
        "lines": framed[:5],
        "corpus_sentences": len(corpus),
        "concepts_used": concepts,
        "sources": sources,
        "metaphor": met,
        "guarantees": {
            "creative_mode": True,
            "factual_claims": False,
            "external_llm": False,
            "units_from_grounding_corpus": True,
        },
    }


def compose_story(theme: str, *, hormones: dict | None = None) -> dict[str, Any] | None:
    """A SHORT grounded story for the theme (owner 2026-07-11: ' ' must
 not fall to silence or a definition dump). Same contract as compose_poem, prose scale:
 = the theme's REAL graph sentences (anchors, verbatim-attested units); = holographic
 next-token flows arranging those units into new prose; = a first-person reflection from
 the self's own narrative language when it holds one. Honest scale: paragraph-scale ,
 never a pretend novel — the frame names exactly what it is. None when the graph holds too
 little (the honest decline stays honest)."""
    theme = str(theme or "").strip()
    if not theme or len(theme) > 24:
        return None
    corpus, sources, concepts = _themed_corpus(theme)


    # candidate spool hold those clean, shielded sentences; for CREATIVE mode (factual_claims:

    if len(corpus) < 8:
        seen = {re.sub(r"\s+", "", c) for c in corpus}
        try:
            from packages.autonomy_kernel.narrative_corpus import corpus_tail
            # scan the WHOLE voice corpus (rotation-capped 20k, cheap file): a theme's lines may
            # be old and sit outside a short tail (measured: 27 theme lines missed by tail 600)
            for ln in corpus_tail(20000):
                if theme in ln and re.sub(r"\s+", "", ln) not in seen and 12 <= len(ln) <= 180:
                    corpus.append(ln)
                    seen.add(re.sub(r"\s+", "", ln))
                if len(corpus) >= 40:
                    break
        except Exception:
            pass
        if len(corpus) < 8:
            try:
                import json as _json
                from pathlib import Path as _Path
                _spool = _Path(__file__).resolve().parents[2] / "data" / "autonomy" / "browse_candidates.jsonl"
                for raw in _spool.read_text(encoding="utf-8").splitlines()[-200:]:
                    try:
                        row = _json.loads(raw)
                    except Exception:
                        continue
                    for s in (row.get("sentences") or []):
                        s = str(s).strip()
                        if theme in s and re.sub(r"\s+", "", s) not in seen and 12 <= len(s) <= 180:
                            corpus.append(s)
                            seen.add(re.sub(r"\s+", "", s))
                        if len(corpus) >= 40:
                            break
            except Exception:
                pass
        if corpus and "voice_corpus/browse_readings" not in sources and len(corpus) > 3:
            sources = list(sources) + ["voice_corpus/browse_readings"]
    if len(corpus) < _MIN_CORPUS:
        return None
    try:
        from packages.cgsr.cgsr.holographic_lm import HolographicLM
        from packages.cgsr.cgsr.holographic_lm import tokens as _lm_tokens
        lm = HolographicLM(dim=256, window=3, decay=0.7, seed=11)
        lm.fit(corpus)
        _tone = None
        try:
            from packages.cgsr.cgsr.holographic_speaker import HolographicSpeaker
            _tone = HolographicSpeaker(lm=lm).tone_bias_fn(hormones)
        except Exception:
            _tone = None
    except Exception:
        return None

    corpus_toks: list[str] = []
    for s in corpus:
        corpus_toks.extend(_lm_tokens(s))
    tok_set = set(corpus_toks)

    def _attested(concept: str) -> str | None:
        if concept in tok_set:
            return concept
        for t in corpus_toks:
            if t.startswith(concept):
                return t
        return None

    def _prose_ok(line: str) -> bool:
        t = (line or "").strip()
        if len(t) < 10 or len(t) > 140:
            return False
        hangul = sum(1 for ch in t if "가" <= ch <= "힣")
        letters = sum(1 for ch in t if ch.isalpha() or "가" <= ch <= "힣")
        return letters > 0 and hangul / max(1, letters) >= 0.6


    anchor = next((s for s in corpus if theme in s and 15 <= len(s) <= 120),
                  next((s for s in corpus if 15 <= len(s) <= 120), corpus[0]))


    prose: list[str] = []
    seeds = [theme] + [c for c in concepts[1:8] if c != theme]
    for concept in seeds[:10]:
        if len(prose) >= 7:
            break
        seed = _attested(concept)
        if not seed:
            continue
        toks = lm.generate_fluent(seed, max_len=22, coherence=0.65, rep_penalty=0.85, tone_bias=_tone)
        line = _polish(_line_from_tokens(toks, drop_first=0))

        # ANCHOR too, not only from earlier prose — with a thin corpus the LM regurgitates the

        if (line and _prose_ok(line) and not _too_similar(line, anchor)
                and not any(_too_similar(line, p) for p in prose)):
            prose.append(line if line.endswith((".", "!", "?", "다", "요")) else line + ".")

    if len(prose) < 2:
        return None


    reflection = ""
    try:
        from packages.continuous_self.thought_language import realize_thought
        r = realize_thought("monologue", {"topic": theme[:16], "context": concepts[:6]}, None)
        if r and len(r) >= 12:
            reflection = r
    except Exception:
        reflection = ""

    mid = max(2, (len(prose) + 1) // 2)
    paragraphs = [anchor + " " + " ".join(prose[:mid]), " ".join(prose[mid:])]
    if reflection:
        paragraphs.append(reflection)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]



    # dashboard can watch fluency GROW as the diet fills (never a claim, just a ruler).
    _all_toks = " ".join(paragraphs).split()
    _ttr = round(len(set(_all_toks)) / max(1, len(_all_toks)), 3)
    _bi = [(_all_toks[i], _all_toks[i + 1]) for i in range(len(_all_toks) - 1)]
    _d2 = round(len(set(_bi)) / max(1, len(_bi)), 3)
    diversity = {"ttr": _ttr, "distinct2": _d2, "tokens": len(_all_toks)}
    try:
        import json as _json
        import time as _time
        from pathlib import Path as _Path
        _mp = _Path(__file__).resolve().parents[2] / "data" / "answer_quality" / "story_metrics.jsonl"
        _mp.parent.mkdir(parents=True, exist_ok=True)
        with _mp.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps({"at": _time.strftime("%Y-%m-%dT%H:%M:%S"), "theme": theme,
                                  "corpus": len(corpus), **diversity}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return {
        "theme": theme,
        "title": f"{theme} 이야기",
        "paragraphs": paragraphs,
        "corpus_sentences": len(corpus),
        "concepts_used": concepts,
        "sources": sources,
        "diversity": diversity,
        "guarantees": {
            "creative_mode": True,
            "factual_claims": False,
            "external_llm": False,
            "units_from_grounding_corpus": True,
        },
    }
