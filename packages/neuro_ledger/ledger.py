# -*- coding: utf-8 -*-
"""The learned-component registry + parameter measurement.

Every LEARNED organ in ATANOR is registered here with: its code path, its role, the SYMBOLIC gate it
sits inside, its persisted weight artifacts, and the invariant ``fact_source=False`` (a learned organ
proposes/scores/routes — it is never a fact provider; facts come from the graph + search API).

Two tiers:
  * enforced=True   the active No-LLM answer-path organs the hard budget governs (tiny logistic
                    routers, PPMI/SVD embeddings, RotatE phases). These must each stay under
                    SINGLE_ORGAN_MAX and sum under TOTAL_MAX.
  * enforced=False  heavy EXPERIMENTAL torch tracks (ACE/ACE2 readers, the neural realizer, the MCQ
                    judge, the math parser). They are registered so the unregistered-artifact
                    detector accounts for them, but they are NOT the production No-LLM brain — the
                    audit surfaces them in an ADVISORY (structure-over-memorization doctrine target:
                    retire), separate from the enforced green gate.

Parameter counts are MEASURED from the real artifact where cheaply loadable (``.npy`` header via
mmap, ``.npz`` array sizes, float leaves of a ``weights.json``) and otherwise HONESTLY ESTIMATED from
the file size (a torch ``state_dict`` ~= bytes/4 float32) — every measurement carries a ``measured``
flag so the estimate is never mistaken for a true count.
"""
from __future__ import annotations

import glob
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# ── budget (parameter counts, not bytes) ─────────────────────────────────────────────────────────
SINGLE_ORGAN_MAX = 25_000_000
TOTAL_MAX = 100_000_000

# soft cap for the advisory tier (experimental organs above this are flagged for retirement)
EXPERIMENTAL_SOFT_MAX = SINGLE_ORGAN_MAX


def repo_root() -> Path:
    """The ATANOR repo root (this file lives at <root>/packages/neuro_ledger/ledger.py)."""
    return Path(__file__).resolve().parents[2]


@dataclass
class Artifact:
    glob: str                       # path glob, relative to repo root
    method: str                     # npy | npz | json_floats | pt_size_est | pkl_size_est
    role: str = "weights"           # component role (checkpoints of one role are counted once)


@dataclass
class Organ:
    id: str
    path: str                       # code file that defines/trains/loads the organ (relative)
    role: str                       # one line: what it decides / scores / encodes
    gate: str                       # the symbolic gate/module it sits inside
    artifacts: list[Artifact]
    fact_source: bool = False       # INVARIANT: must be False (a learned organ is not a fact source)
    enforced: bool = True           # True -> hard budget; False -> experimental advisory tier
    status: str = "active"          # active | shadow | experimental | retire-target
    fallback_params: int = 0        # honest last-known count when the artifact is absent on disk


