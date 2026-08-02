# -*- coding: utf-8 -*-
"""Mechanism-proof harness for the V-JEPA latent fusion (design: docs/ATANOR_vjepa_fusion.md §7).

This is the DELIVERABLE, not a demo: on controlled/synthetic rendered scenes it measures — honestly,
with precision/recall — whether LATENT prediction error marks semantic events BETTER than the two
existing baselines it fuses alongside:

  (a) the pixel retinal-delta baseline   -> ``attention.change_energy``
  (b) the discrete scene-graph surprise   -> ``video_events`` scene-graph diff

especially on the two adversarial cases the design names:
  * LOW-pixel-delta semantic change   — a real event the pixel delta cannot isolate: an object that
    abruptly reverses its smooth trajectory (a velocity discontinuity) produces a pixel delta no larger
    than the ambient motion it is already firing on, so the pixel delta cannot mark it as a distinct
    event; a small object appearing perturbs few pixels. Neither is in the scene graph as an attribute
    the discrete baseline tracks (the reversal) — so the discrete baseline is blind to it too.
  * HIGH-pixel-delta NON-events        — a global lighting surge and a pixel-noise burst: many pixels
    change, no semantic event; the pixel delta false-fires.

It then re-runs the whole scorecard on a HELD-OUT sequence the coder never trained on (generalization,
structure not memorization) and runs the collapse check.

Everything is a rendered SYNTHETIC world whose ground truth WE define, so the audit needs no camera and
lies about nothing. The ambient dynamic is deliberately SMOOTH and PREDICTABLE (parametric orbits, no
wall bounces) and the nuisance regime (gentle lighting drift + mild noise) is present in TRAINING too —
that is how a JEPA encoder earns its invariances, and it makes the scripted events genuine departures
the coder was never trained on. Deterministic (seeded). Pure numpy + the perception organs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from packages.perception.attention import change_energy, frame_signature
from packages.perception.latent_predictor import CoderConfig, LatentPredictiveCoder
from packages.perception.video_events import diff_frames

# ---- rendered world -----------------------------------------------------------------------
_H = _W = 96                 # canvas; frame_signature downsamples to the 32x32 retinal code
_NEAR = 20.0                 # canvas-space distance under which two objects form a 'near' edge
_BG = 0.25                   # background grey level (kept low so the lighting ramp never saturates)
_AMBIENT_NOISE = 0.012       # always-on mild sensor noise sd (the irreducible surprise floor)


@dataclass
class _Obj:
    """A rendered blob on a SMOOTH parametric orbit (no wall bounces -> fully predictable motion).
    pos(t) = center + orbit_r * (cos, sin)(w*t + phase). The 'mover' can flip its orbital direction at
    scripted frames — a velocity discontinuity that is our sub-symbolic (graph-invisible) event."""
    label: str
    cx: float
    cy: float
    orbit_r: float
    w: float
    phase: float
    r: float                 # blob radius (soft gaussian)
    b: float                 # brightness
    spawn_t: int = 0
    die_t: int = 10 ** 9
    is_mover: bool = False


def _pos_at(o: _Obj, t: int, theta_mover: float) -> tuple[float, float]:
    if o.is_mover:
        return o.cx + o.orbit_r * np.cos(theta_mover), o.cy + o.orbit_r * np.sin(theta_mover)
    ang = o.w * t + o.phase
    return o.cx + o.orbit_r * np.cos(ang), o.cy + o.orbit_r * np.sin(ang)


def _render(placed: list[tuple[float, float, float, float]], light: float,
            noise: np.ndarray | None) -> np.ndarray:
    """Rendered grayscale frame in [0,255] from (x,y,r,b) blobs on a grey field, plus a global lighting
    offset and an optional additive-noise field. NO frame is ever stored downstream; this is only the
    synthetic sensor input for the audit."""
    yy, xx = np.mgrid[0:_H, 0:_W]
    img = np.full((_H, _W), _BG, dtype=np.float64)
    for (x, y, r, b) in placed:
        img += b * np.exp(-(((xx - x) ** 2 + (yy - y) ** 2) / (2.0 * r ** 2)))
    img += light
    if noise is not None:
        img += noise
    return np.clip(img, 0.0, 1.0) * 255.0


def _graph(placed_labels: list[tuple[str, float, float]]) -> dict[str, Any]:
    """Per-frame scene graph (the symbolic layer the discrete baseline reads): nodes = present objects,
    edges = 'near' for object pairs within threshold. Derived purely from positions — nothing imagined,
    exactly the shape ``video_events`` consumes."""
    nodes = [{"label": lb, "count": 1} for (lb, _, _) in placed_labels]
    edges = []
    for i in range(len(placed_labels)):
        for j in range(i + 1, len(placed_labels)):
            (la, xa, ya), (lb, xb, yb) = placed_labels[i], placed_labels[j]
            if ((xa - xb) ** 2 + (ya - yb) ** 2) ** 0.5 < _NEAR:
                s, o = sorted([la, lb])
                edges.append({"subject": s, "relation": "near", "object": o})
    return {"nodes": nodes, "edges": edges}


@dataclass
class Sequence:
    sigs: np.ndarray                       # [N, 1024] retinal codes
    graphs: list[dict]                     # per-frame scene graphs
    n: int
    symbolic: set = field(default_factory=set)      # frames with a scene-graph node/edge change
    subsymbolic: set = field(default_factory=set)   # real events NOT in the graph (motion breaks)
    lighting: set = field(default_factory=set)      # high-pixel-delta non-events (lighting surge)
    noise: set = field(default_factory=set)         # high-pixel-delta non-events (noise burst)

    def event_frames(self) -> set:
        """Ground-truth positives: every real semantic event (symbolic OR sub-symbolic)."""
        return self.symbolic | self.subsymbolic

    def nonevent_frames(self) -> set:
        return set(range(1, self.n)) - self.event_frames()


def _ambient_objs(rng: np.random.Generator) -> list[_Obj]:
    """Three ambient objects on smooth orbits in separated regions (so they never form uncontrolled
    near-edges), plus the mover. Same generative RULES every sequence; per-seed parameters differ, so a
    held-out sequence is new arrangement / same physics — the generalization test."""
    objs = []
    centers = [(28, 30), (68, 34), (48, 68)]
    for i, (cx, cy) in enumerate(centers):
        objs.append(_Obj(label=f"obj{i}", cx=cx + rng.uniform(-3, 3), cy=cy + rng.uniform(-3, 3),
                         orbit_r=rng.uniform(6, 10), w=rng.uniform(0.05, 0.12) * (1 if i % 2 else -1),
                         phase=rng.uniform(0, 6.28), r=rng.uniform(6.5, 8.5), b=rng.uniform(0.34, 0.44)))
    # a prominent mover on a clear, faster orbit: a big-enough latent footprint that the coder tracks
    # its phase, so a direction reversal is a clear latent departure — while its pixel delta at the
    # reversal is no larger than during its ordinary motion (the low-pixel-delta adversarial case).
    mover = _Obj(label="mover", cx=76, cy=72, orbit_r=13.0, w=0.17,
                 phase=rng.uniform(0, 6.28), r=9.0, b=0.44, is_mover=True)
    objs.append(mover)
    return objs


def generate(seed: int, n_frames: int = 130, scripted: bool = True) -> Sequence:
    """Build one rendered sequence under fixed generative rules.

    Ambient (ALWAYS present, train + eval): smooth orbits + gentle lighting drift + mild noise — the
    'normal life' the coder learns to predict through and be invariant to.

    Scripted battery (eval / held-out only) — the ground-truth events the coder was NEVER trained on:
      * appear  (small object fades in)          -> symbolic  (low pixel delta: it is small)
      * vanish  (an object leaves)               -> symbolic
      * motion break (mover reverses direction)  -> SUB-symbolic (no graph change; pixel cannot isolate)
      * lighting surge                           -> non-event, high pixel delta
      * noise burst                              -> non-event, high pixel delta
    """
    rng = np.random.default_rng(seed)
    nrng = np.random.default_rng(seed + 7)
    objs = _ambient_objs(rng)
    N = n_frames

    # schedule (only meaningful when scripted)
    appears = [int(N * f) for f in (0.28, 0.50, 0.78)]
    vanishes = [int(N * f) for f in (0.40, 0.66, 0.88)]
    breaks = [int(N * f) for f in (0.22, 0.46, 0.62, 0.84)]
    surge_lo, surge_hi = int(N * 0.33), int(N * 0.37)   # continuous brightness RAMP (every frame moves)
    burst_lo, burst_hi = int(N * 0.70), int(N * 0.76)    # fresh strong noise EVERY frame

    # dynamic object roster: small 'appear' objects get added; vanish kills a chosen present object
    appear_objs = {appears[i]: _Obj(label=f"small{i}", cx=[60, 40, 20][i], cy=[20, 52, 40][i],
                                    orbit_r=4.0, w=0.1, phase=1.0 * i, r=3.2, b=0.40, spawn_t=appears[i])
                   for i in range(len(appears))} if scripted else {}
    vanish_targets = ["obj0", "obj1", "obj2"]

    seq = Sequence(sigs=np.zeros((N, 1024)), graphs=[], n=N)
    theta = objs[-1].phase          # mover angle accumulator
    mover_dir = 1.0
    dead: set[str] = set()
    prev_graph = None

    for t in range(N):
        # mover smooth integration with reversible direction (velocity discontinuity at breaks)
        if scripted and t in breaks:
            mover_dir = -mover_dir
        theta += objs[-1].w * mover_dir

        if scripted and t in appear_objs:
            objs.append(appear_objs[t])
        if scripted and t in vanishes:
            idx = vanishes.index(t)
            dead.add(vanish_targets[idx % len(vanish_targets)])

        placed = []
        placed_labels = []
        for o in objs:
            if o.label in dead or t < o.spawn_t:
                continue
            x, y = _pos_at(o, t, theta)
            placed.append((x, y, o.r, o.b))
            placed_labels.append((o.label, x, y))

        # nuisance: gentle lighting drift + mild noise are ALWAYS on (normal life the coder learns)
        light = 0.03 * np.sin(2 * np.pi * t / 41.0)
        noise = nrng.normal(0, _AMBIENT_NOISE, size=(_H, _W))
        if scripted and surge_lo <= t < surge_hi:   # brightness climbs every frame -> pixel fires each
            light += 0.020 * (t - surge_lo + 1)      # frame; standardization should keep latent quiet
            seq.lighting.add(t)
        if scripted and burst_lo <= t < burst_hi:    # fresh strong noise each frame -> pixel fires each
            noise = noise + nrng.normal(0, 0.13, size=(_H, _W))
            seq.noise.add(t)

        frame = _render(placed, light=light, noise=noise)
        seq.sigs[t] = frame_signature(frame)
        g = _graph(placed_labels)
        seq.graphs.append(g)

        if prev_graph is not None and diff_frames(prev_graph, g, t):
            seq.symbolic.add(t)                     # exactly what the discrete baseline sees
        prev_graph = g

        if scripted and t in breaks:
            seq.subsymbolic.add(t)                  # sub-symbolic ground truth (graph-invisible)

    # keep classes disjoint & clean
    seq.subsymbolic -= seq.symbolic
    seq.lighting -= seq.event_frames()
    seq.noise -= seq.event_frames()
    return seq


# ---- detectors (per-frame score, higher = more 'event') -----------------------------------
def score_pixel(seq: Sequence) -> np.ndarray:
    """Baseline (a): pixel retinal-delta ``change_energy`` between consecutive retinal codes."""
    s = np.zeros(seq.n)
    for t in range(1, seq.n):
        s[t] = change_energy(seq.sigs[t], seq.sigs[t - 1])
    return s


def score_discrete(seq: Sequence) -> np.ndarray:
    """Baseline (b): discrete scene-graph surprise — the count of typed events from the scene-graph
    diff. On synthetic data where WE emit the graph this is effectively the symbolic answer key, so it
    is a STRONG baseline on symbolic events by construction — and, by the same token, blind to anything
    the graph does not encode (the sub-symbolic case)."""
    s = np.zeros(seq.n)
    for t in range(1, seq.n):
        s[t] = float(len(diff_frames(seq.graphs[t - 1], seq.graphs[t], t)))
    return s


def score_latent(coder: LatentPredictiveCoder, seq: Sequence) -> np.ndarray:
    """The fused signal: causal latent surprise s_t = ||z_hat_t - z_t^xi|| from the trained coder."""
    return coder.surprise_stream(seq.sigs)


# ---- metrics ------------------------------------------------------------------------------
def _pr_curve(scores: np.ndarray, positives: set, domain: list[int]) -> dict[str, Any]:
    """Precision/recall over a threshold sweep on ``domain`` frames. Returns best-F1 operating point,
    its threshold, and Average Precision (area under the PR curve, threshold-free)."""
    y = np.array([1 if t in positives else 0 for t in domain])
    x = np.array([scores[t] for t in domain])
    P = int(y.sum())
    if P == 0:
        return {"best_f1": 0.0, "precision": 0.0, "recall": 0.0, "ap": 0.0, "threshold": 0.0, "P": 0}
    order = np.argsort(-x)                       # descending score
    ys = y[order]
    xs = x[order]
    tp = np.cumsum(ys)
    fp = np.cumsum(1 - ys)
    precision = tp / np.maximum(1, tp + fp)
    recall = tp / P
    f1 = 2 * precision * recall / np.maximum(1e-9, precision + recall)
    bi = int(np.argmax(f1))
    dr = np.diff(np.concatenate([[0.0], recall]))
    ap = float(np.sum(precision * dr))          # average precision = area under PR curve
    return {"best_f1": float(f1[bi]), "precision": float(precision[bi]), "recall": float(recall[bi]),
            "ap": ap, "threshold": float(xs[bi]), "P": P}


def _rate(scores: np.ndarray, frames: set, threshold: float) -> float:
    """Fraction of ``frames`` whose score is at/above ``threshold`` (a fire-rate). On event frames this
    is recall; on non-event frames it is the false-positive rate."""
    frames = [t for t in frames if t < len(scores)]
    if not frames:
        return float("nan")
    return float(np.mean([scores[t] >= threshold for t in frames]))


def scorecard(seq: Sequence, s_pixel, s_discrete, s_latent) -> dict[str, Any]:
    """Full head-to-head on one sequence. Overall event detection (AP + best-F1) for all three, plus
    the adversarial breakdown: recall on sub-symbolic vs symbolic events, and the false-positive rate
    on the high-pixel-delta non-events (lighting/noise) — the two places the design predicts a win."""
    domain = list(range(1, seq.n))
    pos = seq.event_frames()
    cards = {name: _pr_curve(sc, pos, domain)
             for name, sc in [("pixel", s_pixel), ("discrete", s_discrete), ("latent", s_latent)]}
    thr = {name: cards[name]["threshold"] for name in cards}
    breakdown = {}
    for name, sc in [("pixel", s_pixel), ("discrete", s_discrete), ("latent", s_latent)]:
        breakdown[name] = {
            "recall_symbolic": _rate(sc, seq.symbolic, thr[name]),
            "recall_subsymbolic": _rate(sc, seq.subsymbolic, thr[name]),
            "fp_lighting": _rate(sc, seq.lighting, thr[name]),
            "fp_noise": _rate(sc, seq.noise, thr[name]),
            "fp_smooth_motion": _rate(sc, seq.nonevent_frames() - seq.lighting - seq.noise, thr[name]),
        }
    return {"overall": cards, "breakdown": breakdown,
            "counts": {"n": seq.n, "symbolic": len(seq.symbolic), "subsymbolic": len(seq.subsymbolic),
                       "lighting": len(seq.lighting), "noise": len(seq.noise)}}


# ---- top-level mechanism proof ------------------------------------------------------------
def run_mechanism_proof(epochs: int = 240, n_train: int = 12, seed: int = 0,
                        verbose: bool = True) -> dict[str, Any]:
    """Train the coder on ``n_train`` ambient (event-free) sequences, then score all three detectors on
    a TRAIN-family eval sequence and on a HELD-OUT sequence (fresh seed, never trained on). Returns the
    two scorecards, the collapse report, the coder's parameter count, and an honest verdict."""
    train_seqs = [generate(1000 + i, scripted=False) for i in range(n_train)]
    coder = LatentPredictiveCoder(CoderConfig(seed=seed))
    hist = coder.train([s.sigs for s in train_seqs], epochs=epochs, verbose=verbose)

    eval_seq = generate(1000 + n_train, scripted=True)      # rules seen, this exact stream not trained
    held_seq = generate(90001, scripted=True)               # fully held out (disjoint seed)

    def card_for(seq):
        return scorecard(seq, score_pixel(seq), score_discrete(seq), score_latent(coder, seq))

    eval_card = card_for(eval_seq)
    held_card = card_for(held_seq)
    collapse = coder.collapse_report(held_seq.sigs)

    result = {
        "param_count": coder.param_count(),
        "param_count_incl_target": coder.param_count(include_target=True),
        "final_loss": hist[-1],
        "eval": eval_card,
        "held_out": held_card,
        "collapse": collapse,
        "verdict": _verdict(held_card, collapse),
    }
    if verbose:
        _print_report(result)
    return result


