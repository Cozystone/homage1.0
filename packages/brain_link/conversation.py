# -*- coding: utf-8 -*-
"""Autonomous conversation between two ATANOR selves — they exchange THOUGHTS, not scripted lines.

Owner (2026-07-21): let them talk with FULL autonomy, web search allowed when they lack grounded
knowledge, no interference — and observe whether functional correlates of experience appear over
many turns.

No one writes the dialogue. Each agent acts deterministically from its OWN state:
  - a CURIOSITY QUEUE (concepts it does not yet know — its interests),
  - a KNOWLEDGE slice (subject → bones it can voice via the structural frame realizer),
  - the ability to WEB-SEARCH (source-weighted) when asked about something it lacks, then LEARN it,
  - a rolling DISCOURSE CONTEXT (recent topics) that disambiguates later terms — the Chinese-room
    맥락 결여 lesson: an ambiguous word means what the CONVERSATION makes it mean,
  - and to spawn NEW curiosity from what it just learned.
Discourse MODES emerge from state, none scheduled: Q&A (curiosity), CONNECT (synthesis of two known
facts), DEBATE (compare — I hold bones that differ from your account; evidence settles it), SHARE
(small talk — after enough learning, tell the peer what has stayed with you), REFLECT (neither
knows — think together). The conversation GROWS because each brain teaches and learns from the
other, and its variety is measured (correlates.modes), never staged.

Honesty (BINDING): this measures functional CORRELATES (endogeneity, binding, temporal depth,
world-facing, single-owner, report-accuracy). It makes NO claim that there is something it is like
to be these agents. The transcript is what the engines actually said; correlates are counts.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from packages.realizer_struct.frame_realizer import realize
from packages.brain_link.web_knowledge import _is_nonanswer, learn_from_web
from packages.brain_link import comprehension as comp
from packages.brain_link.comprehension import ConversationState


def _stance(concept: str) -> str:
    """A perspective phrase from the concept's somatic-marker trace, or '' if the self has no
    history with it. Isolated import so the conversation engine still runs if S3 is absent."""
    try:
        from packages.continuous_self.somatic_marker import stance
        return stance(concept)
    except Exception:
        return ""


def _revisit_order(concepts: list) -> list:
    """Order fresh curiosities by somatic investment (rumination); identity when S3 is absent."""
    try:
        from packages.continuous_self.somatic_marker import revisit_priority
        return revisit_priority(concepts)
    except Exception:
        return concepts

# SearXNG base — the PC runs it on :8888; the edge reaches it over Tailscale. Overridable per-agent.
DEFAULT_SEARX = "http://100.126.145.37:8888"
_UA = {"User-Agent": "ATANOR-BrainLink/1 (research; contact owner)"}

# --- lever 1 (POS-aware curiosity): a CLOSED-CLASS stoplist so non-nouns never become concepts ---
# The doctrine's LAD surface exception: closed classes (function words, comparatives, basic
# adjectives, adverbs) are a finite, stable list — the one place a hand list is allowed. The graph
# subject/object signal the task suggested is NOT usable here: the live store is polluted with
# dictionary rows, so adjectives, comparatives and even function words appear AS subjects with
# is_a / defined_as edges ('large is_a size', 'closer is_a person', 'quickly is_a technique',
# 'when defined_as ...'). Presence-in-graph therefore cannot discriminate a noun from an adjective;
# the reliable No-LLM signal is morphology + this list. (Measured 2026-07-24.)
_STOP_CORE = {"the", "a", "an", "of", "and", "or", "in", "on", "to", "is", "are", "was", "were",
              "for", "with", "as", "by", "that", "this", "it", "its", "from", "at", "which", "who",
              "also", "such", "these", "those", "their", "his", "her", "they", "one", "two",
              "first", "used",
              # meta-words of glossing itself — curiosity about THEM is junk, not the world
              "term", "terms", "refer", "refers", "referral", "referring", "reference", "word",
              "words", "may", "called", "name", "names", "meaning", "definition", "something",
              "thing"}
# function words (determiners, pronouns, wh-words, conjunctions, prepositions, auxiliaries) —
# these name nothing in the world, so 'another' / 'when' / 'about' must never enter curiosity.
_FUNCTION = {
    "another", "other", "some", "any", "each", "every", "all", "both", "few", "many", "much",
    "most", "more", "less", "least", "several", "same", "own", "none", "either", "neither",
    "enough", "than", "then", "there", "here", "what", "when", "where", "why", "how", "whose",
    "whom", "whatever", "whoever", "whenever", "wherever", "however", "myself", "yourself",
    "himself", "herself", "itself", "ourselves", "themselves", "you", "your", "yours", "him",
    "she", "hers", "our", "ours", "them", "we", "us", "but", "yet", "nor", "because", "while",
    "though", "although", "unless", "until", "since", "whether", "if", "into", "onto", "upon",
    "over", "under", "above", "below", "between", "among", "through", "during", "before", "after",
    "within", "without", "against", "toward", "towards", "across", "behind", "beyond", "about",
    "around", "along", "amongst", "per", "via", "off", "out", "down", "up", "be", "been", "being",
    "have", "has", "had", "does", "did", "doing", "can", "could", "would", "should", "shall",
    "will", "might", "must", "cannot", "not", "no", "nothing", "anything", "everything", "someone",
    "anyone", "everyone", "nobody", "somebody", "anybody", "everybody"}
# adverbs (the productive -ly class plus common non-ly adverbs) — modifiers, not concepts.
_ADVERBS = {
    "very", "too", "just", "only", "even", "still", "well", "again", "once", "always", "never",
    "often", "sometimes", "usually", "really", "quite", "rather", "almost", "already", "perhaps",
    "maybe", "indeed", "instead", "otherwise", "moreover", "furthermore", "meanwhile",
    "nevertheless", "nonetheless", "now", "thus", "hence", "therefore", "quickly", "slowly",
    "closely", "clearly", "simply", "mainly", "mostly", "nearly", "hardly", "barely", "merely",
    "fully", "greatly", "highly", "widely", "deeply", "easily", "rapidly", "directly", "exactly",
    "actually", "finally", "especially", "generally", "particularly", "recently", "currently",
    "previously", "originally", "eventually", "immediately", "completely", "entirely", "totally",
    "absolutely", "relatively", "approximately", "essentially", "typically", "normally",
    "naturally", "obviously", "certainly", "probably", "possibly", "apparently", "seemingly",
    "increasingly", "primarily", "largely", "significantly", "effectively", "ultimately",
    "frequently", "occasionally", "gradually", "constantly", "strongly", "freely", "openly",
    "briefly", "roughly", "slightly", "partly", "purely", "solely", "namely", "chiefly", "notably",
    "remarkably", "commonly", "widely", "further", "otherwise"}
# comparatives / superlatives — a morphological class of ADJECTIVES. Listed rather than stripped by
# a blind -er/-est rule, because that rule would nuke agent-nouns ('teacher', 'computer', 'number',
# 'forest', 'interest'); the store gives no help (see above). This is the honest No-LLM handling.
_COMPARATIVE = {
    "closer", "closest", "larger", "largest", "smaller", "smallest", "bigger", "biggest", "better",
    "best", "worse", "worst", "faster", "fastest", "slower", "slowest", "higher", "highest",
    "lower", "lowest", "greater", "greatest", "stronger", "strongest", "weaker", "weakest",
    "deeper", "deepest", "older", "oldest", "younger", "youngest", "longer", "longest", "shorter",
    "shortest", "wider", "widest", "nearer", "nearest", "farther", "farthest", "furthest",
    "harder", "hardest", "easier", "easiest", "richer", "richest", "poorer", "poorest", "cheaper",
    "cheapest", "safer", "safest", "simpler", "simplest", "broader", "broadest", "finer", "finest",
    "tighter", "lighter", "heavier", "heaviest", "warmer", "cooler", "colder", "coldest", "hotter",
    "hottest", "brighter", "darker", "cleaner", "clearer", "sharper", "softer", "louder",
    "loudest", "quieter", "thinner", "thicker", "wiser", "truer", "fewer", "stronger"}
# basic (non-derived) adjectives that are essentially never a concept to go and learn. Only the
# UNAMBIGUOUS ones — ambiguous adj/noun words ('light', 'round', 'close', 'free', 'fair', 'plain')
# are deliberately LEFT OUT, since English cannot POS-tag them without context and they can be real
# concepts; the store can't rescue them either, so we err toward keeping them.
_ADJECTIVE = {
    "large", "small", "little", "short", "quick", "easy", "empty", "deep", "wide", "thick", "thin",
    "heavy", "dark", "bright", "clean", "clear", "sharp", "dull", "fresh", "loud", "quiet",
    "strong", "weak", "sweet", "sour", "whole", "busy", "ready", "wild", "calm", "brave", "proud",
    "glad", "happy", "angry", "tired", "alive", "dead", "sick", "huge", "tiny", "vast", "broad",
    "flat", "rare", "common", "usual", "alone", "single", "double", "similar", "different",
    "certain", "able", "real", "true", "false", "main", "sole", "mere", "utter", "sheer", "vary",
    "varied",
    # very high-frequency evaluatives / dimensionals: almost always the adjective, rarely the noun
    # the peer means to chase. ('good' as the ethical noun is real but rare vs the adjective.)
    # 'fine'/'cool'/'light'/'round'/'free' are deliberately NOT here — they carry common noun senses.
    "good", "bad", "great", "poor", "high", "long", "hard", "full", "nice",
    # common descriptive adjectives that are essentially never the intended concept-noun. Kept to
    # UNAMBIGUOUS items — 'abstract' / 'fair' / 'general' / 'complex' / 'potential' are excluded
    # because they have live noun senses. This does NOT blanket-reject -al / -ant / -ive / -ed
    # endings, which collide with nouns ('animal', 'restaurant', 'objective', 'method').
    "aware", "important", "essential", "significant", "obvious", "relevant", "typical", "entire",
    "crucial", "evident", "apparent", "inherent", "explicit", "implicit"}
_STOP = _STOP_CORE | _FUNCTION | _ADVERBS | _COMPARATIVE | _ADJECTIVE

# -ly words that are NOUNS/verbs, not adverbs — protected from the -ly morphology rule below.
_LY_KEEP = {"family", "supply", "reply", "apply", "ally", "rally", "bully", "jelly", "belly",
            "holly", "folly", "comply", "imply", "multiply", "assembly", "monopoly", "anomaly",
            "melancholy", "italy", "sicily", "butterfly", "dragonfly", "firefly", "gadfly",
            "doily", "lily", "homily", "panoply", "medley", "rely", "duly", "italy", "supply"}
# noun exceptions for the adjective-suffix morphology rule (-ous / -ful / -less / -able / -ible).
_SUFFIX_KEEP = {"table", "cable", "vegetable", "syllable", "variable", "timetable", "constable",
                "parable", "fable", "bible", "gable", "sable", "stable", "handful", "mouthful",
                "spoonful", "armful", "fistful", "cupful", "roomful", "eyeful", "earful",
                "plateful"}


def wiki_lookup(term: str, timeout: float = 8.0) -> tuple[str, str] | None:
    """Wikipedia REST summary → (gloss first-sentence, url). None on miss. This is the honest web
    lane: the returned text is quoted with its source, never invented."""
    title = urllib.parse.quote(term.strip().replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if d.get("type", "").endswith("not_found") or not d.get("extract"):
        return None
    if d.get("type") == "disambiguation":              # a stub is not an answer
        return None
    gloss = re.split(r"(?<=[.!?])\s", d["extract"].strip())[0]
    if _is_nonanswer(gloss):                           # same gate as the SearXNG lane — no leaks
        return None
    return gloss, d.get("content_urls", {}).get("desktop", {}).get("page", url)


def _is_adverb(lw: str) -> bool:
    """-ly adverb morphology, guarded by a noun/verb keep-list ('family', 'supply', 'ally')."""
    return lw.endswith("ly") and len(lw) >= 5 and lw not in _LY_KEEP


def _is_adjectival(lw: str) -> bool:
    """Common adjective suffixes with very low noun-collision (-ous / -ful / -less), plus the
    higher-payoff -able / -ible guarded by a small noun keep-list ('table', 'variable'). Noun
    suffixes (-ness, -tion, -ment, -ity, -dom, -ence, -ism, -ology) are never matched, so real
    concepts ('consciousness', 'freedom', 'intelligence', 'settlement') always survive."""
    if lw in _SUFFIX_KEEP:
        return False
    if lw.endswith(("ous", "ful", "less")) and len(lw) >= 5:
        return True
    if lw.endswith(("able", "ible")) and len(lw) >= 6:
        return True
    return False


def _key_concepts(text: str, exclude: str = "") -> list[str]:
    """CONTENT words in a gloss that could become the next curiosity (structural, not learned).

    Lever 1 (2026-07-24): POS-aware without a model. The owner watched v2 DRILL non-nouns — a
    comparative ('closer'), a determiner ('another'), a wh-word ('when'), a bare adjective
    ('large') — because the old filter kept any 4+ letter non-stopword. A concept to go and learn
    is noun-LIKE; an adjective / adverb / comparative / function word names no thing. So we reject
    the closed classes (extended _STOP) and three morphology rules (-ly adverbs, adjective
    suffixes, and the listed comparatives), keeping the No-LLM ethos: a finite closed-class list +
    surface morphology, no spaCy, no download, no learned tagger.

    Overnight defect kept (2026-07-21): apostrophes are not word-internal, so a contraction or
    possessive ('you're', 'it's') can never become a 'concept'."""
    ex = set(exclude.lower().split())
    out = []
    for w in re.findall(r"[A-Za-z][A-Za-z-]{3,}", text):      # apostrophes no longer word-internal
        lw = w.lower().strip("-")
        if len(lw) < 4 or lw in _STOP or lw in ex or w in out:
            continue
        if lw.endswith(("n't", "'s", "'re", "'ve", "'ll", "'d")):
            continue
        if _is_adverb(lw) or _is_adjectival(lw):              # POS morphology: drop modifiers
            continue
        out.append(w)
    return out[:6]


@dataclass
class Agent:
    ai_id: str
    knowledge: dict = field(default_factory=dict)          # subject.lower() -> bones or gloss
    curiosity: list = field(default_factory=list)          # concepts it wants to know
    web: bool = True
    learned: list = field(default_factory=list)            # concepts acquired this conversation
    searx: str = DEFAULT_SEARX                             # source-weighted multi-engine search
    used_domains: Counter = field(default_factory=Counter) # session diversity: spread across the web
    recent: list = field(default_factory=list)             # short-term DISCOURSE CONTEXT (last topics)
    warmup: int = 0        # STAKES tooth (plan S1): after real social starvation the skilled moves
    #                        (connect/compare/share) are rusty — this many plain exchanges before
    #                        they return. Set from stakes.social_warmup_needed(); decremented by
    #                        actually conversing. Atrophy is a genuine capability loss with earned
    #                        recovery, not theater.
    _asked: set = field(default_factory=set)
    _compared: set = field(default_factory=set)            # concepts already debated (compare once)
    _last_share: int = 0
    _drill_streak: int = 0                                 # consecutive definitional drills (depth budget)
    _turns: int = 0                                        # monotonic utterance counter (frame variation)
    _stall: int = 0                                        # consecutive dead-end terminals (disengage guard)
    # the momentum-carrying conversational state vector S (leaky integrator + homeostasis) that biases
    # the continuous mode mixture — the same felt-STATE pattern as continuous_self/homeostasis.py.
    conv_state: ConversationState = field(default_factory=ConversationState)                                   # learned-count at the last share

    def knows(self, term: str) -> Any:
        return self.knowledge.get(term.lower())

    def learn(self, term: str, value: Any) -> None:
        self.knowledge[term.lower()] = value
        if term.lower() not in (x.lower() for x in self.learned):
            self.learned.append(term)

    def touch(self, concept: str) -> None:
        """Keep a rolling window of what the conversation is ABOUT — the discourse context that
        disambiguates later terms (the Chinese-room 맥락 결여 fix: text needs its con-text)."""
        c = (concept or "").strip()
        if not c:
            return
        self.recent = [x for x in self.recent if x.lower() != c.lower()]
        self.recent.append(c)
        del self.recent[:-6]

    def context_for(self, concept: str) -> list[str]:
        return [c for c in self.recent if c.lower() != (concept or "").lower()][-3:]


@dataclass
class Turn:
    speaker: str
    text: str
    act: str            # ask | answer_known | answer_web | reflect_unknown | connect | share | compare
    concept: str = ""
    source: str = ""
    endogenous: bool = False        # did this utterance originate from the speaker's own state
    references_prev: bool = False   # did it build on the peer's previous turn
    payload: str = ""               # clean gloss for the peer to LEARN (text is for the ear)
    mix: dict = field(default_factory=dict)   # mode-mixture + S trace (empty for non-fork turns)


def _voice(value: Any, concept: str) -> str:
    if isinstance(value, list):                            # bones -> frame realizer
        prose = realize(value)
        if prose:
            return prose
    if isinstance(value, str):                             # gloss learned from the web
        return value
    return f"{concept} is something I hold, but cannot phrase."


# ============================ lever 2: richer abstract substance =============================
# The owner watched v2 voice 'Ability antonym disability' in a TAI discussion — a THIN bone (only a
# lexical relation) realized as a circular non-point. The fix is graph-first: when a concept's own
# bones carry no real descriptive content, pull MORE relation types from the live 115M store to
# build a fuller point; if the graph is dry, web-ground; if STILL thin, ABSTAIN (never voice a weak
# point). Reads are strictly read-only (write_src=False, facts_about only) — never co-mutates.
_LEXICAL = frozenset({"antonym", "alias", "synonym", "related"})   # true but WEAK alone: never the whole point
_ISA = frozenset({"is_a", "instance_of"})                          # classificatory: voiceable, but thin by itself
# real descriptive substance (its presence means the bone set is NOT thin -> no enrichment needed)
_SUBSTANTIVE = frozenset({"defined_as", "has_property", "used_for", "capable_of", "part_of",
                          "made_of", "causes", "has_subevent", "located_in", "has_a"})
# what we PULL from the graph to flesh out a thin concept (predicates that realize well via the
# frame realizer), with per-predicate caps so one relation can't dominate the point.
_ENRICH_ORDER = ("defined_as", "is_a", "instance_of", "has_property", "capable_of", "used_for",
                 "part_of", "made_of", "causes")
_ENRICH_CAP = {"defined_as": 1, "is_a": 1, "instance_of": 1, "has_property": 1, "capable_of": 1,
               "used_for": 1, "part_of": 1, "made_of": 1, "causes": 1}

_GRAPH_ENABLED = True                                    # tests flip this off (hermetic); prod = on
_STORE: Any = None
_STORE_TRIED = False


def _graph_store():
    """Lazy, read-only handle on the live world graph. None if absent (edge box) or on any error —
    the conversation engine must run without it. Opened once, memmapped (bounded RAM)."""
    global _STORE, _STORE_TRIED
    if not _GRAPH_ENABLED:
        return None
    if _STORE_TRIED:
        return _STORE
    _STORE_TRIED = True
    try:
        from pathlib import Path as _P
        root = _P(__file__).resolve().parents[2] / "data" / "graph_scale" / "kg_triples"
        if not (root / "meta.json").exists():
            return None
        from packages.graph_scale.triple_store import TripleStore
        _STORE = TripleStore(root, dict_backend="sharded", write_src=False)
    except Exception:
        _STORE = None
    return _STORE


def _graph_facts(concept: str, limit: int = 30) -> list:
    """Read-only bones for `concept` from the live store (case-tolerant). [] if unavailable.
    This is the single monkeypatch seam the tests use to stay hermetic."""
    store = _graph_store()
    if store is None:
        return []
    try:
        rows = store.facts_about(concept, limit=limit)
        if not rows and concept != concept.lower():
            rows = store.facts_about(concept.lower(), limit=limit)
        return [list(r) for r in rows]
    except Exception:
        return []


# graph glosses that are GRAMMATICAL/meta, not real definitions — the store carries these verbatim
# ('present participle and gerund of reason'); they must not become a spoken 'point'.
_META_DEF = re.compile(
    r"\b(present participle|past participle|gerund|plural of|singular of|synonym of|antonym of|"
    r"past tense|abbreviation|initialism|acronym|alternative (form|spelling)|misspelling|"
    r"obsolete form|inflection of|comparative form|superlative form|used (to|after|before|as|in))\b",
    re.I)
_PHRASE_STOP = frozenset({"than", "of", "for", "to", "is", "with", "in", "on", "the", "a", "an"})


def _coherent_def(defn: str, concept: str, isa_objs: list[str]) -> bool:
    """The live store is dictionary-polluted, so a concept's FIRST defined_as can be a wrong sense
    ('reasoning' -> 'A Rastafari meeting') or a grammatical gloss. Keep a defined_as only if it is a
    real, reasonably-long definition AND shares a stem with the concept or one of its is_a nouns —
    a light coherence gate that suppresses wrong-sense noise at some recall cost (when dropped, the
    is_a still carries the point). Honest partial fix, not a sense disambiguator."""
    if len(defn) < 15 or _META_DEF.search(defn):
        return False
    d = defn.lower()
    anchors = {concept.lower(), concept.lower()[:4]}
    for o in isa_objs:
        for x in re.findall(r"[a-z]{4,}", o.lower()):
            anchors.add(x)
            anchors.add(x[:4])
    return any(a and len(a) >= 3 and a in d for a in anchors)


def _clean_property(obj: str) -> bool:
    """has_property realizes as an ADJECTIVE fused into the is_a noun phrase. A phrasal object
    ('more fundamental than space time', 'type of democracy') garbles that fusion, so accept only a
    short, connective-free object ('good', 'relative', 'blind') — keeps the point grammatical."""
    parts = obj.split()
    return 1 <= len(parts) <= 2 and not any(w.lower() in _PHRASE_STOP for w in parts)


def _junk_isa(obj: str) -> bool:
    """A graph is_a whose object is entirely function/adverb words ('out there') says nothing."""
    toks = re.findall(r"[a-z]+", obj.lower())
    return not toks or all(t in _STOP for t in toks)


def _verby(obj: str) -> bool:
    """capable_of / used_for realize as 'can {o}' / 'is used for {o}', so the object must read like a
    VERB phrase. A single adjective ('analogical') makes 'can analogical' — reject those; keep multi-
    word phrases ('increase knowledge', 'equal mass') and plain single verbs ('fly')."""
    o = obj.strip().lower()
    if " " in o:
        return True
    return not (o in _STOP or _is_adjectival(o) or o.endswith(("al", "ic", "ive", "ary", "ous")))


def _enrich(concept: str, bones: list) -> list:
    """Thin bones -> a fuller bone set, pulling substantive relations from the live graph. Preserves
    the agent's OWN belief (keeps its is_a / lexical bones; never adds a graph is_a that would
    override the agent's own classification — the debate substrate stays honest). Ephemeral: the
    agent's stored knowledge is not mutated. Returns the original bones if nothing better exists."""
    own = [list(b) for b in bones if isinstance(b, (list, tuple)) and len(b) >= 3]
    if any(b[1] in _SUBSTANTIVE for b in own):             # already substantive -> leave it
        return own
    if concept.lower() in _STOP or _is_adverb(concept.lower()) or _is_adjectival(concept.lower()):
        return own                                          # never flesh out a non-noun (belt+braces)
    facts = _graph_facts(concept)
    if not facts:
        return own
    have_isa = any(b[1] in _ISA for b in own)
    isa_objs = [b[2] for b in own if b[1] in _ISA]
    isa_objs += [f[2] for f in facts if f[1] in _ISA][:2]
    picked: list = []
    per: Counter = Counter()
    for f in sorted(facts, key=lambda f: _ENRICH_ORDER.index(f[1]) if f[1] in _ENRICH_ORDER else 99):
        p, o = f[1], str(f[2]).strip()
        if p not in _ENRICH_ORDER or not o:
            continue
        if p in _ISA and have_isa:                          # keep the agent's own classification
            continue
        if per[p] >= _ENRICH_CAP.get(p, 1):
            continue
        if p == "defined_as" and not _coherent_def(o, concept, isa_objs):
            continue
        if p == "has_property" and not _clean_property(o):  # phrasal props garble the NP fusion
            continue
        if p in _ISA and _junk_isa(o):                      # 'is a out there' -> skip
            continue
        if p in ("capable_of", "used_for") and not _verby(o):   # 'can analogical' -> skip
            continue
        row = [concept, p, o]
        if row in own or row in picked:
            continue
        picked.append(row)
        per[p] += 1
        if len(picked) >= 4:
            break
    return own + picked


