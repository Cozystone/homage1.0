# -*- coding: utf-8 -*-
"""AL-1 — one REAL advisory round: mine our top residual, ask a live CLI advisor, scan the reply
as data, run it through constitutional intake, journal everything. Proves the loop end-to-end with
a real frontier mind (default: local ollama, free/unlimited).

  python scripts/advisor_round.py [--advisor ollama|claude|codex] [--n 1]
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.advisor_loop.advisor_session import ask_cli
from packages.advisor_loop.patch_intake import intake
from packages.advisor_loop.question_miner import mine


def main() -> int:
    advisor = sys.argv[sys.argv.index("--advisor") + 1] if "--advisor" in sys.argv else "ollama"
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 1
    questions = mine(max_questions=n)
    if not questions:
        print("no residual questions — batteries are perfect (unlikely); nothing to ask")
        return 0
    for q in questions:
        print(f"\n=== ATANOR asks [{q.topic}] (residual {q.residual:.3f}) ===")
        print(q.text)
        try:
            ex = ask_cli(advisor, q.prompt(), timeout_s=240)
        except Exception as e:
            print(f"advisor '{advisor}' unavailable: {e}")
            return 1
        print(f"\n--- {advisor} replied ({ex.elapsed_s}s, injection_findings={ex.injection_findings}) ---")
        print(ex.reply[:1400] + ("…" if len(ex.reply) > 1400 else ""))
        cand = intake(advisor, ex.reply, summary=f"advice on {q.topic}")
        print(f"\n--- constitutional intake: {cand.status} ---")
        if cand.reason:
            print(f"    reason: {cand.reason}")
        if cand.paths:
            print(f"    paths named: {cand.paths}")
        print("    (verdict is EMPIRICAL — a candidate still faces staging tests + sealed-gate "
              "no-regression before it can touch the tree)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
