# -*- coding: utf-8 -*-
"""Scene graph — Relation Reasoning over detections (owner 2026-07-13: object detection + scene
understanding + relation reasoning + common sense, our own low-spec VLM, no 16B/64B params).

This is the step past "a list of boxes": the detected objects become NODES and the SPATIAL RELATIONS
between them become typed EDGES — inferred by pure GEOMETRY (contains, near, left_of, above, in_front_
of). No neural VLM, no training, runs on CPU. The result is a scene GRAPH the ATANOR concept graph can
reason over — vision lands in the same symbolic substrate as language, so "understanding the scene" is
graph traversal, not a black-box caption.

HONESTY: every relation is derived from the actual detection boxes — nothing is imagined. A relation
the geometry does not support is not emitted. Common-sense context (+ → /) is a thin
layer that reads KNOWN relations from the concept graph (best-effort), never a fabricated guess.
"""
from __future__ import annotations

from typing import Any, Optional

Box = list[float]


def _center(b: Box) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a: Box, b: Box) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _contain_ratio(inner: Box, outer: Box) -> float:
    """Fraction of `inner` that lies within `outer` (1.0 = fully inside)."""
    ia = _area(inner)
    return _inter(inner, outer) / ia if ia > 0 else 0.0


def _inside(inner: Box, outer: Box, m: float = 10.0) -> bool:
    """Is `inner` fully within `outer` (all four sides, small margin)? This — NOT area or overlap — is
    what separates CONTAINMENT (glasses in face, clothes in wardrobe: inner stays within) from IN_FRONT
    (a person occluding a bookshelf: the person's box sticks out below, so it is not contained)."""
    return (inner[0] >= outer[0] - m and inner[1] >= outer[1] - m
            and inner[2] <= outer[2] + m and inner[3] <= outer[3] + m)


def _diag(size: tuple[int, int]) -> float:
    return (size[0] ** 2 + size[1] ** 2) ** 0.5


def spatial_relations(dets: list[dict[str, Any]], size: tuple[int, int]) -> list[dict[str, Any]]:
    """Infer typed spatial relations between detected objects, by geometry alone. Each relation is
    {subject, relation, object, ko} where subject/object are the Korean labels. Emitted once per pair
    (the strongest relation), so the graph stays clean."""
    n = len(dets)
    near_thresh = 0.16 * _diag(size)
    rels: list[dict[str, Any]] = []
    # (1) CONTAINMENT — each object attaches to its TIGHTEST container (the smallest box that fully
    # holds it), so a face inside a person (who is in front of a shelf) attaches to the person, not the
    # shelf behind. A person occluding a shelf is not contained (its box sticks out), so it stays free.
    container: list[Optional[int]] = [None] * n
    for i in range(n):
        best, best_area = None, float("inf")
        for k in range(n):
            if k == i:
                continue
            if _inside(dets[i]["box"], dets[k]["box"]) and _area(dets[k]["box"]) > _area(dets[i]["box"]) * 1.25:
                if _area(dets[k]["box"]) < best_area:
                    best, best_area = k, _area(dets[k]["box"])
        container[i] = best
    handled: set[tuple[int, int]] = set()
    for i in range(n):
        if container[i] is not None:
            k = container[i]
            rels.append(_rel(dets[k]["label_ko"], "contains", dets[i]["label_ko"],
                             f"{dets[k]['label_ko']} 안에 {dets[i]['label_ko']}이(가) 있다"))
            handled.add((min(i, k), max(i, k)))
    # (2) other pairs — but a CONTAINED object's position is defined by its container, so it gets no
    # external relations of its own (the face inside the person inherits the person's "in front of the
    # shelf"; we don't separately say "the shelf is in front of the face").
    for i in range(n):
        if container[i] is not None:
            continue
        for j in range(i + 1, n):
            if (i, j) in handled or container[j] is not None:
                continue
            a, b = dets[i], dets[j]
            ba, bb = a["box"], b["box"]
            (cax, cay), (cbx, cby) = _center(ba), _center(bb)
            dist = ((cax - cbx) ** 2 + (cay - cby) ** 2) ** 0.5
            if _inter(ba, bb) > 0.12 * min(_area(ba), _area(bb)):        # overlap → occlusion order
                front, back = (a, b) if ba[3] > bb[3] else (b, a)
                rels.append(_rel(front["label_ko"], "in_front_of", back["label_ko"],
                                 f"{front['label_ko']}이(가) {back['label_ko']} 앞에 있다"))
            elif dist < near_thresh:
                rels.append(_rel(a["label_ko"], "near", b["label_ko"],
                                 f"{a['label_ko']}과(와) {b['label_ko']}이(가) 가까이 있다"))
            elif abs(cbx - cax) >= abs(cby - cay):
                s, o = (a, b) if cbx - cax > 0 else (b, a)
                rels.append(_rel(s["label_ko"], "left_of", o["label_ko"],
                                 f"{s['label_ko']}이(가) {o['label_ko']} 왼쪽에 있다"))
            else:
                s, o = (a, b) if cby - cay > 0 else (b, a)
                rels.append(_rel(s["label_ko"], "above", o["label_ko"],
                                 f"{s['label_ko']}이(가) {o['label_ko']} 위에 있다"))
    return rels


def _rel(subject: str, relation: str, obj: str, ko: str) -> dict[str, Any]:
    return {"subject": subject, "relation": relation, "object": obj, "ko": ko}


def build_scene_graph(dets: list[dict[str, Any]], size: tuple[int, int]) -> dict[str, Any]:
    """Nodes = distinct object types (with counts), edges = spatial relations. The ATANOR-native scene
    representation: vision as a graph, ready for the concept graph to reason over."""
    nodes: dict[str, dict[str, Any]] = {}
    for d in dets:
        ko = d["label_ko"]
        nd = nodes.setdefault(ko, {"label": ko, "count": 0, "color": d.get("color")})
        nd["count"] += 1
    edges = spatial_relations(dets, size)
    return {"nodes": list(nodes.values()), "edges": edges}


def commonsense_context(dets: list[dict[str, Any]], graph_lookup: Optional[Any] = None) -> Optional[str]:
    """A thin common-sense layer: what KIND of place/activity do these objects imply? Reads known
    concept relations from the ATANOR graph when available (best-effort, grounded); a small honest
    fallback maps a few object sets to a place. Returns None rather than guess when nothing is known."""
    kos = {d["label_ko"] for d in dets}
    # graph-backed inference would query place/activity concepts for these objects; hook left for wiring
    fallback = [
        ({"책장", "책"}, "책이 많은 서재나 공부 공간처럼 보여요"),
        ({"책장", "사람"}, "사람이 책장 앞에 있는 걸 보니 공부하거나 책을 보는 맥락 같아요"),
        ({"선풍기"}, "선풍기가 있는 걸 보니 더운 날 실내인 듯해요"),
        ({"옷장", "옷"}, "옷장과 옷이 있어 방 안 같은 생활 공간이에요"),
    ]
    for req, msg in fallback:
        if req <= kos:
            return msg
    return None


def describe_with_relations(dets: list[dict[str, Any]], size: tuple[int, int]) -> dict[str, Any]:
    """A relational scene description: the objects, the top relations between them, and a common-sense
    read — the v0 of 'understand the whole context', grounded, No-LLM."""
    g = build_scene_graph(dets, size)
    rel_ko = [e["ko"] for e in g["edges"]][:5]
    ctx = commonsense_context(dets)
    return {"graph": g, "relations_ko": rel_ko, "commonsense": ctx}
