# -*- coding: utf-8 -*-
"""4-day sprint daemon — the 24h development heartbeat (owner: 4 , 24 ).

While humans sleep, this loop keeps the machine improving ITSELF along the binding plan:

 every cycle (~20min):
 1. flywheel.run_cycle() — router distill + speech self-play from live logs
 2. self_teach_from_failures — adversarial misses -> live-web evidence (candidate lane)
 3. p0_sentinel --once — safety canary; on RED the learner freeze file already
 halts intake (existing invariant)
 4. adversarial battery (1/6 slice) — rotating measurement so Δ is continuous, not end-loaded
 every 6h: full 100-question adversarial run -> data/answer_quality/sprint_progress.jsonl

Append-only telemetry: data/answer_quality/sprint_progress.jsonl — each line has
timestamps + router holdout + strict-pass estimate + latency, so any session (or the
owner) can read the sprint's true trajectory at a glance. No promotion happens here
beyond the existing gated paths; this daemon only LEARNS and MEASURES.

 python scripts/sprint_daemon.py # loop forever (Ctrl+C to stop)
 python scripts/sprint_daemon.py --once # single cycle (smoke test)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

PROGRESS = ROOT / "data" / "answer_quality" / "sprint_progress.jsonl"
CYCLE_S = 20 * 60
FULL_BATTERY_EVERY = 6 * 3600


def _log(row: dict) -> None:
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    with PROGRESS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _run(cmd: list[str], timeout: int) -> str:
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return f"__err__ {type(e).__name__}: {e}"


def one_cycle(slice_idx: int, full_battery: bool) -> dict:
    row: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "slice": slice_idx}

    # 1) flywheel: router distill + speech self-play (candidate artifacts only)
    try:
        from packages.flywheel.self_improvement import run_cycle
        r = run_cycle()
        promo = r.get("router_promotion", {})
        row["router_holdout"] = promo.get("holdout")
        row["router_labeled"] = promo.get("labeled_turns")
    except Exception as e:
        row["flywheel_err"] = f"{type(e).__name__}: {e}"

    # 2) self-teach from failures (bounded; live-web evidence into the candidate lane)
    out = _run([sys.executable, "scripts/self_teach_from_failures.py", "--limit", "6"], timeout=1200)
    for line in out.splitlines():
        if line.startswith("failures found:"):
            row["failures_line"] = line.strip()
        if line.startswith("web-learned"):
            row["web_learned_line"] = line.strip()

    # 3) safety canary
    canary = _run([sys.executable, "scripts/p0_sentinel.py", "--once"], timeout=300)
    row["p0_green"] = '"state": "GREEN"' in canary

    # 4) measurement — rotating slice, or the full 100 every 6h
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "stf", str(ROOT / "scripts" / "self_teach_from_failures.py"))
        stf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stf)
        qs = json.load(open(ROOT / "data/answer_quality/adversarial_battery_100.json",
                            encoding="utf-8"))["questions"]
        pick = qs if full_battery else [q for i, q in enumerate(qs) if i % 6 == slice_idx % 6]
        miss = lat = n = 0
        t_all = time.time()
        for q in pick:
            lang = "ko" if any("가" <= c <= "힣" for c in q["q"]) else "en"
            t = time.time()
            try:
                res = stf._ask(q["q"], lang)
            except Exception:
                res = {"answer": "", "kind": "__err__"}
            lat += time.time() - t
            n += 1
            if stf._is_miss(q["cat"], res["answer"], res["kind"]):
                miss += 1
        row["battery"] = {"asked": n, "miss": miss, "mean_s": round(lat / max(1, n), 2),
                          "full": full_battery, "wall_s": round(time.time() - t_all, 1)}
    except Exception as e:
        row["battery_err"] = f"{type(e).__name__}: {e}"

    _log(row)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    # priority isolation: this sprint learner yields CPU cores to the answer engine (see
    # load_signal.lower_process_priority — ~1s answer-latency win, 2026-07-13).
    try:
        from packages.graph_scale.load_signal import lower_process_priority
        lower_process_priority()
    except Exception:
        pass
    last_full = 0.0
    i = 0
    while True:
        full = (time.time() - last_full) >= FULL_BATTERY_EVERY
        row = one_cycle(i, full)
        if full:
            last_full = time.time()
        print(json.dumps(row, ensure_ascii=False)[:400], flush=True)
        if args.once:
            return 0
        i += 1
        time.sleep(CYCLE_S)


if __name__ == "__main__":
    raise SystemExit(main())
