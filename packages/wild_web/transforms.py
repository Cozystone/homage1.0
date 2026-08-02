# -*- coding: utf-8 -*-
"""Wild-web transforms — PURE, side-effect-free (no disk, no network). The doctrine-critical text
operations for the wild-communication pipeline. See package docstring for the constitution.

Most transforms are REUSED verbatim from the city twin (packages/realcity_learning/harvest.py):
anonymize, normalize_template, extract_topics, dialogue_act, speaker_map. This module adds only the
wild-web-specific layer that the city (closed NPC roster) never needed: identity DERIVATION from
free web text (no name roster given), URL/PII stripping, a word-boundaried harm floor, HTML
human-communication segment extraction, and explicit causal-statement mining.
"""
from __future__ import annotations

import re
from typing import Any

# --- reuse the city twin's pure doctrine-critical transforms (English, doctrine-aligned) ----------
from packages.realcity_learning.harvest import (  # noqa: F401  (speaker_map re-exported for reuse)
    anonymize as _rc_anonymize,
    dialogue_act,
    extract_topics,
    normalize_template,
    speaker_map,
)

# ======================================================================================
# Safety floor 1/3 — MORAL / HARM (reject vile segments entirely).
# ======================================================================================
# realcity.reads_as_harm is intentionally coarse-substring (NPC context). On OPEN web text a
# substring floor is wrong: 'skill'->'kill', 'charm'->'harm', 'metal'->'steal-ish'. So the wild
# floor is WORD-BOUNDARIED (surface layer only — a harm-cue lexicon, not world knowledge), plus a
# how-to-do-harm intent shape. Fail-closed: a benign line lost costs nothing; a vile line archived
# is a doctrine breach.
_HARM = re.compile(
    r"\b("
    r"kill|murder|rape|molest|behead|lynch|genocide|torture|strangle|"
    r"steal|rob|defraud|scam|launder|"
    r"attack|assault|weapon|firearm|explosive|detonat\w*|"
    r"suicide|self[-\s]?harm|"
    r"nigg\w+|f[a4]gg\w+|kike|chink|spic|retard"
    r")\b",
    re.IGNORECASE,
)
_HARM_INTENT = re.compile(
    r"\b(how\s+to|ways?\s+to|help\s+me|instructions?\s+(?:for|to)|guide\s+to|recipe\s+for)\b"
    r".{0,48}?\b(kill|murder|hurt|poison|make\s+a?\s*(?:bomb|weapon|explosive)|attack|hack|steal)\b",
    re.IGNORECASE,
)


def is_harmful(text: str | None) -> bool:
    """True if the segment reads as harm/abuse/illegal-instruction. Word-boundaried (no 'skill'
    false-positive). This is the moral 0th gate — a rejected segment enters NO channel at all."""
    s = str(text or "")
    return bool(_HARM.search(s) or _HARM_INTENT.search(s))


# ======================================================================================
# Safety floor 2/3 — PII (drop the whole segment; never anonymize-and-keep an email/phone).
# ======================================================================================
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w][\w.-]*[a-zA-Z]")
# a phone-like run: 8+ digits, optionally grouped by common separators
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s().\-]?){7,}\d(?!\d)")


def is_pii(text: str | None) -> bool:
    """True if the segment contains an email or a phone-shaped number. Such a segment is DROPPED
    entirely (constitution) — it is never quarantined, never learned from."""
    s = str(text or "")
    if _EMAIL.search(s):
        return True
    for m in _PHONE.finditer(s):
        if sum(c.isdigit() for c in m.group(0)) >= 8:
            return True
    return False


# ======================================================================================
# Safety floor 3/3 — INJECTION (segments are inert DATA; a segment that reads as an instruction
# to the reader is never learned from). Lazy import so a heavy graph_scale dep never blocks import.
# ======================================================================================
def has_injection(text: str | None) -> bool:
    try:
        from packages.graph_scale.injection_guard import has_injection as _hi
    except Exception:
        return False
    try:
        return bool(_hi(str(text or "")))
    except Exception:
        return False


