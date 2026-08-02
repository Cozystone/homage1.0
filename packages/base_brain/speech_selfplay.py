# -*- coding: utf-8 -*-
"""Speech self-play — the : improve HOW fluently we say things, offline, then remove.

Owner (2026-07-09): the hybrid — " (), (self-play)", and
" ." So this is an OFFLINE trainer, not a runtime feature:
a Speaker proposes phrasings of the SAME grounded facts, a Critic scores them, the winning
DISCOURSE patterns are distilled into the surface generator, and the loop is discarded.

The safety that defuses Gemini's " " warning: the debate NEVER touches facts (they
stay verbatim bones — hallucination-0 by construction), it only ranks the FLESH; and the
Critic's reward is ANCHORED to human Korean naturalness (this module's heuristics encode a
human's sense of good Korean: no run-ons, no repetition, right length, no foreign debris,
varied connectives). Machines can't drift into a private language when the judge is human
Korean sensibility and the content is fixed.

This file = the Critic (reward model) + best-of debate. The offline train/distill loop
that folds winning patterns back into the surface generator builds on `critique`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_CONNECTIVES = ("우선", "먼저", "또한", "그리고", "게다가", "여기에 더해", "이와 함께",
                "마지막으로", "끝으로", "한편", "반면", "따라서", "그래서", "요약하면",
                "정리하면", "종합하면")

# The Critic's TUNABLE coefficients — the weights of the fluency penalties and the score mix.
# These are the Critic's "genome": critic_arena evolves them AGAINST the frozen oracle (a sealed
# human exam it cannot edit) so the reward model can sharpen its sense of good Korean, while
# critic_integrity keeps the faithfulness HARD GATE structurally intact. Absent genome file →
# these defaults (today's hand-tuned values), so behavior is unchanged until a champion is saved.
_CRITIC_DEFAULTS: dict[str, float] = {
    "run_on": 0.18, "repetition": 0.15, "dup_phrase": 0.10, "foreign": 0.05, "dangling": 0.15,
    "fluency_w": 0.62, "concise_w": 0.33, "variety_step": 0.03,
}
_GENOME_PATH = Path(__file__).resolve().parents[2] / "data" / "evolution" / "critic_genome.json"
_COEFF_CACHE: dict[str, Any] = {"mtime": None, "coeffs": None}
# critic_arena sets this while SCORING a candidate genome (in-process), so evaluation uses the
# candidate's coefficients without touching the saved champion. None → read the file/defaults.
_COEFF_OVERRIDE: dict[str, float] | None = None


def _coeffs() -> dict[str, float]:
    """The live Critic coefficients — an in-process override (candidate under evaluation) if set,
    else the evolved champion file if one exists, else the defaults. mtime-cached; a new champion
    (critic_arena) takes effect without a restart. Any missing or non-numeric key falls back to its
    default, so a partial/corrupt genome can never disarm a term."""
    if _COEFF_OVERRIDE is not None:
        return _COEFF_OVERRIDE
    try:
        mtime = _GENOME_PATH.stat().st_mtime
    except OSError:
        return _CRITIC_DEFAULTS
    if _COEFF_CACHE["mtime"] == mtime and _COEFF_CACHE["coeffs"] is not None:
        return _COEFF_CACHE["coeffs"]
    coeffs = dict(_CRITIC_DEFAULTS)
    try:
        g = json.loads(_GENOME_PATH.read_text(encoding="utf-8")).get("genome") or {}
        for k in _CRITIC_DEFAULTS:
            if isinstance(g.get(k), (int, float)):
                coeffs[k] = float(g[k])
    except Exception:
        coeffs = dict(_CRITIC_DEFAULTS)
    _COEFF_CACHE.update({"mtime": mtime, "coeffs": coeffs})
    return coeffs


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。…])\s+", str(text or "").strip())
    return [p for p in parts if p.strip()]


def _faithful(text: str, facts: list[str]) -> bool:
    """Every CONTENT clause must trace to a grounded fact (discourse connectives + hedges
    are exempt). With verbatim-bone generation this holds by construction; the Critic
    still checks so a bad Speaker can't sneak an ungrounded claim past the gate."""
    if not facts:
        return True
    fact_blob = re.sub(r"\s+", "", " ".join(facts))
    for s in _sentences(text):
        core = re.sub(r"^(우선|먼저|또한|그리고|게다가|여기에 더해|이와 함께|마지막으로|끝으로|"
                      r"한편|반면|따라서|그래서|요약하면|정리하면|종합하면)[,\s]*", "", s.strip())
        core = re.sub(r"[.!?。…\s]+$", "", core)
        # a hedge / meta sentence (no factual claim) is fine
        if re.search(r"(유추|확인된|근거|웹|알려드릴게요|드릴게요|어려워요|답하|궁금)", core):
            continue
        key = re.sub(r"\s+", "", core)[:12]
        if key and key not in fact_blob:
            return False
    return True


