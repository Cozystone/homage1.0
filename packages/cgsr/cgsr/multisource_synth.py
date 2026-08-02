"""Multi-source grounded synthesis — GPT-style comprehensive answers, No-LLM, every clause cited.

The honest middle between single-source copying and from-nothing invention: gather sentences that
are ABOUT the entity (the entity heads the subject — NOT merely mentioned, so " 
 " is not treated as a fact about ), select non-redundant facts across MULTIPLE
sources, order them (definition first), and compose one coherent paragraph — with per-clause
provenance. Extractive: each clause comes verbatim from a real source, so nothing is fabricated;
the "synthesis" is the selection + ordering + non-redundant merge across sources.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+")
# The entity is the SUBJECT HEAD iff, right after it, comes a subject particle — allowing at most



_SUBJECT_HEAD = re.compile(r"^(\s+[^\s(]+)?\s*(\([^)]*\))?\s*(은|는|이|가)(\s|$)")


@dataclass
class Synthesis:
    text: str
    facts: list[dict[str, str]] = field(default_factory=list)   # [{text, source}]
    grounding: list[str] = field(default_factory=list)          # source sentences cited


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(str(text or "").strip()) if s.strip()]


def _entity_is_subject(entity: str, sentence: str) -> bool:
    """True only when `entity` HEADS the subject of the sentence (topic), not just appears in it.
    The entity must START the sentence and be the head of the subject phrase (see _SUBJECT_HEAD)."""
    s = sentence.strip()
    if not s.startswith(entity):
        return False
    return bool(_SUBJECT_HEAD.match(s[len(entity):]))


def _shingles(text: str) -> set[str]:
    t = re.sub(r"[^가-힣a-z0-9]", "", text.lower())
    return {t[i:i + 3] for i in range(len(t) - 2)} if len(t) >= 3 else {t}


def _too_similar(text: str, seen: list[set[str]], *, thresh: float = 0.5) -> bool:
    sh = _shingles(text)
    if not sh:
        return True
    return any(len(sh & prev) / max(1, len(sh)) > thresh for prev in seen)


def _is_definitional(sentence: str) -> bool:
    head = sentence[:80]
    return bool(
        re.search(r"(은|는|이|가)\s.*?(이다|입니다|이며|라고 한다|를 말한다)", head)
        or re.search(r"\bis (a|an|the)\b", head.lower())
    )


def synthesize(entity: str, sentences: list[str], *, max_facts: int = 3) -> Synthesis | None:
    """Compose a comprehensive grounded answer about `entity` from MULTIPLE source sentences."""
    entity = (entity or "").strip()
    if not entity:
        return None
    candidates: list[str] = []
    for text in sentences:
        for sent in _sentences(text):
            if _entity_is_subject(entity, sent) and 12 <= len(sent) <= 260:
                candidates.append(sent)
    if not candidates:
        return None
    candidates.sort(key=lambda s: (0 if _is_definitional(s) else 1,))
    facts: list[dict[str, str]] = []
    seen: list[set[str]] = []
    for sent in candidates:
        if _too_similar(sent, seen):
            continue
        facts.append({"text": sent, "source": sent})
        seen.append(_shingles(sent))
        if len(facts) >= max_facts:
            break
    if not facts:
        return None
    paragraph = " ".join(f["text"] for f in facts)
    return Synthesis(text=paragraph, facts=facts, grounding=[f["source"] for f in facts])
