# -*- coding: utf-8 -*-
"""Semantic-bottleneck reconstruction audit — the honest v0 of the owner's autoencoder vision
(2026-07-12): extract context from a scene, rebuild the scene from THAT CONTEXT ONLY, and measure
what survived. If the rebuild can't recover it, the context never contained it.

Three doctrine decisions make this v0 honest (and cheap enough for this box):
  * the decoder is DUMB on purpose — reconstruct_scene is deterministic. A generative decoder
    (diffusion) would paint plausible detail the context never held, hiding extraction gaps and
    poisoning the signal. The bottleneck test only works when the only way to pass is better context.
  * the loss is SEMANTIC TOPOLOGY, not pixels — object identity (set F1), pairwise spatial ORDER
    (left/right, above/below, nearer/farther), position error. Pixel-perfect would reward noise.
  * our extractor is symbolic (non-differentiable), so "training" v0 is a MEASURED CURRICULUM:
    `capacity` names the attributes the truth had that the context schema dropped — the exact list
    of what perception must learn to record next. Fix the schema → rerun → score rises. Flywheel.

Diffusion / feed-forward Gaussian regression (ml-sharp style) enters LATER as an optional realism
RENDERER on GPU hardware — never as the truth signal.
"""
from __future__ import annotations

from typing import Any

_EPS = 0.04                 # deadzone for order comparisons — sub-noise differences don't count
# richer truth attributes the audit checks the schema against, in curriculum order. size+hue are
# mineable from the current sensor (bbox + crop); orientation needs pose/segmentation vision, so it
# stays an HONEST next lesson (named, not faked) until that sensor lands.
_ATTRS = ("size", "hue", "orientation")


