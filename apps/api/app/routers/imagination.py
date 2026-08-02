# -*- coding: utf-8 -*-
"""Imagination API — compile a thought (concepts + relations) into a SPLATRA scene spec.

POST /api/imagination/scene  {concepts, relations, subject?, duration?} -> scene spec

The scene spec ({objects, links, motion, duration}) is what a SPLATRA renderer animates so the
engine can *show* what it is imagining. Deterministic, No-LLM: it lays out only the graph the
engine already activated. The concepts/relations come from the answer path (a later slice wires
that live); for now the caller passes them, so the compiler is exercisable on its own.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from packages.imagination import compile_scene

router = APIRouter(prefix="/api/imagination", tags=["imagination"])


class SceneConcept(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    label: str = Field(default="", max_length=200)
    type: str | None = Field(default=None, max_length=120)
    weight: float = 0.0


class SceneRelation(BaseModel):
    from_: str = Field(alias="from", min_length=1, max_length=200)
    to: str = Field(min_length=1, max_length=200)
    predicate: str = Field(default="", max_length=200)

    model_config = {"populate_by_name": True}


class SceneRequest(BaseModel):
    concepts: list[SceneConcept] = Field(default_factory=list, max_length=64)
    relations: list[SceneRelation] = Field(default_factory=list, max_length=128)
    subject: str | None = Field(default=None, max_length=200)
    duration: float = Field(default=6.0, ge=0.5, le=30.0)


@router.post("/scene")
def scene(body: SceneRequest) -> dict[str, Any]:
    concepts = [{"id": c.id, "label": c.label or c.id, "type": c.type, "weight": c.weight}
                for c in body.concepts]
    relations = [{"from": r.from_, "to": r.to, "predicate": r.predicate} for r in body.relations]
    return compile_scene(concepts, relations, subject_id=body.subject, duration=body.duration)


class QuerySceneRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    duration: float = Field(default=6.0, ge=0.5, le=30.0)


def _pack_concepts() -> list[dict[str, Any]]:
    from packages.base_brain.pack_loader import load_base_brain_pack

    sg = load_base_brain_pack().semantic_graph
    return list(sg.get("concepts") or [])


@router.post("/scene-for-query")
def scene_for_query(body: QuerySceneRequest) -> dict[str, Any]:
    """Imagine a QUERY from the real graph: the matching concept at the center, its topical
    neighborhood around it, related by the graph's own structure. Grounded — never invented."""
    return _scene_for_query(body.query, body.duration)


@router.get("/replay")
def replay(snapshot_id: str | None = None, duration: float = 6.0) -> dict[str, Any]:
    """Spatial Memory Replay: rebuild a remembered space (the latest, or a chosen snapshot) as a
    SPLATRA scene — the objects where they were seen. Idle when nothing has been recorded."""
    from packages.perception.spatial_memory import reconstruct_scene, recall_snapshot

    return reconstruct_scene(recall_snapshot(snapshot_id), duration=duration)


@router.get("/particle")
def particle() -> dict[str, Any]:
    """The aquarium polls this for the AI's OWN hands on the field — a raw expressive intent
    (mood/energy/colour/motion/density/focus) laid over whatever it is showing. Idle (resting)
    when the mind is quiet, so the field settles back on its own."""
    from packages.imagination.particle_intent import get_particle_intent

    intent = get_particle_intent()
    return intent if intent else {"idle": True}


# Doherty guard (owner 2026-07-12: keep interactions under 400ms): the aquarium polls /current
# every 2.5s, but a thought changes rarely — so the EXPENSIVE compile (pack join + graph
# neighborhood) runs ONCE per thought and every later poll is a dict read. This also armors the
# poll against learner GIL storms (measured: 724ms cold, 6-30s under load → cached ~ms).
_SCENE_CACHE: dict[tuple, dict[str, Any]] = {}
_SCENE_CACHE_MAX = 6


@router.get("/current")
def current(duration: float = 6.0) -> dict[str, Any]:
    """The orb polls this: the scene of whatever ATANOR is thinking about right now (the live
    thought stashed by the answer path), compiled graph-grounded. Idle when the mind is quiet."""
    from packages.imagination.live_thought import get_thought

    t = get_thought()
    if not t or not str(t.get("query") or "").strip():
        return {"objects": [], "links": [], "motion": [], "duration": 0.0,
                "meta": {"idle": True}}
    # the mind is recalling a SPACE — the orb rebuilds that remembered room, not a concept scene
    if t.get("mode") == "replay":
        from packages.perception.spatial_memory import reconstruct_scene, recall_snapshot

        scene = reconstruct_scene(recall_snapshot(place=t.get("place")), duration=duration)
        scene["meta"] = {**scene.get("meta", {}), "live_query": t.get("query"), "at": t.get("at")}
        return scene
    key = (str(t["query"]), t.get("at"), tuple(t.get("evidence") or []), round(float(duration), 2))
    hit = _SCENE_CACHE.get(key)
    if hit is not None:
        return hit
    scene = _scene_for_query(str(t["query"]), duration,
                             extra_labels=list(t.get("evidence") or []))
    scene["meta"] = {**scene.get("meta", {}), "live_query": t.get("query"), "at": t.get("at"),
                     "answer_kind": t.get("answer_kind")}
    if len(_SCENE_CACHE) >= _SCENE_CACHE_MAX:          # tiny ring — thoughts churn, memory must not
        _SCENE_CACHE.pop(next(iter(_SCENE_CACHE)))
    _SCENE_CACHE[key] = scene
    return scene


