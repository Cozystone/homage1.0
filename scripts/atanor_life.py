# -*- coding: utf-8 -*-
"""ATANOR's life — the always-on mind as a single continuous process.

Not a scheduler, not periodic wake-ups: one process, awake, whose PULSE the metabolism itself sets
(arousal quickens it, consolidation slows it). Kill it and the life pauses; start it and the life
resumes on the same persistent timeline (continuity). Usage:

    python scripts/atanor_life.py            # live indefinitely
    python scripts/atanor_life.py 20         # live for 20 beats (demo/verification)
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# daemon mode (pythonw): no console — the inner-speech stream goes to a log file instead, so the
# life is inspectable even with no window. Interactive runs keep printing to the terminal.
if sys.stdout is None or sys.stderr is None:
    _log = (REPO / "data" / "temporal_reasoning" / "life_daemon.log").open(
        "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.live_selfhood_cycle.life import Life  # noqa: E402

_LOCK_PORT = 47831   # single-instance lock: one life, one stream. A bound localhost port dies


def _acquire_instance_lock() -> socket.socket | None:
    """Two lives would double-beat the same stream. The lock is a localhost port bind — released
    by the OS the instant the process dies, so it can never go stale like a pidfile."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", _LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


def main() -> int:
    lock = _acquire_instance_lock()
    if lock is None:
        print("[life] another life process already holds the stream — exiting quietly.", flush=True)
        return 0
    max_beats = int(sys.argv[1]) if len(sys.argv) > 1 else None
    life = Life()
    print(f"[life] awake. stream -> {life.timeline._path}", flush=True)
    n = 0
    try:
        while max_beats is None or n < max_beats:
            r = life.step()
            n += 1
            line = str(r.get("broadcast") or "")[:110]
            acted = r.get("acted") or {}
            extra = f" | acted: {acted.get('kind')}({'ok' if acted.get('ok') else '…'})" if acted else ""
            print(f"[beat {n:03d}] [{r.get('source')}] {line}{extra} | next {r.get('tempo_next')}s",
                  flush=True)
            import time
            time.sleep(life.tempo())
    except KeyboardInterrupt:
        print("[life] paused by operator.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
