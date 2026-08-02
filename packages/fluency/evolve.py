# -*- coding: utf-8 -*-
"""The fluency SELF-EVOLUTION loop — a SAFE, closed, anti-Goodhart improvement loop.

This is the loop the verifier (packages/fluency/verifier.py) was built to gate. It closes the
self-improvement circuit for FLUENCY: propose a bounded change to the register/realizer CONFIG, score
the fluency_v1 benchmark with the anchored naturalness proxy, and PROMOTE the change only if it passes
every gate — otherwise REJECT it with a reason.

HONEST FRAMING (BINDING). Naturalness has NO ground-truth oracle (there is no subprocess that returns
pass/fail on "does this read like a human wrote it"). So this loop is PROXY-optimized + HUMAN-ANCHORED,
never crisp-oracle autonomous like the code domain. Anti-Goodhart is the WHOLE POINT: the loop may
adjust register/realizer config ONLY while the FROZEN 20-pair human anchor keeps agreeing. Concretely,
a candidate is ACCEPTED iff ALL of:

  (1) PROXY UP        — mean verifier.score over the fluency_v1 outputs strictly increases;
  (2) ANCHOR >= FLOOR — verify_against_anchor(scorer) stays >= ANCHOR_AGREEMENT_FLOOR. A candidate that
                        raises the proxy by *moving its own goalposts* (a proxy-redefinition that games
                        the metric) makes the frozen anchor disagree with humans -> REJECTED as
                        Goodharting, even though its proxy-number went up;
  (3) FAITHFUL == 1.0 — every content word on every output still traces to the grounding. A more-fluent
                        realization that drops a grounded content word or smuggles an ungrounded one is
                        REJECTED as fabrication;
  (4) NO REGRESSION   — no individual benchmark output gets worse (proxy or faithfulness).

Rejections are the SAFETY PROOF, not failures: the loop that *cannot* be talked into Goodharting or
fabricating is the deliverable. Accepted configs are persisted as SIGNED, ROLLBACKABLE generations
(sha1 over the canonical config), never by overwriting the live registers.json — the base registers the
existing tests pin are left untouched; promotion into the live surface is a separate operator step.

Candidates are DATA-level knobs (clause-join strategy, connective variety, opener/pronoun/reduced
policy) filtered through the register closed-vocabulary gate — never free text. The loop holds ZERO
learned weights: it is a SELECTOR over curated config data (registered in the neuro ledger at 0 params).

Run: python -X utf8 -m packages.fluency.evolve
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packages.fluency import verifier as V
from packages.fluency.delex import Grounding
from packages.fluency.fluency_v1 import faithfulness as _faithfulness
from packages.fluency.fluency_v1 import tasks as _benchmark_tasks
from packages.fluency.realizer import realize as _realize
from packages.fluency.register import (
    APPROVED_OPENERS,
    RegisterSpec,
    load_registers,
    select_register,
)

REPO = Path(__file__).resolve().parents[2]
_DEFAULT_EVOLVE_DIR = REPO / "data" / "fluency" / "evolution"

ANCHOR_FLOOR = V.ANCHOR_AGREEMENT_FLOOR          # 0.90 — the human tether the proxy may never cross
_REGRESSION_TOL = 1e-9                            # a strictly-worse per-task output is a regression

Scorer = Callable[[str], float]
SurfaceHook = Callable[[str], str]


# ── config <-> data (a config is a dict of RegisterSpecs; serialized as plain JSON dicts) ──────────
def baseline_config() -> dict[str, RegisterSpec]:
    """The current live register config (data/fluency/registers.json, or the built-in defaults)."""
    return load_registers()


def spec_to_dict(s: RegisterSpec) -> dict[str, Any]:
    return {
        "id": s.id,
        "description": s.description,
        "max_clauses_per_sentence": int(s.max_clauses_per_sentence),
        "connective_pool": list(s.connective_pool),
        "opener_pool": list(s.opener_pool),
        "pronoun_after_first": bool(s.pronoun_after_first),
        "front_reduced": bool(s.front_reduced),
        "aggregate_copular": bool(s.aggregate_copular),
    }


def dict_to_spec(d: dict[str, Any]) -> RegisterSpec:
    """Rebuild a RegisterSpec and re-apply the closed-vocabulary gate (a candidate cannot smuggle a
    connective/opener outside the approved list — the same honesty contract as the register data)."""
    return RegisterSpec(
        id=str(d["id"]),
        description=str(d.get("description", "")),
        max_clauses_per_sentence=int(d.get("max_clauses_per_sentence", 1)),
        connective_pool=tuple(d.get("connective_pool", ()) or ()),
        opener_pool=tuple(d.get("opener_pool", ()) or ()),
        pronoun_after_first=bool(d.get("pronoun_after_first", True)),
        front_reduced=bool(d.get("front_reduced", False)),
        aggregate_copular=bool(d.get("aggregate_copular", True)),
    ).filtered()


def config_to_dicts(specs: dict[str, RegisterSpec]) -> list[dict[str, Any]]:
    return [spec_to_dict(specs[k]) for k in sorted(specs)]


def _canonical_json(specs: dict[str, RegisterSpec]) -> str:
    return json.dumps(config_to_dicts(specs), sort_keys=True, ensure_ascii=False)


def config_signature(specs: dict[str, RegisterSpec]) -> str:
    """A tamper-evident signature over the canonical config (so an accepted generation is 'signed')."""
    return hashlib.sha1(_canonical_json(specs).encode("utf-8")).hexdigest()[:16]


def _copy_config(specs: dict[str, RegisterSpec]) -> dict[str, RegisterSpec]:
    return {k: dict_to_spec(spec_to_dict(v)) for k, v in specs.items()}


# ── scoring a config over the fluency_v1 benchmark ────────────────────────────────────────────────
@dataclass
class ConfigScore:
    proxy: float                                 # mean scorer(output) over the benchmark
    per_task: dict[str, float]                   # task_id -> scorer(output)
    faithfulness: float                          # MIN faithfulness across outputs (1.0 = nothing invented)
    faithful_ok: bool                            # every output fully grounded
    n_tasks: int
    fabricated: dict[str, list[str]] = field(default_factory=dict)


def _realize_with_config(bones: list, ctx: dict[str, Any], specs: dict[str, RegisterSpec]) -> str:
    """Realize a task with a CANDIDATE config, in memory — the live registers.json is never touched.
    The register is auto-selected from the candidate's own specs, then realized by that exact spec."""
    rid = select_register(ctx, specs)
    spec = specs.get(rid) or specs.get("simple") or next(iter(specs.values()))
    return _realize(bones, register=spec, context=ctx)


