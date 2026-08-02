# -*- coding: utf-8 -*-
"""Speaker evolution arena — the owner's evolutionary network, first honest slice (2026-07-12).

: "16 5 5 
 ."

Five speaker VARIANTS (genomes over the holographic voice's phenotype knobs) compete on a
SEALED holdout fitness. At update time ( ) the champion's genome becomes the live
voice's parameters; the losers are not wasted — the token paths that made their lines fail
are harvested as ANTIBODIES (negative bias) that every later generation AND the live voice
must avoid. = , exactly the owner's design.

Natural selection, but confined to the one layer where evolution is SAFE:

 · what varies = HOW the voice speaks (window/decay/coherence/rep_penalty/top_k/temp) —
 surface phenotype only, the knobs of fluency;
 · what is fixed = WHAT is true. The concept graph and the answer pack are storage, not
 weights — evolution has no write path to them, so it cannot "evolve a
 lie" (facts-are-storage doctrine);
 · what selects = holdout seeds the genomes never fit on, RE-DRAWN each generation
 (anti-Goodhart: you cannot overfit an exam you never see twice), judged
 by the SAME Critic the self-play distill already trusts
 (speech_selfplay.critique — faithfulness hard gate, fluency target);
 · what survives = one champion genome (elitism) + everyone's failure receipts.

Runs OFFLINE (scripts/speaker_evolution.py) in worker processes — the engine only ever
READS the champion genome + antibody files. No store writes, no pack writes, no engine
process changes: P0 is structurally out of reach.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "data" / "evolution"
GENOME_PATH = OUT_DIR / "speaker_genome.json"
ANTIBODY_PATH = OUT_DIR / "antibodies.jsonl"
HISTORY_PATH = OUT_DIR / "arena_history.jsonl"

# The phenotype knobs under selection, with their viable ranges. dim and the vector-space
# seed stay FIXED across genomes so fitness differences come from the knobs, not from one
# genome drawing luckier random phasors. tone_strength is deliberately NOT a gene yet:
# fitness generation runs un-toned (no hormone state in the arena), so the knob would drift
# without selection pressure — it joins the genome when toned generation joins the exam.
BOUNDS: dict[str, tuple[float, float]] = {
    "window": (2, 4),
    "decay": (0.50, 0.90),
    "coherence": (0.35, 0.95),
    "rep_penalty": (0.50, 0.95),
    "top_k": (16, 80),
    "temp": (6.0, 20.0),
}
_INT_GENES = {"window", "top_k"}
DEFAULT_GENOME: dict[str, float] = {
    "window": 3, "decay": 0.70, "coherence": 0.70,
    "rep_penalty": 0.85, "top_k": 40, "temp": 12.0,
}

# fitness floors: a line below FAIL_FLOOR feeds the immune system; only lines at or above
# PASS_FLOOR count as healthy tissue (their bigrams are protected from antibody harvest).
FAIL_FLOOR = 0.35
PASS_FLOOR = 0.60
ANTIBODY_CAP = 2000  # bounded immune memory — oldest antibodies age out


def _clamp_gene(name: str, value: float) -> float:
    lo, hi = BOUNDS[name]
    v = max(lo, min(hi, float(value)))
    return int(round(v)) if name in _INT_GENES else round(v, 4)


def mutate(genome: dict[str, float], rng: random.Random, scale: float = 0.18) -> dict[str, float]:
    """Gaussian jitter on every gene, clamped to the viable range. `scale` is the step as a
    fraction of each gene's full range — small steps, so children stay near a working parent."""
    child = {}
    for name, (lo, hi) in BOUNDS.items():
        step = (hi - lo) * scale * rng.gauss(0.0, 1.0)
        child[name] = _clamp_gene(name, float(genome.get(name, DEFAULT_GENOME[name])) + step)
    return child


def crossover(a: dict[str, float], b: dict[str, float], rng: random.Random) -> dict[str, float]:
    """Uniform crossover: each gene from a random parent ( )."""
    return {name: _clamp_gene(name, (a if rng.random() < 0.5 else b).get(name, DEFAULT_GENOME[name]))
            for name in BOUNDS}


def _tokens(text: str) -> list[str]:
    from packages.cgsr.cgsr.holographic_lm import tokens
    return tokens(text)


