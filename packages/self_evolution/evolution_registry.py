# -*- coding: utf-8 -*-
"""The evolution registry — every known self-improvement loop, as DATA (not code branches).

DOCTRINE (BINDING): self-evolution compounds ONLY where three things coexist:
  (1) a MEASUREMENT gate   — a scorecard/benchmark that says how good the domain is now;
  (2) a candidate GENERATOR — something that proposes an improvement;
  (3) a VERIFIER            — a crisp, automatic check that a candidate is genuinely better.
No verifier -> no autonomous promotion, only a flagged proposal for the operator.

Each loop is a row of DATA describing HOW the domain improves and, critically, WHETHER its verifier is
crisp enough to run autonomously. `autonomous_safe` is DERIVED, never asserted by hand:
    autonomous_safe = gate_exists AND generator_exists AND verifier_exists
                      AND generator_kind != "architecture"      # arch rewrites are operator-gated
                      AND not targets_immutable                  # constitution/tests are immutable

The gate/generator/verifier existence flags are PROBED against the real repo (a module imports, a file
is on disk, an attribute is present) — so this registry describes reality, not wishes. A verifier that
does not exist on disk makes the domain NON-autonomous automatically; there is no hand override.

`base_impact` is a documented per-domain criticality prior (how much the owner-facing capability
matters), kept as DATA here; the live IMPACT is base_impact x measured headroom, computed by the
orchestrator.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


# ── probe primitives: existence is DETECTED, not declared ─────────────────────────────────────────
def _module_importable(dotted: str) -> bool:
    try:
        return importlib.util.find_spec(dotted) is not None
    except Exception:
        return False


def _file_exists(rel: str) -> bool:
    return (repo_root() / rel).exists()


def _attr_present(dotted_attr: str) -> bool:
    """`pkg.mod:attr` — the module imports and defines `attr` (does NOT execute heavy side effects
    beyond import; used only for cheap modules)."""
    mod, _, attr = dotted_attr.partition(":")
    if not _module_importable(mod):
        return False
    try:
        import importlib
        m = importlib.import_module(mod)
        return hasattr(m, attr)
    except Exception:
        return False


def probe(spec: dict[str, Any]) -> bool:
    """A probe spec is any-of over kinds: {"module": [...]}, {"file": [...]}, {"attr": [...]}.
    Returns True iff EVERY listed requirement in the spec is satisfied (all-of across kinds, any-of
    within a kind's list). An empty/None spec means "does not exist" -> False."""
    if not spec:
        return False
    ok = True
    for kind, values in spec.items():
        vals = values if isinstance(values, (list, tuple)) else [values]
        if kind == "module":
            hit = any(_module_importable(v) for v in vals)
        elif kind == "file":
            hit = any(_file_exists(v) for v in vals)
        elif kind == "attr":
            hit = any(_attr_present(v) for v in vals)
        elif kind == "never":
            hit = False  # explicit "this piece does not exist" (e.g., a verifier not yet built)
        else:
            hit = False
        ok = ok and hit
    return ok


@dataclass
class EvolutionLoop:
    domain: str
    loop_id: str
    how_invoked: str                     # the concrete way to run this loop
    generator_kind: str                  # code | data | control | architecture
    base_impact: float                   # owner-facing criticality prior in [0, 1]
    verifier_desc: str                   # what the verifier checks (or why it is absent)
    gate_probe: dict[str, Any]
    generator_probe: dict[str, Any]
    verifier_probe: dict[str, Any]       # {"never": True} when no crisp verifier exists yet
    score_reader: str                    # which sensus reader derives this domain's score
    invocation: dict[str, Any] = field(default_factory=dict)
    targets_immutable: bool = False      # a loop that would need to touch constitution/tests
    note: str = ""


# ── the registry (seeded from the live ATANOR self-improvement machinery, 2026-07-22) ─────────────
def _registry() -> list[EvolutionLoop]:
    return [
        # code authorship: schema induction + a compounding solution library, verified by a subprocess
        # oracle re-running HELD-OUT hidden tests. All three pieces are real and on disk -> autonomous.
        EvolutionLoop(
            domain="code",
            loop_id="schema_induction_library_compounding",
            how_invoked="python -m packages.code_reason.benchmarks.mastery_v1  "
                        "(author -> verify against hidden tests -> keep verified shapes in the library)",
            generator_kind="code",
            base_impact=0.70,
            verifier_desc="subprocess oracle re-runs the HELD-OUT hidden asserts (crisp pass/fail; a "
                          "body that passes the visible gate but fails hidden is scored fail)",
            gate_probe={"module": "packages.code_reason.benchmarks.mastery_v1"},
            generator_probe={"file": ["packages/code_reason/code_author.py",
                                      "packages/code_reason/schema_induction.py"]},
            verifier_probe={"attr": "packages.code_reason.authorship_harness:_run_candidate"},
            score_reader="code",
            invocation={"module": "packages.code_reason.benchmarks.mastery_v1",
                        "entry": "run_benchmark",
                        "promotes": "verified solution shapes into the authorship library"},
        ),
        # world knowledge: wild_web harvest -> graph enrichment, verified by CONSENSUS (k independent
        # sources) + quarantine. The verifier is the consensus-evidence machine; promotion is gated.
        EvolutionLoop(
            domain="knowledge",
            loop_id="wild_web_graph_enrichment_consensus",
            how_invoked="python -m packages.wild_web <topic>  "
                        "(roam -> segment -> quarantine -> promote a fact only on k-source consensus)",
            generator_kind="data",
            base_impact=0.90,
            verifier_desc="consensus-evidence machine: a candidate fact promotes only on agreement "
                          "across k independent sources; everything else stays quarantined (crisp)",
            gate_probe={"file": "data/wild_web/sessions.jsonl", "module": "packages.wild_web"},
            generator_probe={"module": "packages.wild_web"},
            verifier_probe={"file": "data/wild_web/quarantine.jsonl",
                            "module": "packages.wild_web"},
            score_reader="knowledge",
            invocation={"module": "packages.wild_web", "entry": "__main__",
                        "promotes": "consensus-verified register/knowledge into the graph"},
        ),
        # relational routing: a 31-param logistic scorer retrained on generated paraphrases, verified
        # on a deterministic HELD-OUT split. Tiny, fully verifiable -> autonomous.
        EvolutionLoop(
            domain="relational_routing",
            loop_id="relational_router_retrain_heldout",
            how_invoked="packages.base_brain.relational_router.train_and_save()  "
                        "(fit logistic on paraphrases -> score on the held-out split)",
            generator_kind="data",
            base_impact=0.45,
            verifier_desc="held-out accuracy on a deterministic 80/20 content-hash split (crisp)",
            gate_probe={"file": "data/relational_router/heldout.jsonl"},
            generator_probe={"attr": "packages.base_brain.relational_router:train_and_save"},
            verifier_probe={"attr": "packages.base_brain.relational_router:RelationalRouter"},
            score_reader="relational_routing",
            invocation={"module": "packages.base_brain.relational_router", "entry": "train_and_save",
                        "promotes": "updated router weights (data/relational_router/weights.json)"},
        ),
        # processing efficiency: the Metacognitive Efficiency Controller watches its own latency
        # baselines, localizes the worst bottleneck, and re-steers via a bounded policy. The verifier
        # is the objective re-measurement of latency/success -> autonomous (bounded control).
        EvolutionLoop(
            domain="efficiency",
            loop_id="mec_watch_decide_resteer",
            how_invoked="packages.metacog.controller tick over live spans  "
                        "(detect anomaly vs learned baseline -> bounded re-steer -> re-measure)",
            generator_kind="control",
            base_impact=0.55,
            verifier_desc="objective re-measurement: a re-steer is kept only if the span's latency "
                          "returns toward its learned baseline without lowering its ok-rate (crisp)",
            gate_probe={"file": "data/metacog/baselines.json"},
            generator_probe={"file": ["packages/metacog/controller.py", "packages/metacog/policies.py"]},
            verifier_probe={"file": "data/metacog/baselines.json",
                            "module": "packages.metacog.probes"},
            score_reader="efficiency",
            invocation={"module": "packages.metacog.controller", "entry": "tick",
                        "promotes": "a bounded re-steer decision (data/metacog/decisions.jsonl)"},
        ),
        # register fluency / naturalness: harvest registers + delexicalize + copy. The GROUNDING axis
        # (faithfulness) is measured, but the axis the owner cares about — NATURALNESS — has NO crisp
        # automatic verifier. Missing verifier -> NON-autonomous; the operator must build the verifier.
        EvolutionLoop(
            domain="fluency",
            loop_id="register_harvest_delex",
            how_invoked="wild_web register-harvest + delexicalize/copy into surface templates "
                        "(proposes more natural register-appropriate phrasings)",
            generator_kind="data",
            base_impact=0.80,
            verifier_desc="NO CRISP VERIFIER: faithfulness/grounding is measured (track_f), but "
                          "NATURALNESS has no automatic held-out judge — a human currently rates it. "
                          "Until a naturalness verifier exists, this loop cannot promote autonomously.",
            gate_probe={"file": "data/track_f/s2_faithfulness.json"},
            generator_probe={"file": "data/wild_web/register_staging.jsonl",
                             "module": "packages.wild_web"},
            verifier_probe={"never": True},   # a naturalness verifier does not exist on disk
            score_reader="fluency",
            invocation={},   # not autonomous: emitted as an operator proposal
            note="highest-leverage UNLOCK: build a naturalness verifier to make this loop autonomous",
        ),
        # register NATURALNESS self-evolution (the UNLOCK above, now BUILT): the anchored naturalness
        # PROXY verifier (packages/fluency/verifier.py) now exists, so the fluency evolve loop
        # (packages/fluency/evolve.py) can run + self-gate WITHOUT the operator at runtime — but the
        # gate is a PROXY tethered to a FROZEN human anchor, NOT a crisp oracle like code. Verifier-
        # backed and runtime-autonomous, yet permanently anchor-bounded (is_autonomous_safe=False on the
        # verifier's own descriptor: naturalness has no ground-truth oracle). Kept as its own domain so
        # the register-HARVEST 'fluency' loop above stays an honest operator proposal.
        EvolutionLoop(
            domain="fluency_naturalness",
            loop_id="fluency_proxy_anchored_evolution",
            how_invoked="python -m packages.fluency.evolve  (enumerate register/realizer CONFIG knobs -> "
                        "score fluency_v1 with the anchored naturalness PROXY -> PROMOTE a config ONLY on "
                        "proxy-up AND frozen-anchor>=floor AND faithfulness==1.0 AND no-regression; "
                        "signed, rollbackable generations)",
            generator_kind="data",
            base_impact=0.80,
            verifier_desc="anchored naturalness PROXY (packages.fluency.verifier:score) = a learned "
                          "discriminator x a structural rule floor x a FROZEN 20-pair human anchor "
                          "(verify_against_anchor). HONEST: naturalness has no ground-truth oracle, so "
                          "this is PROXY-optimized + HUMAN-ANCHORED, not crisp-oracle autonomy — the "
                          "loop may adjust config ONLY while frozen-anchor agreement stays >= floor (a "
                          "proxy gain that drops anchor is Goodharting -> rejected) and faithfulness "
                          "stays 1.0 (a fabrication is rejected).",
            gate_probe={"module": "packages.fluency.fluency_v1"},
            generator_probe={"file": "packages/fluency/evolve.py", "module": "packages.fluency"},
            verifier_probe={"attr": ["packages.fluency.verifier:verify_against_anchor",
                                     "packages.fluency.verifier:score"]},
            score_reader="fluency_naturalness",   # no single on-disk number: the proxy is computed live
            invocation={"module": "packages.fluency.evolve", "entry": "run",
                        "promotes": "accepted register/realizer CONFIG generations under "
                                    "data/fluency/evolution/ (signed + rollbackable), gated by the "
                                    "frozen human anchor + faithfulness; the live registers.json is "
                                    "never overwritten",
                        "status": "proxy-evolvable-anchored",
                        "autonomy_kind": "runtime-autonomous but PROXY + HUMAN-ANCHORED (not crisp-oracle)",
                        "verifier_flags": {"is_autonomous_safe": False, "needs_human_anchor": True,
                                           "anchor_agreement_floor": 0.90}},
            note="proxy-evolvable-anchored: the frozen 20-pair human anchor is the tether. A Goodharting "
                 "proxy gain (anchor below floor) or any fabrication (faithfulness < 1.0) is rejected. "
                 "NOT crisp-oracle autonomy like code — naturalness has no ground-truth oracle; the "
                 "bounded knob space plateaus quickly by design.",
        ),
        # repo engineering (SWE-bench): domain-blind edit-schema MUTATION of a localized function,
        # each candidate VERIFIED by the repo's own FAIL_TO_PASS + PASS_TO_PASS regression gate (the
        # crisp oracle, isomorphic to physics_truth). Generator = edit_schemas + the fused
        # patch_pipeline; verifier = regression_gate. All three real on disk -> verifier-backed.
        EvolutionLoop(
            domain="repo_engineering",
            loop_id="edit_schema_regression_verified",
            how_invoked="python -m packages.swe_eval.run_verified --patch  "
                        "(localize via deliberation -> propose edit schemas -> VERIFY each with the "
                        "regression gate -> ship only a green diff; fail-0)",
            generator_kind="code",
            base_impact=0.75,
            verifier_desc="regression gate (packages.swe_eval.regression_gate): a candidate diff is "
                          "accepted ONLY if it applies at base_commit and every FAIL_TO_PASS turns "
                          "green while every PASS_TO_PASS holds — the repo's own tests are the oracle "
                          "(crisp pass/fail; nothing plausible-but-unverified is ever shipped).",
            gate_probe={"file": "data/swe_eval/patch_report.json"},
            generator_probe={"file": ["packages/swe_eval/edit_schemas.py",
                                      "packages/swe_eval/patch_pipeline.py"]},
            verifier_probe={"attr": "packages.swe_eval.regression_gate:verify_docker"},
            score_reader="repo_engineering",
            invocation={"module": "packages.swe_eval.run_verified", "entry": "run_patch",
                        "promotes": "verified edit-schema shapes into the repo-engineering library"},
            note="reachable subset: single-file, single-function structural fixes; multi-file and "
                 "multi-token edits remain out of the edit-schema family (next coordinate).",
        ),
        # SWE-engineering SELF-EVOLUTION (the north-star loop, sibling to repo_engineering the way
        # fluency_naturalness is sibling to fluency): the crisp regression oracle now gates a bounded
        # hill-climb over the repo-engineering CONFIG (localization test-fusion + which edit-schema
        # families the proposer may use). Verifier-backed and runtime-autonomous — "SWE resolved" is a
        # real pass/fail, so unlike naturalness there is NO human anchor. HONEST: the loop climbs a
        # NATIVE-FIXTURE PROXY (no Docker); real resolved on the full benchmark is ~0 today. The 90-avg
        # is recorded in `invocation.north_star` as the FAR target the loop climbs toward, with the
        # honest current (~0) beside it — never claimed as reached.
        EvolutionLoop(
            domain="swe_engineering",
            loop_id="swe_proxy_native_evolution",
            how_invoked="python -m packages.swe_eval.evolve  (enumerate repo-engineering CONFIG knobs "
                        "-> score native fixtures with the crisp regression oracle -> PROMOTE a config "
                        "ONLY on oracle-certified proxy-up AND no-unverified-diff AND no-regression; "
                        "signed, rollbackable generations)",
            generator_kind="code",
            base_impact=0.90,     # the 90-avg north star: highest owner-facing criticality
            verifier_desc="crisp regression oracle (packages.swe_eval.regression_gate: verify_native / "
                          "verify_docker) — the repo's OWN FAIL_TO_PASS + PASS_TO_PASS tests are the "
                          "ground truth (accept only green, no human anchor). The self-evolution loop "
                          "climbs a NATIVE-FIXTURE PROXY of this oracle (localization top-1 + "
                          "oracle-certified verified-diff count); a config is promoted only if it raises "
                          "the proxy with NO regression and ZERO unverified diff (a rubber-stamped fix "
                          "the real tests do not certify green is rejected).",
            gate_probe={"file": "data/swe_eval/goal_scoreboard.json"},
            generator_probe={"file": ["packages/swe_eval/evolve.py"], "module": "packages.swe_eval"},
            verifier_probe={"attr": ["packages.swe_eval.regression_gate:verify_native",
                                     "packages.swe_eval.regression_gate:verify_docker"]},
            score_reader="swe_engineering",   # goal_scoreboard current_avg / target (honest, ~0)
            invocation={
                "module": "packages.swe_eval.evolve", "entry": "run",
                "promotes": "accepted repo-engineering CONFIG generations under data/swe_eval/"
                            "evolution/ (signed + rollbackable), gated by the crisp native regression "
                            "oracle (fail-0, no unverified diff); no live surface is overwritten",
                "status": "crisp-oracle-evolvable",
                "autonomy_kind": "runtime-autonomous crisp-oracle on a NATIVE-fixture proxy (real "
                                 "resolved on the full benchmark needs prebuilt Docker images + wider "
                                 "edit-schema reach)",
                "north_star": {
                    "benchmark": "swe_avg", "target": 90.0, "current": 0.05, "claimed_reached": False,
                    "scoreboard": "data/swe_eval/goal_scoreboard.json",
                    "components": {
                        "verified": {"status": "measurable-but-low", "current": 0.2,
                                     "reachable_resolved": 1, "n_full": 500},
                        "pro": {"status": "loads-not-run", "current": 0.0},
                        "multilingual": {"status": "out-of-scope-java", "current": 0.0},
                        "multimodal": {"status": "out-of-scope-vision", "current": 0.0},
                    },
                    "recorded_as": "the target the loop climbs toward, with the honest current value "
                                   "beside it — never claimed as reached",
                },
            },
            note="north star swe_avg=90 is FAR; current ~0 (one reachable Docker-verified instance; Pro "
                 "not run; Multilingual is Java / out of scope; Multimodal needs vision). The loop is a "
                 "SAFE crisp-oracle climb; the deliverable is the working loop + the honest scoreboard, "
                 "not a number. The two levers that move REAL resolved: instance-image availability and "
                 "wider (multi-hunk) edit-schema reach.",
        ),
        # consciousness indicators: the audit measures indicator presence and RE-audits (a verifier),
        # and the build_queue names WHAT to build — but building it (recurrent perceptual refinement,
        # a workspace-directed controller) is ARCHITECTURE-level. Architecture rewrites are
        # operator-gated, never autonomous. All three pieces exist, yet generator_kind=architecture.
        EvolutionLoop(
            domain="consciousness",
            loop_id="consciousness_audit_build_queue",
            how_invoked="build a queued indicator module (e.g. RPT-1 recurrent perceptual refinement) "
                        "then re-run packages.consciousness_audit to verify it is grounded in real code",
            generator_kind="architecture",
            base_impact=0.65,
            verifier_desc="re-audit: an indicator counts as 'present' only when grounded in real "
                          "module paths + a measured behavior (crisp), but the GENERATOR is new "
                          "architecture — operator-gated by doctrine.",
            gate_probe={"file": "data/consciousness_audit/scorecard.json"},
            generator_probe={"file": "data/consciousness_audit/scorecard.json"},  # build_queue lives here
            verifier_probe={"file": "data/consciousness_audit/scorecard.json",
                            "module": "packages.consciousness_audit"},
            score_reader="consciousness",
            invocation={},   # not autonomous: architecture-level, emitted as an operator proposal
            note="operator-gated: building a new indicator is an architecture change, never autonomous",
        ),
    ]


def load_registry() -> list[EvolutionLoop]:
    return _registry()


def evolvability_probes(loop: EvolutionLoop) -> dict[str, bool]:
    """The three existence flags, PROBED against the real repo, plus derived evolvable/autonomous."""
    gate = probe(loop.gate_probe)
    gen = probe(loop.generator_probe)
    ver = probe(loop.verifier_probe)
    evolvable = gate and gen and ver
    autonomous_safe = (
        evolvable
        and loop.generator_kind != "architecture"
        and not loop.targets_immutable
    )
    return {
        "gate_exists": gate,
        "generator_exists": gen,
        "verifier_exists": ver,
        "evolvable": evolvable,
        "autonomous_safe": autonomous_safe,
    }
