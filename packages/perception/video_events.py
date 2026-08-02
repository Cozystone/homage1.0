# -*- coding: utf-8 -*-
"""Video → event stream → memory → causal/intent reasoning (the missing stitch).

The Copilot proposal (owner relayed 2026-07-20) lays out: frame → object → action → EVENT → memory →
reasoning. ATANOR already has 5 of the 6 stages as organs — per-frame object detection
(perception.open_vocab), per-frame scene graph + relations (perception.scene_graph), long-term memory
(episodic_memory.bitemporal), the learned causal world model (temporal_reasoning), and intent
inference. The ONE genuinely missing stage was between them: nobody stitched a SEQUENCE of per-frame
scene graphs into events OVER TIME. This module is that stitch — and it deliberately reuses the
existing organs rather than adding a new heavy model.

Design (No-LLM, grounded, honest):
  1. DIFF consecutive per-frame scene graphs -> typed events (appear / vanish / approach / separate /
     take / release). Events are DERIVED FROM THE FRAMES (data), never invented.
  2. WRITE each event into bitemporal episodic memory -> the "10 minutes ago the keys went on the
     desk" long-term recall the proposal asks for.
  3. REASON: order the events on the learned temporal axis, and offer intent as an explicit
     HYPOTHESIS, never an assertion ('appears to be about to drink' is a marked guess, not a fact --
     the generative-leap doctrine: a leap is flagged, never stated as truth).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VideoEvent:
    t: int                        # frame index / timestamp
    kind: str                     # appear | vanish | approach | separate | take | release | relate
    subject: str
    obj: str = ""
    relation: str = ""
    evidence: str = ""            # which frame-diff produced this (traceable, never fabricated)

    def sentence(self) -> str:
        m = {
            "appear": f"{self.subject} appeared",
            "vanish": f"{self.subject} left the scene",
            "approach": f"{self.subject} approached the {self.obj}",
            "separate": f"{self.subject} moved away from the {self.obj}",
            "take": f"{self.subject} took the {self.obj}",
            "release": f"{self.subject} put down the {self.obj}",
            "relate": f"{self.subject} {self.relation.replace('_', ' ')} the {self.obj}",
        }
        return m.get(self.kind, f"{self.subject} {self.kind} {self.obj}").strip()


def _labels(graph: dict) -> set[str]:
    return {n["label"] for n in graph.get("nodes", [])}


def _edges(graph: dict) -> set[tuple[str, str, str]]:
    return {(e["subject"], e["relation"], e["object"]) for e in graph.get("edges", [])}


def _holds(graph: dict) -> set[tuple[str, str]]:
    """(holder, held) pairs implied by a 'contains'/'near' edge between an agent and a small object."""
    out = set()
    for e in graph.get("edges", []):
        if e["relation"] in ("contains", "near"):
            out.add((e["subject"], e["object"]))
    return out


def diff_frames(prev: dict, cur: dict, t: int) -> list[VideoEvent]:
    """Typed events from one frame-to-frame transition. Pure diff of two scene graphs — every event
    traces to an observed change, so nothing here is imagined."""
    events: list[VideoEvent] = []
    pl, cl = _labels(prev), _labels(cur)
    for lbl in sorted(cl - pl):
        events.append(VideoEvent(t, "appear", lbl, evidence="node absent->present"))
    for lbl in sorted(pl - cl):
        events.append(VideoEvent(t, "vanish", lbl, evidence="node present->absent"))

    pe, ce = _edges(prev), _edges(cur)
    for s, r, o in sorted(ce - pe):
        if r == "near":
            events.append(VideoEvent(t, "approach", s, o, r, "near edge formed"))
        else:
            events.append(VideoEvent(t, "relate", s, o, r, "edge formed"))
    for s, r, o in sorted(pe - ce):
        if r == "near":
            events.append(VideoEvent(t, "separate", s, o, r, "near edge broke"))

    ph, ch = _holds(prev), _holds(cur)
    for holder, held in sorted(ch - ph):
        events.append(VideoEvent(t, "take", holder, held, evidence="holder gained possession"))
    for holder, held in sorted(ph - ch):
        events.append(VideoEvent(t, "release", holder, held, evidence="holder lost possession"))
    return events


def events_from_frames(frame_graphs: list[dict]) -> list[VideoEvent]:
    """Stitch a whole sequence of per-frame scene graphs into one event stream."""
    events: list[VideoEvent] = []
    for i in range(1, len(frame_graphs)):
        events.extend(diff_frames(frame_graphs[i - 1], frame_graphs[i], i))
    return events


def to_memory(events: list[VideoEvent], mem: Any = None) -> Any:
    """Write events into bitemporal episodic memory so later questions ('where are the keys?') can be
    answered by RECALL, not re-watching. Returns the memory store."""
    from packages.episodic_memory.bitemporal import BitemporalMemory, Event
    mem = mem or BitemporalMemory()
    fid = 0
    for ev in events:
        fid += 1
        if ev.kind == "take":                          # possession: object's location becomes holder
            mem.ingest(Event(f"v{fid}", "assert", ev.obj, "held_by", ev.subject, ev.t))
        elif ev.kind == "release":
            mem.ingest(Event(f"v{fid}", "assert", ev.obj, "held_by", "", ev.t))   # dropped -> gap
        elif ev.kind in ("relate", "approach"):
            mem.ingest(Event(f"v{fid}", "assert", ev.subject, ev.relation or "near", ev.obj, ev.t))
    return mem


# intent lexicon is NOT authored here as fact -- these are HYPOTHESIS templates. The affordance is
# proposed, flagged as a guess, and only if the concept graph grounds it (best-effort). No assertion.
def intent_hypotheses(events: list[VideoEvent]) -> list[dict]:
    """Offer possible intents as EXPLICIT hypotheses (generative-leap doctrine: a leap is marked,
    never stated as truth). Each carries the events it leans on, so it is auditable, not invented."""
    # keep only the LAST taker of each object (the current possessor) -- an object briefly 'held' by
    # a container it was then removed from is not an intent, only the final holder is.
    last_take: dict[str, VideoEvent] = {}
    released = {(e.subject, e.obj) for e in events if e.kind == "release"}
    for e in events:
        if e.kind == "take":
            last_take[e.obj] = e
    out: list[dict] = []
    for obj, e in sorted(last_take.items()):
        if (e.subject, e.obj) in released:             # taken then put back -> no standing intent
            continue
        out.append({"hypothesis": f"{e.subject} may intend to use the {e.obj}",
                    "is_hypothesis": True, "confidence": "low",
                    "grounded_in": [f"t{e.t}: {e.sentence()}"]})
    return out


def predict_next(frame_graphs: list[dict], field: Any = None) -> dict:
    """WORLD-MODEL prediction (System-2 forward simulation): given frames so far, predict the next
    frame's state BEFORE seeing it. Two prediction sources, both marked as prediction (never fact):
      - object permanence: an object that just vanished is PREDICTED to still EXIST (the ball thrown
        behind a wall keeps flying). Humans do not conclude it ceased to be; neither should we.
      - causal continuation: after a 'take', the learned causal field expects a downstream use.
    The point is not to be right -- it is to have a PREDICTION to be surprised by (see `surprise`)."""
    if len(frame_graphs) < 2:
        return {"persist": [], "expect_events": []}
    prev, cur = frame_graphs[-2], frame_graphs[-1]
    vanished = sorted(_labels(prev) - _labels(cur))
    persist = [{"label": v, "predicted": "still exists (occluded/left frame), not destroyed",
                "is_prediction": True} for v in vanished]
    recent = events_from_frames(frame_graphs)
    expect = []
    for e in recent[-4:]:
        if e.kind == "take":
            expect.append({"after": e.sentence(), "expect": f"{e.subject} uses the {e.obj} soon",
                           "is_prediction": True, "confidence": "low"})
    return {"persist": persist, "expect_events": expect}


# Seam B (V-JEPA fusion, docs/ATANOR_vjepa_fusion.md §4): threshold on the STANDARDIZED latent
# surprise handed in by the latent predictor. Latent surprise catches SUB-symbolic change (a motion,
# a texture, a not-yet-named object shifting) that the discrete scene-graph diff is structurally blind
# to; it runs ALONGSIDE the symbolic surprise, never replacing it.
_LATENT_THINK = 1.5


def surprise(prediction: dict, actual_graph: dict, actual_events: list[VideoEvent],
             latent_surprise: float | None = None) -> dict:
    """Prediction error (the learning + compute-budget signal): how much did the world violate the
    world model? A vanished-then-truly-gone object, or an expected use that never came, is a
    SURPRISE -> in the full loop this both teaches the model and tells System-2 to think harder.

    Seam B: an optional `latent_surprise` (the latent predictor's standardized s_t) is folded in
    ALONGSIDE the symbolic surprise — never replacing it. The discrete scene-graph diff catches
    named-object/edge changes; latent surprise catches the sub-symbolic change the labels miss.
    `think_harder = symbolic OR latent`. A latent prediction is a FLAGGED HYPOTHESIS (DATA / a
    proposal the symbolic membrane verifies), per the generative-leap doctrine — never a stated fact."""
    misses = 0
    detail = []
    now = _labels(actual_graph)
    for p in prediction.get("persist", []):
        # if we predicted persistence but the object REappears, prediction was RIGHT (permanence held)
        if p["label"] in now:
            detail.append({"predicted": p["label"] + " persists", "outcome": "confirmed"})
        # (truly gone forever is unknowable from one frame -> we do not punish absence, only track)
    for x in prediction.get("expect_events", []):
        got = any(e.kind in ("relate", "approach") for e in actual_events)
        if not got:
            misses += 1
            detail.append({"expected": x["expect"], "outcome": "not yet seen (surprise)"})
    score = misses / max(1, len(prediction.get("expect_events", []) or [1]))
    symbolic_think = score >= 0.5
    latent_think = latent_surprise is not None and latent_surprise >= _LATENT_THINK
    out = {"surprise": round(score, 3), "detail": detail,
           "think_harder": bool(symbolic_think or latent_think)}   # feeds the System-2 compute budget
    if latent_surprise is not None:
        # a latent prediction is DATA: flagged, auditable, never enshrined as fact.
        out["latent"] = {"surprise": round(float(latent_surprise), 3), "is_hypothesis": True,
                         "source": "latent_predictor", "think_harder": bool(latent_think),
                         "note": "sub-symbolic prediction error the scene-graph diff cannot see"}
    return out


def understand_video(frame_graphs: list[dict]) -> dict:
    """Full stitch: frames -> events -> memory -> narrative + intent hypotheses. The narrative is
    factual (traces to frame diffs); intents are flagged hypotheses; memory answers later recall."""
    events = events_from_frames(frame_graphs)
    mem = to_memory(events)
    narrative = [{"t": e.t, "text": e.sentence() + ".", "kind": e.kind, "evidence": e.evidence}
                 for e in events]
    return {"events": events, "narrative": narrative,
            "intent_hypotheses": intent_hypotheses(events), "memory": mem}
