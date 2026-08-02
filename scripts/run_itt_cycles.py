# -*- coding: utf-8 -*-
"""Run many ITT cycles with the assembled trio and evaluate. Detached-friendly: writes per-session
records to quarantine and appends outcomes for the learned strategy to consume. Token via env only."""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packages.itt.adapters import AtanorAdapter, OllamaAdapter, OpenClawAdapter  # noqa: E402
from packages.itt.orchestrator import run_session  # noqa: E402
from packages.itt.evaluation import score_session, aggregate, record_outcome, load_outcomes  # noqa

LOG = ROOT / "data" / "itt" / "cycles.log"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 2


def log(m: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")


def main() -> None:
    key = os.environ.get("ITT_OPENCLAW_KEY")
    if not key:
        log("NO ITT_OPENCLAW_KEY in env; aborting"); return
    log(f"START cycles={N} rounds={ROUNDS}")
    outs = []
    for i in range(N):
        # FRESH adapters per game -> fresh memory each game (fairness). Seat/topic randomized per
        # session inside run_session. The game runs until all three declare who the human is.
        adapters = {"atanor": AtanorAdapter(), "ollama": OllamaAdapter(),
                    "openclaw": OpenClawAdapter(key)}     # new openclaw session id per game
        rec = run_session(adapters, session_id=f"cycle_{int(time.time())}_{i}", rounds=ROUNDS, seed=100 + i)
        o = score_session(rec)
        record_outcome(o)
        outs.append(o)
        log(f"c{i+1} topic={o['topic'][:40]!r} judges_picked_atanor={o['judges_picked_atanor']}/{o['n_judges']} "
            f"humanity_claims={o['atanor_humanity_claims']} offtopic={o['atanor_offtopic_turns']}/{o['atanor_turns']} "
            f"empty_other={o['other_backend_empty_turns']}")
    agg = aggregate(load_outcomes())
    log(f"AGGREGATE (all-time) {agg}")


if __name__ == "__main__":
    main()
