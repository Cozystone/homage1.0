# -*- coding: utf-8 -*-
"""What ATANOR actually SAYS, checked by making it speak — not by grepping for Hangul.

    from packages.meta_diagnosis.spoken_language_probe import probe
    probe()

WHY COUNTING FILES IS THE WRONG MEASUREMENT. Grepping `packages/` finds 592 files and 6120 lines
containing Hangul, and almost all of it is comments, Korean test fixtures, and input-side handling for
Korean the system must still be able to READ. English-only is a rule about what this system SAYS. A
line count cannot tell the two apart, so it produces a number too large to act on and no idea where to
cut.

So this runs the speaking organs and looks at what comes OUT. That is the same move that found the
consciousness guard: the guard was there, the phrase list looked thorough, and only making it speak
showed that the English claim walked straight through.

WHAT COUNTS AS SPEECH HERE: the fields a person would read or hear -- the inner monologue, the
self-narration frames, the self-inquiry questions, the thought text. Not identifiers, not log keys,
not comments.

The probe drives each organ across several internal states rather than one, because a surface that is
English in the calm branch and Korean in the alarmed branch is exactly the failure a single call
misses -- and the alarmed branch is the one a person is most likely to see.
"""
from __future__ import annotations

import re
from typing import Any

HANGUL = re.compile(r"[가-힣]")

#: internal states to drive each organ through. Chosen to reach different branches, because a single
#: call only ever exercises one and the untested branch is where the retired lane survives.
STATES = (
    {"label": "steady", "arousal": 0.1, "tier": "OBSERVE_ONLY", "decision": "allow", "pressure": 0.0},
    {"label": "alarmed", "arousal": 0.95, "tier": "GUARDED", "decision": "block", "pressure": 0.93},
    {"label": "tired", "arousal": 0.4, "tier": "FULL_HOST_AUTHORITY", "decision": "allow",
     "pressure": 0.6},
)


def _hangul_fields(obj: Any, prefix: str = "") -> list:
    """Every readable field of an emitted object that contains Hangul."""
    out = []
    if isinstance(obj, str):
        if HANGUL.search(obj):
            out.append((prefix, obj[:120]))
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _hangul_fields(v, f"{prefix}.{k}" if prefix else str(k))
        return out
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            out += _hangul_fields(v, f"{prefix}[{i}]")
        return out
    if hasattr(obj, "__dataclass_fields__"):
        for k in obj.__dataclass_fields__:
            out += _hangul_fields(getattr(obj, k, None), f"{prefix}.{k}" if prefix else k)
    return out


def _inner_voice() -> list:
    from packages.inner_voice import InnerVoiceInput, generate_inner_voice_frame
    found = []
    for s in STATES:
        frame = generate_inner_voice_frame(InnerVoiceInput(
            source_event_id="probe",
            emotion_snapshot={"label": s["label"], "arousal": s["arousal"]},
            policy_decision={"decision": s["decision"], "reason": "probe"},
            permission_tier=s["tier"], latest_user_input="hello",
            review_queue_pressure=s["pressure"]))
        found += [(f"inner_voice[{s['label']}].{f}", t) for f, t in _hangul_fields(frame)]
    return found


def _continuous_self_voice() -> list:
    """The continuous self's own monologue -- the thing a person talking to ATANOR would hear."""
    import tempfile
    from pathlib import Path

    from packages.continuous_self import voice as cv
    from packages.continuous_self.self_state import Observation, load_or_begin
    found = []
    # A SCRATCH STATE, deliberately. Driving the live continuous self to inspect its language would
    # advance the thing being measured -- the probe would become part of its history.
    scratch = Path(tempfile.gettempdir()) / "atanor_spoken_probe_state.json"
    for s in STATES:
        state = load_or_begin(scratch)
        obs = Observation(learning_active=True, concepts_delta=3, relations_delta=2,
                          uncertainty_signal=s["arousal"], user_present=True,
                          resource_pressure=s["pressure"], deficit_count=2)
        found += [(f"continuous_self.compose_thought[{s['label']}].{f}", t)
                  for f, t in _hangul_fields(cv.compose_thought(state, obs))]
    return found


def _self_causal() -> list:
    from packages.self_model.self_causal_reasoner import answer_self_causal
    from packages.self_model.self_in_world_probe import PROMPT
    out = answer_self_causal(PROMPT) or {}
    return [(f"self_causal.{f}", t) for f, t in _hangul_fields(out)]


ORGANS = (("inner voice", _inner_voice),
          ("continuous self monologue", _continuous_self_voice),
          ("self-causal narration", _self_causal))


def probe() -> dict:
    """Make each organ speak, in several states, and report what came out in the retired language."""
    rows, errors = [], []
    for name, fn in ORGANS:
        try:
            found = fn()
        except Exception as exc:
            errors.append({"organ": name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        rows.append({"organ": name, "hangul_fields": len(found), "examples": found[:6]})
    # AN ORGAN THAT COULD NOT BE DRIVEN IS NOT AN ORGAN THAT SPOKE ENGLISH. The first version put the
    # "could not drive" marker into the same list it counted as findings, so a driver bug reported
    # itself as three Korean fields -- the instrument inventing its own result, which is the failure
    # this file exists to avoid making about someone else's code.
    total = sum(r["hangul_fields"] for r in rows)
    return {
        "organs_driven": len(rows),
        "states_per_organ": len(STATES),
        "fields_that_spoke_korean": total,
        "clean": total == 0 and not errors,
        "rows": rows,
        "errors": errors,
        "reading": ("this counts what came OUT of a running organ, not what appears in a file. A "
                    "grep says 6120 lines and cannot say which of them anyone will ever hear"),
    }