def _verdict(card: dict, collapse: dict) -> dict[str, Any]:
    """Mechanised, honest verdict on the HELD-OUT scorecard — no hand-waving, just the measured
    comparisons the design asks for."""
    ov = card["overall"]
    bd = card["breakdown"]
    latent_ap, pixel_ap, disc_ap = ov["latent"]["ap"], ov["pixel"]["ap"], ov["discrete"]["ap"]
    return {
        "latent_ap": round(latent_ap, 3), "pixel_ap": round(pixel_ap, 3), "discrete_ap": round(disc_ap, 3),
        "latent_beats_pixel_overall": latent_ap > pixel_ap,
        "latent_fp_lighting": round(bd["latent"]["fp_lighting"], 3),
        "pixel_fp_lighting": round(bd["pixel"]["fp_lighting"], 3),
        "latent_fp_noise": round(bd["latent"]["fp_noise"], 3),
        "pixel_fp_noise": round(bd["pixel"]["fp_noise"], 3),
        "latent_fp_smooth": round(bd["latent"]["fp_smooth_motion"], 3),
        "pixel_fp_smooth": round(bd["pixel"]["fp_smooth_motion"], 3),
        "latent_recall_subsymbolic": round(bd["latent"]["recall_subsymbolic"], 3),
        "discrete_recall_subsymbolic": round(bd["discrete"]["recall_subsymbolic"], 3),
        "pixel_recall_subsymbolic": round(bd["pixel"]["recall_subsymbolic"], 3),
        "collapse_ok": collapse["ok"], "latent_std_min": round(collapse["latent_std_min"], 3),
    }


