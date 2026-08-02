# -*- coding: utf-8 -*-
"""The sixth witness, measured instead of argued: can a physics channel testify about kind?

WHAT THIS IS. The witness series (value / co-occurrence / neighbour-kinds / value-only / web) tested
whether a second evidence source is admissible next to the symbolic substrate, on three conditions:
INDEPENDENCE (its errors are not the substrate's errors), COMPETENCE (it is better than chance), and
SHARED REFERENTS (its evidence is about the same defendants). The 4D world state was refused at the
third condition on an argument. This measures the second condition on data, because an argument is
not a measurement and the refusal deserves better than one.

WHERE THE DATA COMES FROM. 5,509,430 per-frame positions of 190 moving objects in Realcity, captured
by a three-line probe that exported the position each frame had ALREADY computed. Nothing about the
capture reads a kind label, so the trajectory cannot have been coloured by the answer.

THE DISCONTINUITY CAP, declared because it is the one cleaning step. Cars advance along a looped path
by `carTs % 1`, so once per lap a car jumps from the end of its path back to the start -- one frame,
several hundred units. The fastest declared speed in the world is 12 m/s and dt is capped at 0.05s
(Traffic.jsx), so the largest legitimate one-frame step is 0.6 units. Steps above 1.0 are dropped as
wraps. The threshold comes from the simulator's own bounds, applies identically to both kinds, and
removed 79 steps from cars and 0 from NPCs out of 5.5M.

THE TWO TASKS, and why the second is the real one.

  A  car vs NPC.  Expected easy and it does not prove much: Traffic.jsx moves cars at 6-12 m/s and
     NPCSystem.jsx moves NPCs at 1.2 m/s, so the speed ranges are disjoint by construction. Reported
     because a witness that cannot pass the easy task is broken, not because passing it is evidence.

  B  NPC ROLE, 10 classes.  This one can fail, and the source says exactly how. `NPCAgent.update()`
     never reads `this.role` -- the walk is identical for a banker and a jogger -- so DYNAMICS carry
     no role information at all. But roles are drawn from `NPC_ROLES[zone(dist)]`, a pool chosen by
     spawn distance from the city centre, so PLACE does carry role information.

PRE-REGISTERED, from reading the generator BEFORE running anything, against a MEASURED null (the
permutation distribution below) rather than against intuition -- the correction that cost this
project four separate errors:

     B/dynamics  at chance.        No mechanism connects role to motion.
     B/place     above chance.     zone(dist) -> role pool is a real dependence.

If that split comes out, the physics channel is competent about WHERE and mute about WHAT, and the
honest description of the sixth witness is not "incompetent" but "competent on a different question".

THE NULL. Labels are permuted 2000 times and the whole leave-one-out procedure re-run. Because
permuting labels does not touch the features, each object's nearest neighbour under leave-one-out
standardisation is fixed and computed once; the permutation is then exact, not approximate. Chance
for these tasks is NOT 1/k -- classes are unbalanced and a nearest-neighbour rule exploits that -- so
the permutation mean is the null, and 1/k is reported only for orientation.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "physics_witness" / "proofs"
sys.path.insert(0, str(ROOT))

# --- partitions, first cut: KEPT ON THE RECORD BECAUSE IT WAS DEFECTIVE -------------------------
# This split was fixed before the run and it did not do what its names claim. Every speed here is a
# 3-D magnitude, so it contains dy -- and dy is the terrain gradient under the object, which is a
# function of WHERE IT IS. `vt_mean` is nothing but terrain slope. So `DYNAMICS` silently carried
# place, and `PLACE` carried motion in return: `ext_x`/`ext_z` are how far the object RANGED, which
# is a property of how it moves, not of where it is. The results from this cut are reported below
# and are not deleted; the corrected cut is measured alongside them.
PLACE = ["y_mean", "y_std", "y_range", "ext_x", "ext_z", "radius_mean"]
DYNAMICS = ["sp_mean", "sp_std", "sp_p50", "sp_p90", "sp_p99", "hz_mean", "vt_mean",
            "idle_frac", "rev_frac", "turn_mean", "turn_std", "straight_w"] + [f"h{i}" for i in range(12)]

# --- partitions, corrected: cut by WHAT EACH QUANTITY IS A FUNCTION OF ---------------------------
# MOTION_H is built only from (dx, dz) steps. In NPCSystem.jsx the horizontal walk is computed from
# `heading` alone -- terrain enters only through the y it is then placed at -- so these five numbers
# cannot see the terrain and therefore cannot see position. That makes MOTION_H the clean test of
# the pre-registration: NPCAgent.update() never reads `this.role`, so if role is not predictable
# here, it is not in the motion.
MOTION_H = ["hz_mean", "idle_frac", "rev_frac", "turn_mean", "turn_std"]
# TERRAIN is height and vertical step: a pure function of position through getTerrainHeight().
TERRAIN = ["y_mean", "y_std", "y_range", "vt_mean"]
# EXTENT is how far the object ranged -- a motion property that the first cut miscalled place.
EXTENT = ["ext_x", "ext_z"]
# LOCATION is the generator's own causal variable: zone(dist) picks the role pool from sqrt(x^2+z^2).
LOCATION = ["radius_mean"]


def load() -> tuple[list[dict], list[str]]:
    rows = list(csv.DictReader((DATA / "realcity_traj_features.csv").open(encoding="utf-8")))
    roles = {r["id"]: r["role"] for r in csv.DictReader((DATA / "realcity_npc_roles.csv").open(encoding="utf-8"))}
    for r in rows:
        r["role"] = roles.get(r["id"], "")
    cols = [c for c in rows[0] if c not in ("id", "kind", "role")]
    return rows, cols


def matrix(rows: list[dict], cols: list[str]) -> np.ndarray:
    return np.array([[float(r[c]) for c in cols] for r in rows], dtype=float)


def loo_neighbour(X: np.ndarray) -> np.ndarray:
    """For each row, its nearest OTHER row, standardised on the held-out fold only.

    Standardising on all rows would let the test row shift the scale it is judged by. It is a small
    leak at n=190 and it is still a leak, and the fix costs one loop."""
    n = len(X)
    nn = np.empty(n, dtype=int)
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        tr = X[mask]
        mu, sd = tr.mean(0), tr.std(0)
        sd = np.where(sd < 1e-12, 1.0, sd)          # a constant column carries nothing; do not blow it up
        Z = (X - mu) / sd
        d = np.linalg.norm(Z - Z[i], axis=1)
        d[i] = np.inf
        nn[i] = int(np.argmin(d))
    return nn


def loo_centroid(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Leave-one-out nearest-centroid prediction indices -> predicted class labels."""
    n = len(X)
    out = np.empty(n, dtype=object)
    classes = sorted(set(y))
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        tr, ytr = X[mask], y[mask]
        mu, sd = tr.mean(0), tr.std(0)
        sd = np.where(sd < 1e-12, 1.0, sd)
        Z, zi = (tr - mu) / sd, (X[i] - mu) / sd
        best, bd = None, np.inf
        for c in classes:
            sel = ytr == c
            if not sel.any():
                continue
            d = float(np.linalg.norm(Z[sel].mean(0) - zi))
            if d < bd:
                best, bd = c, d
        out[i] = best
    return out


