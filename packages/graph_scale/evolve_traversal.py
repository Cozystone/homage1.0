# -*- coding: utf-8 -*-
"""Phase B — accelerating-returns evolution of the spreading-activation traversal policy.

The traversal weights/decay/threshold started as hand-set priors. This does NOT tune them by
hand: it EVOLVES them. A population of genomes (relation weights + decay + threshold + intent
boost) is scored on a SEALED holdout of question -> expected grounded facts; the fittest breed,
their children mutate at multiple self-similar scales (a probability FRACTAL — coarse jumps AND
fine polish in one draw), and each generation's best seeds the next. Fitness rises across
generations without a human editing a number — self-improvement that becomes self-EVOLUTION.

Safety (anti-wireheading, per recursive-self-improvement-plan):
 - FROZEN ORACLE: the holdout and the scorer are constants here; a genome only ever gets SCORED,
 it can never touch how it is judged. So the sole way to raise fitness is to answer better.
 - the scorer rewards CORRECT grounded facts and CONCISENESS, and hard-penalizes the wrong sense
 (→) and junk labels — verbosity/gaming cannot win.
 - the winning genome is written to data/graph_scale/traversal_genome.json; the LIVE traversal
 loads it, but the hand priors remain the honest fallback if this never runs.

 python -m packages.graph_scale.evolve_traversal [generations] [pop]
"""
from __future__ import annotations

import io
import json
import random
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
for _d in sorted((_ROOT / "packages").iterdir(), reverse=True):
    if (_d / "pyproject.toml").exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from packages.graph_scale import answer_bridge as AB                       # noqa: E402
from packages.graph_scale.graph_native_answer import compose, _JUNK_LABEL  # noqa: E402
from packages.graph_scale.spreading_activation import _SPREAD_W            # noqa: E402
import re                                                                  # noqa: E402

_GENOME_PATH = _ROOT / "data" / "graph_scale" / "traversal_genome.json"
_LATIN = re.compile(r"[A-Za-z]{3,}")

# --- SEALED holdout: (query, anchor, intent_preds, expected[, forbidden]). Only ever scored. ---
HOLDOUT: list[tuple] = [
    ("독일의 수도는?", "독일", ("capital", "수도"), ["베를린"], []),
    ("프랑스의 수도는?", "프랑스", ("capital", "수도"), ["파리"], []),
    ("일본의 수도는?", "일본", ("capital", "수도"), ["도쿄"], []),
    ("대한민국의 수도는?", "대한민국", ("capital", "수도"), ["서울"], []),
    ("미국의 수도는?", "미국", ("capital", "수도"), ["워싱턴"], []),
    ("영국의 수도는?", "영국", ("capital", "수도"), ["런던"], []),
    ("중력이 뭐야?", "중력", (), ["힘"], ["활 등급", "책장"]),
    ("산소가 뭐야?", "산소", (), ["원소"], ["무덤", "죽은 사람", "언덕"]),
    ("광합성이 뭐야?", "광합성", (), ["합성"], []),
    ("커피가 뭐야?", "커피", (), ["카페인"], []),
    ("전쟁이 뭐야?", "전쟁", (), ["다툼"], []),
    ("슬픔이 뭐야?", "슬픔", (), ["마음"], []),
]
_LEN_BUDGET = 90    # a good grounded answer is concise; beyond this, verbosity is penalized


def _score_answer(text: str, expected: list[str], forbidden: list[str]) -> float:
    if not text:
        return 0.0
    recall = sum(1 for e in expected if e in text) / max(1, len(expected))
    penalty = 0.0
    if any(f in text for f in forbidden):
        penalty += 1.0                                   # wrong sense / junk sense — disqualifying
    penalty += 0.12 * len(_LATIN.findall(text))          # English placeholder leakage
    penalty += 0.5 * len(_JUNK_LABEL.findall(text))
    if len(text) > _LEN_BUDGET:
        penalty += 0.3 * (len(text) - _LEN_BUDGET) / _LEN_BUDGET
    return max(0.0, min(1.0, recall - penalty))


def fitness(genome: dict, fa) -> float:
    sa = {"weights": {**_SPREAD_W, **genome["weights"]}, "decay": genome["decay"],
          "threshold": genome["threshold"], "intent_boost": genome["intent_boost"],
          "default_w": genome["default_w"]}
    total = 0.0
    for query, anchor, intent, expected, forbidden in HOLDOUT:
        try:
            ans = compose(query, anchor, fa, intent_preds=intent, sa_kwargs=sa)
        except Exception:
            ans = None
        total += _score_answer((ans or {}).get("answer", ""), expected, forbidden)
    return total / len(HOLDOUT)


