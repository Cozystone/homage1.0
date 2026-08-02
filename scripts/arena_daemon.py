# -*- coding: utf-8 -*-
"""Arena daemon — unattended generation accumulation (owner: , 2026-07-12).

Every ATANOR_ARENA_INTERVAL_SEC (default 1800s) it runs one evolution burst (pop 5 x
ATANOR_ARENA_GENERATIONS on 5 workers — the owner's 5-core allocation), on a FRESH draw of
the ever-growing voice corpus, so the champion keeps adapting as the diet grows. When the
burst records the candidate locally. The historical raw-score dopamine coupling now fails
closed at POST /api/selfhood/arena-event until the arena produces an externally signed,
live-context-bound evaluation receipt. Evolution itself never depends on the engine.

Singleton (port lock 18791, same pattern as the watchdog) — one arena per machine.
Offline-only writer of data/evolution/*; never touches stores, packs, or the engine process.
"""
from __future__ import annotations

import json
import os
import random
import socket
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

LOG = REPO / "data" / "evolution" / "arena_daemon.log"
INTERVAL = int(os.getenv("ATANOR_ARENA_INTERVAL_SEC", "1800") or 1800)
GENERATIONS = int(os.getenv("ATANOR_ARENA_GENERATIONS", "6") or 6)
WORKERS = int(os.getenv("ATANOR_ARENA_WORKERS", "5") or 5)
ENGINE_EVENT = "http://127.0.0.1:8502/api/selfhood/arena-event"


def _log(msg: str) -> None:
    line = f"{time.strftime('%F %T')} {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _tell_engine(prev: float, fitness: float, generation: int) -> None:
    """Legacy raw-score notification; the engine must reject it fail-closed."""
    try:
        import urllib.request

        body = json.dumps({"prev_fitness": prev, "fitness": fitness,
                           "generation": generation}).encode("utf-8")
        req = urllib.request.Request(ENGINE_EVENT, body, {"Content-Type": "application/json"})
        rep = json.load(urllib.request.urlopen(req, timeout=10))
        _log(f"engine felt the growth: {rep}")
    except Exception as exc:
        _log(f"engine coupling skipped ({type(exc).__name__}) — evolution unaffected")


def one_burst() -> None:
    from packages.autonomy_kernel.narrative_corpus import corpus_tail
    from packages.evolution.speaker_arena import evolve, load_champion

    prev = load_champion()
    prev_fit = float(prev["fitness"]) if prev else 0.0

    lines = corpus_tail(4000, balanced=True)
    if len(lines) < 60:
        _log(f"corpus too thin ({len(lines)}) — skipping burst")
        return
    random.Random(int(time.time()) % 100000).shuffle(lines)  # fresh split every burst

    # AND the holdout with equal parts per register, so the voice trains on all four evenly instead of
    # drowning in the 43% Wikipedia. Log the register gaps so sourcing/mining can aim at them.
    try:
        from packages.autonomy_kernel.register_diet import balanced_draw, register_mix, under_registers
        rng = random.Random(int(time.time()) % 100000)
        holdout = balanced_draw(lines[:900], 300, rng)
        fit_corpus = balanced_draw(lines[300:], min(3000, len(lines) - 300), rng)
        gaps = under_registers(lines)
        _log(f"register mix {register_mix(lines)['fractions']} — starved: {gaps or 'none'}")
    except Exception as exc:
        _log(f"register balancing skipped ({type(exc).__name__}) — using natural draw")
        holdout, fit_corpus = lines[:300], lines[300:]
    out = evolve(fit_corpus, holdout, pop=5, generations=GENERATIONS, workers=WORKERS,
                 log=lambda m: _log(f"  {m}"))
    champ = out["champion"]
    _log(f"burst done: champion={champ['fitness']} (prev {prev_fit}) "
         f"genome={champ['genome']}")
    if champ["fitness"] > prev_fit:
        _tell_engine(prev_fit, champ["fitness"], out["history"][-1]["gen"])

    # scored WEAK on as diet-mining targets — the web expedition will aim there next, fattening the
    # voice exactly where it was thin. Best-effort; a failure here never stops evolution.
    try:
        from packages.evolution.speaker_arena import draw_seeds, evaluate_genome
        from packages.evolution.diet_steering import record_weakness
        seeds = draw_seeds(holdout, fit_corpus, random.Random(int(time.time()) % 99991), k=8)
        res = evaluate_genome(champ["genome"], fit_corpus, seeds, [])
        scored = list(zip(seeds, [float(l.get("total") or 0.0) for l in res.get("lines", [])]))
        n = record_weakness(scored)
        _log(f"diet steering: {n} weak topic(s) registered for mining from {len(seeds)} seeds")
    except Exception as exc:
        _log(f"diet steering skipped ({type(exc).__name__})")


def main() -> int:
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", 18791))
        lock.listen(1)
    except OSError:
        print("another arena daemon is already running; exiting")
        return 0
    _log(f"arena daemon up — every {INTERVAL}s, pop 5 x {GENERATIONS} gens x {WORKERS} workers")
    while True:
        try:
            one_burst()
        except Exception as exc:
            _log(f"burst failed: {type(exc).__name__}: {exc}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
