# -*- coding: utf-8 -*-
"""Verification-path validation (stage e). We produce ZERO patches (fail-0 abstention), so there is
nothing of ATANOR's to score. What this DOES is a time-boxed GOLD self-test: run the official
swebench Docker harness on the dataset's own gold patch for one instance, to prove the eval path on
this machine correctly resolves a known-good patch. Honest outcomes: 'resolved' (path validated),
'eval-skipped-timeout' (image build/pull exceeded the box), or 'error' (with the reason)."""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO / "data" / "swe_eval" / "eval"


def docker_up() -> tuple[bool, str]:
    try:
        p = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                           capture_output=True, text=True, timeout=30)
        return (p.returncode == 0, (p.stdout or p.stderr).strip()[:100])
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def official_gold_selftest(instance_id: str, timeout_s: int = 480,
                           dataset: str = "princeton-nlp/SWE-bench_Verified",
                           namespace: str = "swebench",
                           run_id: str = "atanor_gold_selftest") -> dict[str, Any]:
    up, ver = docker_up()
    if not up:
        return {"status": "docker-down", "detail": ver}
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    for f in glob.glob(str(EVAL_DIR / f"gold.{run_id}.json")):
        os.remove(f)
    env = dict(os.environ, SWE_INSTANCE_ID=instance_id, SWE_DATASET=dataset,
               SWE_NAMESPACE=namespace, SWE_RUN_ID=run_id, SWE_TIMEOUT="1200",
               PYTHONIOENCODING="utf-8", PYTHONPATH=str(REPO))
    # run the shim runner by absolute path (it imports only swebench, no packages.* deps), so a
    # changed cwd cannot break module resolution.
    cmd = [sys.executable, "-X", "utf8", str(Path(__file__).parent / "_gold_runner.py")]
    try:
        p = subprocess.run(cmd, cwd=str(EVAL_DIR), env=env, capture_output=True, text=True,
                           timeout=timeout_s, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"status": "eval-skipped-timeout", "detail": f"exceeded {timeout_s}s box (image build/pull)"}
    tail = (p.stdout or "").strip().splitlines()[-6:] + (p.stderr or "").strip().splitlines()[-4:]
    # swebench writes gold.<run_id>.json with resolved_instances; find and parse it
    reports = glob.glob(str(EVAL_DIR / f"gold.{run_id}.json")) + \
        glob.glob(str(REPO / f"gold.{run_id}.json"))
    parsed: dict[str, Any] = {}
    for rp in reports:
        try:
            parsed = json.load(open(rp, encoding="utf-8"))
            break
        except Exception:
            continue
    resolved = int(parsed.get("resolved_instances", 0)) if parsed else 0
    status = "resolved" if resolved >= 1 else ("ran-unresolved" if parsed else "no-report")
    return {"status": status, "instance_id": instance_id, "namespace": namespace,
            "resolved_instances": resolved, "report": parsed or None,
            "returncode": p.returncode, "log_tail": tail[-8:]}


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    iid = sys.argv[1] if len(sys.argv) > 1 else "astropy__astropy-12907"
    box = int(sys.argv[2]) if len(sys.argv) > 2 else 480
    res = official_gold_selftest(iid, timeout_s=box)
    print(json.dumps({k: v for k, v in res.items() if k != "report"}, ensure_ascii=False, indent=2))
    # fold into report.json under 'eval'
    rjson = REPO / "data" / "swe_eval" / "report.json"
    if rjson.exists():
        rep = json.load(open(rjson, encoding="utf-8"))
        rep["eval"] = {"gold_selftest": {k: v for k, v in res.items() if k != "report"},
                       "atanor_patches_evaluated": 0,
                       "note": "ATANOR produced 0 patches (fail-0 abstain); resolved 0/10 by "
                               "construction. This is the eval path validated on the gold patch."}
        json.dump(rep, open(rjson, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("folded into report.json")