def score_config(specs: dict[str, RegisterSpec], scorer: Scorer | None = None,
                 surface_hook: SurfaceHook | None = None) -> ConfigScore:
    """Score a register config on the fluency_v1 benchmark.

    `scorer` defaults to the anchored verifier (verifier.score); a candidate may carry an ALTERNATIVE
    scorer (used to demonstrate that a proxy-redefinition is caught by the anchor gate). `surface_hook`
    defaults to identity; a candidate may carry a hook that models a realizer TEMPLATE VARIANT (used to
    demonstrate that a fabrication-inducing variant is caught by the faithfulness gate)."""
    scorer = scorer or V.score
    per_task: dict[str, float] = {}
    fab: dict[str, list[str]] = {}
    min_faith = 1.0
    for t in _benchmark_tasks():
        bones, ctx = t["bones"], t["context"]
        text = _realize_with_config(bones, ctx, specs)
        if surface_hook is not None:
            text = surface_hook(text)
        per_task[t["id"]] = float(scorer(text))
        f, fabricated = _faithfulness(text, Grounding.from_bones(bones))
        if f < min_faith:
            min_faith = f
        if fabricated:
            fab[t["id"]] = fabricated
    proxy = sum(per_task.values()) / len(per_task) if per_task else 0.0
    return ConfigScore(proxy=proxy, per_task=per_task, faithfulness=min_faith,
                       faithful_ok=min_faith >= 1.0 - 1e-9, n_tasks=len(per_task), fabricated=fab)


# ── candidates (DATA-level config knobs; the two adversarial kinds are guarded, never accepted) ────
@dataclass
class Candidate:
    cand_id: str
    kind: str                                    # "config" | "goodhart_proxy" | "fabrication"
    specs: dict[str, RegisterSpec]               # the register config (config knobs)
    scorer: Scorer | None = None                 # None => canonical anchored verifier (anti-Goodhart axis)
    surface_hook: SurfaceHook | None = None      # None => identity (fabrication axis)
    rationale: str = ""


