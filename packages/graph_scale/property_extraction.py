# -*- coding: utf-8 -*-
"""What a thing is FOR, what it can DO, what it is MADE OF — pulled out of one definitional sentence.

    from packages.graph_scale.property_extraction import extract
    extract("bow", "A weapon used for shooting arrows.")     # -> [("used_for", "shooting arrows")]

WHY THIS IS ONE MODULE AND NOT A PATTERN LIST INSIDE EACH SCRIPT. A census of the production store, 2026-
07-31, found the attribute mass sitting almost entirely in structure -- part_of, has_a and made_of are 96%
of it, while used_for is 0.034% and capable_of 0.020% and desires is literally zero. Two corpora on disk
can fill that gap: the Kaikki dictionary and the English Wikipedia dump. Two corpora is exactly the moment
a project grows two slightly different copies of the same judgement, so the judgement lives here and the
harvesters import it.

WHAT MAKES A HAND-WRITTEN PATTERN DEFENSIBLE HERE, given this repository's rule that hand rules are
training wheels: both corpora are DELIBERATELY FORMULAIC. Lexicographers write genus-differentia to a
house style, and a Wikipedia lead sentence is a definition by editorial convention. A pattern over those
is reading a convention rather than guessing at free text. What keeps it honest is that no precision is
claimed -- it is measured against an independent source, and a lane that measures badly gets cut. One
already was: an adjective-before-the-genus-noun rule produced 230,050 has_property candidates at 0.108
agreement, which is why has_property is absent below.
"""
from __future__ import annotations

import re

STOP_OBJ = {"it", "them", "this", "that", "which", "something", "someone", "one", "other", "others",
            "a", "an", "the", "such", "these", "those", "its", "their", "his", "her", "any", "all"}

# Objects the patterns DID grab and should not have. Measured, not guessed: the first run's readable
# sample showed pawn -> "some end", plastic -> "place", skeleton -> "this sport", card -> "achieve a
# purpose". Every one names no purpose, only the shape of one.
GENERIC_OBJ = {"purpose", "purposes", "end", "ends", "place", "places", "access", "support", "use",
               "uses", "thing", "things", "means", "way", "ways", "form", "forms", "type", "types",
               "kind", "kinds", "sort", "part", "parts", "person", "people", "someone", "something",
               "example", "reference", "sport", "game", "activity", "process", "action", "effect",
               "result", "personify", "represent", "denote", "indicate", "refer", "name", "term",
               "word", "letter", "number", "member", "group", "series", "variety", "range"}
DEICTIC = re.compile(r"\b(this|that|these|those|such|some|any|it)\b", re.I)

PATTERNS = [
    ("used_for", re.compile(r"\bused\s+(?:for|in)\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]{2,40}?)(?=[,.;:()]|\s+(?:and|or|by|"
                            r"with|to|as|in|of|that|which)\b|$)", re.I)),
    # "used AS", added on gloss-lane evidence: `meat: the flesh of a killed animal used as food`
    # was a clean miss, and the for/in/to trio simply did not have the word. Measured on 8,000
    # property-stating glosses, recall 0.609 -> 0.743.
    ("used_for", re.compile(r"\bused\s+as\s+(?:a|an)?\s*([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]{2,40}?)"
                            r"(?=[,.;:()]|\s+(?:and|or|by|with|to|in|that|which)\b|$)", re.I)),
    ("used_for", re.compile(r"\bused\s+to\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]{2,40}?)(?=[,.;:()]|\s+(?:and|or|by|with|"
                            r"that|which)\b|$)", re.I)),
    ("used_for", re.compile(r"\b(?:a|an|the)\s+(?:device|tool|instrument|machine|implement|utensil|"
                            r"apparatus)\s+for\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]{2,40}?)(?=[,.;:()]|$)", re.I)),
    ('capable_of', re.compile('\\bable\\s+to\\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\\- ]{2,40}?)(?=[,.;:()]|\\s+(?:and|or|by|with|to|as|in|of|that|which)\\b|$)', re.I)),
    ('capable_of', re.compile('\\bdesigned\\s+to\\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\\- ]{2,40}?)(?=[,.;:()]|\\s+(?:and|or|by|with|to|as|in|of|that|which)\\b|$)', re.I)),
    ('has_a', re.compile('\\bconsisting\\s+of\\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\\- ]{2,40}?)(?=[,.;:()]|\\s+(?:and|or|by|with|to|as|in|of|that|which)\\b|$)', re.I)),
    ('capable_of', re.compile('\\bemployed\\s+to\\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\\- ]{2,40}?)(?=[,.;:()]|\\s+(?:and|or|by|with|to|as|in|of|that|which)\\b|$)', re.I)),
    ('made_of', re.compile('\\ba\\s+vessel\\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\\- ]{2,40}?)(?=[,.;:()]|\\s+(?:and|or|by|with|to|as|in|of|that|which)\\b|$)', re.I)),
    ("made_of", re.compile(r"\bmade\s+(?:of|from|out\s+of)\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]{2,30}?)"
                           r"(?=[,.;:()]|\s+(?:and|or|by|with|to|in|that|which)\b|$)", re.I)),
    ("capable_of", re.compile(r"\b(?:that|which)\s+can\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]{2,40}?)"
                              r"(?=[,.;:()]|\s+(?:and|or)\b|$)", re.I)),
    ("capable_of", re.compile(r"\bcapable\s+of\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]{2,40}?)(?=[,.;:()]|\s+(?:and|or)\b|$)",
                              re.I)),
    # THE FOUR THE GATE HAS BEEN NAMING ALL ALONG. `gloss_lane_recall` reports its top missed cues,
    # and the loop that runs against it plateaued for twenty-one consecutive unattended cycles --
    # identical wins, identical refusal, seven hours. The reason is here rather than in the loop: it
    # searches NUMERIC KNOBS found by walking the AST, and no threshold can extract a pattern that
    # does not exist. "composed of" appeared 77 times in the measured slice and "made of" one line
    # above already caught its synonym, so the deficit was one word wide and structurally outside
    # what the loop can reach. That asymmetry -- the loop turns dials, the deficit is a missing part
    # -- is the whole finding, and it is why this line is a human touch rather than a cycle's work.
    ("made_of", re.compile(r"\bcomposed\s+of\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]{2,30}?)"
                           r"(?=[,.;:()]|\s+(?:and|or|by|with|to|in|that|which)\b|$)", re.I)),
    ("used_for", re.compile(r"\bused\s+to\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]{2,40}?)"
                            r"(?=[,.;:()]|\s+(?:and|or|by|with|in|that|which)\b|$)", re.I)),
    ("capable_of", re.compile(r"\bintended\s+to\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]{2,40}?)"
                              r"(?=[,.;:()]|\s+(?:and|or|by|with|to|as|in|of|that|which)\b|$)", re.I)),
    ("has_a", re.compile(r"\bthat\s+contains\s+([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ\- ]{2,40}?)"
                         r"(?=[,.;:()]|\s+(?:and|or|by|with|to|in|that|which)\b|$)", re.I)),
]

