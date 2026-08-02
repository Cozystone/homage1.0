# -*- coding: utf-8 -*-
"""Auto-launcher: when the Wikidata download completes, start the full world-pack build.

Watches latest-all.json.bz2; completion = size >= 100 GB AND unchanged across 3 checks (60s
apart) AND no curl process still writing it. Then spawns build_world_pack.py DETACHED (survives
this watcher and the terminal) and exits. Journals every decision — the monitoring trail.

  python scripts/world_pack_autolaunch.py            # run once, watches until launch
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DUMP = Path("C:/0.ASKIM ALL-VIN/wikidata/latest-all.json.bz2")
JOURNAL = REPO / "data" / "graph_scale" / "world_pack_build.jsonl"
MIN_BYTES = 100 * 10**9


def _journal(row: dict) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **row}) + "\n")


def _curl_alive() -> bool:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-Process curl -ErrorAction SilentlyContinue) -ne $null"],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return out.lower() == "true"
    except Exception:
        return False


def main() -> int:
    stable = 0
    last = -1
    _journal({"kind": "watch_start", "dump": str(DUMP)})
    while True:
        size = DUMP.stat().st_size if DUMP.exists() else 0
        if size >= MIN_BYTES and size == last and not _curl_alive():
            stable += 1
        else:
            stable = 0
        last = size
        print(f"{time.strftime('%H:%M:%S')} size={size/1e9:.1f}GB stable={stable}/3 "
              f"curl={'alive' if _curl_alive() else 'gone'}", flush=True)
        if stable >= 3:
            break
        time.sleep(60)
    _journal({"kind": "download_complete", "bytes": last})
    # spawn the full build DETACHED (new process group; survives this watcher)
    log = REPO / "data" / "graph_scale" / "world_pack_build.log"
    with log.open("ab") as lf:
        proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(REPO / "scripts" / "build_world_pack.py")],
            cwd=str(REPO), stdout=lf, stderr=lf,
            creationflags=0x00000008 | 0x00000200)     # DETACHED_PROCESS | NEW_PROCESS_GROUP
    _journal({"kind": "build_launched", "pid": proc.pid, "log": str(log)})
    print(f"BUILD LAUNCHED pid={proc.pid} → {log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