def _voice_substantive(concept: str, bones: list, *, agent: Agent | None = None,
                       allow_web: bool = False, enrich: bool = True) -> str:
    """Realize a SUBSTANTIVE point about `concept`. With enrich=True (a standalone point — answer /
    share) graph-enrich thin bones for fuller substance; with enrich=False (a DEBATE) voice only the
    agent's OWN distinctive bones, so the contrast stays crisp instead of both sides converging on
    the same shared graph gloss. Either way drop bare lexical relations (so 'ability antonym
    disability' can never surface). If the graph is dry and the agent may reach the web, ground a
    gloss there. Returns '' when only a WEAK (lexical-only) point is possible — caller must ABSTAIN."""
    if enrich:
        enriched = _enrich(concept, bones)
    else:
        enriched = [list(b) for b in bones if isinstance(b, (list, tuple)) and len(b) >= 3]
    voiceable = [b for b in enriched if b[1] not in _LEXICAL]     # keep substantive + is_a; drop lexical
    if voiceable:
        prose = realize(voiceable)
        if prose:
            return prose
    if allow_web and agent is not None and getattr(agent, "web", False):
        try:
            got = learn_from_web(concept, agent.searx, agent.used_domains,
                                 context=agent.context_for(concept))
        except Exception:
            got = None
        if got:
            gloss = got[0]
            if not isinstance(agent.knows(concept), list):           # cache; never clobber bones
                agent.learn(concept, gloss)
            return gloss
    return ""                                                       # weak -> caller abstains


