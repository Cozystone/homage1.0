# -*- coding: utf-8 -*-
"""Sensory cortex — the organ that UNDERSTANDS what the senses take in.

Owner directive (2026-07-19): build the organ that understands what the senses take in.
The sensor front-ends already exist as separate organs — vision (packages/perception: open_vocab,
scene_graph, face_cortex, visual_kg), hearing (packages/voice_io: faster-whisper), interoception
(the hormone dynamics). What was missing is the layer ABOVE them: a single, modality-agnostic
"understanding" organ that turns whatever any sense delivers into a common typed PERCEPT, and
grounds the perceptual facts into the graph — the way a cortex integrates thalamic input.

This is deliberately the comprehension organ, NOT a new front-end and NOT a
generator. It structures and grounds; it never invents. Design rules (charter-bound):

  * Modality-agnostic Percept: {modality, kind, content, confidence, t, provenance}. Any front-end
    normalises into this, so adding a new sense (a sim tactile sensor, a sound classifier) is one
    adapter, not a rewrite.
  * The honest FACT / NON-FACT split — the crux:
      - PERCEPTUAL FACTS (an object seen, a colour measured, a sound event, a contact) are grounded
        into the graph as SOURCED, auditable triples (source='sensorimotor_perception'), exactly the
        evidence-only-writes discipline visual_kg already uses.
      - HEARD SPEECH is NOT a world-fact. Transcribed words are a percept OF an utterance ("I heard
        someone say X"), never asserted as "X is true". They route to discourse, never to the
        knowledge graph as fact. (Whisper hears the words; it does not make them true.)
      - INTEROCEPTIVE drives (hunger/arousal/curiosity pressure) are internal state, not world
        knowledge — surfaced for the self/motivation loop, never written as fact.
  * Provenance carries the sensor + confidence, so the graph always knows a row is a PERCEPT, not an
    asserted fact — the developmental self can weight it, doubt it, or let it decay accordingly.

No-LLM: nothing here generates. Perceptual facts pass through the same sourced store.add path as any
other evidence. English-only.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# modalities the cortex can integrate; extendable by adding an adapter, not editing the core.
VISION = "vision"
AUDIO = "audio"
PROPRIOCEPTION = "proprioception"      # body pose / joints (sim provides raw)
INTEROCEPTION = "interoception"        # hormone/drive state (our internal sense)
TOUCH = "touch"                        # contact / tactile (sim provides raw)

_PERCEPT_SOURCE = "sensorimotor_perception"   # provenance tag: this row is a PERCEPT, not a fact-claim


@dataclass
class Percept:
    """One understood unit of sensory input. `groundable` marks whether it is a world-FACT eligible
    for the knowledge graph (a seen object) vs a non-fact (heard speech, an internal drive)."""
    modality: str
    kind: str                          # 'object' | 'colour' | 'sound_event' | 'speech' | 'contact' | 'drive' | ...
    content: str
    confidence: float = 0.0
    groundable: bool = False           # True only for perceptual FACTS
    triples: list[tuple[str, str, str]] = field(default_factory=list)   # graph-ready (facts only)
    t: float = field(default_factory=time.time)
    provenance: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Front-end adapters — each wraps an EXISTING sensor organ's output into Percepts.
# They import nothing heavy at module load; callers pass already-computed sensor output.
# ---------------------------------------------------------------------------

def from_vision(scene: dict[str, Any] | None, subject: str | None = None) -> list[Percept]:
    """Vision organ (open_vocab / scene_graph / visual_kg) output -> perceptual facts.
    `scene` shape mirrors perception.visual_memory.recall_scene / scene_graph output."""
    out: list[Percept] = []
    if not scene:
        return out
    src = (scene.get("sources") or [])[:3]
    for det in scene.get("objects") or scene.get("detections") or []:
        label = det.get("label") if isinstance(det, dict) else str(det)
        conf = float(det.get("score", det.get("confidence", 0.0))) if isinstance(det, dict) else 0.0
        if not label:
            continue
        subj = str(label)
        out.append(Percept(VISION, "object", f"saw {subj}", conf, groundable=True,
                           triples=[(subj, "perceived_via", "vision")],
                           provenance={"sensor": "open_vocab", "sources": src}))
    # measured colour / brightness of the subject the measurement was FOR (visual_kg pattern)
    if subject and (scene.get("palette") or scene.get("luminance") is not None):
        subj = str(subject)
        tri: list[tuple[str, str, str]] = []
        lum = scene.get("luminance")
        if lum is not None:
            tri.append((subj, "seen_brightness", "bright" if float(lum) > 0.6
                        else "dark" if float(lum) < 0.35 else "medium"))
        if tri:
            out.append(Percept(VISION, "colour", f"measured appearance of {subj}", 0.7,
                               groundable=True, triples=tri,
                               provenance={"sensor": "visual_kg", "sources": src}))
    return out


def from_audio(transcript: str | None, *, is_speech: bool = True,
               confidence: float = 0.0, lang: str = "en") -> list[Percept]:
    """Hearing organ (whisper) output. HEARD SPEECH is a non-fact percept of an utterance — it goes
    to discourse, never to the knowledge graph as fact. A non-speech sound event (is_speech=False)
    IS a perceptual fact ('a bark was heard')."""
    text = (transcript or "").strip()
    if not text:
        return []
    if is_speech:
        # a percept of WHAT WAS SAID — never asserted as true. groundable=False by construction.
        return [Percept(AUDIO, "speech", text, confidence, groundable=False,
                       provenance={"sensor": "whisper", "lang": lang, "note": "heard, not asserted"})]
    # sound EVENT (a crash, a bark) — a real perceptual fact about the environment
    return [Percept(AUDIO, "sound_event", f"heard {text}", confidence, groundable=True,
                   triples=[(text, "perceived_via", "hearing")],
                   provenance={"sensor": "sound_classifier"})]


def from_touch(contacts: list[dict[str, Any]] | None) -> list[Percept]:
    """Tactile/contact sensor (sim-provided) -> perceptual facts about what the body is touching."""
    out: list[Percept] = []
    for c in contacts or []:
        obj = str(c.get("object") or c.get("with") or "").strip()
        if not obj:
            continue
        out.append(Percept(TOUCH, "contact", f"in contact with {obj}",
                           float(c.get("force", 0.0) and 1.0 or 0.5), groundable=True,
                           triples=[("self", "in_contact_with", obj)],
                           provenance={"sensor": "contact"}))
    return out


def from_interoception(hormones: dict[str, float] | None) -> list[Percept]:
    """Internal sense (hormone/drive state) -> drive percepts. NEVER world-knowledge; these feed the
    self/motivation loop (what the developing self WANTS), which is exactly what a VLA lacks."""
    out: list[Percept] = []
    for name, level in (hormones or {}).items():
        lv = float(level)
        if lv <= 0.0:
            continue
        out.append(Percept(INTEROCEPTION, "drive", f"{name}={lv:.2f}", lv, groundable=False,
                           provenance={"sensor": "hormones"}))
    return out


# ---------------------------------------------------------------------------
# The cortex: integrate + ground.
# ---------------------------------------------------------------------------

def integrate(*bundles: list[Percept]) -> list[Percept]:
    """Fuse percepts from multiple senses into one time-ordered field (the cortex's unified view)."""
    percepts = [p for b in bundles for p in (b or [])]
    percepts.sort(key=lambda p: p.t)
    return percepts


def ground(percepts: list[Percept], store: Any = None) -> dict[str, Any]:
    """Write ONLY perceptual FACTS into the graph as sourced, auditable rows. Heard speech and
    interoceptive drives are returned in `non_facts` for the discourse / motivation loops but never
    grounded as knowledge. Mirrors visual_kg's evidence-only-writes discipline."""
    facts = [p for p in percepts if p.groundable and p.triples]
    non_facts = [p for p in percepts if not p.groundable]
    stored = 0
    written: list[tuple[str, str, str]] = []
    if facts:
        try:
            if store is None:
                from packages.graph_scale.graph_paths import (
                    SENSORY_PROPOSAL_FRAGMENT_ROOT,
                )
                from packages.graph_scale.triple_store import TripleStore
                store = TripleStore(SENSORY_PROPOSAL_FRAGMENT_ROOT)
            for p in facts:
                srcs = ";".join(str(x) for x in (p.provenance.get("sources") or [p.provenance.get("sensor", "")]))
                sid = store.intern_source(_PERCEPT_SOURCE, srcs)
                for s, pr, o in p.triples:
                    if store.add(s, pr, o, source=sid):
                        stored += 1
                        written.append((s, pr, o))
            store.flush()
        except Exception:
            return {"stored": 0, "written": [], "non_facts": len(non_facts),
                    "error": "store_unavailable"}
    return {"stored": stored, "written": written,
            "speech": [p.content for p in non_facts if p.kind == "speech"],
            "drives": [p.content for p in non_facts if p.kind == "drive"],
            "non_facts": len(non_facts)}


def understand(*, vision: dict[str, Any] | None = None, vision_subject: str | None = None,
               audio: str | None = None, audio_is_speech: bool = True,
               touch: list[dict[str, Any]] | None = None,
               hormones: dict[str, float] | None = None,
               store: Any = None, write: bool = False) -> dict[str, Any]:
    """The organ's single entry point: take whatever the senses delivered, understand it into a
    unified percept field, and (optionally) ground the perceptual facts. `write=False` by default so
    perception is safe to run read-only; grounding is a deliberate act (evidence-only-writes)."""
    percepts = integrate(
        from_vision(vision, vision_subject),
        from_audio(audio, is_speech=audio_is_speech),
        from_touch(touch),
        from_interoception(hormones),
    )
    result: dict[str, Any] = {
        "percepts": len(percepts),
        "by_modality": {m: sum(1 for p in percepts if p.modality == m)
                        for m in (VISION, AUDIO, TOUCH, INTEROCEPTION) if any(p.modality == m for p in percepts)},
        "facts": sum(1 for p in percepts if p.groundable),
        "heard_speech": [p.content for p in percepts if p.kind == "speech"],
        "drives": [p.content for p in percepts if p.kind == "drive"],
    }
    if write:
        result["grounded"] = ground(percepts, store)
    return result