def evaluate(name: str, rows: list[dict], cols: list[str], label: str, perms: int = 2000) -> dict:
    y = np.array([r[label] for r in rows], dtype=object)
    X = matrix(rows, cols)
    nn = loo_neighbour(X)
    top1 = float((y[nn] == y).mean())
    cen = loo_centroid(X, y)
    cen_acc = float((cen == y).mean())

    rng = np.random.default_rng(20260729)           # fixed so the null is reproducible, not re-rollable
    null = np.empty(perms)
    for p in range(perms):
        ys = rng.permutation(y)
        null[p] = (ys[nn] == ys).mean()
    _, counts = np.unique(y, return_counts=True)

    return {
        "task": name, "label": label, "n": len(rows), "classes": int(len(set(y))),
        "features": len(cols),
        "top1_1nn": round(top1, 4),
        "top1_centroid": round(cen_acc, 4),
        "majority_baseline": round(float(counts.max() / counts.sum()), 4),
        "one_over_k": round(1.0 / len(set(y)), 4),
        "null_mean": round(float(null.mean()), 4),
        "null_p95": round(float(np.percentile(null, 95)), 4),
        "p_value": round(float(((null >= top1).sum() + 1) / (perms + 1)), 5),
        "x_null": round(top1 / max(null.mean(), 1e-9), 2),
    }