def _scene_for_query(query: str, duration: float,
                     extra_labels: list[str] | None = None) -> dict[str, Any]:
    from packages.base_brain.neighborhood import _content_tokens, gather_neighborhood

    q = str(query or "").strip()
    concepts = _pack_concepts()
    if not q or not concepts:
        return compile_scene([], [], duration=duration)

    qn = q.replace(" ", "")
    subject = next((c for c in concepts
                    if str(c.get("canonical_name", "")).replace(" ", "") == qn), None)
    neighbors = gather_neighborhood(q, concepts, limit=7)
    if subject is not None and len([c for c in neighbors if c is not subject]) < 3:
        by_name: dict[str, dict[str, Any]] = {}
        for c in concepts:
            nm = str(c.get("canonical_name", "")).replace(" ", "")
            if nm and nm != qn:
                by_name.setdefault(nm, c)
        have = {id(c) for c in neighbors} | {id(subject)}
        for tok in _content_tokens(str(subject.get("short_description") or "")):
            c = by_name.get(tok.replace(" ", ""))
            if c is not None and id(c) not in have:
                neighbors.append(c)
                have.add(id(c))

    # the answer's OWN evidence concepts (what it actually reasoned over) join first — each
    # resolved against the pack by name, so the projection shows the real thought flow, grounded.
    for lbl in (extra_labels or []):
        ln = str(lbl).replace(" ", "")
        if not ln or ln == qn:
            continue
        c = next((c for c in concepts
                  if str(c.get("canonical_name", "")).replace(" ", "") == ln), None)
        if c is not None and c is not subject and all(c is not n for n in neighbors):
            neighbors.insert(0, c)

    if subject is None and neighbors:
        subject, neighbors = neighbors[0], neighbors[1:]

    scene_concepts: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(c: dict[str, Any], weight: float) -> str:
        cid = str(c.get("concept_id") or c.get("canonical_name") or "")
        if cid and cid not in seen:
            seen.add(cid)
            scene_concepts.append({"id": cid, "label": c.get("canonical_name") or cid,
                                   "desc": c.get("short_description") or "", "weight": weight})
        return cid

    if subject is None:                                  # nothing grounded — a lone query node
        sid = q
        scene_concepts.append({"id": sid, "label": q, "desc": "", "weight": 1.0})
    else:
        sid = add(subject, 1.0)
    for c in neighbors[:6]:
        nid = add(c, 0.5)
        if nid and nid != sid:
            # the graph relates them topically; carry an explicit predicate if the subject names one
            relations.append({"from": sid, "to": nid, "predicate": "관련"})

    # merge MINED kinetic relations (web-consensus motion ledger): if the corroborated web says

    # nodes carrying their consensus provenance — presentation layer, not answer facts.
    try:
        from packages.imagination.motion_miner import motion_relations_for

        by_label = {str(c["label"]).replace(" ", ""): c["id"] for c in scene_concepts}
        for rel in motion_relations_for(set(by_label.keys()))[:8]:
            s_l = str(rel.get("subject") or "").replace(" ", "")
            o_l = str(rel.get("object") or "").replace(" ", "")
            for lbl in (s_l, o_l):
                if lbl and lbl not in by_label:
                    by_label[lbl] = lbl
                    scene_concepts.append({"id": lbl, "label": rel["subject"] if lbl == s_l else rel["object"],
                                           "desc": "웹 합의(2+도메인) 운동 관계", "weight": 0.4})
            if s_l and o_l:


                # mover is always `to`, its anchor `from`.
                mover, anchor = (s_l, o_l) if rel.get("motion") == "orbit" else (o_l, s_l)
                relations.append({"from": by_label[anchor], "to": by_label[mover],
                                  "predicate": rel.get("predicate", "")})
            elif s_l:                                     # intransitive: the subject itself moves
                relations.append({"from": by_label[s_l], "to": by_label[s_l],
                                  "predicate": rel.get("predicate", "")})
    except Exception:
        pass

    return compile_scene(scene_concepts, relations, subject_id=sid, duration=duration)