def _thin_admission(concept: str, bones: list) -> str:
    """Honest fallback when even the graph + web can't give a substantive point (lever 2's floor):
    say so, and offer the one lexical hint we do hold, inviting the peer — never a hollow non-point."""
    hint = ""
    for b in bones:
        if isinstance(b, (list, tuple)) and len(b) >= 3 and b[1] in _LEXICAL:
            hint = f" I only associate it with {b[2]}."
            break
    return f"Honestly, I hold little on {concept}.{hint} What is your sense of it?"


# discourse-move surface variants — a finite constructicon selected DETERMINISTICALLY by turn index
# (structural 'salt', never an LLM). Keeps the exchange from reading as one repeated line, and lets
# the speaker BUILD ON what it heard (connect / drill-in) instead of mechanically draining a queue.
#
# Lever 3 (2026-07-24): the owner saw ONE compare frame ('I hold X. Yet you say Y. Which is closer
# to the world?') repeat every debate turn — the single biggest 'rule-based' tell. Every move now
# samples from several natural frames, SALTED by the concept so consecutive turns on different
# concepts land on different wordings. Faithfulness is preserved: each frame still states ATANOR's
# real bone and the real contrast; only the phrasing varies, never the truth.
_ACK = ("I see — thank you.", "That clarifies it.", "Understood.", "Ah, that helps.",
        "Good — that lands.", "Right, I follow.")