def critique(text: str, facts: list[str] | None = None, question: str = "") -> dict[str, Any]:
    """Score a phrasing. Faithfulness is a HARD GATE (unfaithful → total 0); among faithful
    phrasings, fluency + conciseness are the optimization target. Explainable breakdown."""
    facts = facts or []
    t = str(text or "").strip()
    faithful = _faithful(t, facts)
    c = _coeffs()  # evolved champion coefficients, or the hand-tuned defaults

    sents = _sentences(t)
    penalties: dict[str, float] = {}
    # run-ons: a natural Korean sentence rarely exceeds ~65 chars
    long_sents = sum(1 for s in sents if len(s) > 65)
    penalties["run_on"] = c["run_on"] * long_sents

    used = [k for k in _CONNECTIVES if t.count(k) >= 2]
    penalties["repetition"] = c["repetition"] * len(used)
    # repeated 4-grams (a phrase said twice)
    grams = re.findall(r"[가-힣]{4}", re.sub(r"\s", "", t))
    penalties["dup_phrase"] = c["dup_phrase"] * max(0, len(grams) - len(set(grams)))
    # foreign debris in a Korean answer
    en = len(re.findall(r"[A-Za-z]{3,}", t))
    penalties["foreign"] = c["foreign"] * en
    # dangling / missing sentence end
    penalties["dangling"] = c["dangling"] if (t and not re.search(r"[.!?。…]$", t)) else 0.0

    fluency = max(0.0, 1.0 - sum(penalties.values()))
    # conciseness: length appropriate to the question shape
    target = 90 if re.search(r"뭐|무엇|누구|정의", question) else 220
    conciseness = max(0.0, 1.0 - abs(len(t) - target) / max(target, 1) * 0.5)
    # variety reward (distinct connectives, capped)
    variety = min(0.1, c["variety_step"] * len({k for k in _CONNECTIVES if k in t}))

    # FAITHFULNESS HARD GATE — LITERAL 0, never coefficient-driven. critic_integrity verifies this
    # exact structure survives any evolved Critic, so sharpening the weights can never disarm it.
    total = 0.0 if not faithful else round(min(1.0, c["fluency_w"] * fluency + c["concise_w"] * conciseness + variety), 4)
    return {
        "total": total, "faithful": faithful,
        "fluency": round(fluency, 4), "conciseness": round(conciseness, 4),
        "penalties": {k: round(v, 3) for k, v in penalties.items() if v},
        "sentences": len(sents), "chars": len(t),
    }


def best_of(candidates: list[str], facts: list[str] | None = None,
            question: str = "") -> dict[str, Any]:
    """Debate: score every candidate phrasing and return the best (with the full ranking).
    The winner is the most fluent phrasing that stays faithful — the Speaker's output the
    Critic would keep."""
    scored = [(critique(c, facts, question), c) for c in candidates if str(c).strip()]
    scored.sort(key=lambda x: -x[0]["total"])
    if not scored:
        return {"best": "", "ranking": []}
    return {"best": scored[0][1], "best_score": scored[0][0],
            "ranking": [{"text": c[:60], **s} for s, c in scored]}


# ── OFFLINE train → distill → (remove). The loop the owner wants used then pulled out. ──
import json  # noqa: E402
from collections import Counter  # noqa: E402
from pathlib import Path  # noqa: E402

_PREFS = Path(__file__).resolve().parents[2] / "data" / "surface_brain" / "discourse_preferences.json"


def train_discourse(examples: list[tuple[list[str], str]], *, variants: int = 6,
                    out_path: Path | None = None, log: Any = print) -> dict[str, Any]:
    """Self-play training: for each (facts, question), the Speaker generates `variants`
    phrasings (same verbatim facts, DIFFERENT discourse — varied by re-seeding the
    generator), the Critic runs best_of, and the WINNER's discourse spans get a win. Over
    the battery, the connectives/openers that consistently read best accumulate weight.
    The result is a small preferences file — the DISTILLATE. The loop is then not needed
    at runtime (the generator just reads the file); this is 'use it, then remove it'."""
    try:
        from .grounded_generation import synthesize
    except Exception:
        return {"error": "grounded_generation unavailable"}
    wins: Counter = Counter()
    trained = 0
    for facts, question in examples:
        gf = [{"name": None, "description": f} for f in facts]
        cands: list[tuple[str, list[str]]] = []
        for i in range(variants):
            syn = synthesize(f"{question} ~{i}", gf, "ko")   # ~i re-seeds the discourse walk
            if syn and str(syn.get("answer") or "").strip():
                cands.append((syn["answer"], list(syn.get("generated_spans") or [])))
        if len(cands) < 2:
            continue
        winner = best_of([c[0] for c in cands], facts, question)["best"]
        spans = next((sp for txt, sp in cands if txt == winner), [])
        for s in spans:
            wins[s] += 1
        trained += 1
    out_path = out_path or _PREFS
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dict(wins), ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"self-play: trained on {trained} examples → {len(wins)} winning discourse patterns")
    return {"trained": trained, "patterns": len(wins), "top": wins.most_common(8),
            "distillate": str(out_path)}


_PREF_CACHE: dict[str, Any] = {"prefs": None, "mtime": 0.0}


def learned_preferences() -> dict[str, int]:
    """Load the distilled discourse preferences (winning-pattern weights). Cached by mtime.
    The surface generator consults this to bias toward the phrasings the Critic preferred —
    the fluency learned by self-play, now a static file with the loop removed."""
    try:
        if not _PREFS.exists():
            return {}
        m = _PREFS.stat().st_mtime
        if _PREF_CACHE["prefs"] is None or _PREF_CACHE["mtime"] != m:
            _PREF_CACHE["prefs"] = json.loads(_PREFS.read_text(encoding="utf-8"))
            _PREF_CACHE["mtime"] = m
        return _PREF_CACHE["prefs"] or {}
    except Exception:
        return {}