def draw_seeds(holdout_lines: list[str], fit_corpus: list[str], rng: random.Random,
               k: int = 8) -> list[str]:
    """Seeds for the exam: topic-bearing tokens FROM THE HOLDOUT (which no genome fit on)
    that also occur in the fit corpus (else generation cannot leave the gate at all).
    Re-drawn every generation so no genome can memorize the exam."""
    fit_vocab: set[str] = set()
    for line in fit_corpus:
        fit_vocab.update(_tokens(line))
    pool: list[str] = []
    seen: set[str] = set()
    lines = list(holdout_lines)
    rng.shuffle(lines)
    for line in lines:
        for tok in _tokens(line):
            if len(tok) >= 2 and tok in fit_vocab and tok not in seen:
                seen.add(tok)
                pool.append(tok)
                break
        if len(pool) >= k:
            break
    return pool


def score_line(line: str, question: str = "") -> dict[str, Any]:
    """One judged line. The judge is the SAME Critic the self-play loop distilled the live
    voice with (faithfulness hard gate + fluency/conciseness), so the arena optimizes the
    bar the product already enforces — with two structural additions the Critic assumes:
    a line must be a clause (≥3 words) and must actually END (sentence-final)."""
    text = " ".join(str(line or "").split())
    out: dict[str, Any] = {"text": text, "total": 0.0}
    if len(text) < 10 or len(text.split()) < 3:
        out["reason"] = "debris"
        return out
    try:
        from packages.base_brain.speech_selfplay import critique
        crit = critique(text, facts=None, question=question)
        out.update({k: crit[k] for k in ("total", "faithful", "fluency", "conciseness") if k in crit})
        out["penalties"] = crit.get("penalties") or {}
    except Exception:
        # critic unavailable (bare env) → structural bars only, honestly weaker
        ends = text.endswith(("다", "요", ".", "!", "?", "…"))
        out["total"] = 0.5 if ends else 0.2
        out["reason"] = "critic_unavailable"
    return out


def evaluate_genome(genome: dict[str, float], fit_corpus: list[str], seeds: list[str],
                    antibody_pairs: list[list[str]]) -> dict[str, Any]:
    """One agent's whole life: fit the voice with its genome, sit the sealed exam, get
 judged. Returns fitness = mean judged score over the exam seeds (+ a small speed term:
 — two equally fluent voices, the cheaper one wins). Top-level and picklable
 so worker processes can run five lives in parallel."""
    from packages.cgsr.cgsr.holographic_lm import HolographicLM

    t0 = time.time()
    lm = HolographicLM(dim=256, window=int(genome["window"]), decay=float(genome["decay"]),
                       seed=7, semantic=False)
    lm.top_k = int(genome["top_k"])
    lm.temp = float(genome["temp"])
    lm.fit(fit_corpus)
    fit_s = time.time() - t0

    antibody = {(a, b) for a, b in antibody_pairs}
    lines: list[dict[str, Any]] = []
    t1 = time.time()
    for seed in seeds:
        toks = lm.generate_fluent(seed, max_len=16, coherence=float(genome["coherence"]),
                                  rep_penalty=float(genome["rep_penalty"]), antibody=antibody)
        lines.append(score_line(" ".join(toks)))
    gen_s = time.time() - t1

    scores = [l["total"] for l in lines]
    mean = sum(scores) / len(scores) if scores else 0.0

    # marks at ≤0.15s/line, zero at ≥1.5s/line.
    per_line = gen_s / max(1, len(seeds))
    economy = max(0.0, min(1.0, (1.5 - per_line) / 1.35))
    fitness = round(0.92 * mean + 0.08 * economy, 4)
    return {"genome": genome, "fitness": fitness, "mean_quality": round(mean, 4),
            "economy": round(economy, 4), "fit_s": round(fit_s, 2),
            "gen_s_per_line": round(per_line, 3), "lines": lines}


