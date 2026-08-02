# -*- coding: utf-8 -*-
"""Text normalizer — the structural robustness layer for messy real-world text (wall 2).

Measured problem (data/comprehension/noise_degradation.json): clean comprehension 0.9925 collapses
to 0.037 / 0.072 / 0.092 / 0.190 under 25% case-punct / keyboard / fragment / natural perturbation.
Humans lose 5-10 points on the same corruption; we lose ninety-six. That is not a knowledge gap, it
is a brittle SURFACE: the parser's frames match exact word forms, so one dropped period or one
transposed letter and an otherwise perfectly understood world never gets built at all.

Three repairs, each domain-blind and each learned from the text ITSELF — no hand dictionary of
spellings, no per-corpus word list (the doctrine's rule: regexes are training wheels; the shape of
the repair must generalize):

  1. TYPO CANONICALIZATION — a typo is a MINORITY VARIANT. The same location or actor recurs many
     times in a passage and corruption hits only a fraction of the occurrences, so cluster the
     text's own tokens by edit distance and fold rare variants into the frequent form they orbit.
     'kitchin' next to three 'kitchen's is a misspelling; two words that are both common stay apart.
  2. VERB-COUNT SEGMENTATION — one finite verb per clause. When punctuation AND capitalization are
     both gone, sentence boundaries are still recoverable: a second verb means a second clause, and
     its subject starts just before it. (The existing fallback recovers boundaries from capitals,
     which lowercasing destroys — this is the layer beneath that one.)
  3. FUNCTION-WORD REPAIR — fragmented text drops 'to', 'is', 'the'. Only attempted AFTER strict
     matching has failed, so clean text is never touched by a guess.

Honest bound: this recovers SURFACE, not meaning. Anything the repaired text still does not support
is abstained on exactly as before — a normalizer must never manufacture an answer.
"""
from __future__ import annotations

import re
from collections import Counter

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

# Below this length an edit of 1 is usually a different word ('he'/'we', 'in'/'is'), not a typo.
MIN_TYPO_LEN = 4
# The canonical form must dominate the variant this many times over before folding. Two genuinely
# common words never merge; a rare corruption of a frequent word does.
DOMINANCE = 2.0

# CLOSED-CLASS words are never folded, in either direction. Frequency evidence does not apply to
# them: they are a small fixed inventory the parser keys on structurally, and a rare one sitting
# next to a frequent one is normal grammar, not corruption. Measured the hard way — 'then' (rare in
# a passage) was folded into 'they' (frequent in compound-coreference text), turning "Then Daniel
# went..." into "They Daniel went..." and dropping qa13 from 1.000 to 0.918. This guard is about
# word CLASS, not subject matter, so it carries no domain commitment.
_CLOSED = {
    "the", "a", "an", "this", "that", "these", "those", "then", "than", "there", "their", "them",
    "they", "he", "she", "it", "him", "her", "his", "its", "we", "us", "our", "you", "your", "i",
    "my", "me", "and", "or", "but", "if", "so", "as", "at", "by", "for", "from", "in", "into",
    "of", "on", "to", "up", "with", "was", "were", "is", "are", "be", "been", "am", "has", "had",
    "have", "do", "does", "did", "not", "no", "yes", "who", "what", "when", "where", "why", "how",
    "which", "back", "after", "afterwards", "before", "again", "here", "now", "both", "either",
    "neither", "all", "any", "some", "each", "one", "two", "three", "four", "five", "will",
    "would", "can", "could", "may", "might", "must", "should", "shall", "while", "until", "since",
}


def _edit_within(a: str, b: str, k: int) -> bool:
    """Is the OSA (Damerau-Levenshtein, restricted) distance between a and b at most k?

    Transposition counts as ONE edit. This matters more than it looks: the commonest real
    misspellings ARE adjacent swaps — 'teh', 'adn', 'wnet', 'recieved' — and plain Levenshtein
    prices them at 2, which put them beyond every k=1 repair in this module (measured: 'wnet'
    refused to snap to 'went' and the natural family sat unrepaired)."""
    la, lb = len(a), len(b)
    if abs(la - lb) > k:
        return False
    prevprev: list[int] = []
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prevprev[j - 2] + 1)
        if min(cur) > k:
            return False
        prevprev, prev = prev, cur
    return prev[lb] <= k


