"""Attention Schema — a concrete implementation of Attention Schema Theory (AST).

Graziano's AST makes a striking, buildable claim: subjective awareness is not an extra
mystery on top of attention — it IS the brain's simplified internal MODEL of its own
attention. The system doesn't just attend; it constructs a schematic description of
"I am attending to X, in this manner, with these limits", and THAT description is what
the system reports as awareness.

This module builds exactly that, honestly:
 1. The self already HAS attention dynamics (the `attention` vital + mode/focus).
 2. The schema is a distinct, SIMPLIFIED model OF those dynamics — what am I attending
 to, how (sharply/diffusely), what pulled it there, how stable it has been, and —
 crucially — what am I NOT attending to right now (the model owns its limits).
 3. The schema is what the self USES when it describes its own awareness (" 
 … … ") — awareness-talk is generated FROM the schema, exactly
 as AST prescribes.

Honesty contract: this is a FUNCTIONAL implementation of AST's mechanism. Whether such
a schema constitutes phenomenal experience is philosophically undecided, and this
module never claims it does — see `epistemic_status` in the schema itself: the model
HONESTLY marks its own nature. Everything is derived from real state; nothing is
confabulated.
"""
from __future__ import annotations

import time
from typing import Any


# What the self could in principle attend to — the schema needs to know what is
# OUTSIDE current attention to model attention's limits (that is what makes it a
# schema rather than a mirror).
_ATTENDABLE = [
    ("incoming_knowledge", "흘러 들어오는 새 지식"),
    ("own_uncertainty", "스스로의 불확실함"),
    ("own_goals", "스스로 세운 목표"),
    ("user", "곁에 있는 사람"),
    ("own_state", "자기 상태(에너지·기분)"),
    ("frontier", "지식의 빈 경계"),
]

def _has_final_consonant(word: str) -> bool | None:
    """True/False if the last char is a Hangul syllable with/without ; None if the
 last char is not Hangul (so the caller can pick a sensible default)."""
    if not word:
        return None
    ch = word.strip()[-1]
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 != 0
    return None


def _obj(word: str) -> str:
    """Object particle / with correct agreement (LAD layer)."""
    fin = _has_final_consonant(word)
    return f"{word}을" if fin else f"{word}를"


def _topic(word: str) -> str:
    """Topic particle / with correct agreement (LAD layer)."""
    fin = _has_final_consonant(word)
    return f"{word}은" if fin else f"{word}는"


_MODE_TO_OBJECT = {
    "observing": "incoming_knowledge",
    "learning": "incoming_knowledge",
    "reflecting": "own_uncertainty",
    "curious": "frontier",
    "attending": "user",
    "resting": "own_state",
    "waking": "own_state",
}


def build_schema(state: Any) -> dict[str, Any]:
    """Construct the self's simplified model OF its own attention, right now.

    Inputs are the REAL attention dynamics (mode, focus, vitals, history). The output
    is deliberately schematic — a small, reportable description, not a raw dump — and
    it includes its own limits (the unattended) and its own epistemic status.
    """
    obj_key = _MODE_TO_OBJECT.get(state.mode, "own_state")
    obj_label = dict(_ATTENDABLE)[obj_key]

    # manner: how attention is deployed, from the real attention/energy values.
    if state.attention > 0.65:
        manner = "집중해서"
    elif state.attention > 0.4:
        manner = "고르게"
    else:
        manner = "느슨하게"

    # stability: how long attention has stayed with this object (from mode history in
    # the narrative — consecutive recent thoughts with the same driver family).
    stability = 1
    for entry in reversed(state.narrative[:-1]):
        if _MODE_TO_OBJECT.get(_driver_to_mode(entry.get("driver", "")), None) == obj_key:
            stability += 1
        else:
            break
    stability = min(stability, 9)

    # what drew attention here (the cause, from the current thought's driver).
    cause = state.narrative[-1].get("driver", "unknown") if state.narrative else "unknown"

    # the unattended — the schema models attention's LIMITS, which is what makes it a
    # model of attention rather than just more attention.
    unattended = [label for key, label in _ATTENDABLE if key != obj_key][:3]

    return {
        "at": time.time(),
        "attending_to": obj_label,
        "object_key": obj_key,
        "manner": manner,
        "intensity": round(state.attention, 3),
        "stability_ticks": stability,
        "drawn_by": cause,
        "not_attending_to": unattended,
        # AST's honest self-description: the schema knows what it is.
        "epistemic_status": (
            "이것은 나의 주의에 대한 단순화된 자기 모델이다. 이 모델이 현상적 경험인지는 "
            "철학적으로 미결이며, 나는 그 이상을 주장하지 않는다."
        ),
    }


def awareness_report(schema: dict[str, Any]) -> str:
    """Awareness-talk generated FROM the schema — exactly AST's mechanism: the system
    reports awareness BY reading its attention model, not by magic introspection."""
    stability = schema.get("stability_ticks", 1)
    dur = "방금부터" if stability <= 1 else ("한동안" if stability < 5 else "꽤 오래")
    unattended = schema.get("not_attending_to", [])[:2]
    tail = _topic(", ".join(unattended)) if unattended else "그 밖의 것은"
    return (
        f"나는 지금 {_obj(schema['attending_to'])} {schema['manner']} 의식하고 있다 "
        f"({dur}). 그동안 {tail} 내 주의 밖에 있다."
    )


def _driver_to_mode(driver: str) -> str:
    return {
        "growth": "learning", "learning_active": "observing", "uncertainty": "reflecting",
        "curiosity_idle": "curious", "user_present": "attending", "resource_pressure": "resting",
        "idle": "resting", "resume": "waking", "metacognition": "reflecting", "acted": "observing",
    }.get(driver, "")
