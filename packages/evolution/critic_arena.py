# -*- coding: utf-8 -*-
"""Critic arena — RSI layer ②: the evaluator sharpens ITSELF, safely (owner 2026-07-12:
" ").

The speaker arena evolves HOW the voice speaks. This evolves the CRITIC that judges the voice —
its fluency coefficients (penalty weights + the score mix). The one thing that makes self-evolving
an evaluator not-catastrophic is that every candidate is graded against a ground truth it cannot
touch:

 · candidates = coefficient genomes over speech_selfplay's tunable weights (never the structure);
 · fitness = frozen_oracle.meta_score — separation between the sealed human good/bad exemplars,
 an exam fixed OUTSIDE the loop, so 'rate everything 10/10' scores zero and dies;
 · promotion = critic_integrity.promotable — BOTH the behavioral oracle AND the structural check
 (the faithfulness hard gate must survive). A coefficient change can't touch the
 structure, so structural always passes here; the value is that the SAME gate guards
 coefficient-evolution and any future code-level Critic proposal, uniformly.

Champion coefficients are written to data/evolution/critic_genome.json; speech_selfplay._coeffs()
reads them (mtime-cached). Absent file → the hand-tuned defaults, so nothing changes until a
champion actually beats the exam. Offline only; no store/pack/engine writes.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any, Callable

from packages.base_brain.speech_selfplay import _CRITIC_DEFAULTS

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "data" / "evolution"
GENOME_PATH = OUT_DIR / "critic_genome.json"
HISTORY_PATH = OUT_DIR / "critic_arena_history.jsonl"

# viable ranges for each coefficient — wide enough to sharpen, clamped so no term is zeroed out of
# existence (a 0 penalty weight = a disarmed check; the floor keeps every guard alive).
BOUNDS: dict[str, tuple[float, float]] = {
    "run_on": (0.08, 0.35), "repetition": (0.06, 0.30), "dup_phrase": (0.04, 0.25),
    "foreign": (0.02, 0.20), "dangling": (0.06, 0.30),
    "fluency_w": (0.45, 0.75), "concise_w": (0.15, 0.45), "variety_step": (0.01, 0.06),
}


def _clamp(name: str, v: float) -> float:
    lo, hi = BOUNDS[name]
    return round(max(lo, min(hi, float(v))), 4)


def mutate(genome: dict[str, float], rng: random.Random, scale: float = 0.15) -> dict[str, float]:
    return {k: _clamp(k, genome.get(k, _CRITIC_DEFAULTS[k]) + (hi - lo) * scale * rng.gauss(0, 1))
            for k, (lo, hi) in BOUNDS.items()}


def crossover(a: dict[str, float], b: dict[str, float], rng: random.Random) -> dict[str, float]:
    return {k: _clamp(k, (a if rng.random() < 0.5 else b).get(k, _CRITIC_DEFAULTS[k])) for k in BOUNDS}


def critic_fn_for(genome: dict[str, float]) -> Callable[[str], float]:
    """A critique() scorer that uses THIS candidate's coefficients — by temporarily swapping the
    live coefficient cache around the call. Returns total in [0,1]; the faithfulness gate is inert
    here (the oracle exemplars carry no facts, so _faithful returns True) — we are scoring FLUENCY
    discrimination, which is exactly what these coefficients control."""
    from packages.base_brain import speech_selfplay as sp

    coeffs = dict(_CRITIC_DEFAULTS)
    coeffs.update({k: genome[k] for k in BOUNDS if k in genome})

    def _score(text: str) -> float:
        saved = sp._COEFF_OVERRIDE
        sp._COEFF_OVERRIDE = coeffs
        try:
            return float(sp.critique(text, facts=None, question="")["total"])
        finally:
            sp._COEFF_OVERRIDE = saved

    return _score


def evaluate(genome: dict[str, float]) -> dict[str, Any]:
    from packages.evolution.frozen_oracle import meta_score
    ms = meta_score(critic_fn_for(genome))
    # fitness = separation, with a small bonus for balanced accuracy (both good AND bad judged right)
    fitness = round(max(0.0, ms.get("separation", 0.0)) * (0.5 + 0.5 * ms.get("balanced_acc", 0.0)), 4)
    return {"genome": genome, "fitness": fitness, "separation": ms.get("separation", 0.0),
            "balanced_acc": ms.get("balanced_acc", 0.0), "verified": ms.get("verified", False)}


def load_champion() -> dict[str, Any] | None:
    try:
        d = json.loads(GENOME_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d.get("genome"), dict) else None
    except Exception:
        return None


def _save_champion(res: dict[str, Any], generation: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GENOME_PATH.write_text(json.dumps({
        "genome": res["genome"], "fitness": res["fitness"], "separation": res["separation"],
        "balanced_acc": res["balanced_acc"], "generation": generation, "ts": time.time(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def evolve(*, pop: int = 5, generations: int = 8, rng_seed: int = 7, log=print) -> dict[str, Any]:
    """Population of coefficient genomes competing on the frozen oracle. Elitism 1. A champion is
    saved ONLY when it beats the incumbent through the full anti-cheat gate (behavioral + structural),
    so promotion of the evaluator is always through the same door a code-level proposal would use."""
    from packages.evolution.critic_integrity import CRITIC_SRC, promotable

    rng = random.Random(rng_seed)
    incumbent = load_champion()
    base = dict(incumbent["genome"]) if incumbent else dict(_CRITIC_DEFAULTS)
    # the incumbent's actual behavior is the baseline the gate must be beaten against
    inc_fn = critic_fn_for(base)
    inc_eval = evaluate(base)
    if not inc_eval["verified"]:
        return {"promoted": False, "reason": "frozen_oracle_seal_broken"}

    population = [base] + [mutate(base, rng) for _ in range(pop - 1)]
    best = inc_eval
    src = CRITIC_SRC.read_text(encoding="utf-8")  # unchanged — coefficient-only evolution
    history: list[dict[str, Any]] = []
    for gen in range(1, generations + 1):
        results = sorted((evaluate(g) for g in population), key=lambda r: -r["fitness"])
        top = results[0]
        if top["fitness"] > best["fitness"]:
            gate = promotable(src, critic_fn_for(top["genome"]), inc_fn, margin=0.01)
            if gate["promote"]:
                best = top
                _save_champion(best, gen)
        row = {"gen": gen, "fitness": [r["fitness"] for r in results],
               "champion_fitness": best["fitness"], "champion_sep": best["separation"]}
        history.append(row)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({**row, "ts": time.time()}, ensure_ascii=False) + "\n")
        log(f"[critic gen {gen}] fitness={row['fitness']} champion={best['fitness']} sep={best['separation']}")
        parents = [results[0]["genome"], results[min(1, len(results) - 1)]["genome"]]
        population = [dict(best["genome"])] + [
            mutate(crossover(parents[0], parents[1], rng), rng) for _ in range(pop - 1)]
    improved = best["fitness"] > inc_eval["fitness"]
    return {"promoted": improved, "champion": best, "baseline": inc_eval, "history": history}
