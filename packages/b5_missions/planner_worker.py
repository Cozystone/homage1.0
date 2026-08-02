# -*- coding: utf-8 -*-
"""Out-of-process planner worker for B5-3-E2E (audit #4: process-level seal).

Reads a JSON list of cases -- each {"idx", "bones"} and NOTHING else -- on stdin, runs the
production reasoning-VM planner, and writes the plans on stdout. The ground-truth labels never enter
this process's memory, so there is no `raw`/grader object to reach for: the seal is physical, not a
tripwire. The grader runs in the parent process with the answer keys.
"""
from __future__ import annotations

import json
import sys

from packages.reasoning_vm.precondition_planner import plan_preconditions


def main() -> None:
    cases = json.loads(sys.stdin.read())
    out = []
    for c in cases:
        plan = plan_preconditions(c["bones"])            # bones ONLY -- no labels exist here
        out.append({
            "idx": c["idx"],
            "steps": [{"text": s.text, "support": s.support} for s in plan.steps],
            "abstained": plan.abstained,
            "goal_emitted": plan.goal_emitted,
        })
    print(json.dumps(out))


if __name__ == "__main__":
    main()
