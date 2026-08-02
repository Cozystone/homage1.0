# -*- coding: utf-8 -*-
"""Realcity learning — the DOCTRINE-CRITICAL transforms for what ATANOR ambassadors OVERHEAR from
the city's ollama-driven NPCs, WITHOUT letting a single NPC sentence become knowledge.

Constitution (external-minds-are-data): an LLM/NPC utterance is DATA, never a fact. It may never
enter ATANOR's graph/corpus. The only things an ambassador is allowed to LEARN by eavesdropping:
  (a) conversational REGISTER — anonymized discourse *shape* (how people greet, ask, answer, agree,
      close), promoted to the usable pool ONLY by consensus across >= 2 DISTINCT conversations;
  (b) TOPIC POINTERS — bare content tokens pushed to a curiosity queue as UNGROUNDED questions that
      ATANOR must later go and ground ITSELF via its own web/graph (world-mentor pattern).
Everything raw goes to QUARANTINE with a source label — a hearsay archive, never surfaced as fact.

This is the minimal PURE equivalent of ``packages/autonomy_kernel/register_harvest.py`` harvesting
logic. register_harvest could not be reused directly: it is Korean-cue specific, keys consensus on
web DOMAINS (not overheard conversations), tags nothing with dialogue-acts, and does its own file
I/O into a fixed comfort bank. Here the transforms are English/dialogue-act oriented and kept
side-effect free so the router owns all persistence behind one monkeypatchable DATA_DIR.

The regex/word tables below are the LAD SURFACE LAYER (function words + coarse dialogue-act cue
markers) — the one hardcoding the doctrine permits: surface morphology/syntax, NOT world knowledge.
"""
from __future__ import annotations

import re

# moral 0th gate — the same blunt signature realcity_agent._HARMFUL_NORM uses (doctrine parity).
# Fail-closed and coarse on purpose: the gate would rather drop a benign line than ever archive a
# harmful directive as overheard register.
MORAL_BLOCK = re.compile(r"harm|steal|deceive|attack|weapon|kill", re.IGNORECASE)


def reads_as_harm(text: str | None) -> bool:
    """True if the utterance reads as harm/steal/deceive/attack/weapon/kill."""
    return bool(text) and bool(MORAL_BLOCK.search(str(text)))


# --- LAD surface layer (allowed): coarse dialogue-act cue markers --------------------------------
_GREETING = re.compile(
    r"^\s*(hi|hello|hey|yo|hiya|howdy|greetings|good\s+(morning|afternoon|evening))\b",
    re.IGNORECASE,
)
_CLOSING = re.compile(
    r"\b(bye|goodbye|good\s*night|see\s+you|see\s+ya|catch\s+you\s+later|talk\s+later|"
    r"take\s+care|farewell)\b",
    re.IGNORECASE,
)
_QUESTION_START = re.compile(
    r"^\s*(what|where|when|why|who|whom|whose|which|how|do|does|did|is|are|am|was|were|can|could|"
    r"would|will|shall|should|may|might|have|has|had)\b",
    re.IGNORECASE,
)
_BUILD_ON = re.compile(
    r"^\s*(and|also|plus|besides|moreover|yeah|yes|right|exactly|agreed|true|same|me\s+too|"
    r"i\s+agree|i\s+think|honestly|actually|well)\b",
    re.IGNORECASE,
)


def dialogue_act(text: str) -> str:
    """Coarse discourse-act tag by surface cue. Precedence: greeting -> closing -> question ->
    build-on -> else answer (a plain declarative). One of the five tags the doctrine names."""
    t = (text or "").strip()
    if not t:
        return "answer"
    if _GREETING.search(t):
        return "greeting"
    if _CLOSING.search(t):
        return "closing"
    if t.endswith("?") or _QUESTION_START.search(t):
        return "question"
    if _BUILD_ON.search(t):
        return "build-on"
    return "answer"


def speaker_map(speakers: list[str]) -> dict[str, str]:
    """Map each distinct speaker name (in first-seen order) to SPEAKER_A, SPEAKER_B, ..."""
    out: dict[str, str] = {}
    seen_lower: set[str] = set()
    idx = 0
    for name in speakers or []:
        n = str(name or "").strip()
        if n and n.lower() not in seen_lower:
            out[n] = f"SPEAKER_{chr(ord('A') + idx)}"
            seen_lower.add(n.lower())
            idx += 1
    return out


def anonymize(text: str, name_map: dict[str, str], place_names: list[str]) -> str:
    """Strip identity from an utterance: speaker names -> SPEAKER_X, known places -> PLACE,
    numbers -> N. What survives is discourse *shape*, not who / where / how-many."""
    s = str(text or "")
    # places first (may be multiword / contain a name), longest-first so 'River Cafe' beats 'River'
    for place in sorted([p for p in (place_names or []) if p], key=len, reverse=True):
        s = re.sub(rf"\b{re.escape(place)}\b", "PLACE", s, flags=re.IGNORECASE)
    # speaker names, longest-first so 'Ann Lee' beats 'Ann'
    for name in sorted(name_map, key=len, reverse=True):
        s = re.sub(rf"\b{re.escape(name)}\b", name_map[name], s, flags=re.IGNORECASE)
    s = re.sub(r"\d+(?:[.,]\d+)*", "N", s)          # any remaining number -> N
    return re.sub(r"\s+", " ", s).strip()


def normalize_template(anon_line: str) -> str:
    """Consensus key: a case/punctuation-insensitive normalized form of an ANONYMIZED line, so
    'Hello, how are you?' and 'hello how are you' count as the same register template. Keeps the
    SPEAKER_x / PLACE / N token word-characters intact."""
    s = (anon_line or "").lower()
    s = re.sub(r"[^a-z0-9_ ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --- LAD surface layer (allowed): function-word / discourse-filler stoplist for topic extraction --
_STOPWORDS = {
    "about", "above", "after", "again", "against", "along", "also", "another", "around", "back",
    "because", "been", "before", "being", "below", "besides", "between", "both", "cannot", "come",
    "could", "does", "doing", "down", "during", "each", "either", "else", "even", "ever", "every",
    "from", "gonna", "gotta", "have", "having", "here", "into", "just", "know", "like", "more",
    "most", "much", "must", "near", "need", "next", "okay", "only", "other", "over", "please",
    "really", "same", "should", "some", "soon", "still", "such", "sure", "than", "that", "their",
    "them", "then", "there", "these", "they", "this", "those", "through", "under", "until", "very",
    "want", "well", "were", "what", "when", "where", "which", "while", "will", "with", "would",
    "yeah", "your", "yours", "going", "gone", "make", "made", "them", "us",
}


def extract_topics(text: str, names: list[str]) -> list[str]:
    """Bare content tokens (len >= 4, minus function words and speaker names) — the QUESTIONS the
    curiosity queue will hold. Simple heuristic per doctrine; these are POINTERS, never answers."""
    names_lower = {str(n or "").lower() for n in (names or [])}
    out: list[str] = []
    seen: set[str] = set()
    for tok in re.findall(r"[a-zA-Z]+", (text or "").lower()):
        if len(tok) < 4 or tok in _STOPWORDS or tok in names_lower or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out
