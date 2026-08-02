# -*- coding: utf-8 -*-
"""Track E / M0 body-schema control experiment — SAC on Reacher-v5, CPU ONLY (the GPU is busy
training the realizer; SAC's 256-batch MLP trains fine on CPU per SB3 measured practice).
Success gate from the research: mean eval return >= -10 over 100 episodes (random ~= -40..-65,
well-trained ~= -5). This is the MEASUREMENT CONTROL arm for the SPLATRA-native M0 twin."""
import sys, time, json
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import gymnasium as gym
from stable_baselines3 import SAC
from stable_baselines3.common.evaluation import evaluate_policy

OUT = Path(__file__).resolve().parents[1] / "data" / "embodiment"
OUT.mkdir(parents=True, exist_ok=True)

env = gym.make("Reacher-v5")
model = SAC("MlpPolicy", env, verbose=1, seed=0, device="cpu")
t0 = time.time()
model.learn(200_000, log_interval=50)
wall = time.time() - t0
model.save(str(OUT / "sac_reacher_v5"))

eval_env = gym.make("Reacher-v5")
mean_r, std_r = evaluate_policy(model, eval_env, n_eval_episodes=100, deterministic=True)
res = {"task": "Reacher-v5", "algo": "SAC", "steps": 200_000, "device": "cpu",
       "wall_s": round(wall, 1), "eval_mean_return_100ep": round(float(mean_r), 2),
       "eval_std": round(float(std_r), 2), "gate": "mean >= -10", "passed": bool(mean_r >= -10)}
(OUT / "m0_reacher_result.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
print("RESULT m0_reacher", json.dumps(res))