# ── the registry (seeded by an exhaustive sweep of packages/ + data/, 2026-07-22) ────────────────
def _registry() -> list[Organ]:
    organs = [
        # ---- enforced: the active No-LLM answer-path organs the budget governs ----
        Organ(
            id="relational_router",
            path="packages/base_brain/relational_router.py",
            role="logistic scorer: routes an 'X of Y' query to RELATIONAL (attribute lookup) vs DEFINE",
            gate="base_brain relational lane (relational_lookup.parse_relational_shape)",
            artifacts=[Artifact("data/relational_router/weights.json", "json_floats")],
            fallback_params=31,
        ),
        Organ(
            id="intent_router",
            path="packages/base_brain/intent_router.py",
            role="multinomial-logistic router: social|personal_unknowable|self_situation|define|relational",
            gate="realcity adapter _route() + base_brain define lane",
            artifacts=[Artifact("data/intent_router/weights.json", "json_floats")],
            fallback_params=145,
        ),
        Organ(
            id="learned_router",
            path="packages/learned_router/router.py",
            role="hashed-ngram softmax intent/lane classifier (shadow; decides where no regex lane fires)",
            gate="routing layer (shadow-logged to the flywheel)",
            artifacts=[Artifact("data/learned_router/*.npz", "npz")],
            status="shadow",
            fallback_params=557_073,
        ),
        Organ(
            id="learned_discriminator",
            path="packages/reasoning_vm/learned_discriminator.py",
            role="PPMI+SVD word vectors + sklearn head: scores which MCQ option the passage SUPPORTS",
            gate="reasoning_vm MCQ answering / RIF honest-CV",
            artifacts=[
                Artifact("data/graph_scale/learned_discriminator/vecs.npy", "npy", role="embeddings"),
                Artifact("data/graph_scale/learned_discriminator/clf.pkl", "pkl_size_est", role="classifier"),
            ],
            fallback_params=5_120_000,
        ),
        Organ(
            id="lexical_field",
            path="packages/graph_scale/lexical_field.py",
            role="PPMI+SVD word vectors: learned valence/similarity/type (replaces hand emotion/pronoun lists)",
            gate="graph_scale affect/lexicon layer",
            artifacts=[Artifact("data/graph_scale/lexical_field/vectors.npy", "npy")],
            fallback_params=576_000,
        ),
        Organ(
            id="rif_enwiki_emb",
            path="packages/reasoning_vm/ace/data.py",
            role="enwiki PPMI+SVD word vectors: warm-start for the ACE encoder token-embedding block",
            gate="ACE reader stack (encoder input)",
            artifacts=[Artifact("data/graph_scale/rif_enwiki_emb/vecs.npy", "npy")],
            fallback_params=7_680_000,
        ),
        Organ(
            id="phase_space",
            path="packages/graph_scale/phase_space.py",
            role="RotatE-style 8-phase per-node vectors: resonance()/neighbors() similarity + link prediction",
            gate="graph_scale semantic-similarity / referent disambiguation",
            artifacts=[
                Artifact("data/graph_scale/phase_space/*.npy", "npy", role="phases"),
                Artifact("data/graph_scale/phase_space_conceptnet/*.npy", "npy", role="phases_conceptnet"),
            ],
            fallback_params=5_169_152,
        ),
        Organ(
            id="learned_realizer_grammar",
            path="packages/base_brain/learned_realizer.py",
            role="mined connective/fusion frequency statistics (NOT neural): fuses grounded clauses",
            gate="base_brain grounded generation / surface realization",
            artifacts=[Artifact("data/surface_brain/realizer_grammar.json", "json_floats")],
            fallback_params=20,
        ),
        Organ(
            id="fluency_register_lever",
            path="packages/fluency/realizer.py",
            role="delexicalized register skeletons + copy mechanism: selects clause complexity "
                 "(simple/neutral/explanatory) and fills entity slots by COPY from grounding — "
                 "templates + copy, ZERO learned weights (fluency without entity memorization)",
            gate="fluency surface realization (delex+copy, behind the grounding copy gate)",
            artifacts=[Artifact("data/fluency/registers.json", "json_floats")],
            fallback_params=0,
        ),
        Organ(
            id="fluency_verifier",
            path="packages/fluency/verifier.py",
            role="tiny logistic over cheap surface features (function-word ratio, connective VARIETY, "
                 "n-gram repetition, clause-length variance, template markers, agreement): a PROXY "
                 "naturalness discriminator (natural vs stiff/template) that GATES the self-evolution "
                 "fluency loop — a scorer behind a structural floor + a frozen human anchor, NEVER a "
                 "fact source and never fully autonomous (naturalness has no ground-truth oracle)",
            gate="fluency self-evolution verifier (learned discriminator x structural floor x frozen "
                 "human anchor; proxy-evolvable-anchored, is_autonomous_safe=False)",
            artifacts=[Artifact("data/fluency/verifier.json", "json_floats")],
            fallback_params=34,
        ),
        # ---- experimental: heavy torch tracks (advisory tier; retire per doctrine) ----
        Organ(
            id="ace_reader",
            path="packages/reasoning_vm/deliberator/planner.py",
            role="ACE v1 answerability(CLS)+span+support JUDGE (a judge, not a generator)",
            gate="reasoning_vm deliberator (MultiHopReader / Adjudicator)",
            artifacts=[Artifact("data/graph_scale/ace_*.pt", "pt_size_est")],
            enforced=False, status="experimental",
            fallback_params=11_117_839,
        ),
        Organ(
            id="ace2_reader",
            path="packages/reasoning_vm/deliberator/planner.py",
            role="ACE2 RoPE+GeGLU reader/adjudicator (larger variant)",
            gate="reasoning_vm deliberator (System-2 research track; GPQA ~= chance)",
            artifacts=[Artifact("data/graph_scale/ace2_*.pt", "pt_size_est")],
            enforced=False, status="retire-target",
            fallback_params=27_907_714,
        ),
        Organ(
            id="trackf_realizer",
            path="packages/grounded_composer/dual_route.py",
            role="~35-55M causal decoder: grounded surface realizer (FORM only, behind the grounding gate)",
            gate="grounded_composer dual-route (open route) — DISCARDED: frame_realizer beat it 1.000 faithful",
            artifacts=[Artifact("data/graph_scale/realizer*.pt", "pt_size_est")],
            enforced=False, status="retire-target",
            fallback_params=56_462_983,
        ),
        Organ(
            id="mcq_judge",
            path="scripts/train_mcq_judge.py",
            role="torch EmbeddingBag+MLP MCQ judge (L1); no in-packages runtime loader (script-only)",
            gate="standalone MCQ track (not wired into a package gate)",
            artifacts=[Artifact("data/graph_scale/mcq_judge.pt", "pt_size_est")],
            enforced=False, status="experimental",
            fallback_params=5_268_714,
        ),
        Organ(
            id="math_parser",
            path="scripts/train_math_parser_v2.py",
            role="torch word-problem parser -> symbolic ops (L2); no in-packages runtime loader",
            gate="standalone math track (not wired into a package gate)",
            artifacts=[Artifact("data/graph_scale/math_parser*.pt", "pt_size_est")],
            enforced=False, status="experimental",
            fallback_params=3_090_090,
        ),
        # ---- control organs: learned from ATANOR's OWN operation, not an answer-path fact source ----
        Organ(
            id="metacog_baselines",
            path="packages/metacog/probes.py",
            role="online per-span latency/success sufficient statistics (Welford mean/variance): the "
                 "learned 'normal' the Metacognitive Efficiency Controller judges anomalies against — a "
                 "self-monitoring control instrument, never a provider of world facts",
            gate="metacog watch-decide-resteer controller (attention-schema-for-control; GWT-4/AST)",
            artifacts=[Artifact("data/metacog/baselines.json", "json_floats", role="sufficient_stats")],
            enforced=False, status="active",
            # honest count: MEC holds no trained weights, only running sufficient statistics per span
            fallback_params=0,
        ),
        Organ(
            id="felt_judgment",
            path="packages/subjective/felt_judgment.py",
            role="value-weights groundable merit by the CURRENT felt state (digital-hormone levels, "
                 "per-concept somatic-marker valence, stakes-vital hunger) to produce agent-relative "
                 "subjective judgments — the FEELING complement to MEC's discomfort re-steer; holds NO "
                 "trained weights, only declared coupling constants over existing organ state; never a "
                 "fact source, and it can never override the moral 0th gate or fabricate merit",
            gate="subjective felt-judgment organ (behind graph_scale.moral_invariants 0th gate + grounding floor)",
            artifacts=[],   # no weight artifacts on disk — a weighting over other organs' state
            enforced=False, status="active",
            # honest count: zero parameters — the constants are curated structure (like homeostasis
            # set-points), not learned weights; the felt inputs are produced by other registered organs
            fallback_params=0,
        ),
        Organ(
            id="conversation_engage",
            path="packages/conversation/engage.py",
            role="engagement composer: assembles a grounded sub-answer (mechanism reasoning, perceived "
                 "state, a graph fact, felt state) into a warm 1-3 sentence turn (acknowledge -> content "
                 "-> offer back) from CLOSED conversational templates + copy from grounding — templates + "
                 "copy, ZERO learned weights; every content word traces to grounding or the closed lexicon",
            gate="realcity adapter _emit()/pre-intercept behind ATANOR_ENGAGE + the verify_grounded "
                 "fabrication gate (an ungrounded candidate is discarded for the terse answer)",
            artifacts=[],   # no weight artifacts on disk — closed-vocabulary templates, not learned weights
            enforced=False, status="active",
            # honest count: zero parameters — the register templates and closed lexicon are curated
            # DATA (the same category as fluency's APPROVED_CONNECTIVES), never trained weights
            fallback_params=0,
        ),
        Organ(
            id="knowledge_harvest",
            path="packages/knowledge_harvest/harvester.py",
            role="bounded relational-fact harvester + graph ingest: appends SOURCED (subject, relation, "
                 "object) edges (capital/population/currency/official_language/located_in/author/inventor) "
                 "pulled from Wikidata SPARQL (verbatim) or a bundled curated CSV into kg_triples so the "
                 "base_brain relational lane FINDS them — a DATA-ingestion pipeline, not a runtime scorer",
            gate="base_brain relational lane (relational_lookup resolves the ingested edge); the facts "
                 "carry Wikidata/curated provenance in the store's src.col, NOT in this code",
            artifacts=[],   # no weight artifacts on disk — the output is graph edges (data), the input is a CSV (data)
            enforced=False, status="active",
            # honest count: zero learned parameters — it transcribes structured facts into the graph;
            # fact_source stays False because the runtime fact source is the GRAPH, never this pipeline
            fallback_params=0,
        ),
        Organ(
            id="causal_fuel",
            path="packages/continuous_self/causal_fuel.py",
            role="corroboration counter for the HOT-3 belief-formation loop: promotes a (cause->effect) "
                 "candidate to a HELD causal law only when >= MIN_SUPPORT INDEPENDENT observations "
                 "(ATANOR's own lived stakes transitions and/or DISTINCT wild-web domains) attest it, "
                 "with directional reliability where lived; below the bar it stays a hypothesis",
            gate="continuous_self causal belief-formation (causal_self.coverage / consciousness_audit "
                 "HOT-3) behind the support/confidence promotion bar + external-minds-are-data "
                 "(wild-web candidates are hypotheses, never facts by themselves)",
            artifacts=[],   # no weight artifacts on disk — it counts other organs' real records live
            enforced=False, status="active",
            # honest count: zero parameters — a count over lived transitions + wild-web domains, not
            # trained weights; fact_source stays False (it forms revisable beliefs, never asserts facts)
            fallback_params=0,
        ),
    ]
    # ---- deliberator (System-2 controller): self-registered, zero-param, guarded so the ledger never
    #      depends on that package importing cleanly (absence just omits the advisory row) ----
    try:
        from packages.deliberator.ledger import ledger_entry as _deliberator_entry
        organs.append(_deliberator_entry())
    except Exception:
        pass
    # ---- perception_recurrence (within-percept RPT refinement): self-registered, zero-param, guarded.
    #      A fixed-point refinement loop over curated dynamical set-points — no trained weights ----
    try:
        from packages.perception_recurrence.refinement import ledger_entry as _recurrence_entry
        organs.append(_recurrence_entry())
    except Exception:
        pass
    # ---- consciousness_blind judge (external-blind adversarial indicator assessor): self-registered,
    #      zero-param, guarded. A measurement/discrimination instrument (curated held-out stimuli +
    #      falsification controls), no trained weights, never a fact source ----
    try:
        from packages.consciousness_blind.neuro_entry import ledger_entry as _blind_entry
        organs.append(_blind_entry())
    except Exception:
        pass
    return organs


