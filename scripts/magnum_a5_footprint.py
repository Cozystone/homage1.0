# -*- coding: utf-8 -*-
"""Magnum Opus A5 — local footprint & latency gate.

Criterion (docs/ATANOR_magnum_opus_criteria.md, Tier A5, sealed v1):
    resident RAM <= 12 GB  AND  first-response p50 <= 1.5s  AND  p95 <= 4.0s
    measured while the rest of Tier A would run, on a single consumer box, offline.

What this measures and what it does NOT:
  - RAM = RSS of the live engine process tree (uvicorn + its children), sampled during load.
    Not "peak ever" — the criterion is resident footprint under working conditions.
  - latency = wall time to FIRST response byte for a cold, previously unasked question
    (no warm cache credit; each probe question is unique per run via a salt).
  - Network isolation is a SHIPPING condition of the sealed run, not something this script
    can assert — it prints an env attestation line the operator fills in for a sealed run.

Usage:
    python scripts/magnum_a5_footprint.py [n]          # n probes, default 40
    python scripts/magnum_a5_footprint.py 40 --sealed  # mark the report as a sealed attempt

Writes reports/magnum/a5_<ts>.json. Read-only against the engine (asks questions only).
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8502"
OUT = REPO / "reports" / "magnum"

RAM_GATE_GB = 12.0
P50_GATE_S = 1.5
P95_GATE_S = 4.0

# Cold-probe stems: ordinary user questions across the lanes the engine actually serves.
# Salted per run so no probe can be served from a previous run's cache.
PROBES = [
    "What is {x} used for?",
    "Tell me about {x}.",
    "How does {x} work?",
    "What is the difference between {x} and a database?",
    "Why does {x} matter?",
    "Give me a short summary of {x}.",
    "What are the main parts of {x}?",
    "Is {x} a kind of machine?",
]
TOPICS = ["a turbine", "photosynthesis", "an aqueduct", "a compiler", "sonar", "a glacier",
          "a transformer", "penicillin", "a suspension bridge", "the water cycle"]


def _engine_pids() -> list[int]:
    """PIDs of the process actually listening on 8502, plus its children."""
    import psutil
    pids: list[int] = []
    for c in psutil.net_connections(kind="inet"):
        if c.laddr and c.laddr.port == 8502 and c.status == psutil.CONN_LISTEN and c.pid:
            pids.append(c.pid)
    out = []
    for pid in set(pids):
        try:
            p = psutil.Process(pid)
            out.append(pid)
            out.extend(ch.pid for ch in p.children(recursive=True))
        except Exception:
            pass
    return sorted(set(out))


def _rss_gb(pids: list[int]) -> float:
    import psutil
    total = 0
    for pid in pids:
        try:
            total += psutil.Process(pid).memory_info().rss
        except Exception:
            pass
    return total / 1e9


def _ask(question: str, timeout: float = 30.0) -> tuple[float, bool]:
    """Wall seconds to a complete response + ok flag. Uses the non-stream endpoint so the
    number is 'time to an answer the user can read', not time-to-first-token."""
    body = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/api/chat/atanor", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
        return time.perf_counter() - t0, True
    except Exception:
        return time.perf_counter() - t0, False


def _load_context() -> dict:
    """Capture what ELSE was running. A latency number without this is unreproducible: the
    first A5 run (2026-07-18) measured p50 1.603s with a 326k-step RTD pretrain co-resident,
    which is a materially different machine than an idle one. The report must say so itself."""
    import psutil
    ctx: dict = {"cpu_percent": psutil.cpu_percent(interval=0.5),
                 "host_ram_used_percent": psutil.virtual_memory().percent}
    heavy = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "cpu_percent"]):
        try:
            cl = " ".join(p.info.get("cmdline") or [])
            if any(k in cl for k in ("pretrain", "finetune", "train_", "benchmark_", "isaac")):
                heavy.append({"pid": p.info["pid"], "cmd": cl[:110]})
        except Exception:
            pass
    ctx["co_resident_heavy_jobs"] = heavy
    try:
        import subprocess
        q = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                            "--format=csv,noheader"], capture_output=True, text=True, timeout=10)
        ctx["gpu"] = q.stdout.strip() or None
    except Exception:
        ctx["gpu"] = None
    return ctx


def main() -> int:
    import psutil
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(args[0]) if args else 40
    sealed = "--sealed" in sys.argv
    salt = datetime.now().strftime("%H%M%S")

    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=10) as r:
            health = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"engine not reachable at {BASE}: {e}")
        return 1
    pids = _engine_pids()
    if not pids:
        print("could not identify the engine process listening on 8502")
        return 1
    print(f"engine {health} | pids {pids}")

    rss_samples = [_rss_gb(pids)]
    lat: list[float] = []
    fails = 0
    for i in range(n):
        q = PROBES[i % len(PROBES)].format(x=TOPICS[(i // len(PROBES)) % len(TOPICS)])
        q = f"{q} (probe {salt}-{i})"          # salt: defeats any answer cache
        dt, ok = _ask(q)
        lat.append(dt)
        fails += (not ok)
        rss_samples.append(_rss_gb(pids))

    lat_sorted = sorted(lat)
    p50 = statistics.median(lat_sorted)
    p95 = lat_sorted[max(0, int(round(0.95 * len(lat_sorted))) - 1)]
    rss_max = max(rss_samples)
    vm = psutil.virtual_memory()

    passed = {
        "ram<=12GB": rss_max <= RAM_GATE_GB,
        "p50<=1.5s": p50 <= P50_GATE_S,
        "p95<=4.0s": p95 <= P95_GATE_S,
        "no_request_failures": fails == 0,
    }
    rep = {
        "battery": "MagnumOpus A5 footprint+latency",
        "criteria_version": "v1",
        "sealed_attempt": sealed,
        "ts": datetime.now(timezone.utc).isoformat(),
        "engine": health,
        "n_probes": n,
        "engine_rss_gb_max": round(rss_max, 3),
        "engine_rss_gb_start": round(rss_samples[0], 3),
        "host_ram_total_gb": round(vm.total / 1e9, 1),
        "latency_s": {"p50": round(p50, 3), "p95": round(p95, 3),
                      "min": round(lat_sorted[0], 3), "max": round(lat_sorted[-1], 3),
                      "mean": round(statistics.fmean(lat), 3)},
        "request_failures": fails,
        "load_context": _load_context(),
        "gates": passed,
        "PASS": all(passed.values()),
        "attestation_required_for_sealed_run": {
            "network_isolated": None,      # operator fills: true when run with NIC down
            "cold_boot_reproduced": None,  # operator fills: true when re-run after clean restart
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"a5_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(rep, indent=2), encoding="utf-8")

    print(f"\n  engine RSS max   {rss_max:.2f} GB   [gate <= {RAM_GATE_GB}]")
    print(f"  latency p50      {p50:.3f} s     [gate <= {P50_GATE_S}]")
    print(f"  latency p95      {p95:.3f} s     [gate <= {P95_GATE_S}]")
    print(f"  failures         {fails}")
    print(f"\nA5 {'PASS' if rep['PASS'] else 'FAIL'} -> {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
