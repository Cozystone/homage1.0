"""Scene-grounding extractor (M4).

The ATANOR philosophy: SPLATRA visualizes a particle scene **only when the verified
evidence is concrete** — a placeable object that actually moves or is positioned in
space (e.g. "an apple fell from the tree toward Newton"). Abstract definitions
("gravity is the attraction between masses") are explained in words only; the
particle field stays ambient.

That decision is a *language/reasoning* responsibility, not a particle one, so it
lives here. This module is a **deterministic, inspectable** analyzer over the
verified-evidence sentences — it classifies, it never generates an answer, so it
does not violate the no-rule-based-answer constraint. It is conservative: when in
doubt it returns ``eligible=False`` (text-only).

Output contract (consumed by SPLATRA — see docs/SPLATRA_PARTICLE_CONTRACT.md):

    {
        "eligible": bool,     # True only for concrete entity + physical motion
        "basis": str,         # short reason
        "entities": [str],    # concrete objects found in evidence
        "spatial": [str],     # spatial relations linking entities
        "motion": [str],      # motion / path cues
    }
"""

from __future__ import annotations

import re
from typing import Any, Iterable


# Physical motion verbs (base + common inflections). Eligibility REQUIRES one of
# these — a real movement — so abstract method verbs ("retrieves", "uses",
# "requires") and copular definitions never open a scene.
MOTION_VERBS = {
    "fall", "fell", "falls", "falling",
    "drop", "dropped", "drops", "dropping",
    "move", "moved", "moves", "moving",
    "rise", "rose", "rises", "rising",
    "rotate", "rotated", "rotates", "rotating",
    "spin", "spun", "spins", "spinning",
    "orbit", "orbited", "orbits", "orbiting",
    "flow", "flowed", "flows", "flowing",
    "collide", "collided", "collides", "colliding",
    "push", "pushed", "pushes", "pushing",
    "pull", "pulled", "pulls", "pulling",
    "throw", "threw", "thrown", "throws", "throwing",
    "travel", "traveled", "travels", "traveling",
    "slide", "slid", "slides", "sliding",
    "roll", "rolled", "rolls", "rolling",
    "bounce", "bounced", "bounces", "bouncing",
    "swing", "swung", "swings", "swinging",
    "accelerate", "accelerated", "accelerates",
    "descend", "descended", "descends",
    "ascend", "ascended", "ascends",
    "launch", "launched", "launches",
    "crash", "crashed", "crashes",
    "spread", "spreads", "spreading",
    "float", "floated", "floats", "floating",
}

# Prepositions that describe a path/direction (recorded for SPLATRA; with a motion
# verb they help describe the trajectory). They do NOT grant eligibility on their own.
PATH_PREPS = {"toward", "towards", "into", "onto", "from", "across", "through", "down", "up", "past"}

# Static spatial relations (recorded; do not grant eligibility on their own in v0).
SPATIAL_PREPS = {"on", "in", "above", "below", "under", "beneath", "over", "beside", "between", "near", "inside", "atop", "upon"}

# Words that never count as a concrete entity.
_NON_ENTITY = {
    "the", "a", "an", "and", "or", "but", "of", "to", "it", "its", "this", "that",
    "these", "those", "is", "are", "was", "were", "be", "been", "being", "by", "for",
    "with", "as", "at", "so", "if", "then", "than", "which", "who", "what", "when",
    "where", "while", "into", "onto", "from", "toward", "towards", "through", "across",
    "on", "in", "above", "below", "under", "over", "between", "near", "inside",
}
_NON_ENTITY |= MOTION_VERBS

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_PROPER = re.compile(r"\b([A-Z][a-z]{2,})\b")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
_ARTICLES = {"the", "a", "an"}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(str(text or "")) if s.strip()]


def _is_definition(sentence_lower: str) -> bool:
    """Copular definitions ('X is a kind of Y', 'gravity is the attraction between …')."""
    if re.search(r"\b(is|are|was|were)\s+(a|an|the)\b", sentence_lower):
        return True
    if re.search(r"\b(is|are)\s+\w+\s+(of|between)\b", sentence_lower):
        return True
    return False


def _content_word(tokens: list[str], index: int, step: int) -> str | None:
    """Walk from index in direction step, skipping articles, return first content word."""
    i = index + step
    while 0 <= i < len(tokens):
        tok = tokens[i]
        if tok in _ARTICLES:
            i += step
            continue
        if tok in _NON_ENTITY or len(tok) < 3:
            return None
        return tok
    return None


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def extract_scene_grounding(
    answer: str,
    evidence_sentences: list[str] | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Classify verified evidence as abstract (text-only) vs concrete (scene-eligible)."""
    if language != "en":
        # Korean (and others) reuse this pipeline later with locale morphology.
        return {
            "eligible": False,
            "basis": "non_english_extractor_pending",
            "entities": [],
            "spatial": [],
            "motion": [],
        }

    sources = [str(answer or "")] + [str(s or "") for s in (evidence_sentences or [])]
    entities: list[str] = []
    spatial: list[str] = []
    motion: list[str] = []

    for source in sources:
        for sentence in _sentences(source):
            lowered = sentence.lower()
            tokens = _WORD.findall(lowered)
            definitional = _is_definition(lowered)

            # Proper nouns (e.g. Newton) are concrete entities, but skip a leading
            # capitalized word that is only sentence-initial.
            for match in _PROPER.finditer(sentence):
                proper = match.group(1)
                if match.start() == 0:
                    continue
                if proper.lower() not in _NON_ENTITY:
                    entities.append(proper)

            for index, tok in enumerate(tokens):
                if tok in MOTION_VERBS:
                    motion.append(tok)
                    subject = _content_word(tokens, index, -1)
                    if subject:
                        entities.append(subject)
                    obj = _content_word(tokens, index, +1)
                    if obj:
                        entities.append(obj)
                elif tok in PATH_PREPS:
                    motion.append(tok)
                    obj = _content_word(tokens, index, +1)
                    if obj:
                        entities.append(obj)
                elif tok in SPATIAL_PREPS:
                    # 'between masses' inside a definition is conceptual, not a scene.
                    if not definitional:
                        spatial.append(tok)
                        obj = _content_word(tokens, index, +1)
                        if obj:
                            entities.append(obj)

    entities = _dedupe_keep_order(entities)
    spatial = _dedupe_keep_order(spatial)
    motion = _dedupe_keep_order(motion)

    has_motion_verb = any(token in MOTION_VERBS for token in motion)
    eligible = bool(entities) and has_motion_verb

    if eligible:
        basis = "concrete_entity_with_motion"
    elif entities and (spatial or motion):
        basis = "entities_without_physical_motion_text_only"
    else:
        basis = "abstract_definition_no_entity_or_motion"

    return {
        "eligible": eligible,
        "basis": basis,
        "entities": entities[:12],
        "spatial": spatial[:8],
        "motion": motion[:8],
    }