def load_ledger() -> list[Organ]:
    """The seeded registry of every learned organ."""
    return _registry()


# ── parameter measurement ────────────────────────────────────────────────────────────────────────
def _npy_numel(path: Path) -> int | None:
    import numpy as np
    try:
        return int(np.load(path, mmap_mode="r").size)
    except Exception:
        try:
            with path.open("rb") as fh:
                ver = np.lib.format.read_magic(fh)
                shape, _fortran, _dt = np.lib.format._read_array_header(fh, ver)
            n = 1
            for d in shape:
                n *= int(d)
            return n
        except Exception:
            return None


def _npz_numel(path: Path) -> int | None:
    import numpy as np
    try:
        with np.load(path) as z:
            return int(sum(z[k].size for k in z.files))
    except Exception:
        return None


def _json_float_count(path: Path) -> int | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    n = 0

    def walk(x: Any) -> None:
        nonlocal n
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            n += 1
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)

    # count the actual parameter arrays; ignore scalar metadata keys
    for key in ("weights", "bias", "mean", "std", "W", "b", "coef", "intercept",
                "connective_freq", "fusion_rate", "backref_rate"):
        if key in data:
            walk(data[key])
    return n


def _artifact_numel(art: Artifact, root: Path) -> tuple[int, bool, int, int]:
    """Return (params, measured, n_files_present, total_bytes) for one artifact spec.

    Checkpoints of the SAME role are counted ONCE (the max single file), so a model with 15 training
    checkpoints is one model's worth of params, not fifteen.
    """
    files = [Path(p) for p in glob.glob(str(root / art.glob), recursive=True)]
    files = [p for p in files if p.is_file()]
    if not files:
        return 0, False, 0, 0
    total_bytes = sum(p.stat().st_size for p in files)
    per_file: list[int] = []
    measured = True
    for p in files:
        if art.method == "npy":
            n = _npy_numel(p)
        elif art.method == "npz":
            n = _npz_numel(p)
        elif art.method == "json_floats":
            n = _json_float_count(p)
        elif art.method == "pt_size_est":
            n, measured = p.stat().st_size // 4, False        # float32 state_dict estimate
        elif art.method == "pkl_size_est":
            n, measured = p.stat().st_size // 8, False        # rough sklearn estimate
        else:
            n = None
        if n is None:
            n, measured = p.stat().st_size // 4, False
        per_file.append(int(n))
    return max(per_file), measured, len(files), total_bytes


