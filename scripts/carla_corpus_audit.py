# -*- coding: utf-8 -*-
"""What is actually in the depth corpus — read off the disk, never off a collection run's log.

WHY THIS EXISTS. The first collection printed four episode lines and I nearly reported "4 of 32
succeeded". The disk held fourteen complete episodes and 3,500 frames: the loop's `tail -6` had
simply cut the rest. The opposite error is just as easy — a run that prints a success line for an
episode that later crashed mid-write leaves a directory with no `meta.json`, and counting log lines
would count it as good.

So the corpus is audited by opening it. A run log says what a process believed; this says what
exists.

    python scripts/carla_corpus_audit.py

It runs on the REPO python (3.13) and needs no carla client — it only reads .npz and .json.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\carla\episodes")
SKY = 11                    # CARLA 0.9.14+ semantic id; see carla_depth_recorder.SEMANTIC_TAGS
FAR_PLANE_M = 1000.0


def audit(root: Path = ROOT, deep_sample: int = 3) -> dict:
    eps = sorted(d for d in root.iterdir() if d.is_dir()) if root.exists() else []
    good, broken = [], []

    for d in eps:
        n = len(list(d.glob("*.npz")))
        mp = d / "meta.json"
        if not mp.exists():
            broken.append({"ep": d.name, "frames": n, "why": "no meta.json (crashed mid-episode)"})
            continue
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
        except Exception as exc:
            broken.append({"ep": d.name, "frames": n, "why": f"unreadable meta: {type(exc).__name__}"})
            continue
        if m.get("frames") != n:
            broken.append({"ep": d.name, "frames": n,
                           "why": f"meta claims {m.get('frames')} frames, {n} on disk"})
            continue
        good.append({"ep": d.name, "town": str(m.get("map", "?")).split("/")[-1],
                     "weather": m.get("weather", "?"), "frames": n,
                     "dropped": m.get("dropped_misregistered")})

    # THE DEPTH CHECK, on a sample of every episode rather than on one frame of one episode. Sky
    # sitting exactly on the far plane is the property that fails loudly if the packed 24-bit depth
    # was decoded wrongly or the sensors drifted apart, so it is worth paying for on every episode.
    depth_checks = []
    for row in good:
        files = sorted((root / row["ep"]).glob("*.npz"))
        if not files:
            continue
        picks = files[:: max(1, len(files) // deep_sample)][:deep_sample]
        skies, mins, meds = [], [], []
        for f in picks:
            try:
                z = np.load(f)
                dep = z["depth_m"].astype(np.float32)
                sem = z["semantic"]
            except Exception:
                continue
            mins.append(float(dep.min()))
            meds.append(float(np.median(dep)))
            if (sem == SKY).any():
                skies.append(float(np.median(dep[sem == SKY])))
        ok = bool(skies) and all(abs(s - FAR_PLANE_M) < 1.0 for s in skies)
        depth_checks.append({"ep": row["ep"], "sampled": len(picks), "sky_medians": skies,
                             "sky_on_far_plane": ok,
                             "depth_min": round(min(mins), 2) if mins else None,
                             "depth_median": round(float(np.median(meds)), 2) if meds else None})

    weathers = Counter(r["weather"] for r in good)
    towns = Counter(r["town"] for r in good)
    total = sum(r["frames"] for r in good)

    # Balance, stated as a ratio rather than a verdict. A corpus 12/14 wet is not "broken", it is
    # skewed, and how much that matters depends on what it is used for -- so the number is reported
    # and the judgement is left to whoever reads it.
    worst = max(weathers.values()) if weathers else 0
    least = min(weathers.values()) if weathers else 0
    return {
        "episodes_good": len(good), "episodes_broken": len(broken), "broken": broken,
        "frames": total, "npz_on_disk": len(list(root.rglob("*.npz"))) if root.exists() else 0,
        "towns": dict(towns), "weathers": dict(weathers),
        "weather_imbalance": f"{worst}:{least}" if weathers else "n/a",
        "weathers_never_recorded": sorted(
            {"ClearNoon", "CloudySunset", "WetNoon", "HardRainNoon", "ClearSunset",
             "MidRainyNoon", "SoftRainSunset", "WetCloudyNoon"} - set(weathers)),
        "dropped_total": sum(int(r["dropped"] or 0) for r in good),
        "depth_checks": depth_checks,
        "depth_check_failures": [c["ep"] for c in depth_checks if not c["sky_on_far_plane"]],
        "episodes": good,
    }


def main() -> None:
    a = audit()
    print(f"episodes: {a['episodes_good']} good, {a['episodes_broken']} broken")
    for b in a["broken"]:
        print(f"   BROKEN {b['ep']}: {b['why']}")
    print(f"frames: {a['frames']} (npz on disk {a['npz_on_disk']}) | misregistered dropped: {a['dropped_total']}")
    print(f"towns: {a['towns']}")
    print(f"weathers: {a['weathers']}")
    print(f"  imbalance (most:least) {a['weather_imbalance']} | never recorded: {a['weathers_never_recorded']}")
    fails = a["depth_check_failures"]
    print(f"depth check (sky on the {FAR_PLANE_M:.0f}m far plane): "
          f"{len(a['depth_checks']) - len(fails)}/{len(a['depth_checks'])} episodes pass")
    if fails:
        print(f"   FAILED: {fails}")
    out = ROOT / "audit.json"
    out.write_text(json.dumps(a, indent=2), encoding="utf-8")
    print("wrote", out)
    sys.exit(1 if (fails or a["episodes_broken"]) else 0)


if __name__ == "__main__":
    main()