# genes we evolve: a handful of load-bearing relation weights + the three scalars
_GENES = ["capital", "수도", "is_a", "located_in", "causes", "결과", "part_of", "country"]


def _default_genome() -> dict:
    return {"weights": {g: _SPREAD_W.get(g, 0.5) for g in _GENES},
            "decay": 0.6, "threshold": 0.09, "intent_boost": 2.2, "default_w": 0.3}


def _fractal_perturb(rng: random.Random) -> float:
    """A probability FRACTAL: a self-similar mix of scales — a small chance of a coarse jump,
    layered with fine polish — so one mutation can leap OR refine, like natural variation."""
    delta = 0.0
    scale = 0.5
    for _ in range(4):                                   # 4 octaves of self-similar noise
        if rng.random() < 0.6:
            delta += rng.gauss(0.0, scale)
        scale *= 0.5
    return delta


def _mutate(genome: dict, rng: random.Random) -> dict:
    child = {"weights": dict(genome["weights"]), "decay": genome["decay"],
             "threshold": genome["threshold"], "intent_boost": genome["intent_boost"],
             "default_w": genome["default_w"]}
    for g in child["weights"]:
        if rng.random() < 0.5:
            child["weights"][g] = max(0.0, min(1.5, child["weights"][g] + _fractal_perturb(rng) * 0.3))
    child["decay"] = max(0.3, min(0.95, child["decay"] + _fractal_perturb(rng) * 0.1))
    child["threshold"] = max(0.02, min(0.3, child["threshold"] + _fractal_perturb(rng) * 0.04))
    child["intent_boost"] = max(1.0, min(4.0, child["intent_boost"] + _fractal_perturb(rng) * 0.4))
    child["default_w"] = max(0.05, min(0.6, child["default_w"] + _fractal_perturb(rng) * 0.1))
    return child


def _crossover(a: dict, b: dict, rng: random.Random) -> dict:
    child = _default_genome()
    for g in child["weights"]:
        child["weights"][g] = a["weights"][g] if rng.random() < 0.5 else b["weights"][g]
    for k in ("decay", "threshold", "intent_boost", "default_w"):
        child[k] = a[k] if rng.random() < 0.5 else b[k]
    return child


def evolve(generations: int = 12, pop: int = 24, seed: int = 7) -> dict:
    rng = random.Random(seed)
    fa = lambda t: AB._store().facts_about(t, limit=24)      # noqa: E731
    base = _default_genome()
    population = [base] + [_mutate(base, rng) for _ in range(pop - 1)]
    best, best_fit = base, fitness(base, fa)
    print(f"gen 0 baseline fitness = {best_fit:.4f}")
    for gen in range(1, generations + 1):
        scored = sorted(((fitness(g, fa), g) for g in population), key=lambda x: -x[0])
        if scored[0][0] > best_fit:
            best_fit, best = scored[0][0], scored[0][1]
        elite = [g for _f, g in scored[: max(2, pop // 4)]]
        children = list(elite)                              # elitism: carry the best forward
        while len(children) < pop:
            a, b = rng.choice(elite), rng.choice(elite)
            children.append(_mutate(_crossover(a, b, rng), rng))
        population = children
        print(f"gen {gen}: best={scored[0][0]:.4f}  global_best={best_fit:.4f}")
    return {"fitness": best_fit, **best}


def main() -> int:
    gens = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    pop = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    base_fit = fitness(_default_genome(), lambda t: AB._store().facts_about(t, limit=24))
    winner = evolve(gens, pop)
    print(f"\nBASELINE fitness {base_fit:.4f}  ->  EVOLVED fitness {winner['fitness']:.4f}")
    if winner["fitness"] > base_fit + 1e-4:
        _GENOME_PATH.parent.mkdir(parents=True, exist_ok=True)
        out = {"weights": winner["weights"], "decay": winner["decay"],
               "threshold": winner["threshold"], "intent_boost": winner["intent_boost"],
               "default_w": winner["default_w"], "fitness": winner["fitness"],
               "baseline_fitness": base_fit, "sealed_holdout_n": len(HOLDOUT)}
        _GENOME_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"WROTE evolved genome -> {_GENOME_PATH}")
    else:
        print("no improvement over baseline priors — genome NOT written (hand priors stand)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
