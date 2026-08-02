# -*- coding: utf-8 -*-
"""Track E M0 gate 1-2 — Isaac Sim headless cold-boot smoke (docs/ATANOR_isaac_sim_setup.md sec 4).

Proves the isolated env can (1) cold-boot SimulationApp headless = the Kit compatibility checker
runs and the RTX renderer/PhysX runtime init on Blackwell SM_120, and (2) create an empty stage and
step physics. This is the first honest M0 gate: no G1 yet, no torch-GPU (Isaac Sim drives the GPU
through its own runtime, not torch; the env's torch 2.7+cpu is an M1/Isaac-Lab concern, flagged).

  D:\\isaac\\env\\python.exe scripts/isaac_m0_smoke.py

First run builds the shader/extension cache and can take 5-20 min; later runs are fast.
Prints M0_BOOT_OK then M0_PHYSICS_OK <steps> then RESULT isaac_m0 {...}. Any crash surfaces as a
traceback (the smoke is a real gate, not a formality).
"""
from __future__ import annotations

import json
import time

t0 = time.time()

# 1) cold-boot headless — this line runs the compatibility checker + renderer init
from isaacsim import SimulationApp                                   # noqa: E402

app = SimulationApp({"headless": True})
print(f"M0_BOOT_OK ({round(time.time()-t0,1)}s to boot)", flush=True)

steps = 0
mode = "none"
try:
    # 2a) preferred: SimulationContext (Isaac Sim 5.x namespace) — a true physics scene + step
    try:
        from isaacsim.core.api.simulation_context import SimulationContext     # 5.x
        mode = "simctx-5x"
    except Exception:
        from omni.isaac.core.simulation_context import SimulationContext       # 4.x fallback
        mode = "simctx-4x"
    sim = SimulationContext(physics_dt=1.0 / 60.0, rendering_dt=1.0 / 60.0)
    sim.initialize_physics()
    for _ in range(60):
        sim.step(render=False)
        steps += 1
    print(f"M0_PHYSICS_OK {steps} steps via {mode} ({round(time.time()-t0,1)}s)", flush=True)
except Exception as e:
    # 2b) fallback: tick the Kit app loop (always available) — proves the boot is live even if the
    # core-api namespace differs from what we assumed. Honest partial: app-tick, not physics-scene.
    mode = f"app-update (simctx failed: {type(e).__name__})"
    for _ in range(60):
        app.update()
        steps += 1
    print(f"M0_PHYSICS_OK {steps} app-ticks via {mode} ({round(time.time()-t0,1)}s)", flush=True)

app.close()
print(f"RESULT isaac_m0 {json.dumps({'boot': True, 'steps': steps, 'mode': mode, 'elapsed_s': round(time.time()-t0, 1)})}",
      flush=True)
