from __future__ import annotations


def style_profile(language: str, audience_level: str = "beginner", tone: str = "clear") -> dict:
    return {
        "language": language,
        "audience_level": audience_level,
        "tone": tone,
        "register": "polite technical" if language == "ko" else "clear technical",
        "sentence_rhythm": "medium",
        "trace_visible_by_default": False,
        "avoid_internal_path_dump": True,
        "explanation_depth": "beginner-friendly" if audience_level in {"beginner", "general"} else "expert-compact",
    }