def substrate_probe(rows: list[dict], label: str) -> dict:
    """Does the substrate's OWN scoring rule -- unchanged -- classify continuous world states?

    The mapping is structural, not semantic: a histogram bin plays the part of a predicate, and
    "has mass in this bin" plays the part of "holds this predicate". Nothing is given a name and no
    role is invented, which is the line `read_schema` and `_bridging` were both refused at. What is
    chosen is the DISCRETISATION -- 12 bins over [0, 0.30] speed -- and that choice is mine, so this
    is reported as a probe of the scoring rule and not as a second measurement of the witness."""
    from packages.substrate import Behaviour, decisive_kind

    bins = [f"h{i}" for i in range(12)]
    beh = {}
    for r in rows:
        v = {b: float(r[b]) for b in bins if float(r[b]) > 0.0}
        tot = sum(v.values())
        beh[r["id"]] = Behaviour(r["id"], {k: x / tot for k, x in v.items()} if tot else {}, len(v))

    y = {r["id"]: r[label] for r in rows}
    ids = [r["id"] for r in rows]
    right = wrong = abstained = 0
    for held in ids:
        prof: dict[str, dict[str, float]] = {}
        for k in sorted(set(y.values())):
            members = [i for i in ids if i != held and y[i] == k]
            if not members:
                continue
            prof[k] = {b: sum(1.0 for m in members if beh[m].shares.get(b, 0.0) > 0.0) / len(members)
                       for b in bins}
        kind, _score, _why = decisive_kind(beh[held], prof)
        if kind is None:
            abstained += 1
        elif kind == y[held]:
            right += 1
        else:
            wrong += 1
    placed = right + wrong
    return {"probe": "substrate decisive_kind on speed histogram", "label": label, "n": len(ids),
            "placed": placed, "abstained": abstained,
            "coverage": round(placed / len(ids), 4),
            "accuracy_on_placed": round(right / placed, 4) if placed else None}


def error_correlation(npcs: list[dict], sets: dict[str, list[str]]) -> dict:
    """Phi between the CORRECTNESS vectors of two witnesses over the SAME defendants.

    This is the independence half of the witness test, and it is the half the graph witnesses cannot
    take part in. Independence is only defined when both witnesses judge the same defendants, and a
    Realcity object has no counterpart in the graph -- `npc17` is not an entity the substrate has a
    single fact about, so its error vector there is undefined, not uncorrelated. What CAN be
    measured is whether the two physics channels are independent of each other, which is reported
    here because it is the honest thing this data supports."""
    y = np.array([r["role"] for r in npcs], dtype=object)
    correct: dict[str, np.ndarray] = {}
    for name, cols in sets.items():
        nn = loo_neighbour(matrix(npcs, cols))
        correct[name] = (y[nn] == y).astype(float)
    names = sorted(correct)
    out = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = correct[names[i]], correct[names[j]]
            if a.std() < 1e-12 or b.std() < 1e-12:
                out[f"{names[i]} x {names[j]}"] = None
                continue
            out[f"{names[i]} x {names[j]}"] = round(float(np.corrcoef(a, b)[0, 1]), 4)
    return out