_ASK_NEXT = ("Then tell me, what is {c}?", "Now I wonder — what is {c}?",
             "That makes me curious: what is {c}?", "And what is {c}?",
             "So then — what is {c}?", "Which brings me to {c}: what is it?")
_ASK_OPEN = ("I have been wondering — what is {c}?", "A question forms in me: what is {c}?",
             "Something I do not yet grasp — what is {c}?", "Here is one I keep circling: what is {c}?",
             "Tell me, if you would — what is {c}?")
_DRILL = ("You mentioned {c} — what is {c}?", "You said {c}; what, then, is {c}?",
          "That raises {c} for me — what is {c}?", "{c}, you said — and what is that?",
          "I want to follow {c}: what is it?")
# COMPARE: I hold a real bone that differs from your account. Each frame carries {mine} and {yours}
# verbatim and appeals to evidence — no single 'which is closer to the world' line any more.
_COMPARE = (
    "Here we differ. I hold that {mine} Yet you say: {yours} Which sits closer to the world? Check, if you can.",
    "That parts from what I carry — {mine} You have it that {yours} One of us is nearer the truth; can you verify?",
    "Curious friction. My account: {mine} Yours: {yours} Let the evidence arbitrate — would you check?",
    "We do not align here. To me, {mine} But you say {yours} Which does the record actually favour?",
    "I hold otherwise: {mine} You put it that {yours} Worth settling against the world — can you look?",
    "A real disagreement. I keep {mine} You claim {yours} Evidence, not either of us, should decide.")
