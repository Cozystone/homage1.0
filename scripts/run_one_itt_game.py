# -*- coding: utf-8 -*-
"""Run ONE ITT game with fresh memory and write its record. Args: <game_id> <seed>. Token via env.
Used to run games in parallel (each process = one independent, fresh-memory game)."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packages.itt.adapters import AtanorAdapter, OllamaAdapter, OpenClawAdapter  # noqa: E402
from packages.itt.orchestrator import run_session  # noqa: E402

gid = sys.argv[1] if len(sys.argv) > 1 else "g1"
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 0
key = os.environ.get("ITT_OPENCLAW_KEY")
if not key:
    print("NO ITT_OPENCLAW_KEY"); sys.exit(1)

adapters = {"atanor": AtanorAdapter(), "ollama": OllamaAdapter(), "openclaw": OpenClawAdapter(key)}
rec = run_session(adapters, session_id=f"laws_{gid}", rounds=4, seed=seed)
out = ROOT / "data" / "itt" / f"game_{gid}.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
print(f"game_{gid} done: {out}")