# THE RELATIVE-CLAUSE VERB, added because the modal patterns above barely fire. A dictionary writes "a
# bird that flies", not "a bird that can fly", so capable_of came out at 593 rows against used_for's
# 7,950. This reads the finite verb of a restrictive clause instead of waiting for a modal.
_REL_VERB = re.compile(r"\b(?:that|which)\s+(?:[a-z]+ly\s+)?"
                       r"((?!is\b|are\b|was\b|were\b|has\b|have\b|had\b|can\b|could\b|may\b|might\b|"
                       r"will\b|would\b|does\b|do\b|did\b|means\b|belongs\b|refers\b|seems\b|"
                       r"remains\b|exists\b|appears\b|occurs\b)[a-z]{3,}(?:s|es))"
                       r"(\s+(?:a|an|the)?\s*[a-z][a-z\- ]{2,28}?)?"
                       r"(?=[,.;:()]|\s+(?:and|or|but|for|from|with|which|that|when|while|because)\b|$)",
                       re.I)
_AUX = {"is", "are", "was", "were", "has", "have", "had", "does", "do", "did"}
# Verbs that assert a capability only when they carry a complement. "a publication that provides
# synonyms" is a real capability; bare "provide" is not, and "a sport that involves ..." is never one.
_LIGHT_VERB = {"involve", "include", "contain", "consist", "comprise", "feature", "concern",
               "describe", "denote", "indicate", "represent", "resemble", "relate", "mean", "allow",
               "enable", "require", "provide", "produce", "cause", "form", "make", "use", "carry",
               "hold", "give", "take", "become", "serve", "act", "occur", "consist"}


def _deinflect(verb: str) -> str | None:
    """flies -> fly, washes -> wash, runs -> run. Crude on purpose; it is measured, not trusted."""
    v = verb.lower()
    if v.endswith("ies") and len(v) > 4:
        return v[:-3] + "y"
    for suf in ("sses", "shes", "ches", "xes", "zes"):
        if v.endswith(suf):
            return v[:-2]
    if v.endswith("oes") and len(v) >= 4:      # goes -> go. len > 4 left "goe" in the ledger.
        return v[:-2]
    if v.endswith("s") and not v.endswith("ss") and len(v) > 3:
        return v[:-1]
    return None


def clean_object(o: str) -> str | None:
    """Normalise a captured span, or refuse it. Refusal is the point: a generic span is worse than none."""
    o = re.sub(r"\s+", " ", o).strip().strip(",.;:").lower()
    o = re.sub(r"^(?:a|an|the)\s+", "", o)
    # SIX WORDS, NOT FOUR. The cap was a guess and it was throwing away correct captures: `die: a
    # device for cutting into a specified shape` is five words and was silently refused. Raising it
    # is the kind of change that usually buys recall with precision, so both were measured on the
    # gloss lane -- recall 0.743 -> 0.796 AND agreement ROSE, used_for 0.541 -> 0.576 and capable_of
    # 0.250 -> 0.360. The longer spans were not noise; they were the specific ones.
    if len(o) < 3 or len(o.split()) > 6 or o in STOP_OBJ:
        return None
    if not re.fullmatch(r"[a-zÀ-ɏ][a-zÀ-ɏ\- ]*[a-zÀ-ɏ]", o):
        return None
    if DEICTIC.search(o):
        return None
    words = o.split()
    if words[-1] in GENERIC_OBJ:
        return None
    if len(words) <= 2 and any(w in GENERIC_OBJ for w in words):
        return None
    return o


