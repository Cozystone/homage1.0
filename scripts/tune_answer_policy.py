#!/usr/bin/env python3
"""Run the answer-policy self-tuner: measure routing quality on the labelled battery,
do bounded margin coordinate descent, and (optionally) save the improved weights.

The tuner only ever RAISES routing accuracy — it can self-correct a drifted/bad policy
but can never lower quality. Safe to run periodically or on demand.

  python scripts/tune_answer_policy.py            # dry run (report only)
  python scripts/tune_answer_policy.py --save      # persist if it strictly improves
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from packages.base_brain.answer_policy_tuning import tune  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="persist improved weights (only if accuracy rose)")
    ap.add_argument("--steps", type=int, default=30)
    args = ap.parse_args()
    report = tune(steps=args.steps, save=args.save)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[TUNE] accuracy {report['base_accuracy']} -> {report['tuned_accuracy']}"
          f" | improved={report['improved']} | saved={report.get('saved', False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