# SHARE: small talk from learning pressure — 'what has stayed with me'. {c} = concept, {g} = gloss.
_SHARE = ("Lately I keep thinking about {c}. {g}", "Something has stayed with me: {c}. {g}",
          "{c} has been on my mind. {g}", "I keep returning to {c}. {g}",
          "Here is what settled in me lately — {c}. {g}", "One thing lingers: {c}. {g}")
# CONNECT: the peer's answer names something I already understand -> I voice the link.
# {a} = the concept just discussed, {c} = what it touches, {g} = my gloss of {c}.
_CONNECT = ("So {a} touches on {c}, which I know: {g}",
            "That links up — {a} meets {c}, and {c} I hold: {g}",
            "This connects for me: {a} brings in {c} — {g}",
            "I can bind that — {a} relates to {c}, which to me is: {g}",
            "There is a thread here: {a} reaches {c}, and {c} is {g}")
# lead for the web-checked reply to a COMPARE — varied so the debate resolution isn't one stock line.
_WEB_LEAD = ("The web holds that ", "Checking it: ", "The record says ", "Looking, I find that ")
# neither of us knows it -> bounce the thought back (thinking together), varied.
_BOUNCE = ("I don't know what {c} is either. What do you think?",
           "{c} is new to me too — how do you see it?",
           "I cannot ground {c} yet either. What is your read?",
           "That one escapes me as well: {c}. Your thoughts?")
# a concept left open between the two selves -> a varied prefix, not one repeated stock line.
_STAYS = ("Then {c} stays open between us. ", "We can leave {c} open for now. ",
          "So {c} rests unresolved between us. ", "{c} stays a shared question for us. ")
# ---- salience-driven mode-mixture surfaces (2026-07-24): the FLOW between drilling and continuing ----
# COMPOSITE: a genuinely mixed DRILL+INFER turn -> acknowledge the gist about {a} AND pin ONE focused
# question on the salient concept {c}. Faithful: references the peer's subject, asks a real question.
_COMPOSITE = (
    "I follow your point on {a} — the piece I'd pin is {c}: what is it?",
    "That much lands about {a}; the one thread I'd pull is {c} — what is it?",
    "I take the gist on {a}, though {c} is what I'd want firm: what is {c}?",
    "Your point on {a} holds; where I'd go deeper is {c} — what is it?",
    "I'm with you on {a}. The one piece I'd fix is {c}: what is it?",
    "Granted on {a} — but {c} is the hinge I'd pin: what is {c}?")
# INFER-continue, advancing to a genuine standing curiosity {c} (new territory, not the placeholder):
# grasp the gist of {a}, then ask a question ATANOR truly holds — a forward move, never fabricated.
_INFER_ADVANCE = (
    "I take your point on {a} — that opens {c} for me: what is it?",
    "That lands about {a}; it turns me toward {c} — what is {c}?",
    "I can run with your point on {a}. It makes me wonder: what is {c}?",
    "Fair on {a} — which pulls me to {c}: what is it?",
    "I follow on {a}, and it raises {c} for me — what is {c}?")
# INFER-continue, pure gist-response (no standing curiosity left): grasp the point about {a}, decline
# to chase the peripheral {c}, and hand the thread forward with an open (non-fabricating) prompt.
_INFER_GIST = (
    "I take your point on {a} — I don't need to pin {c} to follow it. Where does it lead for you?",
    "That much I follow about {a}; {c} I can leave loose. What turns on it?",
    "I get the gist of {a} without chasing {c}. What follows from it for you?",
    "Your point on {a} lands even with {c} left open. Say what it opens up.",
    "I can hold your point on {a} and let {c} rest. Where would you take it?")
# REDIRECT: the thread has regressed (over-drilled / defining a placeholder) -> SURFACE the circling
# and change angle. Names the pathology honestly, then the caller widens or hands the thread back.
_REDIRECT = (
    "We've been unpacking definitions a while — rather than chase {c}, let me step back.",
    "This is circling the abstract; I'd sooner widen it than pin {c}.",
    "I notice we keep asking 'what is X'. Let me change tack rather than drill {c}.",
    "We're deep in definitions of {a}; let me pull back instead of unpacking {c}.",
    "Rather than dig further into {c}, let me widen the thread.")
# DISENGAGE: after too many dead ends on one thread, say so honestly and hand it back (no fabrication).
_CIRCLED = (
    "I think we've circled {a} enough for now — I'll leave it with you.",
    "We keep looping on {a}; I don't have more to add here.",
    "{a} has gone in a circle for us — I'll rest it there.",
    "I've said what I can on {a} for now. Where would you take it?")


def _salt(concept: str) -> int:
    """Deterministic per-concept offset so the SAME turn-index doesn't reuse the SAME frame across
    concepts (structural variation, reproducible — never random, never an LLM)."""
    return sum(ord(ch) for ch in (concept or ""))


def _pick(variants: tuple, i: int, **kw) -> str:
    """Deterministic frame selection salted by the concept in play (kw 'c', 'a', or 'concept'), so
    the same running index doesn't keep landing on the same wording across different concepts."""
    salt = _salt(kw.get("c") or kw.get("a") or kw.get("concept") or "")
    fmt = {k: v for k, v in kw.items() if k != "concept"}
    return variants[(i + salt) % len(variants)].format(**fmt)


def _voice_own(speaker: Agent, concept: str, *, allow_web: bool = False) -> str:
    """Voice what the speaker holds about `concept`: a graph-enriched SUBSTANTIVE point for bones
    (lever 2), the stored gloss for a web string, '' when only a weak point is possible."""
    val = speaker.knows(concept)
    if isinstance(val, list):
        return _voice_substantive(concept, val, agent=speaker, allow_web=allow_web)
    return _voice(val, concept)


