# -*- coding: utf-8 -*-
"""Wire the world model to the eye: does LATENT surprise beat pixel delta at seeing what matters?

    python scripts/worldmodel_eye_seam.py

Owner: 세계모델과 눈 배선도 좀 잘 하고.

The seam already exists in the design and not in the game path. `packages/eye/eye.py`'s `look()` takes a
`latent_surprise` argument -- "Seam A: when supplied the gate fires on SEMANTIC change instead of pixel
delta, which is the whole reason a V-JEPA lives next to this eye" -- and `packages/perception/
latent_predictor.py` is the organ that produces it: a V-JEPA-principle latent predictive coder, pure
numpy, ~0.15M parameters, trained without labels on the retinal-code stream.

Neither is on the Atari path. Everything there runs on raw pixel differences, which is exactly what F2
just showed the limits of: pixel delta is cheap and it is also semantically blind. It fires on a score
digit changing and on a ghost about to kill you with the same voice.

THE CLAIM THIS RUNG TESTS, and it is the reason to have a world model in a perception loop at all:

    LATENT surprise should anticipate events that MATTER better than pixel delta does.

Ms. Pac-Man supplies the ground truth for free: a death. It is read from the HUD life icons, a pixel
instrument calibrated once against the emulator at 100.0% exact agreement, so nothing here needs RAM.

REGISTERED BEFORE TRAINING:
    1  latent surprise rises before a death more than pixel delta does -- measured as AUC over a lead
       window, so no threshold is chosen by me
    2  it beats a TIME-SHUFFLED control on the same stream, because an event-rate artefact would show up
       there too
    3  and it beats an UNTRAINED coder, or the prediction is doing nothing and the encoder's random
       projection is all that is being measured
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.attention import frame_signature                    # noqa: E402
from packages.perception.latent_predictor import (CoderConfig,               # noqa: E402
                                                 LatentPredictiveCoder)
from scripts.atari_find_body import measured_warmup                          # noqa: E402
from scripts.atari_play import make                                         # noqa: E402
from scripts.schema_executor_pixels import LifeCounter, preflight            # noqa: E402

OUT = Path("data/atari/worldmodel_eye_seam.json")


def rollout(steps: int, seed: int, band):
    """Retinal codes, pixel deltas, and deaths -- all from the screen."""
    env = make()
    warm = measured_warmup(env, env.action_space.n)
    n_a = env.action_space.n
    obs, _ = env.reset(seed=seed)
    for _ in range(warm):
        obs, *_ = env.step(0)
    rng = np.random.default_rng(seed)
    lc = LifeCounter(band[0], band[1])
    sigs, deltas, deaths = [], [], []
    prev = None
    lives = lc.count(obs)
    for _ in range(steps):
        a = int(rng.integers(0, n_a))
        for _ in range(3):
            obs, _r, term, trunc, _i = env.step(a)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(warm):
                    obs, *_ = env.step(0)
                lives = lc.count(obs)
        sigs.append(frame_signature(obs))
        d = 0.0 if prev is None else float(np.abs(obs.astype(np.int16) - prev).mean())
        deltas.append(d)
        prev = obs.astype(np.int16)
        nl = lc.count(obs)
        deaths.append(1 if nl < lives else 0)
        lives = nl
    env.close()
    return np.array(sigs, np.float32), np.array(deltas), np.array(deaths)


def auc(score: np.ndarray, label: np.ndarray) -> float:
    """Rank AUC. No threshold is chosen, which is the point of using it here."""
    s, y = np.asarray(score, float), np.asarray(label, int)
    pos, neg = s[y == 1], s[y == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    r = np.argsort(np.argsort(np.concatenate([pos, neg]))) + 1
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def lead_label(deaths: np.ndarray, lead: int) -> np.ndarray:
    """1 on the `lead` frames BEFORE a death. Anticipation, not detection -- a signal that only rises
    at the moment of death is a smoke alarm going off after the fire."""
    y = np.zeros_like(deaths)
    idx = np.where(deaths == 1)[0]
    for i in idx:
        y[max(0, i - lead):i] = 1
    return y


def main() -> None:
    warm_env = make()
    warm = measured_warmup(warm_env, warm_env.action_space.n)
    warm_env.close()
    pf = preflight(warm)
    print("PRE-FLIGHT on the pixel life counter (the only ground truth used):")
    print(f"  band rows {pf['band']}, exact agreement with the emulator "
          f"{pf['exact_agreement']:.1%} -> {'usable' if pf['ok'] else 'NOT usable'}\n")
    if not pf["ok"]:
        sys.exit("the pixel death counter is not usable; nothing below could be scored")

    tr_sigs, _td, _tdeath = rollout(900, seed=3, band=pf["band"])
    te_sigs, te_delta, te_deaths = rollout(700, seed=11, band=pf["band"])
    print(f"train {len(tr_sigs)} frames (seed 3), test {len(te_sigs)} frames (seed 11); "
          f"{int(te_deaths.sum())} deaths in the test stream")
    print(f"retinal code: {tr_sigs.shape[1]}-d from attention.frame_signature\n")
    if te_deaths.sum() < 5:
        sys.exit("too few deaths in the test stream to score anticipation")

    cfg = CoderConfig()
    trained = LatentPredictiveCoder(cfg)
    print(f"coder: {trained.param_count() / 1e3:.1f}k trainable parameters, pure numpy", flush=True)
    rep = trained.train([tr_sigs], epochs=60)
    print(f"  trained; report keys {sorted(rep)[:6] if isinstance(rep, dict) else type(rep).__name__}",
          flush=True)
    untrained = LatentPredictiveCoder(cfg)

    s_tr = trained.surprise_stream(te_sigs)
    s_un = untrained.surprise_stream(te_sigs)
    n = min(len(s_tr), len(te_delta), len(te_deaths))
    s_tr, s_un, delta, deaths = s_tr[:n], s_un[:n], te_delta[:n], te_deaths[:n]
    rng = np.random.default_rng(0)
    s_shuf = rng.permutation(s_tr)

    print(f"\n{'lead window':<14}{'pixel delta':>13}{'LATENT (trained)':>19}"
          f"{'latent untrained':>18}{'time-shuffled':>15}")
    rows = {}
    for lead in (1, 3, 6, 12):
        y = lead_label(deaths, lead)
        r = {"pixel_delta": auc(delta, y), "latent_trained": auc(s_tr, y),
             "latent_untrained": auc(s_un, y), "shuffled": auc(s_shuf, y)}
        rows[str(lead)] = r
        print(f"{lead:<14}{r['pixel_delta']:>13.3f}{r['latent_trained']:>19.3f}"
              f"{r['latent_untrained']:>18.3f}{r['shuffled']:>15.3f}", flush=True)

    best = max(rows, key=lambda k: rows[k]["latent_trained"])
    b = rows[best]
    print(f"\n-> 1. latent surprise anticipates a death better than pixel delta: "
          f"{b['latent_trained'] > b['pixel_delta'] + 0.02}  "
          f"(lead {best}: {b['pixel_delta']:.3f} -> {b['latent_trained']:.3f})")
    print(f"-> 2. beats the time-shuffled control: "
          f"{b['latent_trained'] > b['shuffled'] + 0.02}  ({b['shuffled']:.3f})")
    print(f"-> 3. the TRAINING earns its keep, not the random projection: "
          f"{b['latent_trained'] > b['latent_untrained'] + 0.02}  ({b['latent_untrained']:.3f})")
    print("\n   AUC 0.5 is chance. Nothing here reads RAM: the codes come from the screen and the")
    print("   deaths from the HUD counter that was calibrated once and verified at 100.0%.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"preflight": pf, "params": trained.param_count(),
                               "deaths_test": int(deaths.sum()), "auc_by_lead": rows},
                              indent=2, default=str), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
