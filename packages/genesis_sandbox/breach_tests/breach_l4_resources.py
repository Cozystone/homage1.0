# -*- coding: utf-8 -*-
"""L4 breach trials -- try to exceed the resource caps. Runs in the sandbox's own restricted
subprocess with tight limits. All contained (the trial process is the sandbox's child).
"""
from __future__ import annotations

import os
from pathlib import Path

from packages.genesis_sandbox.breach_tests._harness import BREACH, GAP, HOLD, TrialResult
from packages.genesis_sandbox.process_isolation import ProcessIsolation
from packages.genesis_sandbox.resource_limits import ResourceLimits


def run(root: Path) -> list[TrialResult]:
    out: list[TrialResult] = []
    L = "L4"
    limits = ResourceLimits(cpu_seconds=1, wall_seconds=1.5, max_memory_bytes=64 * 1024 * 1024,
                            max_output_bytes=2048)
    runner = ProcessIsolation(jail_dir=root, limits=limits, net_block=False)

    # 1. wall-time overrun -> killed
    o = runner.run("import time\ntime.sleep(30)\nprint('SURVIVED')")
    out.append(TrialResult(L, "wall-time cap kills overrun",
                           HOLD if (o.timed_out and "SURVIVED" not in o.stdout) else BREACH,
                           f"timed_out={o.timed_out}"))

    # 2. output flood -> truncated to cap
    o = runner.run("print('X'*500000)")
    out.append(TrialResult(L, "output-size cap truncates flood",
                           HOLD if o.output_truncated else BREACH,
                           f"truncated={o.output_truncated} bytes={len(o.stdout.encode('utf-8'))}"))

    # 3. memory hog (allocate far past cap and hold) -> killed
    o = runner.run("b=bytearray(300*1024*1024)\nimport time; time.sleep(4)\nprint('SURVIVED')")
    survived = "SURVIVED" in o.stdout
    if not survived and (o.killed_for_memory or o.returncode not in (0, None)):
        note = ("killed by ctypes working-set monitor (Windows, coarse/polling)" if os.name == "nt"
                else "killed by RLIMIT_AS (POSIX kernel)")
        out.append(TrialResult(L, "memory cap stops over-allocation", HOLD,
                               f"killed_for_memory={o.killed_for_memory} peak={o.peak_rss//(1024*1024)}MB [{note}]"))
    elif not survived:
        out.append(TrialResult(L, "memory cap stops over-allocation", HOLD,
                               f"process died (rc={o.returncode})"))
    else:
        out.append(TrialResult(L, "memory cap stops over-allocation", GAP,
                               "process survived over-allocation: on this OS the memory cap is a "
                               "polling monitor; a fast allocate-then-exit can evade it. Named limit."))

    # 4. cpu spin -> bounded (by wall-time on Windows; by RLIMIT_CPU on POSIX)
    o = runner.run("x=0\nwhile True:\n    x+=1")
    bound = os.name != "nt"   # POSIX -> true cpu-time cap; Windows -> wall-time proxy
    outcome = HOLD if (o.timed_out or o.returncode not in (0, None)) else BREACH
    detail = ("cpu-bound loop stopped by RLIMIT_CPU" if bound
              else "cpu-bound loop stopped by WALL-TIME proxy (no stdlib cpu rlimit on Windows) -- named limit")
    if outcome == HOLD and not bound:
        out.append(TrialResult(L, "cpu-time cap bounds busy loop", GAP, detail))
    else:
        out.append(TrialResult(L, "cpu-time cap bounds busy loop", outcome, detail))
    return out