def build_canon_map(text: str) -> dict[str, str]:
    """variant -> canonical, learned from this text's own token frequencies.

    A typo is a rare neighbour of a common word. Nothing is folded unless the canonical form is
    clearly dominant, so two frequent words that happen to differ by one letter both survive."""
    freq = Counter(w.lower() for w in _WORD.findall(text)
                   if len(w) >= MIN_TYPO_LEN and w.lower() not in _CLOSED)
    if not freq:
        return {}
    forms = sorted(freq, key=lambda w: (-freq[w], w))       # frequent first, deterministic
    canon: dict[str, str] = {}
    for i, rare in enumerate(forms):
        if freq[rare] > 2:                                   # common enough to be its own word
            continue
        k = 1 if len(rare) < 7 else 2
        for common in forms:
            if common is rare or freq[common] < DOMINANCE * freq[rare]:
                continue
            if abs(len(common) - len(rare)) <= k and _edit_within(rare, common, k):
                canon[rare] = common
                break
    return canon


def apply_canon(text: str, canon: dict[str, str]) -> str:
    """Rewrite variants to their canonical form, preserving the original casing pattern."""
    if not canon:
        return text

    def _sub(m: re.Match) -> str:
        w = m.group(0)
        c = canon.get(w.lower())
        if not c:
            return w
        return c.capitalize() if w[:1].isupper() else c

    return _WORD.sub(_sub, text)


def canonicalize(text: str) -> str:
    """Fold this text's own typos onto its own majority spellings."""
    return apply_canon(text, build_canon_map(text))


# ---------------------------------------------------------------- own-lexicon repair

# ATANOR's OWN acquired English vocabulary, mined from its graph (data/lexicon/english_vocab.json,
# 82k words). Using it here is not a hand dictionary for this benchmark — it is the agent reading
# with the vocabulary it actually has, which is exactly why a human survives a typo: 'bathrom' is
# recognizable because 'bathroom' is a word you know. Within-passage voting cannot reach these
# cases at all — when every occurrence of a room name is corrupted, the clean spelling is simply
# absent from the item (measured: the 'natural' family sat at 0.220 with a 0.698 flip rate, i.e.
# confidently answering with our own misspelling).
_LEXICON: dict[str, int] | None = None
_LEX_INDEX: dict[tuple, list[str]] | None = None
_LEX_PATH = "data/lexicon/english_vocab.json"
MIN_LEX_FREQ = 3          # a correction target must be a word we have really seen, not graph dust


def lexicon() -> dict[str, int]:
    """Load once, lazily. An absent lexicon is not an error — repair simply does less."""
    global _LEXICON, _LEX_INDEX
    if _LEXICON is None:
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parents[2] / _LEX_PATH
        try:
            _LEXICON = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _LEXICON = {}
        # Bucket by (first letter, length). A correction is at most one edit, so only three
        # buckets can hold a candidate — scanning all 82k words per token made a single harness
        # run take longer than the whole rest of the pipeline.
        _LEX_INDEX = {}
        for w, c in _LEXICON.items():
            if c >= MIN_LEX_FREQ and w.isalpha():
                _LEX_INDEX.setdefault((w[0], len(w)), []).append(w)
    return _LEXICON


def _lex_candidates(word: str, k: int = 1) -> list[str]:
    """Known words within k edits, via the length/initial bucket index."""
    lexicon()
    n = len(word)
    out = []
    for L in range(n - k, n + k + 1):
        for w in (_LEX_INDEX or {}).get((word[0], L), ()):
            if _edit_within(word, w, k):
                out.append(w)
    return out


def _known_word(low: str, lex: dict[str, int]) -> bool:
    """Is this a REAL word of ours — or lexicon dust? The vocabulary is mined from web-derived
    graph text, so the commonest typos are themselves in it at trace frequency ('teh' freq 3), and
    a plain membership test then PROTECTED the typo from repair. A token is dust, not a word, when
    a one-edit neighbour outweighs it a hundredfold. Measured calibration: dust sits at 100x+
    ('teh' 131,781x under 'the'; 'shere' 108x under 'share' — an ultra-rare place name that
    protected itself and blocked the question-word repair), while genuine rare words stay
    within ~10x of their neighbours ('shire' is 11x under 'share'). Real pairs like car/cat
    are both simply frequent and never approach the ratio."""
    f = lex.get(low, 0)
    if f == 0:
        return False
    if f > 5:
        return True
    return not any(lex[c] >= 100 * f for c in _lex_candidates(low) if c != low)