def zone_ceiling(npcs: list[dict]) -> dict:
    """The most any position-based witness could score, because zone is all position gives it.

    `zone(dist)` returns one of four names and the role is then drawn UNIFORMLY from that zone's
    pool, so position tells a witness which pool -- and nothing about which draw. The ceiling is
    therefore the leave-one-out majority role within each zone. A place-based witness scoring at
    this number has extracted everything there is; scoring below it has not; scoring above it is
    reading something other than zone."""
    zones = {r["id"]: r["zone"] for r in csv.DictReader(
        (DATA / "realcity_npc_roles.csv").open(encoding="utf-8"))}
    right = 0
    for r in npcs:
        z, own = zones[r["id"]], r["role"]
        others = [o["role"] for o in npcs if o["id"] != r["id"] and zones[o["id"]] == z]
        if others and max(set(others), key=others.count) == own:
            right += 1
    counts: dict[str, int] = {}
    for r in npcs:
        counts[zones[r["id"]]] = counts.get(zones[r["id"]], 0) + 1
    return {"zone_ceiling_loo": round(right / len(npcs), 4), "zones": counts}


def main() -> None:
    rows, cols = load()
    npcs = [r for r in rows if r["kind"] == "npc"]

    out = {
        "source": {"objects": len(rows), "samples": 5_509_430, "frames_per_object": 28_997,
                   "cars": sum(1 for r in rows if r["kind"] == "car"), "npcs": len(npcs),
                   "discontinuities_dropped": {"car": 79, "npc": 0}},
        "prereg": {"B_dynamics": "at chance", "B_place": "above chance",
                   "basis": "NPCAgent.update() ignores this.role; role drawn from NPC_ROLES[zone(dist)]"},
        "zone_ceiling": zone_ceiling(npcs),
        "results": [
            evaluate("A: kind (car vs npc), all features", rows, cols, "kind"),
            evaluate("A: kind, MOTION_H (terrain-blind)", rows, MOTION_H, "kind"),
            evaluate("A: kind, TERRAIN", rows, TERRAIN, "kind"),
            evaluate("B: npc role, all features", npcs, cols, "role"),
            evaluate("B: npc role, dynamics only [defective cut]", npcs, DYNAMICS, "role"),
            evaluate("B: npc role, place only [defective cut]", npcs, PLACE, "role"),
            evaluate("B: npc role, MOTION_H (terrain-blind)", npcs, MOTION_H, "role"),
            evaluate("B: npc role, TERRAIN", npcs, TERRAIN, "role"),
            evaluate("B: npc role, EXTENT", npcs, EXTENT, "role"),
            evaluate("B: npc role, LOCATION (radius only)", npcs, LOCATION, "role"),
        ],
        "substrate_probe": [substrate_probe(rows, "kind"), substrate_probe(npcs, "role")],
        "error_correlation": error_correlation(
            npcs, {"MOTION_H": MOTION_H, "TERRAIN": TERRAIN, "LOCATION": LOCATION}),
        "error_correlation_with_graph_witnesses":
            "UNDEFINED -- no shared defendants. A Realcity object is not an entity in the shipped "
            "graph, so the graph witnesses have no fact about it and produce no error vector to "
            "correlate against. This is the sixth witness's ORIGINAL refusal, unchanged.",
    }
    (DATA / "physics_witness_result.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{'task':44s} {'top1':>7s} {'cent':>7s} {'major':>7s} {'null':>7s} {'xnull':>6s} {'p':>8s}")
    for r in out["results"]:
        print(f"{r['task']:44s} {r['top1_1nn']:7.3f} {r['top1_centroid']:7.3f} "
              f"{r['majority_baseline']:7.3f} {r['null_mean']:7.3f} {r['x_null']:6.2f} {r['p_value']:8.5f}")
    print()
    for p in out["substrate_probe"]:
        print(f"substrate rule on {p['label']:5s}: coverage {p['coverage']:.3f} "
              f"({p['placed']}/{p['n']}), accuracy_on_placed {p['accuracy_on_placed']}")
    print()
    print(f"zone ceiling (LOO majority within zone): {out['zone_ceiling']['zone_ceiling_loo']}")
    for k, v in out["error_correlation"].items():
        print(f"error corr  {k:24s} {v}")


if __name__ == "__main__":
    main()
