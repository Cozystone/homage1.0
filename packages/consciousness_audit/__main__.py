# -*- coding: utf-8 -*-
"""Run the battery: `python -X utf8 -m packages.consciousness_audit`."""
from __future__ import annotations

from packages.consciousness_audit.battery import run_all, SCORECARD


def main() -> None:
    sc = run_all()
    c = sc["counts"]
    print(f"present={c['present']} partial={c['partial']} absent={c['absent']} flagged={c['flagged']}")
    for th, row in sc["by_theory"].items():
        print(f"  {th}: {row['present']}/{row['total']} present  {row['present_ids']}")
    print("build queue:", ", ".join(f"{q['id']}({q['verdict']})" for q in sc["build_queue"]) or "empty")
    print("scorecard:", SCORECARD)


if __name__ == "__main__":
    main()