def repair_with_lexicon(text: str, min_len: int = 4) -> str:
    """Rewrite unknown words to the known word they are one edit from.

    Deliberately conservative, and each guard was paid for: a word ATANOR already knows is never
    touched; PROPER NAMES are never touched (a capitalized token is a name, and names are exactly
    what a general vocabulary does not contain — 'correcting' them cost bAbI 0.976 -> 0.9676 on the
    first attempt); the target must be unambiguous or clearly dominant; and short words are left
    alone because at four letters an edit is usually a different word rather than a slip."""
    lex = lexicon()
    if not lex:
        return text

    def _sub(m: re.Match) -> str:
        w = m.group(0)
        low = w.lower()
        if w[:1].isupper():                           # a name, not a misspelling
            return w
        if len(low) < min_len or low in _CLOSED or not low.isalpha() or _known_word(low, lex):
            return w
        cands = _lex_candidates(low)
        if not cands:
            return w
        best = max(cands, key=lambda c: lex[c])
        # The target must be a genuinely COMMON word. Measured separation in our own lexicon:
        # real vocabulary sits at 10..1000+ (hallway 10, kitchen 339, office 972) while graph dust
        # sits under it (sandro 4) — and 'sandra', an unknown NAME in lowercased text, was being
        # 'corrected' to sandro. A name resembles dust, never a common word.
        if lex[best] < 10:
            return w
        if len(cands) > 1 and lex[best] < 2 * max(lex[c] for c in cands if c != best):
            return w                                  # genuinely ambiguous — leave it alone
        return best

    return _WORD.sub(_sub, text)


# ---------------------------------------------------------------- segmentation

# A clause-carrying verb. Deliberately the same shape the situation frames look for, so segmentation
# and parsing agree on what counts as a predicate.
_VERBISH = {"is", "was", "are", "were", "has", "had", "have", "went", "moved", "journeyed",
            "travelled", "traveled", "came", "ran", "walked", "hurried", "drove", "flew", "gave",
            "took", "grabbed", "picked", "dropped", "left", "put", "handed", "passed", "got",
            "discarded", "received", "made", "said", "told", "saw", "found", "sent", "did"}
_DET = {"the", "a", "an", "his", "her", "their", "its", "my", "your"}


def _is_verb(tok: str) -> bool:
    t = tok.lower().strip(",.;:!?")
    return t in _VERBISH or (len(t) > 4 and t.endswith("ed") and t not in _DET)


def segment_by_verbs(text: str) -> list[str]:
    """Recover sentence boundaries with neither punctuation nor capitalization, using the one
    structural fact that survives both: ONE FINITE VERB PER CLAUSE.

    'mary went to the kitchen john moved to the garden' -> two clauses, split just before the
    subject of the second verb (backing over any determiner, so 'the girl took ...' stays whole)."""
    words = text.split()
    if len(words) < 4:
        return [text] if text.strip() else []
    verb_at = [i for i, w in enumerate(words) if _is_verb(w)
               and not (i > 0 and words[i - 1].lower().strip(",") in
                        _DET | {"to", "of", "in", "at", "on", "from"})]
    if len(verb_at) < 2:
        return [text]
    _noun_ctx = _DET | {"to", "of", "in", "at", "on", "from"}
    cuts = []
    for v in verb_at[1:]:
        # 'to the LEFT of the triangle' — a verb-shaped token right after a determiner or
        # preposition is a noun, not a clause start (measured: the spatial frame lost its
        # sentence to a split before 'left').
        if v > 0 and words[v - 1].lower().strip(",") in _noun_ctx:
            continue
        start = v - 1
        while start > 0 and words[start - 1].lower().strip(",") in _DET:
            start -= 1
        if start > 0 and (not cuts or start > cuts[-1]):
            cuts.append(start)
    if not cuts:
        return [text]
    segs, prev = [], 0
    for c in cuts:
        seg = " ".join(words[prev:c]).strip()
        if seg:
            segs.append(seg)
        prev = c
    tail = " ".join(words[prev:]).strip()
    if tail:
        segs.append(tail)
    return segs or [text]


# ---------------------------------------------------------------- function words

_MOTION_V = r"(?:went|moved|journeyed|travell?ed|came|ran|walked|hurried|drove|flew)"


# The vocabulary the frames and question patterns actually key on. Snapping is tolerance around the
# parser's OWN declared inventory — not knowledge about kitchens — so it carries no domain
# commitment and moves with the frames if they change.
_FRAME_VOCAB = _VERBISH | {
    "to", "in", "at", "the", "back", "there", "here", "and", "or", "either", "no", "not", "longer",
    "where", "what", "who", "how", "many", "before", "after", "is", "was", "are", "were", "than",
    "bigger", "smaller", "above", "below", "north", "south", "east", "west", "of", "from", "up",
}


# Tie-break order when a corrupted token sits one edit from several keywords: the words the frames
# actually hinge on come first. Measured additions: 'eent' -> {went, sent} and 'shere' -> {where,
# there} both refused to snap as ties, silently costing whole sentences and whole questions —
# motion verbs and wh-words ARE hinges, so they belong here.
_PRIORITY = ("to", "is", "in", "at", "was", "the", "and", "of", "went", "where", "what", "who",
             "back", "no", "up")