def _match(truth: list[dict[str, Any]], probe: list[dict[str, Any]]
           ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Pair truth↔probe objects by label, nearest-position first for duplicate labels."""
    used: set[int] = set()
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for t in truth:
        best_j, best_d = -1, 9e9
        for j, p in enumerate(probe):
            if j in used or str(p.get("label")) != str(t.get("label")):
                continue
            d = abs(float(p.get("x", .5)) - float(t.get("x", .5))) + \
                abs(float(p.get("y", .5)) - float(t.get("y", .5)))
            if d < best_d:
                best_j, best_d = j, d
        if best_j >= 0:
            used.add(best_j)
            pairs.append((t, probe[best_j]))
    return pairs


def topology_score(truth: list[dict[str, Any]], probe: list[dict[str, Any]]) -> dict[str, Any]:
    """How much of the truth's SEMANTIC STRUCTURE survives in the probe. Components reported
    separately (an honest breakdown, never one opaque number):
      set_f1    — are the same objects there?
      relation  — for every matched pair: is the spatial ORDER (x/y/depth sign) preserved?
      position  — mean position error over matches, as 1-err;
      capacity  — which truth attributes the probe carries vs DROPPED (the curriculum)."""
    truth, probe = list(truth or []), list(probe or [])
    if not truth:
        return {"set_f1": 1.0 if not probe else 0.0, "relation": 1.0, "position": 1.0,
                "total": 1.0 if not probe else 0.0, "matched": 0,
                "capacity": {"preserved": [], "dropped": []}}
    pairs = _match(truth, probe)
    m = len(pairs)
    prec = m / len(probe) if probe else 0.0
    rec = m / len(truth)
    set_f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0

    # pairwise order consistency across matched objects (the topology that MEANS "where things are")
    ok = tot = 0
    for i in range(m):
        for j in range(i + 1, m):
            (t1, p1), (t2, p2) = pairs[i], pairs[j]
            for axis in ("x", "y", "depth"):
                dt = float(t1.get(axis, .5)) - float(t2.get(axis, .5))
                if abs(dt) < _EPS:
                    continue                       # truth itself has no order here — nothing to preserve
                dp = float(p1.get(axis, .5)) - float(p2.get(axis, .5))
                tot += 1
                if dt * dp > 0:
                    ok += 1
    relation = ok / tot if tot else 1.0

    pos_err = sum(abs(float(t.get("x", .5)) - float(p.get("x", .5))) +
                  abs(float(t.get("y", .5)) - float(p.get("y", .5))) +
                  abs(float(t.get("depth", .5)) - float(p.get("depth", .5)))
                  for t, p in pairs) / (3 * m) if m else 1.0
    position = max(0.0, 1.0 - pos_err * 2)

    preserved, dropped = [], []
    for attr in _ATTRS:
        if not any(attr in t for t in truth):
            continue                               # truth doesn't carry it — nothing to test
        if pairs and all(attr in p and abs(float(p[attr]) - float(t[attr])) <= 0.1 * max(1.0, float(t[attr]))
                         for t, p in pairs if attr in t):
            preserved.append(attr)
        else:
            dropped.append(attr)

    total = round((set_f1 + relation + position) / 3, 4)
    return {"set_f1": round(set_f1, 4), "relation": round(relation, 4),
            "position": round(position, 4), "total": total, "matched": m,
            "capacity": {"preserved": preserved, "dropped": dropped}}


def _invert_scene(scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Scene space → image space (the exact inverse of reconstruct_scene's transform), plus any
    attributes the scene object carried through. What this can't recover, the context lost."""
    out: list[dict[str, Any]] = []
    for o in scene.get("objects") or []:
        px, py, pz = (o.get("pos") or [0, 0, 0])[:3]
        rec: dict[str, Any] = {"label": str(o.get("label", "")).split("#")[0],
                               "x": (float(px) + 1) / 2, "y": (1 - float(py)) / 2,
                               "depth": (float(pz) + 1) / 2}
        for attr in _ATTRS:
            if attr in o:
                rec[attr] = o[attr]
        out.append(rec)
    return out


# a synthetic room whose truth WE define — so the audit needs no camera and lies about nothing.
# It carries size+hue on purpose: the capacity probe shows which of them the pipeline can hold.
_FIXTURE: list[dict[str, Any]] = [
    {"label": "물병", "x": 0.25, "y": 0.62, "depth": 0.28, "size": 0.06, "hue": 200.0, "orientation": 0.0},
    {"label": "노트북", "x": 0.62, "y": 0.55, "depth": 0.35, "size": 0.18, "hue": 30.0, "orientation": 90.0},
    {"label": "컵", "x": 0.48, "y": 0.70, "depth": 0.22, "size": 0.03, "hue": 10.0, "orientation": 0.0},
    {"label": "화분", "x": 0.82, "y": 0.40, "depth": 0.66, "size": 0.10, "hue": 120.0, "orientation": 45.0},
]


def cycle_audit(truth: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One full bottleneck cycle, ledger-free: truth → context (the snapshot schema, exactly what
    record_snapshot would keep) → reconstruct_scene → invert → compare to truth. The score is the
    pipeline's real fidelity; `capacity.dropped` is the next lesson perception must learn."""
    from packages.perception.spatial_memory import reconstruct_scene

    truth = list(truth or _FIXTURE)
    # the CONTEXT: pass truth through the same distillation record_snapshot applies (schema fields
    # only) — a pure in-memory snapshot, so audits never pollute the real spatial ledger
    context = {"id": "audit", "place": "감사", "objects": [
        {"label": t["label"], "x": t["x"], "y": t["y"], "depth": t.get("depth", 0.5),
         **({"size": t["size"]} if "size" in t else {}),
         **({"hue": t["hue"]} if "hue" in t else {})} for t in truth]}
    scene = reconstruct_scene(context)
    probe = _invert_scene(scene)
    score = topology_score(truth, probe)
    return {**score, "n_truth": len(truth), "n_rebuilt": len(probe),
            "decoder": "deterministic — generative decoders are barred from the truth signal",
            "next_lessons": score["capacity"]["dropped"]}