#: function words that are never the head of an object phrase
_PHRASE_STOP = {"the", "a", "an", "to", "of", "in", "for", "with", "by", "on", "at", "from",
                "be", "being", "into", "over", "as", "or", "and"}


def head_forms(obj: str, relation: str = "used_for") -> list[str]:
    """Short, matchable forms of a multi-word object — emitted ALONGSIDE it, never instead of it.

    WHY, measured rather than assumed. E5-2 showed a change reaches B1 (which reads prose directly) at
    +5.3% and B2 (which reads through a CONSENSUS gate) at +1.9%: a row only counts for B2 once a
    second source confirms it. So B2's lever is corroborability, not recall — and corroborability
    turns out to depend sharply on length. Agreement against ConceptNet, by object word count:

        used_for     1 word 0.441   2 words 0.229   3 words 0.219
        capable_of   1 word 0.185   2 words 0.000   3 words 0.020

    A single-word object is confirmed 2-9x more often, and the collapse starts at two words. Which
    means E5-1's cap raise (4 -> 6 words) bought B1 exactly the rows B2 cannot use.

    Shortening the object would be the obvious fix and it is known to be wrong: bare stubs like "lung
    cancer capable_of originate" are what E5-1 REPAIRED. So both are emitted. Measured on multi-word
    objects: full span alone 0.228 / 0.018; with head forms admitted, 0.605 / 0.228 — 2.7x and 12.7x
    more corroborable, with the specific fact still in the graph.

    WHICH END IS THE HEAD DEPENDS ON THE RELATION, and reading the actual phrases settled it after a
    first version emitted both and produced nonsense:

        made_of     "ground meat" -> meat, "nylon fibers" -> fibers        the head is LAST
                    the first word is a modifier: ground, fermented, plush, two
        capable_of  "carry a meaning" -> carry, "entering into contracts" -> entering   head is FIRST
                    the last word is the verb's object, and "morpheme capable_of meaning" is not a fact

    A material phrase is a noun phrase and a capability phrase is a verb phrase. That distinction is
    not declared here: `relation_fit.clusters()` groups relations by MEASURED object-vocabulary
    overlap and returns exactly [used_for, capable_of] against [made_of] — the verb-taking relations
    against the noun-taking one. The grouping is counted from the graph, so a new relation lands on
    the right side without this function being edited."""
    words = [w for w in str(obj or "").split() if w not in _PHRASE_STOP]
    if len(str(obj or "").split()) < 2 or not words:
        return []                                  # a single-word object is already its own head
    try:
        from packages.self_repair.relation_fit import clusters
        verbish = any(relation in g and "capable_of" in g for g in clusters())
    except Exception:
        verbish = relation in ("used_for", "capable_of")   # profiles unavailable; the observed split
    cand = words[0] if verbish else words[-1]
    if cand != obj and len(cand) >= 3 and cand not in GENERIC_OBJ:
        return [cand]
    return []


def extract(subject: str, sentence: str, *,
            require_complement: bool = False) -> list[tuple[str, str]]:
    """(predicate, object) pairs asserted about `subject` by this one sentence. Empty is a fine answer.

    `require_complement` drops bare-verb capable_of rows -- "acoustics can deal", "aberration can
    deviate" -- keeping only ones that carry an object, like "pollinate flowers". It costs the good bare
    cases too ("a bird that flies" -> fly), so which setting is right is a measurement and not a taste;
    scripts/wiki_property_sweep.py runs both on the same pages and the answer is in its docstring."""
    out: list[tuple[str, str]] = []
    seen = set()
    for pred, rx in PATTERNS:
        for m in rx.finditer(sentence):
            o = clean_object(m.group(1))
            if o and o != subject and (pred, o) not in seen:
                seen.add((pred, o))
                out.append((pred, o))
    for m in _REL_VERB.finditer(sentence):
        base = _deinflect(m.group(1))
        if not base or base in _AUX or base == subject:
            continue
        tail = clean_object(m.group(2) or "")
        if tail:
            value = f"{base} {tail}"
        elif require_complement or base in _LIGHT_VERB:
            continue                       # a light verb with no complement asserts nothing
        else:
            value = base
        if ("capable_of", value) not in seen:
            seen.add(("capable_of", value))
            out.append(("capable_of", value))
    for pred, obj in list(out):
        for head in head_forms(obj, pred):
            if (pred, head) not in seen and head != subject:
                seen.add((pred, head))
                out.append((pred, head))
    return out
