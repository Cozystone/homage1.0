# -*- coding: utf-8 -*-
"""Engine watchdog — the ports must never die again.

Watches the local companion engine (:8502) and the SPLATRA particle engine
(:8010). A service is restarted when it is (a) down, (b) unresponsive three
checks in a row, or (c) bloated past its memory ceiling — today's incident:
the engine grew to 8 GB and starved every request to death, killing chat for
hours. Restarts are safe by design: the selfhood layer RESUMES (continuity
keystone, born_at preserved), it is not reborn.

Run:  python scripts/engine_watchdog.py
Logs: data/watchdog.log
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(HERE, "data", "watchdog.log")

SERVICES = [
    {
        "name": "atanor-engine",
        "port": 8502,
        "health": "http://127.0.0.1:8502/health",
        # BASE footprint is ~5.2-6.2GB now (488k triple store + full stack) —
        # a 4GB cap put the engine in a permanent 60s kill-restart loop that
        # read as "random deaths" (measured 2026-07-08, data/watchdog.log).
        # Cap must sit well above base but still catch a true runaway.
        "rss_limit_mb": 12288,
        # A paged-out process can have tiny RSS while its private commit still fills
        # pagefile.sys. The engine must be guarded by the resource that exhausted.
        "memory_metric": "private",
        # PROCESS ISOLATION (2026-07-11 final assault): the engine serves REQUESTS ONLY —
        # the always-on learners run in the atanor-learner sidecar below, so a hot learning
        # tick can never hold this process's GIL and starve chat latency.
        # atanor-ops.vercel.app = the operator dashboard (owner-ordered deploy 2026-07-11);
        # the hosted page's BROWSER fetches this local engine — telemetry never leaves the box.
        "env": {"ATANOR_LEARNERS_EXTERNAL": "1",
                "ATANOR_EXTRA_CORS_ORIGINS": "https://atanor-ops.vercel.app"},
        "cwd": HERE,
        "cmd": [sys.executable, "-m", "uvicorn", "app.main:app",
                "--host", "127.0.0.1", "--port", "8502", "--app-dir", "apps/api"],
    },
    {
        "name": "atanor-learner",
        "port": 8509,
        "health": "http://127.0.0.1:8509/",
        # decompose/gate + candidate stores live here now; generous but bounded
        "rss_limit_mb": 8192,
        "memory_metric": "private",

        # (no request GIL to protect), so the conservative 20s tick was engine-era caution.
        # 5s tick × 8 titles × ko-bias 3 ≈ measured ~10x diet intake; gates unchanged —
        # purity comes from mine_text/judge, not from starvation. Wikipedia load stays
        # polite (~2 req/s, contact UA). Abstain drain re-paced for 5s ticks (24 ticks
        # = 2 terms per ~2min; the seeded gap backlog clears in about an hour).
        #
        # PACK-PROMOTION DECOUPLED (P0 regression 2026-07-11, root cause): at 10x intake the
        # every-40-tick pack re-promotion pulled random wiki-flood candidates into the CURATED

        # language) may flood fast — it's register, not facts — but the answer pack is the
        # curated fact store and must NOT auto-grow from the flood. ATANOR_PROMOTE_EVERY=0
        # disables auto-promotion; the pack grows only via gated/operator promotion. Truth >
        # coverage; answer-pack vs cloud-graph split.

        # ~doubles diet throughput without touching the knowledge gate or answer pack. Safe because
        # promotion is off AND the atanor-p0-sentinel freezes learning on any quality regression.
        "env": {"ATANOR_ABSTAIN_FEED_EVERY": "24",
                "ATANOR_LEARN_INTERVAL_SEC": "5",
                "ATANOR_LEARN_WIKI_TITLES": "8",
                "ATANOR_LEARN_KO_BIAS": "3",
                "ATANOR_DIET_PER_TICK": "60",
                "ATANOR_DIET_BOOST_TITLES": "8",
                "ATANOR_PROMOTE_EVERY": "0"},
        "cwd": HERE,
        "cmd": [sys.executable, "scripts/learner_daemon.py"],
    },
    {
        "name": "atanor-ops-relay",
        "port": 8510,
        "health": "http://127.0.0.1:8510/health",
        # read-only LAN relay for the phone dashboard (3 GET paths, allowlist only)
        "rss_limit_mb": 512,
        "cwd": HERE,
        "cmd": [sys.executable, "scripts/ops_relay.py"],
    },
    {
        "name": "atanor-p0-sentinel",
        "port": 8511,
        "health": "http://127.0.0.1:8511/",
        # unattended answer-quality parole officer: canary every 15 min, FREEZES learning +
        # writes an /ops alert the instant P0 quality regresses (diet-flood safety net). This is
        # what makes pushing the diet FASTER safe — a regression is caught in minutes, not hours.
        "rss_limit_mb": 512,
        "cwd": HERE,
        "cmd": [sys.executable, "scripts/p0_sentinel.py"],
    },
    {
        "name": "splatra",
        "port": 8010,
        "health": "http://127.0.0.1:8010/v1/models",
        "rss_limit_mb": 6144,          # torch models are heavy; higher ceiling

        # fell to a procedural hash-colored sphere (owner-reported pink blob).
        # TRIPOSR = learned single-image 3D reconstruction (measured: warm
        # ~6s / 170k gaussians on this GPU) — quality default; SD silhouette
        # lift (~1s) remains the automatic fallback if TripoSR errors.
        "env": {"SPLATRA_SD": "1", "SPLATRA_TRIPOSR": "1",
                "SPLATRA_TRIPOSR_DIR": r"C:\Users\anseo\.cache\splatra\TripoSR"},
        "cwd": r"C:\0.ASKIM ALL-VIN\26.SPLATRA",
        "cmd": [sys.executable, "-m", "uvicorn", "apps.plugin_api:app",
                "--port", "8010"],
    },
]

# --- multiprocess sharding (opt-in, default OFF) ------------------------------------------
# ATANOR_LEARNER_SHARDS=N replaces the single :8509 learner with N GIL-free shard workers
# (scripts/learner_shard.py), each owning its own corpus + candidate files (single-writer at
# N-way scale) for ~N× learning throughput. Unset (default) leaves this list byte-identical, so
# the live watchdog is unchanged until the owner opts in. Between runs, scripts/corpus_compactor.py
# folds the shard corpora into the main store. See docs/ATANOR_multiprocess_sharding_design.md.
_SHARDS = int(os.environ.get("ATANOR_LEARNER_SHARDS", "0") or "0")
if _SHARDS >= 2:
    SERVICES = [s for s in SERVICES if s["name"] != "atanor-learner"]   # shards replace it
    for _i in range(_SHARDS):
        SERVICES.append({
            "name": f"atanor-learner-shard-{_i}",
            "port": 8520 + _i,
            "health": f"http://127.0.0.1:{8520 + _i}/",
            "rss_limit_mb": 4096,          # per-shard cap (N shards share the box)
            "env": {"ATANOR_CORPUS_SHARD": str(_i), "ATANOR_CORPUS_SHARDS": str(_SHARDS),
                    "ATANOR_LEARN_INTERVAL_SEC": "5", "ATANOR_PROMOTE_EVERY": "0"},
            "cmd": [sys.executable, "scripts/learner_shard.py", str(_i), str(_SHARDS)],
        })

CHECK_EVERY_S = 30
FAILS_TO_RESTART = 3
HEALTH_TIMEOUT_S = 8
# A TripoSR generation legitimately monopolizes splatra for 20-60s (GIL-heavy
# torch), which reads as 2-3 failed probes — the watchdog was killing the
# service MID-GENERATION (measured 2026-07-08 18:08/18:12). Busy is not dead:
# services may declare a higher per-service fail budget.
SERVICE_FAILS = {"splatra": 8}


def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def healthy(svc: dict) -> bool:
    try:
        with urllib.request.urlopen(svc["health"], timeout=HEALTH_TIMEOUT_S) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


# every helper spawn MUST be windowless: a background daemon that shells out
# every 30s otherwise flashes a console window each time — the exact
# "popup keeps appearing and dying" the owner reported
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def pid_on_port(port: int) -> int | None:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-NetTCPConnection -LocalPort {port} -State Listen "
             f"-ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess"],
            capture_output=True, text=True, timeout=20,
            creationflags=NO_WINDOW).stdout.strip()
        return int(out) if out else None
    except Exception:
        return None


def memory_mb(pid: int, metric: str = "rss") -> float:
    try:
        prop = "PrivateMemorySize64" if metric == "private" else "WorkingSet64"
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).{prop}"],
            capture_output=True, text=True, timeout=20,
            creationflags=NO_WINDOW).stdout.strip()
        return int(out) / (1024 * 1024) if out else 0.0
    except Exception:
        return 0.0


def restart(svc: dict) -> None:
    pid = pid_on_port(svc["port"])
    if pid:
        log(f"{svc['name']}: killing pid {pid}")
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, timeout=30, creationflags=NO_WINDOW)
        time.sleep(2)
    log(f"{svc['name']}: starting -> {' '.join(svc['cmd'])}")
    # CREATE_NO_WINDOW (a HIDDEN console the service's own children inherit),
    # never DETACHED_PROCESS: detached means NO console, so every child the
    # service shells out to (nvidia-smi, docker stats, git ...) allocates a
    # fresh VISIBLE console — the terminal-flash storm on the owner's screen.
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | NO_WINDOW
    env = {**os.environ, **svc["env"]} if svc.get("env") else None
    # STDERR IS EVIDENCE, NOT NOISE (2026-07-17). This was DEVNULL, so every application
    # traceback the engine ever raised was destroyed at birth. Measured cost: a live HTTP 500
    # ('What is a aberdeen angus?', 1 in 120) could not be diagnosed at all — the only logs on
    # disk were from a previous era's launcher. A watchdog that restarts a process without
    # keeping its dying words tells you the port is up and nothing about whether it is well.
    # Rotated (10MB, .1 kept) — the same discipline that killed the 1GB log growth: capped, not
    # discarded. stdout stays DEVNULL: uvicorn's access log is noise, its stderr is the signal.
    err_path = os.path.join(HERE, "logs", "startup", f"{svc['name']}.err.log")
    os.makedirs(os.path.dirname(err_path), exist_ok=True)
    try:
        if os.path.exists(err_path) and os.path.getsize(err_path) > 10 * 1024 * 1024:
            prev = err_path + ".1"
            if os.path.exists(prev):
                os.remove(prev)
            os.replace(err_path, prev)
    except OSError:
        pass  # a live reader holds it; append anyway rather than lose the next traceback
    err = open(err_path, "ab", buffering=0)
    subprocess.Popen(svc["cmd"], cwd=svc["cwd"], creationflags=flags, env=env,
                     stdout=subprocess.DEVNULL, stderr=err)


def main() -> None:
    # SINGLETON lock: duplicate watchdogs once stacked 4-deep and their helper
    # shells flashed console windows nonstop. One localhost port = one instance.
    import socket

    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", 18790))
        lock.listen(1)
    except OSError:
        print("another watchdog instance is already running; exiting")
        return

    fails = {s["name"]: 0 for s in SERVICES}
    log("watchdog up - " + ", ".join(s["name"] + ":" + str(s["port"]) for s in SERVICES))
    while True:
        for svc in SERVICES:
            name = svc["name"]
            ok = healthy(svc)
            reason = None
            if ok:
                fails[name] = 0
                pid = pid_on_port(svc["port"])
                if pid:
                    metric = svc.get("memory_metric", "rss")
                    mem = memory_mb(pid, metric)
                    if mem > svc["rss_limit_mb"]:
                        reason = (f"{metric} memory {mem:.0f}MB > "
                                  f"{svc['rss_limit_mb']}MB")
            else:
                fails[name] += 1
                if fails[name] >= SERVICE_FAILS.get(name, FAILS_TO_RESTART):
                    reason = f"unhealthy x{fails[name]}"
            if reason:
                log(f"{name}: RESTART ({reason})")
                try:
                    restart(svc)
                except Exception as e:
                    log(f"{name}: restart failed: {e}")
                fails[name] = 0
                time.sleep(15)                 # grace for boot
        time.sleep(CHECK_EVERY_S)


if __name__ == "__main__":
    main()
