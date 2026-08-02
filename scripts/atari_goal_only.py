# -*- coding: utf-8 -*-
"""Give it the score and nothing else. Does finding its own body fall out on the way?

    python scripts/atari_goal_only.py

Owner: 몸을 찾으라고 줘야만 해? 딱 점수를 내와 라고만 주면 스스로 방안을 찾을 수 없나? 그 과정에서
몸도 찾고.

That is a criticism of what I had been doing and it lands. I decomposed the problem myself — find the
body, then learn the schema, then play — and handed each piece over as a specification. Nothing
justified that decomposition; it was my guess at what is needed. A system that can only solve the
sub-problems someone else carved out is not the thing this project is trying to build. The rule
against supplying content was kept and a curriculum was supplied instead.

SO NOTHING HERE IS TOLD TO FIND A BODY. The outer measure is the game's score. Inside, the only drive
is the one already built: `packages/hand/explore.py` chooses moves by how much NEW WORLD they deliver,
where new means far from everything already seen. Body identity is then MEASURED afterwards, as a
side effect, using the same command-prediction statistic that failed when it was the stated task. If
it comes out higher here, the decomposition was not just unnecessary but harmful.

THE HONEST OTHER SIDE. "Just give it the score" only works if the search can find anything. Nine
actions over thousands of steps is a space blind search does not cross, which is why credit
assignment is the whole difficulty in this kind of game. So the comparison is against what random
play scores, and if curiosity does not beat random the answer is that the goal alone was not enough
— which is worth knowing and is not a failure of the idea.

THREE ARMS, because one number cannot separate learning from luck:

    random        uniform actions — the floor
    curiosity     novelty-driven choice, no body task, no score signal used to choose
    replay        the curiosity run's action sequence, replayed from a different seed

Replay is the control that matters. If the curiosity arm scores well and its own action sequence
scores just as well replayed into a differently-seeded game, the score came from the sequence
happening to suit that maze, not from anything responsive.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_babble import blobs, match, sprite_mask          # noqa: E402
from scripts.atari_find_body import command_prediction, measured_warmup   # noqa: E402

OUT = Path("data/atari/goal_only.json")
GAME = "ALE/MsPacman-v5"


def make_env():
    import ale_py  # noqa: F401
    import gymnasium as gym
    return gym.make(GAME, obs_type="rgb", frameskip=1, repeat_action_probability=0.0)


def retina(frame: np.ndarray) -> np.ndarray:
    """The same coarse code the eye already uses, so novelty here means what it means elsewhere."""
    from packages.perception.attention import frame_signature
    return frame_signature(frame)


def play(mode: str, steps: int, warm: int, seed: int, actions=None):
    """One episode. `mode` is 'random' or 'curiosity'; `actions` replays a recorded sequence."""
    from packages.perception.attention import change_energy

    env = make_env()
    obs, _ = env.reset(seed=seed)
    for _ in range(warm):
        obs, *_ = env.step(0)
    n_a = env.action_space.n
    rng = np.random.default_rng(seed)

    bgbuf = []
    for _ in range(150):
        obs, *_ = env.step(int(rng.integers(0, n_a)))
        bgbuf.append(obs)
    bg = np.median(np.array(bgbuf, dtype=np.int16), axis=0)

    seen: list[np.ndarray] = [retina(obs)]
    value = {a: [0.0, 0] for a in range(n_a)}          # [total novelty, tries]
    score = 0.0
    chosen: list[int] = []
    tracks: dict[int, list] = defaultdict(list)
    prev = blobs(sprite_mask(obs, bg))
    ids = list(range(len(prev)))
    nxt = len(prev)
    HOLD = 6

    for t in range(steps):
        if actions is not None:
            a = actions[t % len(actions)]
        elif mode == "random":
            a = int(rng.integers(0, n_a))
        else:
            # optimism for the untried, then measured novelty. No score term anywhere.
            def sc(k):
                tot, n = value[k]
                return 1e9 if n == 0 else tot / n + 0.5 * np.sqrt(np.log(t + 2) / n)
            a = max(range(n_a), key=sc)
        chosen.append(a)
        for _ in range(HOLD):
            obs, r, term, trunc, _i = env.step(a)
            score += float(r)
            if term or trunc:
                obs, _ = env.reset()
                for _ in range(warm):
                    obs, *_ = env.step(0)
        code = retina(obs)
        nov = min(change_energy(code, s) for s in seen) if seen else 1.0
        if nov >= 0.02:
            seen.append(code)
            if len(seen) > 3000:
                seen.pop(0)
        if mode == "curiosity" and actions is None:
            value[a][0] += float(nov)
            value[a][1] += 1

        cur = blobs(sprite_mask(obs, bg))
        new_ids: list = [None] * len(cur)
        for i0, i1, dx, dy in match(prev, cur):
            new_ids[i1] = ids[i0]
            if abs(dx) > 0.5 or abs(dy) > 0.5:
                tracks[ids[i0]].append((a, dx, dy))
        for k in range(len(cur)):
            if new_ids[k] is None:
                new_ids[k] = nxt
                nxt += 1
        prev, ids = cur, new_ids
    env.close()
    return {"score": score, "actions": chosen, "tracks": tracks, "places": len(seen)}


def body_excess(tracks, rng) -> tuple[float, float]:
    """The command-prediction excess of the best track, and the field mean. Measured, not asked for."""
    rows_out = []
    for _tr, rows in tracks.items():
        if len(rows) < 20:
            continue
        real = command_prediction(rows)
        acts = [a for a, _dx, _dy in rows]
        null = []
        for _ in range(40):
            sh = list(acts)
            rng.shuffle(sh)
            null.append(command_prediction([(sh[i], rows[i][1], rows[i][2])
                                            for i in range(len(rows))]))
        rows_out.append(real - float(np.mean(null)))
    if not rows_out:
        return 0.0, 0.0
    v = np.array(sorted(rows_out, reverse=True))
    return float(v[0]), float(v[1:].mean() if len(v) > 1 else 0.0)


def main() -> None:
    env = make_env()
    warm = measured_warmup(env, env.action_space.n)
    env.close()
    print(f"control begins after {warm} warmup frames (measured)\n")

    STEPS, SEEDS = 500, 3
    rng = np.random.default_rng(0)
    res: dict[str, dict] = {}

    for mode in ("random", "curiosity"):
        scores, bodies, fields, places = [], [], [], []
        rec = None
        for s in range(SEEDS):
            out = play(mode, STEPS, warm, seed=100 + s)
            b, f = body_excess(out["tracks"], rng)
            scores.append(out["score"])
            bodies.append(b)
            fields.append(f)
            places.append(out["places"])
            if mode == "curiosity" and rec is None:
                rec = out["actions"]
        res[mode] = {"score_mean": float(np.mean(scores)), "scores": scores,
                     "body_excess": float(np.mean(bodies)),
                     "field_mean": float(np.mean(fields)),
                     "places_seen": float(np.mean(places))}
        print(f"{mode:10} score {np.mean(scores):7.1f} {scores}   "
              f"body-excess {np.mean(bodies):.4f} (field {np.mean(fields):.4f})   "
              f"places {np.mean(places):.0f}")

    # the control that matters: replay curiosity's own actions into differently-seeded games
    rep = []
    for s in range(SEEDS):
        out = play("replay", STEPS, warm, seed=900 + s, actions=rec)
        rep.append(out["score"])
    res["replay"] = {"score_mean": float(np.mean(rep)), "scores": rep}
    print(f"{'replay':10} score {np.mean(rep):7.1f} {rep}   "
          f"(curiosity's own sequence, different maze seeds)")

    c, r_, p = res["curiosity"]["score_mean"], res["random"]["score_mean"], res["replay"]["score_mean"]
    print(f"\n-> curiosity beats random: {c > r_}   ({c:.1f} vs {r_:.1f})")
    print(f"-> and beats its own replay: {c > p}   ({c:.1f} vs {p:.1f})")
    print(f"   if it beats random but not replay, the score came from the SEQUENCE, not from responding")
    print(f"\n-> body identity as a SIDE EFFECT (never asked for):")
    print(f"     curiosity  best {res['curiosity']['body_excess']:.4f}  field {res['curiosity']['field_mean']:.4f}")
    print(f"     random     best {res['random']['body_excess']:.4f}  field {res['random']['field_mean']:.4f}")
    print(f"     when it WAS the stated task: best 0.1403, field 0.0153, bar 1.5x -> failed at 1.48x")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
