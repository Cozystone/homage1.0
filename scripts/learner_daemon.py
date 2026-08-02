# -*- coding: utf-8 -*-
"""Learner sidecar — the always-on learners in their OWN process, GIL-free from the engine.

Owner (2026-07-11, final assault): the battery's last red mark is speed, and the measured root
is that the CPU-bound learner threads (continuous tick's decompose/gate, the firehose sentence
loop, relation discovery) share the ENGINE's GIL — no amount of in-process yielding fixes a
tick that holds the GIL for 10-20s once started. This daemon runs those exact workers in a
separate process:

  * the ENGINE (:8502) starts with ATANOR_LEARNERS_EXTERNAL=1 → its in-process learner threads
    never start; every request cycle owns the engine GIL;
  * THIS process imports the same cloud_brain module and runs the same three workers at full
    speed — writes go to the same on-disk candidate stores/journals the engine reads (the
    engine's answer_bridge growth-gate reload picks up new knowledge as before);
  * health: a tiny localhost HTTP server on :8509 (the shared watchdog probes it and enforces
    an RSS ceiling like any other service);
  * status: a snapshot of the learner counters lands in data/autonomy/learner_daemon_status.json
    every 5s so the engine's /learning/continuous/metrics endpoint keeps telling the truth.

Single-writer contract: with the engine's learners off, THIS process is the only writer of the
candidate stores — same file contracts as before, just a different (dedicated) process.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "apps" / "api"))
# replicate the engine's local-package path setup (app.main._configure_local_package_paths):
# routers import bare package roots like `guard.checker` that live under packages/<pkg>/<pkg>/.
_packages = HERE / "packages"
if _packages.exists():
    for _pkg in sorted(_packages.iterdir(), reverse=True):
        if (_pkg / "pyproject.toml").exists() or (_pkg / _pkg.name / "__init__.py").exists():
            _p = str(_pkg)
            if _p not in sys.path:
                sys.path.insert(0, _p)

HEALTH_PORT = 8509
STATUS = HERE / "data" / "autonomy" / "learner_daemon_status.json"


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib contract
        body = b'{"ok": true, "service": "atanor-learner"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):  # silence request logging
        pass


def _serve_health() -> None:
    HTTPServer(("127.0.0.1", HEALTH_PORT), _Health).serve_forever()


LOG = HERE / "data" / "autonomy" / "learner_daemon.log"


def _log(msg: str) -> None:
    """File log — the watchdog DEVNULLs our stdout, which made the empty-Tavily starvation
    invisible for an hour (measured 2026-07-11). Never again: every lifecycle event lands here."""
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def main() -> None:
    # THIS process runs the learners — make sure the external-mode gate is off HERE
    os.environ.pop("ATANOR_LEARNERS_EXTERNAL", None)
    # PRIORITY ISOLATION (2026-07-13): the learners already run GIL-free in this dedicated
    # process, but without a priority gap this process and the answer engine compete equally for
    # CPU cores — measured ~1s of answer latency. Self-demote to idle: full speed on free cores,
    # instant yield the moment the engine needs the CPU.
    try:
        from packages.graph_scale.load_signal import lower_process_priority
        _log(f"learner daemon priority -> {lower_process_priority()}")
    except Exception:
        pass
    _log(f"learner daemon starting (pid {os.getpid()})")
    threading.Thread(target=_serve_health, name="health", daemon=True).start()

    from app.routers import cloud_brain as cb

    started = cb.cloud_brain_continuous_start()   # continuous + relation discovery + firehose
    print(f"[learner-daemon] workers started: {started}", flush=True)


    # realizer's fusion grammar (+ the discourse thermometer) from the real prose the workers have
    # ingested, so fluency compounds autonomously — no hand-authoring. Error-isolated: a bad
    # re-mine must never kill the learners.
    _grammar_every = 60                            # 60 * 5s ≈ 5 min
    _tick = 0

    while True:
        _tick += 1
        if _tick % _grammar_every == 1:
            try:
                from packages.base_brain.learned_realizer import learn_and_save
                from packages.base_brain.discourse_learner import learn as _learn_discourse
                g = learn_and_save()
                _learn_discourse()
                _log(f"realizer grammar re-mined: n={g.get('n')} fusion_rate={g.get('fusion_rate')} "
                     f"connectives={list((g.get('noun_connectives') or {}).keys())}")
            except Exception as exc:
                _log(f"grammar re-mine skipped: {exc}")
        try:
            with cb._CONT_LOCK:
                cont = {k: v for k, v in cb._CONT.items() if isinstance(v, (int, float, str, bool, type(None)))}
            with cb._FIREHOSE_LOCK:
                fh = {k: v for k, v in cb._FIREHOSE.items() if isinstance(v, (int, float, str, bool, type(None)))}
            with cb._RELDISC_LOCK:
                rd = {k: v for k, v in cb._RELDISC.items() if isinstance(v, (int, float, str, bool, type(None)))}
                rd_recent = list(cb._RELDISC.get("recent") or [])
            STATUS.parent.mkdir(parents=True, exist_ok=True)
            STATUS.write_text(json.dumps({
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pid": os.getpid(),
                "external": True, "continuous": cont, "firehose": fh,
                "relation_discovery": {**rd, "recent": rd_recent},
            }, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:  # status must never kill the workers
            print(f"[learner-daemon] status write failed: {exc}", flush=True)
        time.sleep(5.0)


if __name__ == "__main__":
    main()
