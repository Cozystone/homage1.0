# -*- coding: utf-8 -*-
"""Run ONE self-improvement cycle with a live advisor search (default: local ollama, free).
Measures ATANOR's worst residuals, searches to understand them, routes results through the
constitution, journals the cycle. The owner's universal benchmark self-improvement loop, running.

  python scripts/self_improve_cycle.py [--top 2] [--advisor ollama]
"""
import sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(REPO))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from packages.advisor_loop.advisor_session import ask_cli
from packages.self_improve.loop import run_cycle, journal

def main():
    top = int(sys.argv[sys.argv.index("--top")+1]) if "--top" in sys.argv else 2
    adv = sys.argv[sys.argv.index("--advisor")+1] if "--advisor" in sys.argv else "ollama"
    def search(q):
        try: return ask_cli(adv, q.prompt(), timeout_s=120).reply
        except Exception as e: return ""
    rep = run_cycle(search_fn=search, top_k=top)
    journal(rep, now_utc=time.time())
    print("=== self-improvement cycle ===")
    for w in rep.weaknesses: print(f"  weakness: {w['topic']} (residual {w['residual']:.3f})")
    for c in rep.candidates: print(f"  -> {c['topic']}: intake={c['status']}"
                                   + (f" ({c['reason']})" if c.get('reason') else ""))
    print(f"SUMMARY: {rep.summary}")
    return 0
raise SystemExit(main())
