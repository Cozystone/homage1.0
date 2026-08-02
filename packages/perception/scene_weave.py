# -*- coding: utf-8 -*-
"""Scene weave — the LIVING context narrative (owner 2026-07-13: " 85% 
 ").

People do not re-describe the room every frame. They narrate CHANGE: ", ", " 
 ". This applies the conversation-weave model to vision — the same substrate that runs the
voice session (continuous spine + threads + emergent episodes):

 • objects are THREADS — persistent entities with presence streaks, not per-frame blips. A brief
 detector flicker does not kill a thread (grace window), so the narrative doesn't stutter.
 • changes are EPISODES — appear / return / disappear events, and only THOSE update the narrative.
 An unchanged room keeps its sentence (that IS the human behavior), so the HUD reads like a
 companion's remark, not a scrolling classifier log.

HONESTY: every narrative line is derived from actual detection deltas — nothing imagined. The base
scene sentence + relations come from open_vocab/scene_graph (grounded); this layer only decides WHEN
something is worth saying and says it in Korean with correct josa. Pure logic, CPU, No-LLM.
"""
from __future__ import annotations

import time
from typing import Any, Optional

# thread lifecycle (seconds)
_GONE_AFTER = 12.0
_RETURN_AFTER = 30.0
_MAX_EVENTS = 3          # narrate at most this many changes at once (a person, not a logger)
_STABLE_FRAMES = 2       # a thread must be seen this many times before its DISAPPEARANCE is narrated —



def _batchim(w: str) -> bool:
    return bool(w) and "가" <= w[-1] <= "힣" and (ord(w[-1]) - 0xAC00) % 28 != 0


def _i_ga(w: str) -> str:
    return "이" if _batchim(w) else "가"


def new_state() -> dict[str, Any]:
    return {"threads": {}, "started": False, "last_sentence": "", "last_change_ts": 0.0}


def observe(state: dict[str, Any], labels: list[str], scene_sentence: str,
            now: Optional[float] = None) -> dict[str, Any]:
    """Weave one observation into the scene state. Returns {narrative, changed, events} — narrative is
    a Korean remark when something worth saying happened (first sight / appear / return / disappear),
    else None and the last sentence stands. `labels` = the Korean labels detected THIS frame."""
    t = float(now if now is not None else time.time())
    seen = set(labels)
    threads = state["threads"]
    events: list[dict[str, str]] = []

    # update present threads; detect appearances and returns
    for lb in seen:
        th = threads.get(lb)
        if th is None:
            threads[lb] = {"first": t, "last": t, "alive": True, "times": 1, "frames": 1}
            if state["started"]:
                events.append({"kind": "appear", "label": lb})
        elif not th["alive"]:
            th["alive"] = True
            th["times"] += 1
            th["frames"] += 1
            kind = "return" if t - th["last"] >= _RETURN_AFTER else "appear"
            th["last"] = t
            if state["started"]:
                events.append({"kind": kind, "label": lb})
        else:
            th["last"] = t
            th["frames"] += 1

    # detect disappearances — a longer grace window absorbs flicker, and ONLY a thread that was
    # stably present (seen ≥ _STABLE_FRAMES) narrates its exit; a one-frame blip just expires quietly.
    for lb, th in threads.items():
        if th["alive"] and lb not in seen and t - th["last"] > _GONE_AFTER:
            th["alive"] = False
            if th.get("frames", 1) >= _STABLE_FRAMES:
                events.append({"kind": "gone", "label": lb})

    # ---- narrate ----
    narrative: Optional[str] = None
    if not state["started"]:
        state["started"] = True
        narrative = scene_sentence                                  # first sight = the full scene read
        state["last_change_ts"] = t
    elif events:
        parts: list[str] = []
        for ev in events[:_MAX_EVENTS]:
            lb = ev["label"]
            if ev["kind"] == "return":
                parts.append(f"{lb}{_i_ga(lb)} 다시 보여요")
            elif ev["kind"] == "appear":
                parts.append(f"방금 {lb}{_i_ga(lb)} 새로 보였어요")
            else:
                parts.append(f"{lb}{_i_ga(lb)} 시야에서 사라졌네요")
        narrative = ", ".join(parts) + "."
        state["last_change_ts"] = t
    elif scene_sentence and scene_sentence != state["last_sentence"] \
            and t - state["last_change_ts"] > 20.0:
        narrative = scene_sentence                                  # slow drift: refresh the base read
        state["last_change_ts"] = t

    if narrative:
        state["last_sentence"] = narrative
    return {"narrative": narrative, "changed": bool(narrative), "events": events,
            "last_sentence": state["last_sentence"]}