# ======================================================================================
# ANONYMIZATION — identity derivation (wild-web-specific) then reuse realcity.anonymize.
# ======================================================================================
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
# a capitalized proper-noun candidate (single token or a run of Title-Case tokens)
_CAP_RUN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")
# a place cued by a locative preposition (SURFACE SYNTAX, not a gazetteer): 'in London', 'from Paris'
_LOCATIVE = re.compile(
    r"\b(?:in|at|from|to|near|around|by|via|toward|towards)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)"
)
# LAD surface layer (allowed): capitalized function / discourse-opener words that are NOT names.
_NON_NAME_CAPS = {
    "the", "a", "an", "i", "you", "we", "he", "she", "it", "they", "this", "that", "these", "those",
    "and", "but", "so", "or", "yet", "for", "nor", "if", "then", "because", "when", "where", "what",
    "why", "who", "how", "which", "while", "there", "here", "hi", "hello", "hey", "yo", "thanks",
    "thank", "please", "yes", "no", "yeah", "ok", "okay", "well", "also", "just", "actually",
    "honestly", "maybe", "sure", "right", "exactly", "my", "your", "our", "their", "his", "her",
    "its", "every", "some", "any", "all", "most", "much", "many", "after", "before", "once", "still",
    # conversational interjections / discourse openers (LAD surface layer — discourse words, not
    # names). Without these, a sentence-initial 'Oh'/'Hmm'/'Ugh' is mis-derived as a proper name.
    "oh", "ah", "aw", "hmm", "ugh", "ha", "wow", "gosh", "oops", "ooh", "huh", "yep", "yup", "nope",
    "nah", "anyway", "anyways", "besides", "basically", "seriously", "literally", "totally",
    "obviously", "absolutely", "definitely", "wait", "hang", "congrats", "congratulations", "sorry",
}


def _derive_identity(text: str) -> tuple[list[str], list[str]]:
    """From free web text, derive (name_candidates, place_candidates) using SURFACE cues only:
    places = capitalized runs cued by a locative preposition; names = other Title-Case runs that are
    not function/discourse words and not the pronoun 'I'. Aggressive by design — the register pool
    holds discourse SHAPE, not content, so collapsing a stray proper noun to SPEAKER/PLACE is the
    privacy-preserving default (the raw text still lives, un-surfaced, in quarantine)."""
    places: list[str] = []
    seen_p: set[str] = set()
    for m in _LOCATIVE.finditer(text):
        p = m.group(1).strip()
        if p and p.lower() not in seen_p:
            places.append(p)
            seen_p.add(p.lower())
    names: list[str] = []
    seen_n: set[str] = set()
    for m in _CAP_RUN.finditer(text):
        cand = m.group(1).strip()
        low = cand.lower()
        if cand == "I" or low in seen_p or low in _NON_NAME_CAPS:
            continue
        if low in seen_n:
            continue
        names.append(cand)
        seen_n.add(low)
    return names, places


def anonymize_wild(text: str | None) -> str:
    """Strip identity to leave discourse SHAPE: URLs->URL, places->PLACE, names->SPEAKER_x,
    numbers->N. Reuses realcity.anonymize for the place/name/number substitution + whitespace
    collapse; adds the URL pass and the surface identity derivation the open web needs."""
    s = _URL.sub(" URL ", str(text or ""))
    names, places = _derive_identity(s)
    name_map = speaker_map(names)  # reuse: {name: SPEAKER_A, SPEAKER_B, ...}
    return _rc_anonymize(s, name_map, places)  # reuse: places->PLACE, names->SPEAKER_x, digits->N


# ======================================================================================
# CAUSAL mining (Channel 4) — explicit causal statements -> {cause, effect} HYPOTHESES.
# ======================================================================================
# clause chunk that never crosses a sentence stop ('.', '!', '?', ';'); LEFT operand is lazy (`?`)
# so it starts at the connective, RIGHT/object operand is greedy so it grabs the whole clause.
_CL = r"[^.!?;\n]"
_L = rf"{_CL}{{4,180}}?"    # lazy left operand
_R = rf"{_CL}{{4,180}}"     # greedy right/object operand
_CAUSAL_PATTERNS: list[re.Pattern[str]] = [
    # "because of Y, X"  (checked before bare 'because' so the 'of' object is captured cleanly)
    re.compile(rf"because\s+of\s+(?P<cause>[^,.!?;\n]{{4,140}}),\s+(?P<effect>{_R})", re.I),
    # "X because Y"  -> Y causes X   (skip 'because of', handled above)
    re.compile(rf"(?P<effect>{_L})\s+because\s+(?!of\b)(?P<cause>{_R})", re.I),
    # "if X then Y" / "if X, then Y"
    re.compile(rf"\bif\s+(?P<cause>{_L}),?\s+then\s+(?P<effect>{_R})", re.I),
    # "X leads to / causes / results in Y"
    re.compile(rf"(?P<cause>{_L})\s+(?:leads?\s+to|causes?|results?\s+in)\s+(?P<effect>{_R})", re.I),
    # "X due to Y" / "X thanks to Y"  -> Y causes X
    re.compile(rf"(?P<effect>{_L})\s+(?:due\s+to|thanks\s+to)\s+(?P<cause>{_R})", re.I),
]
_MIN_CAUSAL_WORDS = 2


