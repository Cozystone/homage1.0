# -*- coding: utf-8 -*-
"""Generated inner speech — the self's thoughts are REALIZED BY THE LANGUAGE
ENGINE, never picked from a hand-written snippet table (owner hard directive
2026-07-08: ).

Mechanism — everything already exists and is learned, nothing is templated:
 bones = the live state (driver, current topic, open question) decides what
 the thought is ABOUT;
 flesh = HolographicLM next-token flows, fit on the language the self actually
 holds for that topic (the graph's themed utterance corpus + the
 self's own accumulated narrative), decide HOW it is worded.

The wording therefore drifts as the self learns and remembers — two moments
with different histories think in different sentences. Where the self holds no
language for a topic, this returns None and the caller falls back to the old
line MARKED generated=False, so nothing ever pretends to be generated.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_NARRATIVE_WINDOW = 120
# fitted-LM cache: corpus fingerprint -> (lm, corpus_tokens). See realize_thought.
_LM_CACHE: dict[str, tuple] = {}


# The offline speaker arena (packages/evolution/speaker_arena.py) evolves the voice's
# phenotype knobs and harvests antibodies from Critic-rejected speech. The live voice only


_EVO_DIR = Path(__file__).resolve().parents[2] / "data" / "evolution"
_EVO_CACHE: dict[str, tuple[float, Any]] = {}


def _evo_file(name: str, parse) -> Any:
    path = _EVO_DIR / name
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    hit = _EVO_CACHE.get(name)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        value = parse(path)
    except Exception:
        value = None
    _EVO_CACHE[name] = (mtime, value)
    return value


def _champion_genome() -> dict[str, float] | None:
    import json
    return _evo_file("speaker_genome.json",
                     lambda p: (json.loads(p.read_text(encoding="utf-8")) or {}).get("genome"))


def _antibodies() -> set[tuple[str, str]]:
    import json

    def _parse(p: Path) -> set[tuple[str, str]]:
        pairs: set[tuple[str, str]] = set()
        for ln in p.read_text(encoding="utf-8").splitlines()[-2000:]:
            try:
                d = json.loads(ln)
                pairs.add((str(d["a"]), str(d["b"])))
            except Exception:
                continue
        return pairs

    return _evo_file("antibodies.jsonl", _parse) or set()


#: link-aggregator scaffolding. Not a style judgement -- these are strings no person utters, so a
#: voice fitted on them learns a feed's shape rather than a mind's.
_CHROME = re.compile(
    r"\b\d+\s+points?\s+by\b|\bhours?\s+ago\b|\|\s*hide\b|\bcomments?\s*$|\bpage\s+\d+\b"
    r"|\bsubmitted by\b|\bupvot|\bdiscuss\s*$|\(\s*[a-z0-9.-]+\.(?:com|org|net|io|app|dev)\s*\)",
    re.IGNORECASE)


_STREAM = Path(__file__).resolve().parents[2] / "data" / "temporal_reasoning" / "life_stream.jsonl"


def _own_speech(n: int = 600) -> list:
    """My own inner speech, most recent first, each line once.

    Deduplicated because 52% of the raw stream is repetition -- feeding that in would teach the voice
    to say what it has already said, which is the collapse this lane is otherwise worth risking."""
    out: list = []
    seen: set = set()
    if not _STREAM.exists():
        return out
    try:
        with _STREAM.open(encoding="utf-8", errors="replace") as fh:
            tail = fh.readlines()[-4000:]
    except Exception:
        return out
    for line in reversed(tail):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            # ONLY a malformed line, never any error. `json` was missing from this module's imports
            # and a bare `except Exception` swallowed the NameError on every single line, so this
            # returned an empty diet and the generator went from 1 of 8 speaking to 0 — reported as
            # "no own speech available" rather than as the import bug it was. Seventh time in one day
            # that a defensive catch turned a defect into a quiet zero.
            continue
        t = str(row.get("content") or "").strip()
        if len(t) < 20 or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= n:
            break
    return out


def _topic_of(driver: str, facts: dict[str, Any]) -> str:
    explicit = str((facts or {}).get("topic") or "").strip()
    if explicit:
        return explicit[:16]
    # ENGLISH TOPICS, BECAUSE THE SEED IS LOOKED UP IN AN ENGLISH CORPUS.
    #
    # This map stayed Korean when the diet was switched to English, and the whole generator ran
    # aground on it silently. `realize_thought` picks a seed token by `startswith(topic)`; with a
    # Korean topic and an English corpus no seed can EVER be found, so it returned None every time
    # and every thought fell back to a snippet. Measured across the whole diet:
    #
    #     '연결' '문장' '상태'        0 seeds     every Korean topic, always
    #     'world'                     31 seeds
    #     'question' 'thought' 'knowledge' 'connection' 'person' 'self'   attested
    #
    # The fallback was doing its job and saying `generated=False`, so nothing lied -- it just meant
    # the owner's directive that thoughts be GENERATED had not held in practice for some time.
    return {
        "growth": "connection", "learning_active": "knowledge", "uncertainty": "thought",
        "curiosity_idle": "question", "idle": "quiet", "user_present": "person",
        "open_self_question": "question", "resource_pressure": "rest",
    }.get(driver, "thought")


def realize_thought(driver: str, facts: dict[str, Any] | None, state: Any = None) -> str | None:
    """One generated line of inner speech, or None when the self holds too
    little language about the topic to speak from (the honest decline)."""
    topic = _topic_of(driver, facts or {})
    corpus: list[str] = []
    try:
        from packages.grounded_composer.creative_composer import _themed_corpus

        themed = list(_themed_corpus(topic)[0] or [])


        # the topic WORD alone pulled both senses' corpus). When the caller passes the page's
        # co-occurring concepts, only themed lines living near that field may teach the mouth;
        # the other sense never gets a vote. No matching lines → the themed pool contributes
        # nothing and the voice may honestly fall silent.
        ctx = [str(c).lower() for c in ((facts or {}).get("context") or []) if str(c).strip()]
        ctx = [c for c in ctx if c != topic.lower()]
        if ctx:
            themed = [t for t in themed if any(c in t.lower() for c in ctx)]
        corpus.extend(themed[:40])
    except Exception:
        pass
    # The self's own lived narrative is corpus too — and it is WEIGHTED (x3):

    # first-person observation register; without the weight the LM speaks like
    # an encyclopedia instead of a mind (measured). The voice literally grows
    # out of its history, which is what makes it a voice and not a table.
    narrative_lines: list[str] = []
    if state is not None:
        for entry in (getattr(state, "narrative", []) or [])[-_NARRATIVE_WINDOW:]:
            text = str((entry or {}).get("text") or "").strip()
            if len(text) >= 8:
                narrative_lines.append(text)
    corpus.extend(narrative_lines * 3)
    # The PERSISTENT narrative corpus (Moltbook comments, expedition prose, accepted monologue
    # lines) is the voice's growing diet — the owner's directive that the language accumulate
    # instead of evaporate. Monologue-accepted lines land here too, closing the self-play loop.
    try:
        from packages.autonomy_kernel.narrative_corpus import corpus_tail

        # register-balanced (2026-07-11): the accelerated wiki lane floods the raw tail with
        # encyclopedic declaratives; balanced sampling over-weights the scarce conversational/
        # question/emotive lines so the fitted voice sounds like a person, not an encyclopedia.
        # 60 WAS TOO SMALL TO SEED FROM, measured rather than guessed. At 60 lines only two of the
        # eight topics this voice ever asks for appear anywhere in the diet; at 2000 all eight do.
        # A seed that does not exist in the corpus is the second half of why the voice was silent --
        # the first was asking for it in the retired language.
        corpus.extend(corpus_tail(1200, balanced=True))
    except Exception:
        pass
    # HARVESTED HUMAN REGISTER — speech from OUTSIDE, which is what this diet was missing.
    #
    # `autonomy_kernel.register_harvest` has existed since 2026-07-14 for exactly this problem, with
    # the same root cause in its own docstring. Nothing read it: zero references from here, the eighth
    # built-present-unread case of the day. And it could not have helped anyway -- it REQUIRED Hangul
    # and REJECTED any latin word, so the organ built to cure "the diet has no conversational
    # register" could only harvest the language this system retired. 124 patterns banked, none with a
    # person in them.
    #
    # Now it takes speech in either language, keeps only person-marked fragments, and still promotes
    # to usable only after >= 2 INDEPENDENT DOMAINS agree -- a phrase many strangers use is common
    # register, not one person's words. That consensus rule is also what keeps this lane from becoming
    # a hole: what reaches the mouth is what many people say, scrubbed of who said it.
    try:
        from packages.autonomy_kernel.register_harvest import usable_patterns
        corpus.extend(usable_patterns(limit=200))
    except Exception:
        pass

    # ITS OWN INNER SPEECH IS NOT ADDED, AND THE REASON IS MEASURED RATHER THAN ASSUMED.
    #
    # It looked like the obvious fix. The web lane is 10-13% first-person and even those are headlines
    # with "I" in them; its own life stream is 100% first-person, which is exactly the register the
    # quality gate demands. The two vocabularies are complementary -- 1,873 tokens appear only in its
    # own speech and 2,914 only on the web. Deduplicated, its stream offers 600 clean lines.
    #
    # Both ways of using it failed, and the failures are worth keeping written down:
    #
    #   MIXED with the web lane, generation rose from 1 of 8 drivers to 3 -- and produced chimeras:
    #     "thoughtfully curated from us to work on this is still with me I have..."
    #   Marketing copy spliced to its own voice. Worse than silence, because the fragment of its own
    #   speech SUPPLIES THE PRONOUN and the first-person gate passes text with nobody in it. A gate
    #   defeated by the diet it was meant to hold out is worse than a gate that stays shut.
    #
    #   ALONE, it is coherent -- "weak is still with me I have raised this once and it needs
    #   something" -- and it is an ECHO. Its stream is itself mostly produced by the fallback
    #   templates and the verbaliser, so fitting on it recovers those templates. That is not
    #   generation; it is the voice saying what it already says, with extra steps.
    #
    # So the generator stays honestly shut, and what it needs is now specific rather than vague:
    # genuine first-person speech from OUTSIDE -- people talking -- not pages, and not its own echo.
    # ENGLISH ONLY (doctrine 2026-07-18): the inner voice thinks in English, so its diet is
    # English. The themed lane still carries Korean-era graph utterances — after the narrative
    # corpus was cleaned, the LM locked onto a single Korean dictionary line ('지식은 무엇을
    # 배우거나…', measured via test_voice) because it was the only themed text left standing.
    # Filtering here, at the single point where every lane converges, keeps the diet's LANGUAGE
    # invariant no matter which lane fed it; too little English left => the honest None below.
    corpus = [t for t in corpus if not any("가" <= ch <= "힣" for ch in t)]
    # SITE CHROME IS NOT SPEECH, and it was 35.2% of this diet -- measured, 423 of 1200 lines. Link
    # aggregator scaffolding: "( example.com ) 114 points by someone 4 hours ago hide 76 comments".
    # Nobody says that, so a mind fitted on it does not learn to talk; it learns to look like a feed.
    # Found by unblocking the generator and reading what came out: "quiet village in the browser
    # hologram page 33 points by speckx 20 hours ago" was offered as an inner thought. Filtered at the
    # same single point as the language, for the same reason -- every lane converges here, so the diet
    # stays clean whichever lane fed it.
    corpus = [t for t in corpus if not _CHROME.search(t)]
    if len(corpus) < 6:
        return None
    try:
        from packages.cgsr.cgsr.holographic_lm import HolographicLM
        from packages.cgsr.cgsr.holographic_lm import tokens as _lm_tokens

        ticks = int(getattr(state, "ticks", 0) or 0)
        # FIT CACHE (whole-architecture acceleration, 2026-07-10): refitting the LM on every call
        # was the single largest answer-path cost (3–9s per felt/identity/advice turn, measured on
        # the battery). The fitted model only changes when the CORPUS changes, so it is keyed by a
        # corpus fingerprint and refit only on real language growth. Variation across calls still
        # comes from the ticks-rotated seed pool and the drifting corpus — time varies the walk,
        # not the weights.
        import hashlib
        genome = _champion_genome() or {}
        fp = hashlib.md5(("\n".join(corpus[:3]) + "\x1f" + "\n".join(corpus[-5:])
                          + f"\x1f{len(corpus)}\x1f{sorted(genome.items())}"
                          ).encode("utf-8", "ignore")).hexdigest()
        cached = _LM_CACHE.get(fp)
        if cached is None:
            lm = HolographicLM(dim=256, window=int(genome.get("window", 3)),
                               decay=float(genome.get("decay", 0.7)),
                               seed=((abs(hash(driver)) * 31 + ticks) & 0xFFFF) or 7)
            if genome.get("top_k"):
                lm.top_k = int(genome["top_k"])
            if genome.get("temp"):
                lm.temp = float(genome["temp"])
            lm.fit(corpus)
            corpus_tokens = []
            for sentence in corpus:
                corpus_tokens.extend(_lm_tokens(sentence))
            if len(_LM_CACHE) >= 6:
                _LM_CACHE.clear()   # tiny bound; corpora rotate slowly
            _LM_CACHE[fp] = (lm, corpus_tokens)
        else:
            lm, corpus_tokens = cached
        # Seed preference: a topic-bearing token from the self's OWN narrative

        # resort (that seed tends to continue into a dictionary definition).
        seed = None
        seed_pool: list[str] = []
        for line in narrative_lines:
            if topic in line:
                for tok in _lm_tokens(line):
                    if tok.startswith(topic) and tok not in seed_pool:
                        seed_pool.append(tok)
        if seed_pool:
            seed = seed_pool[ticks % len(seed_pool)]
        if seed is None:
            seed = next((t for t in corpus_tokens if t.startswith(topic) and len(t) > len(topic)), None)
        if seed is None and topic in corpus_tokens:
            seed = topic
        if seed is None:
            question = str((facts or {}).get("question") or "").strip()
            if question:
                q_tokens = _lm_tokens(question)
                seed = next((t for t in corpus_tokens if q_tokens and t == q_tokens[0]), None)
        if seed is None:
            return None

        # HolographicSpeaker — the self's live digital-hormone state tilts word choice (warm when
        # content, brisk when aroused) inside the same coherence walk. Tone re-ranks corpus-attested
        # candidates only (multiplicative, zero-clamped), so this cannot fabricate; and the quality
        # gate + honest fallback below still stand, so a thin voice degrades gracefully, never worsens.
        _tone = None
        try:
            from packages.cgsr.cgsr.holographic_speaker import HolographicSpeaker
            _hormones = getattr(state, "hormones", None)
            if isinstance(_hormones, dict):
                _tone = HolographicSpeaker(lm=lm).tone_bias_fn(_hormones)
        except Exception:
            _tone = None
        out = lm.generate_fluent(seed, max_len=13,
                                 coherence=float(genome.get("coherence", 0.7)),
                                 rep_penalty=float(genome.get("rep_penalty", 0.85)),
                                 tone_bias=_tone, antibody=_antibodies() or None)
        line = " ".join(out).strip() if isinstance(out, (list, tuple)) else str(out or "").strip()
        line = re.sub(r"\s+", " ", line)
        # quality gate: a thought must be a readable clause, not token debris
        if len(line) < 10 or len(line.split()) < 3:
            return None
        # AND IT MUST BE SOMEONE THINKING. Not a style preference -- a definitional property: inner
        # speech is the self speaking about its own situation, so it is first-person. Unblocking the
        # generator showed why this is needed. With the topic map fixed it produced, as thoughts:
        #
        #     "personalized learning dashboard that empower learners to study the motion of..."
        #     "thoughtfully curated from us to continue on our mission and all contributors"
        #     "quiet village in the world around you with DW Documentary gives you knowledge"
        #
        # Fluent, and nobody is home. That is WORSE than the fallback, which at least marks itself
        # `generated=False` and does not pretend -- and the owner's stated use for this voice is to
        # judge the system's state by talking to it, which fluent nobody-text actively defeats.
        # So the generator stays honestly silent until the diet can feed a first person. The diet is
        # the real bottleneck and it is measured: 35.2% of it was link-aggregator chrome, and what
        # remains is headlines, course blurbs and marketing copy -- web scrapings, not speech.
        if not re.search(r"\b(?:I|I'm|I'll|I've|me|my|myself)\b", line):
            return None
        if not line.endswith(("다", ".", "요", "까", "지", "네")):
            line += " …"  # an unfinished thought reads as thinking — honest trail-off
        return line[:90]
    except Exception:
        return None