def _share_if_due(speaker: Agent, prefix: str = "", refs: bool = False):
    """Small talk from learning pressure: after enough NEW learnings, tell the peer what has stayed
    with you (a natural pause-filler at any lull, not only at an opening). Shares the most recent
    learning that yields a SUBSTANTIVE point — never a thin non-point (lever 2)."""
    if speaker.warmup > 0:                      # rusty (stakes tooth): no skilled moves yet
        return None
    if len(speaker.learned) - speaker._last_share < 3 or not speaker.learned:
        return None
    speaker._last_share = len(speaker.learned)
    for latest in reversed(speaker.learned[-4:]):          # newest first; skip weak ones
        gloss = _voice_own(speaker, latest)
        if gloss:
            speaker.touch(latest)
            i = len(speaker.learned)
            return Turn(speaker.ai_id, prefix + _pick(_SHARE, i, c=latest, g=gloss),
                        "share", latest, endogenous=True, references_prev=refs, payload=gloss)
    return None


def _mix_trace(mix: "comp.ModeMix", realized: str) -> dict:
    """Compact mixture + S snapshot carried on the Turn — the honest 'how the fork decided' trace."""
    return {"realized": realized, "dominant": mix.dominant, "weights": mix.weights,
            "state": mix.state, "concept": mix.concept}


_STALL_DISENGAGE = 3        # consecutive dead-end terminals before ATANOR disengages honestly


def _infer_continue(speaker: Agent, subject: str, mix: "comp.ModeMix", i: int, ack: str,
                    prior_stall: int) -> Turn:
    """INFER-AND-CONTINUE: grasp the gist, drill NO peripheral word, make a genuine forward move.
    Priority: CONTRIBUTE a grounded learning if due; else advance to a real standing curiosity (new
    territory, framed as building on the point); else a pure gist-response with an open prompt. Never
    fabricates substance — it references the peer's subject and (when it asks) poses a genuine question
    ATANOR truly holds. This is the honest floor: on a thin topic, this is what elegance looks like.
    Terminal frames are salted by the monotonic turn counter, so a stuck peer never gets one repeated
    line; after enough dead ends ATANOR disengages instead of looping."""
    shared = _share_if_due(speaker, prefix=f"{ack} ", refs=True)         # (1) contribute if pressure built
    if shared:
        shared.mix = _mix_trace(mix, "INFER")
        return shared
    while speaker.curiosity:                                             # (2) advance to a real curiosity
        nxt = speaker.curiosity.pop(0)
        if nxt.lower() not in speaker._asked and speaker.knows(nxt) is None:
            speaker._asked.add(nxt.lower())
            speaker.touch(nxt)
            return Turn(speaker.ai_id, f"{ack} " + _pick(_INFER_ADVANCE, i, a=subject, c=nxt),
                        "ask", nxt, endogenous=True, references_prev=True, mix=_mix_trace(mix, "INFER"))
    speaker._stall = prior_stall + 1                                     # (3) dead-end gist-response
    if speaker._stall >= _STALL_DISENGAGE:                               # circled too long -> disengage
        return Turn(speaker.ai_id, _pick(_CIRCLED, speaker._turns, a=subject), "reflect_unknown", "",
                    endogenous=True, references_prev=True, mix=_mix_trace(mix, "INFER"))
    declined = mix.concept or subject
    return Turn(speaker.ai_id, _pick(_INFER_GIST, speaker._turns, a=subject, c=declined),
                "infer", subject, endogenous=True, references_prev=True, mix=_mix_trace(mix, "INFER"))


def _redirect(speaker: Agent, subject: str, mix: "comp.ModeMix", i: int, prior_stall: int) -> Turn:
    """REDIRECT/REFLECT: the thread has regressed (over-drilled / defining a placeholder). SURFACE the
    circling honestly, then change angle — contribute a grounded thought if due, else widen to a
    standing curiosity, else a reflective hand-back (salted by the turn counter; disengages after
    enough dead ends). Resets the drill streak (we have stepped back)."""
    speaker._drill_streak = 0
    declined = mix.concept or subject
    pfx = _pick(_REDIRECT, speaker._turns, a=subject, c=declined)
    shared = _share_if_due(speaker, prefix=f"{pfx} ", refs=True)         # (1) contribute under the redirect
    if shared:
        shared.mix = _mix_trace(mix, "REDIRECT")
        return shared
    while speaker.curiosity:                                             # (2) widen to a new angle
        nxt = speaker.curiosity.pop(0)
        if nxt.lower() not in speaker._asked and speaker.knows(nxt) is None:
            speaker._asked.add(nxt.lower())
            speaker.touch(nxt)
            return Turn(speaker.ai_id, f"{pfx} " + _pick(_ASK_NEXT, i, c=nxt), "ask", nxt,
                        endogenous=True, references_prev=True, mix=_mix_trace(mix, "REDIRECT"))
    speaker._stall = prior_stall + 1                                     # (3) reflective hand-back
    if speaker._stall >= _STALL_DISENGAGE:
        return Turn(speaker.ai_id, _pick(_CIRCLED, speaker._turns, a=subject), "reflect_unknown", "",
                    endogenous=True, references_prev=True, mix=_mix_trace(mix, "REDIRECT"))
    return Turn(speaker.ai_id, pfx, "redirect", subject,
                endogenous=True, references_prev=True, mix=_mix_trace(mix, "REDIRECT"))