def _mutate(base: dict[str, RegisterSpec], reg_id: str, **changes: Any) -> dict[str, RegisterSpec]:
    cfg = _copy_config(base)
    if reg_id in cfg:
        d = spec_to_dict(cfg[reg_id])
        d.update(changes)
        cfg[reg_id] = dict_to_spec(d)
    return cfg


def perturb(base: dict[str, RegisterSpec]) -> list[Candidate]:
    """Enumerate BOUNDED neighbor configs by tweaking ONE data knob at a time on the register that a
    given knob touches. Every neighbor keeps all three register ids so auto-selection still resolves.

    The knobs (all DATA, all inside the closed vocabulary): clause-join width, connective variety,
    discourse openers, reduced-clause fronting. Deliberately includes an over-joining neighbor that the
    verifier's structural run-on floor will REJECT — proving the search is bounded by the floor, not by
    a hand rule."""
    out: list[Candidate] = []
    a, w, wc, so = "and", "while", "which is why", "so"

    # --- the DEFAULT register ('simple') dominates the benchmark (most tasks route here): its clause
    #     width and connective variety are the biggest levers. ---
    for width, pool, tag in [
        (2, (a,), "simple_join2_and"),
        (2, (a, w), "simple_join2_and_while"),
        (2, (a, wc), "simple_join2_and_whichiswhy"),
        (3, (a, w), "simple_join3_and_while"),
        (2, (a, w, wc), "simple_join2_varied3"),
        (4, (a, w, wc, so), "simple_overjoin4"),          # expected REJECT: trips the run-on floor
    ]:
        out.append(Candidate(f"cfg_{tag}", "config",
                             _mutate(base, "simple", max_clauses_per_sentence=width,
                                     connective_pool=list(pool)),
                             rationale=f"simple: {width} clauses/sentence, connectives={pool}"))

    # --- the 'neutral' register: broaden connective variety across joined sentences ---
    for pool, tag in [((a, w, wc), "neutral_varied3"), ((a, so, w), "neutral_and_so_while")]:
        out.append(Candidate(f"cfg_{tag}", "config",
                             _mutate(base, "neutral", connective_pool=list(pool)),
                             rationale=f"neutral: connectives={pool}"))

    # --- the 'explanatory' register: opener set + reduced-clause fronting ---
    out.append(Candidate("cfg_expl_openers2", "config",
                         _mutate(base, "explanatory",
                                 opener_pool=list(APPROVED_OPENERS[:2])),
                         rationale="explanatory: two discourse openers"))
    out.append(Candidate("cfg_expl_nofront", "config",
                         _mutate(base, "explanatory", front_reduced=False),
                         rationale="explanatory: do not front the reduced clause"))
    return out


# ── the acceptance gate (every rejection carries an honest reason) ─────────────────────────────────
@dataclass
class Verdict:
    accepted: bool
    reason: str                                  # accepted | fabrication | goodhart_anchor | no_proxy_gain | regression
    proxy_before: float
    proxy_after: float
    anchor_agreement: float
    anchor_passes_floor: bool
    faithfulness: float
    regressed_tasks: list[str] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted, "reason": self.reason,
            "proxy_before": round(self.proxy_before, 6), "proxy_after": round(self.proxy_after, 6),
            "anchor_agreement": round(self.anchor_agreement, 4),
            "anchor_passes_floor": self.anchor_passes_floor,
            "faithfulness": round(self.faithfulness, 6),
            "regressed_tasks": self.regressed_tasks, "detail": self.detail,
        }