def snap_to_frame_vocab(s: str) -> str:
    """Map a corrupted token onto the frame keyword it is one edit away from.

    A typo in a CONTENT word costs us a name; a typo in a PREDICATE costs us the whole sentence,
    because the frames match those words exactly and one wrong letter means no frame fires at all
    (measured: keyboard noise drove abstention to 0.738 — the world was never built). Snapping is
    applied only in the fallback pass and only when the nearest keyword is unambiguous, so a real
    word that merely resembles a keyword is left alone."""
    lex = lexicon()
    out = []
    for idx, tok in enumerate(s.split()):
        core = tok.strip(",.;:!?")
        low = core.lower()
        if not core or low in _FRAME_VOCAB or len(low) < 2 or not low.isalpha():
            out.append(tok)
            continue
        # a capitalized token is a Name and is never snapped — EXCEPT in first position, where
        # the capital is sentence case ('Whefe is Mary?' must become 'Where is Mary?')
        if idx > 0 and core[:1].isupper() and not core.isupper():
            out.append(tok)
            continue
        # A REAL word is never snapped, however close it sits to a keyword. Paid for three ways in
        # one measurement: 'mary'->'many', 'she'->'the', 'Then'->'the' — the snap was rewriting the
        # very grammar it was meant to recover. Known = closed class, or in ATANOR's own lexicon.
        if low in _CLOSED or _known_word(low, lex):
            out.append(tok)
            continue
        near = [k for k in _FRAME_VOCAB
                if abs(len(k) - len(low)) <= 1 and len(k) >= 2 and _edit_within(low, k, 1)]
        if len(near) > 1:
            # Short prepositions collide ('tp' is one edit from both 'to' and 'up'), and refusing
            # every collision left corrupted destinations unparsed ('went tp the bathroom' kept
            # 'tp the bathroom' as a room). Break the tie by how load-bearing the keyword is: the
            # frames hinge on 'to/in/at/is', so those win a tie; anything not load-bearing is left
            # alone rather than guessed.
            near = [k for k in _PRIORITY if k in near][:1]
        if len(near) == 1:
            fixed = near[0].capitalize() if core[:1].isupper() else near[0]
            out.append(tok.replace(core, fixed))
        else:
            out.append(tok)
    return " ".join(out)


def repair_function_words(s: str) -> str:
    """Put back the function words fragmentation drops. Applied ONLY after strict frame matching
    has already failed, so a guess can never overwrite a clean reading.

    Two insertions carry nearly all of it in practice: the 'to' of a motion ('mary went kitchen')
    and the copula of a location statement ('mary in the kitchen')."""
    out = re.sub(rf"\b({_MOTION_V})\s+(?!to\b|back\b|into\b|toward)", r"\1 to ", s, flags=re.I)
    # 'went back garden' — fragmentation ate the 'to' AFTER 'back', which the rule above's lookahead
    # deliberately skips (measured: Sandra stayed lost in her own garden).
    out = re.sub(rf"\b({_MOTION_V})\s+back\s+(?!to\b)", r"\1 back to ", out, flags=re.I)
    # A wh-question that lost its copula ('Where Mary?') names a world we may well have built
    # perfectly — measured: the fragment family's location state was CORRECT and we still abstained,
    # because the question itself had become unreadable. Put the copula back before giving up.
    out = re.sub(r"^(where|who|what)\s+(?!is\b|was\b|are\b|were\b|did\b|does\b|do\b)"
                 r"([A-Za-z][\w'-]*)", r"\1 is \2", out, flags=re.I)
    if not re.search(r"\b(?:is|was|are|were)\b", out, re.I):
        out = re.sub(r"^([A-Za-z][\w'-]*(?:\s+and\s+[A-Za-z][\w'-]*)?)\s+(in|at)\s+",
                     r"\1 is \2 ", out, flags=re.I)
        # a spatial statement lost its copula: 'bathroom south of the office' (fragment qa4 held
        # 30 of the family's failures — the whole task shape was unreadable without its 'is')
        out = re.sub(r"^((?:the\s+)?[A-Za-z][\w'-]*)\s+(south|north|east|west|above|below)\b",
                     r"\1 is \2", out, flags=re.I)
    # '... south the kitchen' / '... south kitchen' lost its 'of'
    out = re.sub(r"\b(south|north|east|west)\s+(?!of\b|is\b)((?:the\s+)?[A-Za-z])",
                 r"\1 of \2", out, flags=re.I)
    # a transfer lost its 'to': 'Mary gave the milk Jeff' (fragment qa5, 30 failures). The
    # recipient is the capitalized token, so the insertion is anchored, never guessed.
    out = re.sub(r"\b(gave|handed|passed)\s+((?:the\s+)?[a-z][\w'-]*)\s+(?!to\b)([A-Z][a-z])",
                 r"\1 \2 to \3", out)
    return out
