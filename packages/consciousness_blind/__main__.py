# -*- coding: utf-8 -*-
"""CLI: python -m packages.consciousness_blind  ->  run the blind assessment, save verdict + report."""
from __future__ import annotations

from packages.consciousness_blind.judge import run_blind, VERDICT_JSON, REPORT_MD


def main() -> None:
    v = run_blind(save=True)
    agg = v["aggregate_blind_score"]
    print(f"BLIND: present={agg['present']}/{agg['of']} partial={agg['partial']} "
          f"absent={agg['absent']} falsely-present-caught={agg['falsely_present_caught']}")
    print(f"adversarial: caught={v['adversarial']['caught']}/{v['adversarial']['of']} "
          f"fooled={v['adversarial']['fooled'] or 'none'}")
    d = v["delta_vs_self_audit"]
    print(f"delta: self-audit present {d['self_audit_present']}/14 -> blind present "
          f"{d['blind_present']}/14 ({d['reading']})")
    for drop in d["drops"]:
        print(f"  DROP {drop['id']} {drop['self_audit']}->{drop['blind']}")
    for th, row in v["by_theory"].items():
        print(f"  {th}: present {row['present']}/{row['total']}  {row['present_ids']}")
    print("verdict:", VERDICT_JSON)
    print("report :", REPORT_MD)


if __name__ == "__main__":
    main()