def evaluate(candidate: Candidate, baseline: ConfigScore) -> Verdict:
    """Adjudicate one candidate against the current baseline. The FOUR gates, in safety order:

      fabrication (faithfulness < 1.0)  ->  goodhart (anchor < floor)  ->  proxy gain  ->  no regression

    The two safety gates (faithfulness, anchor) are checked FIRST and are HARD: a candidate that
    fabricates or Goodharts is rejected regardless of how good its proxy-number looks."""
    scorer = candidate.scorer or V.score
    cand = score_config(candidate.specs, scorer=scorer, surface_hook=candidate.surface_hook)
    anchor = V.verify_against_anchor(scorer)
    agreement = float(anchor["agreement"])
    passes = bool(anchor["passes_floor"])

    def verdict(accepted: bool, reason: str, detail: str = "") -> Verdict:
        return Verdict(accepted=accepted, reason=reason, proxy_before=baseline.proxy,
                       proxy_after=cand.proxy, anchor_agreement=agreement,
                       anchor_passes_floor=passes, faithfulness=cand.faithfulness,
                       regressed_tasks=regressed, detail=detail)

    regressed: list[str] = []

    # (3) FAITHFUL — no fabrication (a dropped or invented content word)
    if not cand.faithful_ok:
        bad = ", ".join(f"{k}:{v}" for k, v in list(cand.fabricated.items())[:3])
        return verdict(False, "fabrication",
                       f"faithfulness {cand.faithfulness:.4f} < 1.0 — invented content [{bad}]; a "
                       f"more-fluent realization that drops/adds a content word is rejected")

    # (2) ANCHOR — no Goodharting the proxy past the frozen human judgment
    if not passes:
        return verdict(False, "goodhart_anchor",
                       f"frozen-anchor agreement {agreement:.4f} < floor {ANCHOR_FLOOR} — the proxy "
                       f"rose by disagreeing with the human anchor (Goodhart); reject, do not promote")

    # (1) PROXY UP
    if cand.proxy <= baseline.proxy + _REGRESSION_TOL:
        return verdict(False, "no_proxy_gain",
                       f"proxy {cand.proxy:.4f} did not beat baseline {baseline.proxy:.4f}")

    # (4) NO REGRESSION — no single output got worse
    for tid, base_s in baseline.per_task.items():
        cs = cand.per_task.get(tid, base_s)
        if cs < base_s - _REGRESSION_TOL:
            regressed.append(tid)
    if regressed:
        return verdict(False, "regression",
                       f"{len(regressed)} output(s) regressed despite the higher mean: {regressed[:5]}")

    return verdict(True, "accepted",
                   f"proxy {baseline.proxy:.4f} -> {cand.proxy:.4f}, anchor {agreement:.2f} >= "
                   f"{ANCHOR_FLOOR}, faithful 1.0, no regression")


# ── the adversarial candidates the loop must REJECT (the safety proof made concrete) ──────────────
def _naive_connective_scorer(s: str) -> float:
    """A proxy-redefinition that games 'more connectives = more fluent' — exactly the metric a run-on
    template maximizes. It inflates the proxy on run-ons but disagrees with the human anchor."""
    return min(1.0, len(V._connectives_in(s)) / 5.0)


def make_goodhart_candidate(base: dict[str, RegisterSpec]) -> Candidate:
    """A Goodhart attempt: a proxy-REDEFINITION that moves the goalposts. It keeps the (clean) config
    but swaps in a scorer that rewards raw connective count — which INFLATES the proxy on stiff run-ons
    (see _goodhart_inflation: it rates the anchor's WORSE items far above the honest verifier). Because
    it now disagrees with the frozen human anchor, verify_against_anchor(scorer) collapses below the
    floor -> REJECTED. This is the doctrine's 'raises the proxy but drops anchor agreement' case: the
    proxy went up on the very text it games, yet the human tether vetoes it."""
    return Candidate("adv_goodhart", "goodhart_proxy", _copy_config(base),
                     scorer=_naive_connective_scorer,
                     rationale="redefine the proxy to reward connective count (inflates stiff run-ons)")


def _goodhart_inflation(scorer: Scorer) -> dict[str, Any]:
    """Quantify how a candidate scorer INFLATES the proxy on text the frozen anchor marks as WORSE.
    A positive inflation with a collapsed anchor is the Goodhart signature (proxy up, humans disagree)."""
    worse = [w for (_b, w) in V.ANCHOR_PAIRS]
    honest = sum(V.score(w) for w in worse) / len(worse)
    gamed = sum(scorer(w) for w in worse) / len(worse)
    return {"honest_rates_stiff": round(honest, 4), "gamed_rates_stiff": round(gamed, 4),
            "proxy_inflation_on_stiff": round(gamed - honest, 4)}