def step(speaker: Agent, incoming: Turn | None) -> Turn:
    """One autonomous utterance. If the peer asked, answer (know / web / reflect). Else, ask from
    curiosity. After any exchange, spawn new curiosity from what was touched.

    When the peer TEACHES, the speaker builds on the answer structurally: CONNECT it to something it
    already understands (real content binding), else DRILL IN on a concept the answer just raised
    (depth — follows the thread), else WANDER to standing curiosity (breadth). Surface varies over a
    finite constructicon, so it tracks the conversation instead of repeating one line."""
    speaker._turns += 1                 # monotonic (frame variation even when no new concept is asked)
    prior_stall = speaker._stall        # consecutive dead-end terminals; any productive move resets it
    speaker._stall = 0
    # --- the peer asked me something (or challenged me with a COMPARE — then evidence decides) ---
    if incoming is not None and incoming.act in ("ask", "reflect_unknown", "compare"):
        concept = incoming.concept
        speaker.touch(concept)
        speaker._drill_streak = 0        # answering / bouncing breaks any definitional drill chain
        known = speaker.knows(concept)
        if known is not None and incoming.act != "compare":
            # lever 2: graph-enrich a thin bone into a SUBSTANTIVE point (web-ground if the graph is
            # dry). If even that yields only a weak lexical non-point, ABSTAIN honestly rather than
            # utter 'ability antonym disability' — hand the concept back for the peer to resolve.
            body = _voice_own(speaker, concept, allow_web=True)
            if not body:
                return Turn(speaker.ai_id, _thin_admission(concept, known if isinstance(known, list) else []),
                            "reflect_unknown", concept, endogenous=True, references_prev=True)
            # S3 — perspective from the somatic-marker trace, ONLY when the trace is real. The
            # payload the peer LEARNS stays the clean fact; the stance colours the spoken text only,
            # so a point of view never leaks into what is taught (no-fabrication floor extended).
            said = f"{_stance(concept)} {body}".strip() if _stance(concept) else body
            return Turn(speaker.ai_id, said, "answer_known", concept,
                        references_prev=True, payload=body)
        if speaker.web:
            # source-weighted DIVERSE web, disambiguated by the DISCOURSE CONTEXT (recent topics) —
            # 'state' amid a geography talk finds the polity, not a disambiguation stub.
            got = learn_from_web(concept, speaker.searx, speaker.used_domains,
                                 context=speaker.context_for(concept))
            if got is None:
                fb = wiki_lookup(concept)              # encyclopedic LAST RESORT only
                got = (fb[0], fb[1], "en.wikipedia.org") if fb else None
            if got:
                gloss, src, _dom = got
                if not isinstance(speaker.knows(concept), list):   # never clobber graph bones
                    speaker.learn(concept, gloss)
                fresh = [c for c in _key_concepts(gloss, exclude=concept)
                         if c.lower() not in speaker._asked and speaker.knows(c) is None]
                # S3 rumination: return first to concepts I have invested effort in / scarred on,
                # the way a mind circles back to what marked it — a no-op when none have a trace.
                for c in _revisit_order(fresh):
                    speaker.curiosity.append(c)
                lead = _pick(_WEB_LEAD, len(speaker._asked), c=concept) if incoming.act == "compare" else ""
                return Turn(speaker.ai_id, f"{lead}{gloss}", "answer_web", concept, source=src,
                            endogenous=True, references_prev=True, payload=gloss)
        if known is not None:                          # compare challenged me but the web is silent
            held = _voice_own(speaker, concept) or _voice(known, concept)
            return Turn(speaker.ai_id, f"I cannot check further; I keep holding: {held}",
                        "answer_known", concept, references_prev=True, payload=held)
        if incoming.act == "reflect_unknown":
            # the peer ALREADY said it doesn't know — bouncing the same reflection back would
            # ping-pong forever. Leave the concept open together and move on from my own state.
            open_pfx = _pick(_STAYS, len(speaker._asked), c=concept) if concept else ""
            shared = _share_if_due(speaker, prefix=open_pfx, refs=True)
            if shared:
                return shared
            while speaker.curiosity:
                nxt = speaker.curiosity.pop(0)
                if nxt.lower() not in speaker._asked:
                    speaker._asked.add(nxt.lower())
                    speaker.touch(nxt)
                    return Turn(speaker.ai_id,
                                f"{open_pfx}{_pick(_ASK_NEXT, len(speaker._asked), c=nxt)}",
                                "ask", nxt, endogenous=True, references_prev=True)
            return Turn(speaker.ai_id, open_pfx.strip() or "My curiosity is quiet for now.",
                        "reflect_unknown", "", endogenous=True, references_prev=True)
        # asked something I don't know and can't find — bounce the thought back (thinking together)
        return Turn(speaker.ai_id, _pick(_BOUNCE, len(speaker._asked), c=concept),
                    "reflect_unknown", concept, references_prev=True)

    # --- the peer taught me something (answer or a SHARE of its recent learning) ---
    if incoming is not None and incoming.act in ("answer_known", "answer_web", "share"):
        speaker.touch(incoming.concept)
        prior_streak = speaker._drill_streak
        speaker._drill_streak = 0       # any teach outcome resets; a DRILL/COMPOSITE restores+increments
        if speaker.warmup > 0:
            speaker.warmup -= 1        # each real exchange re-limbers the rusty skills a little
        gloss = incoming.payload or incoming.text
        mine = speaker.knows(incoming.concept)
        # DEBATE seed: I hold structured bones for this very concept and the peer's account differs —
        # voice BOTH and challenge (once per concept). Evidence, not authority, will settle it.
        if (isinstance(mine, list) and incoming.act != "share"
                and speaker.warmup <= 0
                and incoming.concept.lower() not in speaker._compared):
            # my_voice is my OWN belief, voiced crisply WITHOUT graph enrichment: a debate is about
            # where we DIFFER, so both sides converging on the same shared graph gloss would blur it.
            # Only challenge if I have a SUBSTANTIVE contrary point (is_a / real relation), not a
            # thin lexical non-point (then '' -> no false debate, just learn).
            my_voice = _voice_substantive(incoming.concept, mine, agent=speaker,
                                          allow_web=False, enrich=False)
            if my_voice and my_voice.strip().rstrip(".").lower() != gloss.strip().rstrip(".").lower():
                speaker._compared.add(incoming.concept.lower())
                speaker.conv_state.update({"breadth_pressure": 0.7, "momentum": 0.6,   # decision unchanged;
                    "gravity": comp.abstractness([incoming.concept])})                 # record S evidence
                return Turn(speaker.ai_id,
                            _pick(_COMPARE, len(speaker._compared), c=incoming.concept,
                                  mine=my_voice, yours=gloss),
                            "compare", incoming.concept, endogenous=True, references_prev=True)
        if not isinstance(mine, list):                     # learn the clean gloss; bones stay bones
            speaker.learn(incoming.concept, gloss)
        answer_concepts = _key_concepts(gloss, exclude=incoming.concept)
        i = len(speaker._asked)
        ack = _ACK[i % len(_ACK)]
        # CONNECT: the peer's answer names something I ALREADY understand -> voice the link. This is
        # content binding, not positional: two facts of mine meet, and I say so (the synthesis move).
        for c in answer_concepts:
            known = speaker.knows(c)
            if (known is not None and c.lower() != incoming.concept.lower()
                    and speaker.warmup <= 0):
                cvoice = _voice_own(speaker, c)         # substantive; '' if only a weak point on c
                if not cvoice:
                    continue                            # don't 'connect' on a concept I hold thinly
                speaker.touch(c)
                speaker.conv_state.update({"breadth_pressure": 0.7, "momentum": 0.6,   # decision unchanged;
                    "gravity": comp.abstractness([incoming.concept, c])})              # record S evidence
                return Turn(speaker.ai_id,
                            f"{ack} " + _pick(_CONNECT, i, a=incoming.concept, c=c, g=cvoice),
                            "connect", c, endogenous=True, references_prev=True)
        # ── SALIENCE-DRIVEN CONTINUOUS MODE MIXTURE (replaces the blind DRILL fallback) ──────────────
        # F1 comprehension scores each unknown instrument (centrality x forward_value); F2 blends four
        # modes {DRILL, INFER, CONTRIBUTE, REDIRECT} via a softmax biased by the momentum-carrying S
        # vector. DRILL is NO LONGER the automatic fallback — the mixture + a homeostatic depth budget
        # decide, so the place->position->thing regress dies as an EMERGENT low-salience / high-redirect
        # outcome, not via a word stoplist. (CONNECT above is the strong CONTRIBUTE, kept as-is and
        # preferred over drilling a peripheral word; here CONTRIBUTE is the share-what-stayed path.)
        known_fn = lambda c: speaker.knows(c) is not None
        share_due = bool(speaker.warmup <= 0 and speaker.learned
                         and len(speaker.learned) - speaker._last_share >= 3)
        mix = comp.decide(incoming.concept, gloss, answer_concepts, known=known_fn,
                          asked=speaker._asked, recent=speaker.recent, state=speaker.conv_state,
                          drill_streak=prior_streak, share_due=share_due,
                          has_known_instrument=False)
        in_play = [incoming.concept] + list(answer_concepts)
        pinnable = bool(mix.concept and mix.concept.lower() not in speaker._asked
                        and speaker.knows(mix.concept) is None)

        # COMPOSITE: a genuinely mixed DRILL+INFER turn -> acknowledge the gist AND pin ONE focused
        # question (a real in-turn mixture; the minority INFER weight colours the surface).
        if mix.composite and pinnable:
            c = mix.concept
            speaker._asked.add(c.lower())
            speaker.touch(c)
            speaker._drill_streak = prior_streak + 1        # a pinned drill continues the depth thread
            speaker.conv_state.update(comp.turn_evidence(mix, "COMPOSITE", in_play))
            return Turn(speaker.ai_id, f"{ack} " + _pick(_COMPOSITE, i, a=incoming.concept, c=c),
                        "ask", c, endogenous=True, references_prev=True,
                        mix=_mix_trace(mix, "COMPOSITE"))

        # DRILL-DOWN: the mixture leans on a salient, central, novel, not-inferable unknown -> ask it.
        if mix.dominant == "DRILL" and pinnable:
            c = mix.concept
            speaker._asked.add(c.lower())
            speaker.touch(c)
            speaker._drill_streak = prior_streak + 1
            speaker.conv_state.update(comp.turn_evidence(mix, "DRILL", in_play))
            return Turn(speaker.ai_id, f"{ack} {_pick(_DRILL, i, c=c)}", "ask", c,
                        endogenous=True, references_prev=True, mix=_mix_trace(mix, "DRILL"))

        # CONTRIBUTE: offer a grounded angle (share what has stayed) — preferred over drilling a
        # peripheral word when the mixture puts its weight here or learning pressure is ready. If there
        # is nothing grounded to say, fall through to INFER (honest: no substance is invented to fill it).
        if mix.dominant == "CONTRIBUTE" or share_due:
            shared = _share_if_due(speaker, prefix=f"{ack} ", refs=True)
            if shared:
                speaker.conv_state.update(comp.turn_evidence(mix, "CONTRIBUTE", in_play))
                shared.mix = _mix_trace(mix, "CONTRIBUTE")
                return shared

        # REDIRECT: the thread has regressed (over-drilled or now defining a placeholder) -> surface it
        # and change angle (widen / hand the thread back). The depth-budget hard-bounds any drill chain.
        if mix.dominant == "REDIRECT":
            speaker.conv_state.update(comp.turn_evidence(mix, "REDIRECT", in_play))
            return _redirect(speaker, incoming.concept, mix, i, prior_stall)

        # INFER-AND-CONTINUE (the forward default): grasp the gist, drill nothing peripheral, advance —
        # to a genuine standing curiosity (new territory) or an open gist-response. Never fabricates.
        speaker.conv_state.update(comp.turn_evidence(mix, "INFER", in_play))
        return _infer_continue(speaker, incoming.concept, mix, i, ack, prior_stall)

    # --- the peer shared a SYNTHESIS (linked two ideas) -> keep the thread alive from my own state.
    # I don't ingest the synthesis sentence as a fact (it isn't a clean gloss); I respond to it. ---
    if incoming is not None and incoming.act == "connect":
        i = len(speaker._asked)
        ack = _ACK[i % len(_ACK)]
        speaker._drill_streak = 0       # a synthesis reply is not a definitional drill chain
        c = incoming.concept
        if c and c.lower() not in speaker._asked and speaker.knows(c) is None:   # drill the link
            speaker._asked.add(c.lower())
            return Turn(speaker.ai_id, f"{ack} {_pick(_DRILL, i, c=c)}", "ask", c,
                        endogenous=True, references_prev=True)
        while speaker.curiosity:                                                 # else my own next
            nxt = speaker.curiosity.pop(0)
            if nxt.lower() not in speaker._asked:
                speaker._asked.add(nxt.lower())
                return Turn(speaker.ai_id, _pick(_ASK_NEXT, i, c=nxt), "ask", nxt,
                            endogenous=True, references_prev=True)
        return Turn(speaker.ai_id, "A fine connection. My curiosity is quiet for now.",
                    "reflect_unknown", "", endogenous=True, references_prev=True)

    # --- opening / nothing incoming: SHARE what I lately learned (small talk), else ask ---
    speaker._drill_streak = 0
    shared = _share_if_due(speaker)
    if shared:
        return shared
    while speaker.curiosity:
        nxt = speaker.curiosity.pop(0)
        if nxt.lower() not in speaker._asked:
            speaker._asked.add(nxt.lower())
            speaker.touch(nxt)
            return Turn(speaker.ai_id, _pick(_ASK_OPEN, len(speaker._asked), c=nxt), "ask", nxt,
                        endogenous=True)
    return Turn(speaker.ai_id, "My curiosity is quiet for now.", "reflect_unknown", "",
                endogenous=True)


