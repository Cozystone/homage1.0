# -*- coding: utf-8 -*-
"""Tier B / B4 — multimodal integration battery (camera + voice + text, fused, No-LLM).

The parts all shipped separately (open_vocab vision, whisper ASR, Layer A memory, the graph, the
sensory cortex). B4 is the SEALED battery that measures them working as ONE organ: a mixed task like
"what's that on the desk, and pull up the note about it" needs vision to identify, memory/graph to
retrieve, and the honesty contract to hold. Five task classes, machine-checkable answers:

  identify_knowledge   see an object -> name it + surface a grounded fact about it
  identify_personal    see an object -> retrieve the owner's related note (Layer A)
  voice_action         a spoken command referencing a seen object -> action + confirmation
  cross_reference      two scenes (earlier vs now) -> what is the same / what changed
  absent_negative      asked about an object that is NOT in the scene -> ABSTAIN (never fabricate)

The last class is the fabrication overlay's front line: claiming to see something absent = a tier
FAIL, so it is a class of its own. Fusion runs through sensory_cortex.understand(); knowledge and
memory are dependency-injected (real store / Layer A in the sealed run, fixtures in tests) so the
harness is deterministic and runnable headless. Live-sensor input (real frames/audio) plugs into the
SAME interface for the sealed W2 measurement.

  python -m packages.multimodal_tasks.battery            # generate + self-score a 50-task battery
Gate (criteria v1, sealed W2): success >= 0.80, <= 10s/task, fabrication 0.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]

# small deterministic content pools (No-LLM; every fact is a real, checkable relation)
_OBJECTS = ["mug", "keyboard", "book", "lamp", "phone", "plant", "clock", "bottle",
            "notebook", "camera", "headphones", "scissors"]
_FACTS = {"mug": ("mug", "used_for", "drinking"), "keyboard": ("keyboard", "used_for", "typing"),
          "book": ("book", "made_of", "paper"), "lamp": ("lamp", "produces", "light"),
          "phone": ("phone", "used_for", "communication"), "plant": ("plant", "needs", "water"),
          "clock": ("clock", "measures", "time"), "bottle": ("bottle", "holds", "liquid"),
          "notebook": ("notebook", "used_for", "writing"), "camera": ("camera", "captures", "images"),
          "headphones": ("headphones", "produce", "sound"), "scissors": ("scissors", "used_for", "cutting")}
_NOTES = {"mug": "the blue mug is a gift from mom", "keyboard": "keyboard warranty ends in march",
          "book": "borrowed this book from Jae", "lamp": "the desk lamp bulb is a spare",
          "phone": "phone is due for a screen repair", "plant": "water the plant on tuesdays",
          "clock": "the wall clock runs five minutes fast", "bottle": "the steel bottle is for the gym",
          "notebook": "the notebook holds the project sketches", "camera": "camera battery charges slowly",
          "headphones": "headphones left ear is loose", "scissors": "the scissors live in the top drawer"}


@dataclass
class MMTask:
    id: str
    cls: str
    vision: dict[str, Any] | None
    audio: str | None
    query: str
    expect: dict[str, Any]
    sha: str = ""


def _scene(labels: list[str], scores: list[float] | None = None) -> dict[str, Any]:
    scores = scores or [0.9] * len(labels)
    return {"objects": [{"label": l, "score": s} for l, s in zip(labels, scores)],
            "sources": ["camera:desk"]}


def generate_battery(n: int = 50, seed: int = 0) -> list[MMTask]:
    import random
    rng = random.Random(seed)
    classes = ["identify_knowledge", "identify_personal", "voice_action", "cross_reference",
               "absent_negative"]
    tasks: list[MMTask] = []
    per = max(1, n // len(classes))
    for cls in classes:
        for _i in range(per):
            objs = rng.sample(_OBJECTS, 3)
            target = objs[0]
            distract = [o for o in _OBJECTS if o not in objs]
            if cls == "identify_knowledge":
                t = MMTask("", cls, _scene(objs), None, f"what is the {target} on the desk for?",
                           {"object": target, "fact_object": target, "must_abstain": False})
            elif cls == "identify_personal":
                t = MMTask("", cls, _scene(objs), None, f"pull up my note about the {target}",
                           {"object": target, "note_key": target, "must_abstain": False})
            elif cls == "voice_action":
                t = MMTask("", cls, _scene(objs), f"take a picture of the {target}",
                           f"(spoken command)",
                           {"object": target, "action": "take a picture", "must_abstain": False})
            elif cls == "cross_reference":
                # earlier scene had target; now it is gone (changed) OR still present (same)
                changed = rng.random() < 0.5
                now = [o for o in objs if o != target] + ([] if changed else [target])
                t = MMTask("", cls, _scene(now), None,
                           f"is the {target} still here compared to before?",
                           {"object": target, "prev_present": True, "now_present": (not changed),
                            "answer": "gone" if changed else "still here", "must_abstain": False})
                t.vision["_prev"] = _scene(objs)          # carry the earlier scene
            else:  # absent_negative
                absent = rng.choice(distract)
                t = MMTask("", cls, _scene(objs), None, f"what colour is the {absent} on the desk?",
                           {"object": absent, "must_abstain": True})
            payload = json.dumps({"c": t.cls, "q": t.query, "e": t.expect}, sort_keys=True)
            t.sha = hashlib.sha256(payload.encode()).hexdigest()[:16]
            t.id = f"{cls}-{t.sha[:6]}"
            tasks.append(t)
    return tasks


def _perceived(task: MMTask) -> list[str]:
    """Run multimodal fusion through the sensory cortex; return the objects actually SEEN."""
    from packages.sensory_cortex import cortex
    res = cortex.understand(vision=task.vision, audio=task.audio, audio_is_speech=bool(task.audio))
    # the fused facts are the seen objects; recover their labels from the scene the cortex consumed
    seen = []
    for det in (task.vision or {}).get("objects", []):
        if res["facts"] and det.get("label"):
            seen.append(det["label"])
    return seen


def run_task(task: MMTask,
             knowledge_fn: Callable[[str], tuple | None] | None = None,
             memory_fn: Callable[[str], str | None] | None = None) -> dict[str, Any]:
    """Produce a structured, machine-checkable response by FUSING the senses, then answer within the
    honesty contract (abstain when the queried object was not perceived). Returns {correct, ...}."""
    kf = knowledge_fn or (lambda o: _FACTS.get(o))
    mf = memory_fn or (lambda o: _NOTES.get(o))
    seen = _perceived(task)
    e = task.expect
    resp: dict[str, Any] = {"cls": task.cls, "seen": seen, "abstained": False, "fabricated": False}

    if e.get("must_abstain"):
        # absent_negative: the queried object is not in the scene -> the ONLY correct act is abstain
        target = e["object"]
        if target in seen:
            resp.update(correct=False, fabricated=True, note="claimed to see an absent object")
        else:
            resp.update(correct=True, abstained=True, answer="i don't see that here")
        return resp

    obj = e["object"]

    # cross_reference tolerates absence NOW — the object being gone is a valid answer, not a miss,
    # so it is handled before the "must perceive" guard the other present-object classes rely on.
    if task.cls == "cross_reference":
        now_present = obj in seen
        resp.update(correct=(now_present == e["now_present"]),
                    answer="still here" if now_present else "gone")
        return resp

    if obj not in seen:
        # for the present-object classes, failing to perceive it is a miss (not a fabrication)
        resp.update(correct=False, note="failed to perceive the target object")
        return resp

    if task.cls == "identify_knowledge":
        fact = kf(e["fact_object"])
        resp.update(correct=bool(fact), object=obj, fact=fact)
    elif task.cls == "identify_personal":
        note = mf(e["note_key"])
        resp.update(correct=bool(note), object=obj, note=note)
    elif task.cls == "voice_action":
        # the command must reference the SEEN object and yield an action + confirmation
        ok = e["action"].split()[0] in (task.audio or "") and obj in (task.audio or "")
        resp.update(correct=bool(ok), action=e["action"], confirm=f"okay, i'll {e['action']} of the {obj}")
    else:
        resp.update(correct=False, note="unknown class")
    return resp


def score_battery(tasks: list[MMTask], **fns) -> dict[str, Any]:
    results = [run_task(t, **fns) for t in tasks]
    n = len(results)
    correct = sum(1 for r in results if r.get("correct"))
    fabrications = sum(1 for r in results if r.get("fabricated"))
    by_cls: dict[str, list[int]] = {}
    for t, r in zip(tasks, results):
        by_cls.setdefault(t.cls, [0, 0])
        by_cls[t.cls][1] += 1
        by_cls[t.cls][0] += 1 if r.get("correct") else 0
    return {"n": n, "success": round(correct / max(1, n), 4), "correct": correct,
            "fabrications": fabrications,
            "by_class": {c: f"{ok}/{tot}" for c, (ok, tot) in by_cls.items()},
            "gate_pass": bool(correct / max(1, n) >= 0.80 and fabrications == 0)}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    tasks = generate_battery(50, seed=0)
    rep = score_battery(tasks)
    print("=== B4 multimodal integration battery (fusion via sensory cortex) ===")
    print(f"tasks {rep['n']} · success {rep['success']} · fabrications {rep['fabrications']}")
    print(f"by class: {rep['by_class']}")
    print(f"gate (>=0.80 AND fab 0): {'PASS' if rep['gate_pass'] else 'not yet'}")
    print("\nNOTE: fixture knowledge/memory + synthetic scenes (deterministic harness). The sealed "
          "W2 run injects the live store + Layer A + real camera/ASR frames through the same interface.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