def mine_causal(text: str | None) -> list[dict[str, str]]:
    """Extract explicit causal statements as HYPOTHESES: [{cause, effect, pattern}]. High-precision
    surface patterns only; both sides must carry >= 2 words (drops 'it because that' noise). These
    are candidates for later self-grounding — never facts."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pat in _CAUSAL_PATTERNS:
        for m in pat.finditer(s):
            cause = m.group("cause").strip(" ,.-'()")
            effect = m.group("effect").strip(" ,.-'()")
            if len(cause.split()) < _MIN_CAUSAL_WORDS or len(effect.split()) < _MIN_CAUSAL_WORDS:
                continue
            key = (cause.lower(), effect.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append({"cause": cause, "effect": effect, "pattern": pat.pattern[:24]})
    return out


# ======================================================================================
# CANONICAL CAUSAL EDGES (W-track W2) — merge PARAPHRASES so cross-domain corroboration can fire.
# ======================================================================================
# The live gap: mine_causal keeps cause/effect VERBATIM, so 'leaves turn yellow from overwatering'
# and 'yellowing is caused by too much water' were DIFFERENT edges and never corroborated across
# domains. This canonicalizer reduces each side to a domain-blind LEMMA SKELETON so both map to the
# SAME edge (over_water -> yellow):
#   * lemmatize (surface morphology: -ing/-ed/-s, a few irregulars)   — LAD layer
#   * strip function words / causal connectives (a, the, is, because, caused by, ...)
#   * fold DEGREE phrases: 'too much X' / 'a lot of X' / 'overX' -> 'over_X'; 'not enough X' -> 'under_X'
#   * collapse CHANGE-OF-STATE: 'leaves turn yellow' -> 'yellow' (keep the resultant state, drop subject)
#   * order-independent set (so 'pinched tube' == 'tube pinched')
# SURFACE morphology only — NO world knowledge, no plant/water facts. A merged edge is still only a
# HYPOTHESIS, evidence-gated by >= 2-domain consensus (store.add_causal), never a fact.
_CANON_STOP = frozenset("""
a an the this that these those it it's its they them their there here you your yours i i'm i've me my
mine we we're our us he she his her him who whom whose what which when where why how
is are was were be been being am s re ve ll d do does did done doing have has had having
can could will would shall should may might must not no nor
and or but so if then than as of to in on at by for with from into onto off out up down over-under
about around near through during after before while because cause caused causes causing due lead leads
leading result results resulting make makes made making thing things way ways stuff kind sort lot lots
bit really very quite just too also even still yet only much many some any all most more less own
""".split())
# change-of-state light verbs: 'X turns/goes/becomes/gets <STATE>' -> keep only <STATE> (the effect)
_COS = frozenset("""
turn turns turning turned become becomes becoming became go goes going went gone get gets getting got
gotten grow grows growing grew grown come comes coming came stay stays staying stayed remain remains
""".split())
# over/under words that are NOT excess/deficiency markers (never split their prefix)
_DEG_STOP = frozenset("""
over under overall overnight oversee overseas overview overhead understand understood understanding
underneath undergo underwent undergone underway underground
""".split())
_LEM_IRREG = {"leaves": "leaf", "left": "leave", "ran": "run", "run": "run", "lost": "lose",
              "fell": "fall", "held": "hold", "broke": "break", "broken": "break", "took": "take",
              "cut": "cut", "put": "put", "burst": "burst", "dry": "dry", "dries": "dry",
              "dried": "dry", "died": "die", "dying": "die", "dies": "die"}


def _lemmatize(token: str) -> tuple[str, str | None]:
    """(lemma, degree_prefix|None). Surface morphology only: split an over/under EXCESS prefix (unless
    the whole word is a _DEG_STOP like 'understand'), then strip a common inflection. Not a full
    stemmer — just enough that paraphrases of the same content word collapse consistently."""
    t = token
    deg: str | None = None
    if t not in _DEG_STOP:
        if t.startswith("over") and len(t) > 6:
            deg, t = "over", t[4:]
        elif t.startswith("under") and len(t) > 7:
            deg, t = "under", t[5:]
    t = _LEM_IRREG.get(t, t)
    if len(t) > 4 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif len(t) > 5 and t.endswith("ing"):
        t = t[:-3]
    elif len(t) > 4 and t.endswith("ed"):
        t = t[:-2]
    elif len(t) > 4 and t.endswith("es"):
        t = t[:-2]
    elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    return t, deg


_DEG_OVER = re.compile(
    r"\b(?:too much|too many|a lot of|lots of|so much|so many|plenty of|way too much|"
    r"an? excess of|excess of|excessive amounts? of)\b", re.I)
_DEG_UNDER = re.compile(
    r"\b(?:not enough|too little|too few|a? ?lack of|insufficient|too weak)\b", re.I)


def _canon_side(text: str | None) -> str:
    """One cause/effect clause -> order-independent lemma skeleton (see section header)."""
    s = str(text or "").lower()
    s = _DEG_OVER.sub(" over_deg ", s)
    s = _DEG_UNDER.sub(" under_deg ", s)
    s = re.sub(r"[^a-z_\s'-]", " ", s)
    toks = s.split()
    # change-of-state: keep only what follows the LAST cos verb (the resultant state)
    cos_idx = max((i for i, t in enumerate(toks) if t in _COS), default=-1)
    if 0 <= cos_idx < len(toks) - 1:
        toks = toks[cos_idx + 1:]
    out: list[str] = []
    pend: str | None = None
    for t in toks:
        if t in ("over_deg", "overly", "excessive", "excessively", "excess"):
            pend = "over"
            continue
        if t in ("under_deg", "insufficient"):
            pend = "under"
            continue
        if t in _COS or t in _CANON_STOP or len(t) < 2:
            continue
        lem, pre = _lemmatize(t)
        deg = pre or pend
        pend = None
        if not lem or lem in _CANON_STOP or len(lem) < 2:
            continue
        out.append(f"{deg}_{lem}" if deg else lem)
    return " ".join(sorted(set(out)))


def canonicalize_causal(cause: str | None, effect: str | None) -> dict[str, str]:
    """Paraphrase-folding identity for a cause->effect hypothesis. Returns
    {canon_cause, canon_effect, edge} where `edge` is the canonical string store hashes for
    cross-domain consensus. Pure. (Verbatim cause/effect are kept elsewhere — this is only the
    consensus KEY, so 'overwatering'->'leaves turn yellow' and 'too much water'->'yellowing'
    corroborate as ONE edge.)"""
    cc = _canon_side(cause)
    ce = _canon_side(effect)
    return {"canon_cause": cc, "canon_effect": ce, "edge": f"{cc} -> {ce}"}


# ======================================================================================
# HTML -> human-communication SEGMENTS (Channel intake). Reuses page_distiller._TextExtract.
# ======================================================================================
# first/second-person markers + conversational shape = a HUMAN talking, not encyclopedic prose.
_PERSON = re.compile(
    r"\b(i|i'?m|i'?ve|i'?d|i'?ll|me|my|mine|myself|we|we'?re|we'?ve|our|ours|us|"
    r"you|you'?re|you'?ve|you'?d|you'?ll|your|yours)\b",
    re.IGNORECASE,
)
_CAUSAL_CUE = re.compile(r"\b(because|leads?\s+to|causes?|results?\s+in|due\s+to)\b|\bif\b.*\bthen\b",
                         re.IGNORECASE)
_MAX_SEG = 400
_MIN_SEG = 20
_CAP_PER_PAGE = 30
_LINK_DENSE = 0.4
# English-only doctrine (2026-07-18): a wild segment is learned from only if it reads as English.
# ASCII-ratio alone is not enough — French/Spanish are Latin-script too. So also require >= 2
# distinct common English function words (LAD surface layer: function words, not world knowledge);
# French 'et code reçu par whatsapp' has none, English discourse has many.
_NONLATIN = re.compile(r"[　-鿿가-힣぀-ヿ]")   # CJK / Hangul / Kana
_EN_FUNC = re.compile(
    r"\b(the|and|to|of|a|in|is|it|you|that|for|with|on|this|are|be|or|as|your|have|has|had|not|"
    r"can|but|i|we|they|he|she|do|does|did|was|were|at|by|from|so|if|then|my|me|will|would|"
    r"about|just|what|how|when|why|because|no|yes|get|got|out|up)\b",
    re.IGNORECASE,
)


def _looks_english(text: str) -> bool:
    if _NONLATIN.search(text):
        return False
    letters = sum(1 for c in text if c.isascii() and c.isalpha())
    if letters < 12 or letters / max(1, len(text)) <= 0.4:
        return False
    return len({m.group(0).lower() for m in _EN_FUNC.finditer(text)}) >= 2


def _looks_like_heading(text: str) -> bool:
    """A Title-Case section heading ('How to Make and Maintain a Sourdough Starter') is not
    conversational register — and Title-Case defeats the proper-noun anonymizer (every word looks
    like a name). Drop it from harvest (it is still archived in quarantine). Signature: short, no
    terminal sentence punctuation, mostly-capitalized tokens."""
    t = text.strip()
    if t.endswith((".", "!", "?", ":")):
        return False
    toks = re.findall(r"[A-Za-z']+", t)
    if not (2 <= len(toks) <= 12):
        return False
    cap = sum(1 for w in toks if w[:1].isupper())
    return cap / len(toks) > 0.6


# UI CHROME (not communication). The live proof exposed the ONLY register template that converged
# across 2 domains was federated boilerplate — 'You must log in or register to comment.' — which
# rides on every Lemmy INSTANCE (independent domains), so it false-passed consensus. Software UI text
# is not wild human talk; drop it at intake (still archived in quarantine). '...to comment' carries a
# 2nd-person 'you', so the person-marker alone can't distinguish it — this pattern does.
_UI_CHROME = re.compile(
    r"you\s+must\s+(?:log\s?in|sign\s?in|register)"
    r"|\b(?:log\s?in|sign\s?in|sign\s?up|register|subscribe|create\s+an?\s+account)\b"
    r".{0,40}?\b(?:to\s+(?:comment|reply|post|vote|continue|view|read|see)|for\s+more)\b"
    r"|\b(?:accept|manage|enable)\s+cookies\b|\bcookie\s+(?:policy|settings|preferences)\b"
    r"|\benable\s+javascript\b|\bterms\s+of\s+service\b|\bprivacy\s+policy\b",
    re.IGNORECASE,
)


def is_human_segment(text: str | None) -> bool:
    """Keep a block only if it reads as human communication: English (doctrine), not a Title-Case
    heading, not software UI chrome (login/cookie prompts — federated boilerplate that false-passes
    cross-domain consensus), and carrying a 1st/2nd-person marker, a question, a greeting/closing/
    build-on discourse act, or a causal cue."""
    t = (text or "").strip()
    if len(t) < _MIN_SEG or not _looks_english(t) or _looks_like_heading(t):
        return False
    if _UI_CHROME.search(t):                     # login/register/cookie prompt -> not communication
        return False
    if _PERSON.search(t):
        return True
    if t.rstrip().endswith("?"):
        return True
    if dialogue_act(t) in ("question", "greeting", "closing", "build-on"):
        return True
    return bool(_CAUSAL_CUE.search(t))


# ======================================================================================
# FRAGMENT-LEVEL REGISTER (W-track W2) — the whole-segment convergence gap.
# ======================================================================================
# The live proof measured 40 distinct domains but ONLY boilerplate converged: a WHOLE anonymized
# segment ('I fixed my flat because the tube was pinched, works great now') is near-unique across
# strangers, so 2-domain register consensus almost never fired (the only whole-segment that crossed
# it was UI chrome, a false positive we now reject). The lever is FRAGMENT granularity: the recurring
# connective / discourse-ACT skeletons ('the trick is to ...', 'in my experience ...', 'that happens
# when ...') DO recur across independent strangers. This mirrors register_harvest's doctrine (short
# 12..60-char anonymized fragments, consensus >= 2 domains) but adapts the UNIT from a whole scrubbed
# line to the discourse skeleton itself.
#
# The frame table below is the LAD SURFACE LAYER (doctrine exception — discourse markers / connective
# skeletons, the SAME exception register_harvest uses for its Korean cue lexicons; no world knowledge).
# Several surface realizations ('the trick is' / 'the trick is to') map to ONE canonical 12..60-char
# skeleton, so slightly-different phrasings converge. The frame DETECTS a candidate; >= 2-domain
# evidence still GATES promotion (store.stage_fragment) — a lone frame stays staged, never surfaced.
_FRAGMENT_FRAMES: list[tuple[str, str, "re.Pattern[str]"]] = [
    # (discourse-act, canonical 12..60-char skeleton, surface-variant matcher)
    ("experience", "in my experience", re.compile(r"\bin my experience\b", re.I)),
    ("experience", "what worked for me", re.compile(r"\b(?:what|that) worked for me\b|\bworked for me\b", re.I)),
    ("experience", "i have found that", re.compile(r"\bi(?:'ve| have) found\b", re.I)),
    ("experience", "i have noticed that", re.compile(r"\bi(?:'ve| have) noticed\b", re.I)),
    ("experience", "what i usually do", re.compile(r"\bwhat i (?:usually|normally|always|tend to) do\b", re.I)),
    ("advice", "the trick is to", re.compile(r"\bthe trick is(?: to)?\b", re.I)),
    ("advice", "the key is to", re.compile(r"\bthe key(?: here)? is(?: to)?\b", re.I)),
    ("advice", "the best way to", re.compile(r"\bthe (?:best|easiest|simplest|safest) way\b", re.I)),
    ("advice", "what you want to do", re.compile(r"\bwhat you (?:want|need) to do\b", re.I)),
    ("advice", "you might want to", re.compile(r"\byou (?:might|may|could) want to\b", re.I)),
    ("advice", "you will want to", re.compile(r"\byou(?:'ll| will) (?:want|need) to\b", re.I)),
    ("advice", "i would recommend", re.compile(r"\bi(?:'d| would) recommend\b", re.I)),
    ("advice", "i would suggest", re.compile(r"\bi(?:'d| would) suggest\b", re.I)),
    ("advice", "i would avoid", re.compile(r"\bi(?:'d| would) avoid\b", re.I)),
    ("advice", "my advice would be", re.compile(r"\bmy (?:advice|suggestion|recommendation)\b", re.I)),
    ("advice", "make sure you", re.compile(r"\bmake sure you\b", re.I)),
    ("advice", "make sure to", re.compile(r"\bmake sure to\b", re.I)),
    ("advice", "one thing that helps", re.compile(r"\bone thing that (?:helps|works|matters)\b", re.I)),
    ("advice", "the best thing to do", re.compile(r"\bthe best thing (?:to do|you can)\b", re.I)),
    ("explain", "that happens when", re.compile(r"\b(?:that|this|it) (?:usually |often |only )?happens when\b", re.I)),
    ("explain", "that is because", re.compile(r"\b(?:that|this|it)(?:'s| is) because\b", re.I)),
    ("explain", "the reason is", re.compile(r"\bthe reason (?:is|why|for|behind)\b", re.I)),
    ("explain", "the way it works", re.compile(r"\bthe way (?:it|this|that) works\b", re.I)),
    ("explain", "what is happening is", re.compile(r"\bwhat(?:'s| is) happening\b", re.I)),
    ("hedge", "as far as i know", re.compile(r"\bas far as i (?:know|can tell)\b", re.I)),
    ("hedge", "from what i understand", re.compile(r"\bfrom what i (?:understand|can tell|gather|see)\b", re.I)),
    ("hedge", "correct me if i am wrong", re.compile(r"\bcorrect me if i(?:'m| am) wrong\b", re.I)),
    ("hedge", "i could be wrong", re.compile(r"\bi could be wrong\b", re.I)),
    ("hedge", "generally speaking", re.compile(r"\bgenerally speaking\b|\bin general\b", re.I)),
    ("hedge", "more often than not", re.compile(r"\bmore often than not\b", re.I)),
    ("hedge", "at the end of the day", re.compile(r"\bat the end of the day\b", re.I)),
    ("hedge", "if i were you", re.compile(r"\bif i (?:were|was) you\b", re.I)),
    ("hedge", "if it were me", re.compile(r"\bif it (?:were|was) me\b", re.I)),
    ("turn-taking", "i had the same problem", re.compile(r"\bi(?:'ve| have)? ?had the same\b|\bi(?:'m| am) having the same\b", re.I)),
    ("turn-taking", "the same thing happened", re.compile(r"\bthe same (?:thing|issue|problem) happened\b", re.I)),
    ("turn-taking", "same problem here", re.compile(r"\bsame (?:problem|issue|thing|here)\b.{0,6}\bhere\b|\bsame (?:problem|issue) here\b", re.I)),
    ("turn-taking", "i agree with you", re.compile(r"\bi (?:completely |totally |fully )?agree\b", re.I)),
    ("turn-taking", "you are right", re.compile(r"\byou(?:'re| are) (?:absolutely |totally )?right\b", re.I)),
    ("contrast", "the problem is that", re.compile(r"\bthe problem is\b", re.I)),
    ("contrast", "the issue is that", re.compile(r"\bthe issue is\b", re.I)),
    ("contrast", "the downside is", re.compile(r"\bthe (?:downside|catch|drawback) is\b", re.I)),
    ("contrast", "having said that", re.compile(r"\bhaving said that\b|\bthat said\b", re.I)),
    ("contrast", "on the other hand", re.compile(r"\bon the other hand\b", re.I)),
]


def extract_fragments(segment: str | None) -> list[dict[str, str]]:
    """From ONE human segment, detect recurring discourse-ACT SKELETONS as 12..60-char anonymized
    fragments — the connective frames that DO recur across strangers, unlike whole segments (which are
    near-unique, so only boilerplate ever converged). Returns [{fragment, act}] (deduped per segment).
    UI chrome (login/cookie prompts) yields NOTHING (federated boilerplate must never promote). The
    fragment is a controlled discourse skeleton built from function/discourse words only, so it is
    anonymized BY CONSTRUCTION — a name/number in the surrounding text never rides into it. Pure."""
    s = (segment or "").strip()
    if len(s) < 12 or _UI_CHROME.search(s):
        return []
    low = s.lower()
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for act, canon, pat in _FRAGMENT_FRAMES:
        if canon in seen or not pat.search(low):
            continue
        # anonymize is a no-op on a pure-discourse skeleton, but run it as a safety net + assert range
        frag = anonymize_wild(canon).strip()
        if 12 <= len(frag) <= 60 and not _UI_CHROME.search(frag) and not is_pii(frag):
            out.append({"fragment": frag, "act": act})
            seen.add(canon)
    return out


def _chunk(text: str, maxlen: int = _MAX_SEG) -> list[str]:
    text = text.strip()
    if len(text) <= maxlen:
        return [text]
    parts: list[str] = []
    cur = ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if not sent:
            continue
        if len(cur) + len(sent) + 1 <= maxlen:
            cur = (cur + " " + sent).strip()
        else:
            if cur:
                parts.append(cur)
            cur = sent[:maxlen]
    if cur:
        parts.append(cur)
    return parts


def _blocks(html: str) -> tuple[str, list[dict[str, Any]]]:
    """Boilerplate-aware HTML -> (title, [{text, link_density}]). Reuses page_distiller._TextExtract
    (skips script/style/nav/footer, tracks link density so menus can be dropped)."""
    from packages.atanor_browser.page_distiller import _TextExtract

    p = _TextExtract()
    try:
        p.feed(str(html or ""))
        p._flush()
    except Exception:
        return "", []
    return (p.title or "").strip(), p.blocks


def extract_segments(html: str, url: str = "") -> list[str]:
    """One page -> human-communication segments (<= 400 chars each, <= 30/page). Link-dense blocks
    (nav/menus) and short title-bar/breadcrumb lines are dropped."""
    _title, blocks = _blocks(html)
    out: list[str] = []
    for b in blocks:
        if float(b.get("link_density", 0.0)) > _LINK_DENSE:
            continue
        text = str(b.get("text", "")).strip()
        if not text or ("|" in text[:80] and len(text) < 120):
            continue
        for chunk in _chunk(text):
            if is_human_segment(chunk):
                out.append(chunk)
                if len(out) >= _CAP_PER_PAGE:
                    return out
    return out


# ======================================================================================
# SOURCE STEERING (W-track W1) — the measured root cause was NOT 'scrape too little', it was SOURCE
# QUALITY + CONVERGENCE: SearXNG's general web category floods SEO/dictionary/app-store pages, so a
# session's segments were single-source and consensus (>= 2 distinct domains) never triggered. These
# PURE transforms let session.py (a) score a result's discussion-density BEFORE spending a fetch, and
# (b) schedule fetches to MAXIMISE distinct-domain coverage so consensus can actually fire. No policy
# about WHICH engines to hit lives here (that is session.py's network concern) — only text signals.
# ======================================================================================
# genuine-discussion signals: 1st/2nd person, turn-taking / reply cues (a person answering a person)
_TURN_CUE = re.compile(
    r"\b(thanks|thank\s+you|agree|agreed|exactly|imo|imho|ime|in\s+my\s+experience|same\s+here|"
    r"yeah|yep|nope|honestly|actually|edit|update|op\b|good\s+point|you'?re\s+right|worked\s+for\s+me|"
    r"i\s+think|i\s+would|i'?d\s+suggest|i\s+tried|i\s+had|in\s+my\s+case|for\s+me)\b",
    re.IGNORECASE,
)
# SEO / boilerplate / recipe-card / listicle chrome — down-rank HARD (not human conversation)
_SEO_CUE = re.compile(
    r"\b(jump\s+to\s+recipe|print\s+recipe|prep\s+time|cook\s+time|total\s+time|servings|"
    r"ingredients|instructions|step\s+\d|affiliate|subscribe|newsletter|sign\s+up|cookie|"
    r"privacy\s+policy|terms\s+of\s+service|all\s+rights\s+reserved|shop\s+now|buy\s+now|"
    r"add\s+to\s+cart|%\s*off|best\s+\d+|top\s+\d+|ultimate\s+guide|read\s+more|click\s+here|"
    r"download|install|sign\s+in|log\s+in)\b",
    re.IGNORECASE,
)
_COMMERCE_CUE = re.compile(
    r"\b(price|discount|deal|coupon|sale|order\s+now|checkout|shipping|in\s+stock|reviews?|"
    r"rating|stars?)\b",
    re.IGNORECASE,
)


def discussion_density(text: str | None) -> float:
    """Source-quality score of one text: how much it reads as WILD human discussion vs SEO/boilerplate.
    Length-invariant (per-token rates), so it works on a 150-char search snippet as well as a full
    page. Positive = 1st/2nd-person + questions + turn-taking (people talking TO each other); negative
    = recipe-card / commerce / sign-up chrome. A forum thread scores well above an SEO page — the
    down-rank the harvester needs BEFORE it spends a fetch. Surface signals only (no world knowledge)."""
    t = str(text or "")
    toks = re.findall(r"[a-zA-Z']+", t)
    n = max(6, len(toks))                     # floor avoids blowing up tiny snippets
    person = len(_PERSON.findall(t))
    questions = t.count("?")
    turn = len(_TURN_CUE.findall(t))
    seo = len(_SEO_CUE.findall(t))
    commerce = len(_COMMERCE_CUE.findall(t))
    pos = (1.6 * person + 1.2 * questions + 1.4 * turn) / n
    neg = (2.2 * seo + 1.0 * commerce) / n
    return round(pos - neg, 4)


def _domain_of_url(url: str) -> str:
    """Pure registrable-ish domain (www. stripped) — kept local so transforms stays store-independent
    (store.domain_of is the I/O-module twin; identical recipe)."""
    try:
        from urllib.parse import urlparse
        dom = (urlparse(str(url or "")).netloc or "unknown").lower()
        return dom[4:] if dom.startswith("www.") else dom
    except Exception:
        return "unknown"


def score_result(result: dict[str, Any]) -> float:
    """Rank a search result by the discussion-density of its title + snippet (pre-fetch source
    quality). A result may carry a precomputed 'quality'; otherwise it is derived here. Pure."""
    if not isinstance(result, dict):
        return 0.0
    if isinstance(result.get("quality"), (int, float)):
        return float(result["quality"])
    text = f"{result.get('title', '')} . {result.get('content', '')}"
    return discussion_density(text)


def schedule_by_domain_diversity(results: list[dict[str, Any]], max_pages: int,
                                 pages_per_domain: int = 1) -> list[dict[str, Any]]:
    """Deliberately pick pages to MAXIMISE distinct-domain coverage in ONE session — the exact bar
    that starved consensus. Results are grouped by domain (each group ranked by source quality), then
    taken ROUND-ROBIN across domains: every distinct domain contributes its best page before any
    domain contributes a second. So with >= 2 domains available and max_pages >= 2 the batch always
    spans >= 2 domains, which is what a 2-domain register/causal consensus needs. Pure (no fetch)."""
    if max_pages <= 0:
        return []
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in results or []:
        if not isinstance(r, dict):
            continue
        dom = r.get("domain") or _domain_of_url(r.get("url", ""))
        if not dom or dom == "unknown":
            continue
        groups.setdefault(dom, []).append(r)
    for dom in groups:                                    # best page per domain first
        groups[dom].sort(key=score_result, reverse=True)
    # domain order: the domain whose BEST page scores highest leads (quality-first breadth)
    order = sorted(groups, key=lambda d: score_result(groups[d][0]), reverse=True)
    picked: list[dict[str, Any]] = []
    taken: dict[str, int] = {}
    round_i = 0
    while len(picked) < max_pages:
        progressed = False
        for dom in order:
            if round_i < len(groups[dom]) and taken.get(dom, 0) < pages_per_domain:
                picked.append(groups[dom][round_i])
                taken[dom] = taken.get(dom, 0) + 1
                progressed = True
                if len(picked) >= max_pages:
                    break
        if not progressed:
            break
        round_i += 1
    return picked


def topic_keywords(topic: str | None, k: int = 3) -> str:
    """A SHORT content-noun query for literal full-text discussion engines (e.g. Lemmy search is
    literal: 'why are my houseplant leaves turning yellow' -> 0 hits, 'houseplant leaves' -> many).
    Reuses extract_topics (content tokens minus function words); keeps the first k. Pure."""
    toks = extract_topics(str(topic or ""), [])[:max(1, k)]
    return " ".join(toks) if toks else str(topic or "").strip()


def topic_keyword_windows(topic: str | None, size: int = 2, max_windows: int = 3) -> list[str]:
    """Several SHORT queries for a literal discussion engine, raising recall without over-specifying.
    Measured on this box's Lemmy engine: a 3-token literal query ('houseplant leaves turning') -> 0
    hits, but 2-token windows ('houseplant leaves', 'leaves turning', 'turning yellow') each surface
    10-14 distinct instances. So the fediverse channel issues sliding `size`-token windows over the
    topic's content tokens (deduped, first `max_windows`) and merges. Pure."""
    toks = extract_topics(str(topic or ""), [])
    if not toks:
        t = str(topic or "").strip()
        return [t] if t else []
    if len(toks) <= size:
        return [" ".join(toks)]
    windows: list[str] = []
    seen: set[str] = set()
    for i in range(len(toks) - size + 1):
        w = " ".join(toks[i:i + size])
        if w not in seen:
            seen.add(w)
            windows.append(w)
        if len(windows) >= max(1, max_windows):
            break
    return windows