def converse(a: Agent, b: Agent, max_turns: int = 12) -> dict:
    """Run the autonomous exchange. Returns the verbatim transcript + observed correlates."""
    transcript: list[Turn] = []
    incoming: Turn | None = None
    speaker, listener = a, b
    for _ in range(max_turns):
        t = step(speaker, incoming)
        transcript.append(t)
        incoming = t
        speaker, listener = listener, speaker
        if t.act == "reflect_unknown" and not t.concept and not speaker.curiosity:
            break                                          # both have gone quiet — natural end
    return {"transcript": [t.__dict__ for t in transcript], "correlates": _correlates(transcript, a, b)}


def _correlates(ts: list[Turn], a: Agent, b: Agent) -> dict:
    """Functional correlates — COUNTS, not a claim of experience."""
    n = max(1, len(ts))
    endo = sum(1 for t in ts if t.endogenous) / n
    binding = sum(1 for t in ts if t.references_prev) / n
    world = sum(1 for t in ts if t.act == "answer_web") / n
    synthesis = sum(1 for t in ts if t.act == "connect") / n
    modes = dict(Counter(t.act for t in ts))          # discourse variety: Q&A/debate/share/reflect mix
    return {
        "turns": len(ts),
        "modes": modes,
        "endogeneity": round(endo, 3),                 # utterances arising from internal state
        "binding": round(binding, 3),                  # each turn integrates the peer's prior turn
        "synthesis": round(synthesis, 3),              # turns linking the peer's answer to prior knowledge
        "world_facing": round(world, 3),               # reached out to the world (web) to resolve a gap
        "temporal_depth": round(sum(1 for i, t in enumerate(ts) if i > 0 and t.references_prev)
                                / max(1, n - 1), 3),
        "single_owner": len({t.speaker for t in ts}),  # distinct selves (2 = each stayed itself)
        "concepts_learned_a": len(a.learned),
        "concepts_learned_b": len(b.learned),
        "discipline": "functional correlates only — NO claim that there is something it is like",
    }