def measure_params(organ: Organ) -> dict[str, Any]:
    """Measure one organ's parameter count from its real artifacts (sum over distinct roles, max
    within a role). Falls back to the declared last-known count when no artifact is on disk."""
    root = repo_root()
    total = 0
    measured_all = True
    present_files = 0
    total_bytes = 0
    per_artifact: list[dict[str, Any]] = []
    for art in organ.artifacts:
        n, measured, nfiles, nbytes = _artifact_numel(art, root)
        present_files += nfiles
        total_bytes += nbytes
        if nfiles:
            total += n
            measured_all = measured_all and measured
        per_artifact.append({"glob": art.glob, "role": art.role, "method": art.method,
                             "params": n, "files": nfiles, "bytes": nbytes, "measured": measured})
    present = present_files > 0
    if not present:
        return {"id": organ.id, "params": int(organ.fallback_params), "measured": False,
                "present": False, "artifact_bytes": 0, "artifacts": per_artifact,
                "note": "artifact absent on disk; using declared last-known count"}
    return {"id": organ.id, "params": int(total), "measured": measured_all, "present": True,
            "artifact_bytes": int(total_bytes), "artifacts": per_artifact}


def measure_all(ledger: list[Organ] | None = None) -> list[dict[str, Any]]:
    """Measure every organ; attach the registry metadata each audit gate needs."""
    ledger = ledger if ledger is not None else load_ledger()
    out: list[dict[str, Any]] = []
    for organ in ledger:
        m = measure_params(organ)
        m.update({"path": organ.path, "role": organ.role, "gate": organ.gate,
                  "fact_source": organ.fact_source, "enforced": organ.enforced,
                  "status": organ.status})
        out.append(m)
    return out


def organ_to_dict(organ: Organ) -> dict[str, Any]:
    d = asdict(organ)
    return d
