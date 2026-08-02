# -*- coding: utf-8 -*-
"""Learner SHARD worker — one GIL-free process of the split-then-merge sharding prototype.

`python scripts/learner_shard.py <shard_id> <N>` runs the same always-on learners as
learner_daemon.py, but with EVERY write path isolated to this shard so N processes never
contend for one file (the single-writer contract at N-way scale):

  * corpus  : ATANOR_CORPUS_SHARD=<id> → narrative_corpus.shard<id>.jsonl (union-read by all)
  * candidate store : ATANOR_CANDIDATE_STORE_PATH=<...>/candidate_store.shard<id>
  * health  : 8509 + id          (the watchdog probes each; RSS-capped per service)
  * status  : learner_daemon_status.shard<id>.json

Safety (docs/ATANOR_multiprocess_sharding_design.md):
  * SPLIT = independent random (each worker fetches its own wiki; the offline compactor dedups
    at the tail) — zero coordination, the safest N-way start.
  * The P0 sentinel data/autonomy/LEARNING_FROZEN is a shared file that cloud_brain's worker
    already checks each tick, so every shard freezes together on any regression.
  * Promotion stays OFF; shards only grow the corpus + candidate stores, never the answer pack
    ([[diet-flood-p0-regression]]). The offline compactor (corpus_compactor.py) folds shards
    into main between runs.
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
_packages = HERE / "packages"
if _packages.exists():
    for _pkg in sorted(_packages.iterdir(), reverse=True):
        if (_pkg / "pyproject.toml").exists() or (_pkg / _pkg.name / "__init__.py").exists():
            _p = str(_pkg)
            if _p not in sys.path:
                sys.path.insert(0, _p)

# fresh port range so shard health servers never collide with :8509 learner / :8510 ops-relay
# / :8511 p0-sentinel: shard i listens on 8520+i.
BASE_HEALTH_PORT = 8520


def _parse_args() -> tuple[str, int]:
    shard_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ATANOR_CORPUS_SHARD", "0")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.environ.get("ATANOR_CORPUS_SHARDS", "3"))
    return str(shard_id), n


def _isolate_writes(shard_id: str) -> None:
    """Point every write path at this shard so N workers never share a file."""
    os.environ["ATANOR_CORPUS_SHARD"] = shard_id
    # candidate store: a per-shard directory keeps the single-writer contract when promotion
    # is later re-enabled; the compactor merges shard candidates by k-source consensus then.
    cand_root = HERE / "data" / "cloud_brain" / "candidate_store" / f"shard{shard_id}"
    os.environ["ATANOR_CANDIDATE_STORE_PATH"] = str(cand_root)


def _health_server(port: int, shard_id: str) -> None:
    body = json.dumps({"ok": True, "service": f"atanor-learner-shard-{shard_id}"}).encode()

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib contract
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a):
            pass

    HTTPServer(("127.0.0.1", port), _H).serve_forever()


def main() -> None:
    shard_id, n = _parse_args()
    _isolate_writes(shard_id)
    os.environ.pop("ATANOR_LEARNERS_EXTERNAL", None)   # THIS process runs the workers

    port = BASE_HEALTH_PORT + int(shard_id)   # 8520 + id (collision-free range)
    status = HERE / "data" / "autonomy" / f"learner_daemon_status.shard{shard_id}.json"

    print(f"[learner-shard {shard_id}/{n}] pid {os.getpid()} health :{port} "
          f"corpus=shard{shard_id} cand={os.environ['ATANOR_CANDIDATE_STORE_PATH']}", flush=True)
    threading.Thread(target=_health_server, args=(port, shard_id), name="health", daemon=True).start()

    from app.routers import cloud_brain as cb

    started = cb.cloud_brain_continuous_start()
    print(f"[learner-shard {shard_id}] workers started: {started}", flush=True)

    while True:
        try:
            with cb._CONT_LOCK:
                cont = {k: v for k, v in cb._CONT.items()
                        if isinstance(v, (int, float, str, bool, type(None)))}
            status.parent.mkdir(parents=True, exist_ok=True)
            status.write_text(json.dumps({
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pid": os.getpid(),
                "shard": shard_id, "shards": n, "continuous": cont,
                "frozen": bool(cont.get("frozen")),
            }, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            print(f"[learner-shard {shard_id}] status write failed: {exc}", flush=True)
        time.sleep(5.0)


if __name__ == "__main__":
    main()