def harvest_antibodies(results: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """ : bigram token paths that appear in FAILING lines (< FAIL_FLOOR) and never
 in any PASSING line (≥ PASS_FLOOR) this generation. Conjunctive on purpose — a bigram
 that healthy speech also uses is tissue, not pathogen, and must not be banned."""
    fail_grams: set[tuple[str, str]] = set()
    pass_grams: set[tuple[str, str]] = set()
    for res in results:
        for line in res.get("lines") or []:
            toks = _tokens(line.get("text") or "")
            grams = set(zip(toks, toks[1:]))
            if float(line.get("total") or 0.0) < FAIL_FLOOR:
                fail_grams |= grams
            elif float(line.get("total") or 0.0) >= PASS_FLOOR:
                pass_grams |= grams
    return sorted(fail_grams - pass_grams)


def load_antibodies(path: Path = ANTIBODY_PATH, cap: int = ANTIBODY_CAP) -> list[list[str]]:
    if not path.exists():
        return []
    rows: list[list[str]] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(ln)
            rows.append([str(d["a"]), str(d["b"])])
        except Exception:
            continue
    return rows[-cap:]


def _append_antibodies(pairs: list[tuple[str, str]], generation: int) -> int:
    if not pairs:
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    known = {tuple(p) for p in load_antibodies()}
    fresh = [p for p in pairs if p not in known]
    if fresh:
        with ANTIBODY_PATH.open("a", encoding="utf-8") as f:
            for a, b in fresh:
                f.write(json.dumps({"a": a, "b": b, "gen": generation, "ts": time.time()},
                                   ensure_ascii=False) + "\n")
    # keep the immune memory bounded (oldest age out)
    rows = ANTIBODY_PATH.read_text(encoding="utf-8").splitlines()
    if len(rows) > ANTIBODY_CAP:
        ANTIBODY_PATH.write_text("\n".join(rows[-ANTIBODY_CAP:]) + "\n", encoding="utf-8")
    return len(fresh)


def save_champion(result: dict[str, Any], generation: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GENOME_PATH.write_text(json.dumps({
        "genome": result["genome"], "fitness": result["fitness"],
        "mean_quality": result["mean_quality"], "generation": generation,
        "ts": time.time(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def load_champion(path: Path = GENOME_PATH) -> dict[str, Any] | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d.get("genome"), dict) else None
    except Exception:
        return None


def evolve(fit_corpus: list[str], holdout_lines: list[str], *, pop: int = 5,
           generations: int = 6, workers: int = 5, rng_seed: int = 7,
           log=print) -> dict[str, Any]:
    """The full loop: population → sealed exam → selection → antibodies → reproduction.
 `workers` worker processes = the owner's "5 5" (serial when workers <= 1,
 which is what the tests use). Elitism 1: the champion is never mutated away."""
    rng = random.Random(rng_seed)
    champion = load_champion()
    base = dict(champion["genome"]) if champion else dict(DEFAULT_GENOME)
    population: list[dict[str, float]] = [base] + [mutate(base, rng) for _ in range(pop - 1)]

    history: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for gen in range(1, generations + 1):
        seeds = draw_seeds(holdout_lines, fit_corpus, rng)  # re-drawn: a fresh exam every generation
        if not seeds:
            raise RuntimeError("no viable exam seeds — holdout and fit corpus share no vocabulary")
        antibodies = load_antibodies()
        args = [(g, fit_corpus, seeds, antibodies) for g in population]
        if workers <= 1:
            results = [evaluate_genome(*a) for a in args]
        else:
            import multiprocessing as mp
            with mp.Pool(processes=workers) as pool:
                results = pool.starmap(evaluate_genome, args)
        results.sort(key=lambda r: -r["fitness"])
        gen_best = results[0]
        if best is None or gen_best["fitness"] > best["fitness"]:
            best = gen_best
            save_champion(best, gen)
        fresh = _append_antibodies(harvest_antibodies(results), gen)
        row = {"gen": gen, "seeds": seeds,
               "fitness": [r["fitness"] for r in results],
               "champion_fitness": best["fitness"], "new_antibodies": fresh}
        history.append(row)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({**row, "ts": time.time()}, ensure_ascii=False) + "\n")
        log(f"[gen {gen}] fitness={row['fitness']} champion={best['fitness']} "
            f"antibodies+{fresh} seeds={seeds[:4]}…")
        # reproduction: champion survives untouched; the rest are children of the top two
        parents = [results[0]["genome"], results[min(1, len(results) - 1)]["genome"]]
        population = [dict(best["genome"])] + [
            mutate(crossover(parents[0], parents[1], rng), rng) for _ in range(pop - 1)
        ]
    return {"champion": best, "history": history}