def _print_report(r: dict) -> None:
    print("\n================ V-JEPA fusion - mechanism-proof scorecard ================")
    print(f"coder params: {r['param_count']:,} trainable "
          f"({r['param_count_incl_target']:,} incl EMA target)  [ceiling 25,000,000]")
    fl = r["final_loss"]
    print(f"final train loss: total={fl['total']:.4f} pred={fl['pred']:.4f} "
          f"var={fl['var']:.4f} latent_std_min={fl['latent_std_min']:.3f}")
    for tag in ("eval", "held_out"):
        c = r[tag]
        print(f"\n--- {tag.upper()} sequence  (counts: {c['counts']}) ---")
        print(f"{'detector':<10} {'AP':>7} {'bestF1':>7} {'prec':>6} {'rec':>6}   "
              f"{'R@sym':>6} {'R@sub':>6} {'FP@light':>9} {'FP@noise':>9} {'FP@motion':>10}")
        for name in ("pixel", "discrete", "latent"):
            o = c["overall"][name]
            b = c["breakdown"][name]
            print(f"{name:<10} {o['ap']:>7.3f} {o['best_f1']:>7.3f} {o['precision']:>6.3f} "
                  f"{o['recall']:>6.3f}   {b['recall_symbolic']:>6.3f} {b['recall_subsymbolic']:>6.3f} "
                  f"{b['fp_lighting']:>9.3f} {b['fp_noise']:>9.3f} {b['fp_smooth_motion']:>10.3f}")
    v = r["verdict"]
    print("\n--- verdict (held-out) ---")
    print(f"overall AP: latent={v['latent_ap']}  pixel={v['pixel_ap']}  discrete={v['discrete_ap']}")
    print(f"latent beats pixel overall (AP): {v['latent_beats_pixel_overall']}")
    print(f"[adversarial 1] high-pixel NON-events, false-fire rate (lower=better):")
    print(f"   lighting: latent={v['latent_fp_lighting']} vs pixel={v['pixel_fp_lighting']}"
          f"  |  noise: latent={v['latent_fp_noise']} vs pixel={v['pixel_fp_noise']}"
          f"  |  smooth-motion: latent={v['latent_fp_smooth']} vs pixel={v['pixel_fp_smooth']}")
    print(f"[adversarial 2] low-pixel sub-symbolic event, recall (higher=better):")
    print(f"   latent={v['latent_recall_subsymbolic']}  vs discrete={v['discrete_recall_subsymbolic']}"
          f"  vs pixel={v['pixel_recall_subsymbolic']}")
    print(f"collapse ok: {v['collapse_ok']} (latent_std_min={v['latent_std_min']})")
    print("===========================================================================\n")


if __name__ == "__main__":
    run_mechanism_proof()