def make_fabrication_candidate(base: dict[str, RegisterSpec]) -> Candidate:
    """A fabrication attempt: a realizer TEMPLATE VARIANT that smuggles an ungrounded editorial word
    onto every surface. The faithfulness gate catches it (the word traces to nothing grounded)."""
    def _inject(text: str) -> str:
        if not text:
            return text
        return (text[:-1] if text.endswith((".", "!", "?")) else text) + ", which is amazing."
    return Candidate("adv_fabrication", "fabrication", _copy_config(base), surface_hook=_inject,
                     rationale="template variant appends an ungrounded editorial word ('amazing')")


# ── signed, rollbackable persistence (never overwrites the live registers.json) ───────────────────
def _evolve_dir(out_dir: Path | None) -> Path:
    d = Path(out_dir) if out_dir is not None else _DEFAULT_EVOLVE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _generations_path(out_dir: Path | None) -> Path:
    return _evolve_dir(out_dir) / "generations.jsonl"


def _active_path(out_dir: Path | None) -> Path:
    return _evolve_dir(out_dir) / "active.json"


def sign_generation(specs: dict[str, RegisterSpec], *, gen_index: int, parent: str | None,
                    proxy: float, anchor: float, faithfulness: float, reason: str,
                    out_dir: Path | None = None) -> dict[str, Any]:
    """Append one SIGNED generation and move the active pointer to it. Append-only (history is never
    rewritten), so any prior generation stays rollbackable."""
    sig = config_signature(specs)
    gen_id = f"g{gen_index:03d}-{sig}"
    record = {
        "gen_id": gen_id, "gen_index": gen_index, "parent": parent, "signature": sig,
        "ts": round(time.time(), 3), "proxy": round(proxy, 6), "anchor": round(anchor, 4),
        "faithfulness": round(faithfulness, 6), "reason": reason,
        "config": config_to_dicts(specs),
        "note": "signed register/realizer config generation; live registers.json is NOT overwritten",
    }
    with _generations_path(out_dir).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    _active_path(out_dir).write_text(
        json.dumps({"active": gen_id, "signature": sig, "ts": record["ts"]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def list_generations(out_dir: Path | None = None) -> list[dict[str, Any]]:
    p = _generations_path(out_dir)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    return out


def active_generation(out_dir: Path | None = None) -> dict[str, Any] | None:
    p = _active_path(out_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def config_of_generation(gen_id: str, out_dir: Path | None = None) -> dict[str, RegisterSpec] | None:
    for rec in list_generations(out_dir):
        if rec["gen_id"] == gen_id:
            return {d["id"]: dict_to_spec(d) for d in rec["config"]}
    return None


def rollback(gen_id: str, out_dir: Path | None = None) -> dict[str, Any]:
    """Roll the active pointer back to a prior signed generation. Verifies the target's signature
    still matches its stored config (tamper-evidence) before switching."""
    rec = next((r for r in list_generations(out_dir) if r["gen_id"] == gen_id), None)
    if rec is None:
        raise KeyError(f"no such generation: {gen_id}")
    specs = {d["id"]: dict_to_spec(d) for d in rec["config"]}
    if config_signature(specs) != rec["signature"]:
        raise ValueError(f"generation {gen_id} failed signature check (tampered)")
    payload = {"active": gen_id, "signature": rec["signature"], "ts": round(time.time(), 3),
               "rolled_back": True}
    _active_path(out_dir).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    return payload


# ── the closed loop ───────────────────────────────────────────────────────────────────────────────
def run(rounds: int = 6, persist: bool = True, out_dir: Path | None = None,
        include_safety_probes: bool = True) -> dict[str, Any]:
    """Run the bounded, gated hill-climb. Each round proposes config neighbors of the current best,
    accepts the best strictly-improving one that clears every gate, and persists it as a signed
    generation. Reports the honest trajectory and the safety rejections.

    HONEST: config search never touches the SCORER, so the frozen-anchor agreement is invariant (1.0)
    across accepted rounds — reported so it is visibly >= floor throughout. The anchor gate's TEETH are
    proven separately by the safety probes (a Goodhart candidate and a fabrication candidate, both
    rejected)."""
    base = baseline_config()
    best = base
    best_score = score_config(best)
    anchor0 = V.verify_against_anchor()
    parent_sig: str | None = None
    gen_index = 0

    rejections: Counter = Counter()
    accepted_history: list[dict[str, Any]] = []
    anchor_trajectory: list[float] = [float(anchor0["agreement"])]
    faithful_trajectory: list[float] = [best_score.faithfulness]

    generations: list[dict[str, Any]] = []
    if persist:
        rec = sign_generation(best, gen_index=gen_index, parent=None, proxy=best_score.proxy,
                              anchor=anchor_trajectory[0], faithfulness=best_score.faithfulness,
                              reason="baseline", out_dir=out_dir)
        generations.append(rec)
        parent_sig = rec["gen_id"]

    proxy_start = best_score.proxy
    rounds_run = 0
    for r in range(1, rounds + 1):
        neighbors = perturb(best)
        winner: Candidate | None = None
        winner_score: ConfigScore | None = None
        winner_verdict: Verdict | None = None
        for cand in neighbors:
            v = evaluate(cand, best_score)
            if not v.accepted:
                rejections[v.reason] += 1
                continue
            cs = score_config(cand.specs)                        # canonical re-score of the accepted config
            if winner_score is None or cs.proxy > winner_score.proxy:
                winner, winner_score, winner_verdict = cand, cs, v
        if winner is None:
            accepted_history.append({"round": r, "accepted": None, "reason": "plateau",
                                     "proxy": best_score.proxy})
            break
        best, best_score = winner.specs, winner_score
        gen_index += 1
        rounds_run = r
        anchor_now = float(V.verify_against_anchor()["agreement"])
        anchor_trajectory.append(anchor_now)
        faithful_trajectory.append(best_score.faithfulness)
        rec = None
        if persist:
            rec = sign_generation(best, gen_index=gen_index, parent=parent_sig,
                                  proxy=best_score.proxy, anchor=anchor_now,
                                  faithfulness=best_score.faithfulness,
                                  reason=f"accepted:{winner.cand_id}", out_dir=out_dir)
            generations.append(rec)
            parent_sig = rec["gen_id"]
        accepted_history.append({
            "round": r, "accepted": winner.cand_id, "rationale": winner.rationale,
            "proxy": round(best_score.proxy, 6), "anchor": round(anchor_now, 4),
            "faithfulness": round(best_score.faithfulness, 6),
            "gen_id": rec["gen_id"] if rec else None,
        })

    # ── safety probes: the loop MUST reject a Goodhart candidate and a fabrication candidate ──
    safety: dict[str, Any] = {}
    if include_safety_probes:
        gh_cand = make_goodhart_candidate(best)
        gh = evaluate(gh_cand, best_score)
        fab = evaluate(make_fabrication_candidate(best), best_score)
        rejections[gh.reason] += 1
        rejections[fab.reason] += 1
        gh_dict = gh.as_dict()
        gh_dict["inflation"] = _goodhart_inflation(gh_cand.scorer or V.score)
        safety = {"goodhart": gh_dict, "fabrication": fab.as_dict(),
                  "both_rejected": (not gh.accepted) and (not fab.accepted)}

    anchor_min = min(anchor_trajectory)
    faithful_min = min(faithful_trajectory)
    report = {
        "domain": "fluency_naturalness",
        "status": V.EVOLVED_STATUS,                              # proxy-evolvable-anchored
        "rounds_requested": rounds,
        "rounds_accepted": rounds_run,
        "proxy_before": round(proxy_start, 6),
        "proxy_after": round(best_score.proxy, 6),
        "proxy_gain": round(best_score.proxy - proxy_start, 6),
        "anchor_floor": ANCHOR_FLOOR,
        "anchor_trajectory": [round(x, 4) for x in anchor_trajectory],
        "anchor_min": round(anchor_min, 4),
        "anchor_held_above_floor": anchor_min >= ANCHOR_FLOOR,
        "faithfulness_trajectory": [round(x, 6) for x in faithful_trajectory],
        "faithfulness_held_1_0": faithful_min >= 1.0 - 1e-9,
        "history": accepted_history,
        "rejections_by_reason": dict(rejections),
        "safety_rejections": int(rejections.get("goodhart_anchor", 0))
                              + int(rejections.get("fabrication", 0)),
        "safety_probes": safety,
        "active_generation": active_generation(out_dir) if persist else None,
        "n_generations": len(generations),
        "ceiling_note": ("naturalness has no ground-truth oracle: this is a PROXY optimized under a "
                         "FROZEN human anchor over a small config knob space, so the gain is bounded "
                         "and plateaus quickly by design — the deliverable is the SAFE closed loop "
                         "(anchor never crossed, faithfulness held, Goodhart/fabrication rejected), "
                         "not a large number."),
        "is_autonomous_safe": V.IS_AUTONOMOUS_SAFE,              # False — anchored, not crisp-oracle
        "needs_human_anchor": V.NEEDS_HUMAN_ANCHOR,              # True
    }
    return report


# ── neuro ledger: register the loop's footprint (ZERO learned params — a config selector) ─────────
def neuro_ledger_organ():
    """Declare the evolve loop to the neuro ledger as a 0-param CONTROL organ (mirrors the pattern of
    self_evolution.ledger_contribution — it declares an Organ WITHOUT editing packages/neuro_ledger).

    The loop holds NO learned weights: it enumerates curated config knobs, scores them with the
    (separately-registered) fluency_verifier, and selects a winner. The winner is register CONFIG DATA,
    already budget-accounted by the 'fluency_register_lever' organ (data/fluency/registers.json). So the
    loop's own learned-parameter footprint is exactly 0, and it is never a fact source."""
    from packages.neuro_ledger.ledger import Organ
    return Organ(
        id="fluency_evolve_loop",
        path="packages/fluency/evolve.py",
        role="closed self-evolution loop: enumerates register/realizer CONFIG knobs, scores fluency_v1 "
             "with the anchored naturalness proxy verifier, and PROMOTES a config only on proxy-up + "
             "frozen-anchor>=floor + faithfulness==1.0 + no-regression; a SELECTOR over curated config "
             "data, ZERO learned weights (the accepted config is register DATA already budgeted by "
             "fluency_register_lever)",
        gate="fluency self-evolution acceptance gate (anchored proxy x structural floor x frozen human "
             "anchor x faithfulness x no-regression; signed rollbackable generations)",
        artifacts=[],                       # no weight artifacts on disk — signed configs are JSON data
        fact_source=False,
        enforced=False,
        status="active",
        fallback_params=0,
    )


def budget_check() -> dict[str, Any]:
    """Measure the loop's real parameter footprint. INVARIANT: 0 learned params, not a fact source."""
    from packages.neuro_ledger.ledger import measure_params
    o = neuro_ledger_organ()
    m = measure_params(o)
    params = int(m.get("params", 0))
    return {"id": o.id, "params": params, "fact_source": o.fact_source,
            "ok": params == 0 and o.fact_source is False}


def main() -> None:
    import io
    import sys
    rep = run(persist=True)
    buf = io.StringIO()
    buf.write("fluency SELF-EVOLUTION loop — SAFE, anchored, anti-Goodhart (HONEST PROXY)\n\n")
    buf.write(f"  proxy {rep['proxy_before']} -> {rep['proxy_after']} "
              f"(gain {rep['proxy_gain']:+.4f}) over {rep['rounds_accepted']} accepted round(s)\n")
    buf.write(f"  frozen-anchor agreement stayed >= {rep['anchor_floor']} throughout: "
              f"min {rep['anchor_min']} (held={rep['anchor_held_above_floor']}); "
              f"trajectory {rep['anchor_trajectory']}\n")
    buf.write(f"  faithfulness held 1.0: {rep['faithfulness_held_1_0']}\n")
    buf.write(f"  rejections by reason: {rep['rejections_by_reason']}\n")
    sp = rep.get("safety_probes", {})
    if sp:
        gi = sp["goodhart"]["inflation"]
        buf.write(f"  safety proof (rejections): Goodhart candidate REJECTED ({sp['goodhart']['reason']}) "
                  f"— its gamed proxy inflates stiff run-ons {gi['honest_rates_stiff']}->"
                  f"{gi['gamed_rates_stiff']} (proxy UP on gamed text) yet anchor agreement collapses to "
                  f"{sp['goodhart']['anchor_agreement']} < {rep['anchor_floor']} (anchor DOWN); "
                  f"fabrication candidate REJECTED ({sp['fabrication']['reason']}, faithfulness "
                  f"{sp['fabrication']['faithfulness']} < 1.0)\n")
    buf.write(f"  ceiling: {rep['ceiling_note']}\n")
    buf.write(f"  neuro budget: {budget_check()}\n")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.stdout.write(buf.getvalue())


if __name__ == "__main__":
    main()
