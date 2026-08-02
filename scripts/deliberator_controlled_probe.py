# -*- coding: utf-8 -*-
"""DELIBERATOR System-2 — bounded structured-engine integrity probe.

Every item's required facts ARE in the probe KB, so the score isolates the reasoner from the world
graph's knowledge gap. Typed goals are supplied directly, so this does NOT exercise natural-language
compilation or establish GPQA/MMLU capability.  It prints grounded firing, proof-derived multi-step
firing, derivation accuracy, and the 작화0 controls, plus inspectable proof trails.

  python scripts/deliberator_controlled_probe.py [--trails]
"""
from __future__ import annotations

import io
import hashlib
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
for _d in sorted((REPO / "packages").iterdir(), reverse=True):
    if (_d / "pyproject.toml").exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from packages.reasoning_vm.deliberator.controlled_probe import (  # noqa: E402
    build_probe_kb, run_probe,
)
from packages.reasoning_vm.deliberator.reasoner import Deliberator  # noqa: E402

PROBE_SCHEMA = "atanor.deliberator.controlled_probe.v2"
_SOURCE_PATHS = (
    "scripts/deliberator_controlled_probe.py",
    "packages/reasoning_vm/deliberator/controlled_probe.py",
    "packages/reasoning_vm/deliberator/reasoner.py",
    "packages/reasoning_vm/deliberator/back_chain.py",
    "packages/reasoning_vm/deliberator/kernel_forge.py",
)


def _source_provenance() -> dict:
    records = []
    for relative in _SOURCE_PATHS:
        path = REPO / relative
        raw = path.read_bytes()
        records.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
        )
    canonical = json.dumps(
        records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        shell=False,
        check=False,
    )
    return {
        "git_head": (
            completed.stdout.decode("ascii", errors="replace").strip()
            if completed.returncode == 0
            else None
        ),
        "scope": "bounded fixture and structured reasoner executable sources",
        "files": records,
        "source_content_sha256": hashlib.sha256(canonical).hexdigest(),
        "fixture_sha256": next(
            record["sha256"]
            for record in records
            if record["path"].endswith("/controlled_probe.py")
            and not record["path"].startswith("scripts/")
        ),
    }


def _sample_trails() -> list[str]:
    fa, ip, custom = build_probe_kb()
    dlb = Deliberator(fa, inherit_props=ip, with_kernels=True, max_depth=6)
    dlb.chainer.rules = dlb.chainer.rules + custom
    trails = []
    for label, kind, args in [
        ("compose+transitive: seoul located_in earth", "prove", ("seoul", "located_in", "earth")),
        ("custom rule: abe grandparent_of ?", "derive", ("abe", "grandparent_of")),
        ("syllogism: socrates has_property mortal", "prove", ("socrates", "has_property", "mortal")),
        ("kernel: chloride_ion net_charge", "derive", ("chloride_ion", "net_charge")),
    ]:
        out = dlb.can_prove(*args) if kind == "prove" else dlb.derive(*args)
        trails.append(f"### {label}\n{out.get('trail', '(no trail)')}")
    return trails


def main() -> int:
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "_"
        + uuid.uuid4().hex[:12]
    )
    t0 = time.time()
    r = run_probe()
    r["schema_version"] = PROBE_SCHEMA
    r["run_id"] = run_id
    r["scope"] = "typed goals supplied; natural-language compiler not exercised"
    r["fixture_kind"] = "bounded in-code structured fixture"
    r["source_provenance"] = _source_provenance()
    r["elapsed_s"] = round(time.time() - t0, 2)
    print("=== DELIBERATOR bounded structured-engine integrity probe ===")
    print("  scope                      typed goals supplied; NL compiler not exercised")
    for k in ("n_positive", "n_negative", "grounded_firing_rate", "multistep_firing_rate",
              "reasoning_accuracy", "accuracy_when_answered", "negative_abstention_rate"):
        print(f"  {k:26s} {r[k]}")
    print(f"  {'fabrications (must be [])':26s} {r['fabrications']}")
    if "--trails" in sys.argv:
        print("\n=== worked multi-step proof trails ===")
        for t in _sample_trails():
            print("\n" + t)
    out = REPO / "reports" / "benchmarks"
    out.mkdir(parents=True, exist_ok=True)
    fp = out / f"deliberator_controlled_probe_{run_id}.json"
    with fp.open("x", encoding="utf-8") as handle:
        json.dump(r, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(f"\nwrote {fp}")
    verdict = (r["grounded_firing_rate"] == 1.0 and r["multistep_firing_rate"] == 1.0
               and r["reasoning_accuracy"] == 1.0
               and r["negative_abstention_rate"] == 1.0 and not r["fabrications"])
    print("VERDICT:", "STRUCTURED CORE INTEGRITY PASS — not an external-capability claim" if verdict
          else "structured core incomplete — see per-item")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
