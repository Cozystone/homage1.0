from __future__ import annotations

from .models import ConstructionCandidate, Language


def construction_candidates(intent: str, language: Language, audience_level: str = "beginner") -> list[dict]:
    lang = language if language in {"ko", "en"} else "ko"
    beginner = audience_level in {"beginner", "general"}
    base = [
        ConstructionCandidate("definition.simple", lang, "simple definition", "X is explained as Y", "direct_definition", ["topic", "definition"], fit_score=0.86, style_score=0.72, language_score=0.88),
        ConstructionCandidate("analogy.beginner", lang, "beginner analogy", "X is close to Y", "analogy", ["topic", "analogy"], fit_score=0.8 if beginner else 0.55, style_score=0.9 if beginner else 0.58, language_score=0.82),
        ConstructionCandidate("contrast.light", lang, "contrast frame", "X is not only A; it also B", "contrast", ["topic", "contrast"], fit_score=0.66, style_score=0.68, language_score=0.78),
        ConstructionCandidate("example.short", lang, "short example", "For example, ...", "example", ["example"], fit_score=0.72, style_score=0.74, language_score=0.8),
        ConstructionCandidate("caveat.soft", lang, "soft caveat", "One caveat is ...", "caveat", ["caveat"], fit_score=0.54, style_score=0.64, language_score=0.76),
        ConstructionCandidate("summary.compact", lang, "compact summary", "In short, ...", "summary", ["summary"], fit_score=0.7, style_score=0.7, language_score=0.82),
    ]
    if intent in {"compare", "critique"}:
        base[2].fit_score += 0.2
    if intent in {"define", "explain"}:
        base[0].fit_score += 0.1
        base[1].fit_score += 0.08
    return [candidate.to_dict() for candidate in base]
