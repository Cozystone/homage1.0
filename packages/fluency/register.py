# -*- coding: utf-8 -*-
"""Register lever — clause-complexity selection over DATA-driven register templates.

The corpus-composition diagnosis says the fluency wall is register complexity: a store that is 52%
encyclopaedia recites long compound sentences and cannot pitch a simple, natural answer. frame_realizer
has exactly ONE register — it aggregates every fact for a subject into a single ", and ... , and ..."
sentence. This lever adds the missing knob.

A register is DATA (``data/fluency/registers.json``, extensible), never a code branch. Each spec
declares parameters the realizer reads — how many clauses per sentence, which connectives it may vary
between, whether to pronominalize the subject after first mention, whether to front a reduced clause.
Adding a "journalistic" or "childlike" register is a data edit. The output vocabulary stays CLOSED:
a register may only reference connectives/openers on the approved lists below, so register data can
never smuggle in free text (the same honesty contract as the discourse model).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
REGISTERS_PATH = REPO / "data" / "fluency" / "registers.json"

# closed, approved surface vocabulary. Register data RANKS/selects from these; it cannot go outside.
APPROVED_CONNECTIVES = ("and", "while", "which is why", "so", "and in turn", "as well as")
APPROVED_OPENERS = ("In addition", "As a result", "Beyond that", "On top of that", "It also follows that")

# closed, approved CONVERSATIONAL discourse markers (the LAD surface layer: closed-class discourse
# words with NO propositional content, doctrine-allowed like connectives/openers). A conversational
# register RANKS/selects from these to open a continuation sentence; it cannot go outside. They carry
# pragmatic stance but not truth-conditional content, so a marker never changes the fact set — and the
# realizer applies them BOUNDEDLY (never on every sentence) so they are not forced where they misfit.
APPROVED_DISCOURSE_MARKERS = ("Well", "So", "Now", "Actually", "Anyway")


@dataclass
class RegisterSpec:
    id: str
    description: str
    max_clauses_per_sentence: int = 1            # 1 = one clause per sentence (simplest)
    connective_pool: tuple[str, ...] = ()        # varied between clauses joined in one sentence
    opener_pool: tuple[str, ...] = ()            # discourse openers for continuation sentences
    pronoun_after_first: bool = True             # refer to the subject by pronoun after first mention
    front_reduced: bool = False                  # front a reduced clause: "Located in X, it ..."
    aggregate_copular: bool = True               # fuse is_a + adjectives into one NP (correctness)
    aggregate_reduced: bool = True               # attach reduced participles to the head ("made of X");
                                                 # False -> emit them as full pronoun clauses ("it is
                                                 # made of X"), the plainer conversational segmentation
    contractions: bool = False                   # collapse copula/aux function words: "it is" -> "it's"
    discourse_marker_pool: tuple[str, ...] = ()  # conversational openers, applied BOUNDEDLY (not forced)
    # ── the CLAUSE-COMBINING lever (R4 next lever) ────────────────────────────────────────────────
    # Off by default (every existing register is a FLAT/aggregated planner). When on, the realizer
    # tries to re-package a subject's bones into a VARIED syntactic structure — demote is_a to an
    # appositive so a predicate becomes the main clause, coordinate same-subject predicates, or
    # subordinate a capability as a relative clause — and FAITHFULNESS-GATES every combined sentence
    # against the flat baseline: a combination that fails faithfulness / drops or adds a fact / runs on
    # is REJECTED and the flat clause stands. A wrong combination is worse than a flat clause.
    combine: bool = False                        # master switch for the clause-combining planner
    appose_is_a: bool = False                    # demote is_a to an appositive: "X, a Y, <verb>s Z"
    relativize: bool = False                     # subordinate a lone capability: "X is a Y that can W"
    combine_max_main: int = 2                    # max predicates coordinated in the appositive's main VP

    def filtered(self) -> "RegisterSpec":
        """Drop any connective/opener/marker not on the approved lists — the closed-vocabulary gate."""
        self.connective_pool = tuple(c for c in self.connective_pool if c in APPROVED_CONNECTIVES)
        self.opener_pool = tuple(o for o in self.opener_pool if o in APPROVED_OPENERS)
        self.discourse_marker_pool = tuple(
            m for m in self.discourse_marker_pool if m in APPROVED_DISCOURSE_MARKERS)
        return self


# ── the default registers (the Python fallback; the JSON file is the extensible surface) ──────────
def default_registers() -> dict[str, RegisterSpec]:
    return {
        # SIMPLE — beginner/plain register: one fact per short sentence, pronoun after first mention.
        # Breaks frame_realizer's run-on into readable sentences. The default.
        "simple": RegisterSpec(
            id="simple",
            description="plain, one clause per short sentence; pronoun after first mention",
            max_clauses_per_sentence=1,
            connective_pool=(),
            opener_pool=(),
            pronoun_after_first=True,
            front_reduced=False,
        ),
        # NEUTRAL — balanced register: up to two clauses per sentence joined by a VARIED connective
        # (not "and" every time), reduced clauses aggregated onto the head.
        "neutral": RegisterSpec(
            id="neutral",
            description="balanced; up to two clauses per sentence with varied connectives",
            max_clauses_per_sentence=2,
            connective_pool=("and", "while"),
            opener_pool=(),
            pronoun_after_first=True,
            front_reduced=False,
        ),
        # EXPLANATORY — higher clause complexity: front a reduced clause, open continuation sentences
        # with a discourse connective, richer joining. For "explain/why/how" contexts.
        "explanatory": RegisterSpec(
            id="explanatory",
            description="explanatory; fronted reduced clauses and discourse-connective openers",
            max_clauses_per_sentence=2,
            connective_pool=("which is why", "and in turn", "so"),
            opener_pool=("In addition", "As a result", "Beyond that"),
            pronoun_after_first=True,
            front_reduced=True,
        ),
        # CONVERSATIONAL — plain SIMPLE clause structure (one fact per short sentence, pronoun after
        # first mention) with the conversational SURFACE knobs on: copula/aux contractions ("it is" ->
        # "it's") and a bounded set of discourse-marker openers. Only the surface FORM changes; the
        # clause structure, the copy gate, and the fact set are identical to 'simple'. Selected only on
        # an explicit conversational/casual audience or intent (never from a factual query string), so
        # the encyclopaedic answer path is never routed here by accident.
        "conversational": RegisterSpec(
            id="conversational",
            description="conversational; simple clauses + contractions + bounded discourse markers",
            max_clauses_per_sentence=1,
            connective_pool=(),
            opener_pool=(),
            pronoun_after_first=True,
            front_reduced=False,
            aggregate_reduced=False,
            contractions=True,
            discourse_marker_pool=("So", "Now", "Well"),
        ),
        # COMPOSED — the CLAUSE-COMBINING register (R4 next lever). Same copy gate and morphology floor
        # as the others, but the planner re-packages a subject's bones into varied syntax: it demotes
        # is_a to an appositive so a real predicate becomes the main clause ("Kettle, a vessel made of
        # steel, can whistle and has a spout."), coordinates same-subject predicates, and subordinates a
        # lone capability as a relative clause ("Mice are small rodents that can climb."). EVERY combined
        # sentence is faithfulness-gated against the flat baseline and rejected -> flat on any failure.
        # Leftover clauses use the neutral 2-clause continuation. Explicit-only (never auto-routed from a
        # query string), like conversational, so the factual answer path is never re-shaped by accident.
        "composed": RegisterSpec(
            id="composed",
            description="composed prose; appositive/coordination/relative combining, faithfulness-gated with flat fallback",
            max_clauses_per_sentence=2,
            connective_pool=("and", "while"),
            opener_pool=(),
            pronoun_after_first=True,
            front_reduced=False,
            aggregate_copular=True,
            aggregate_reduced=True,
            combine=True,
            appose_is_a=True,
            relativize=True,
            combine_max_main=2,
        ),
    }


def _spec_from_dict(d: dict[str, Any]) -> RegisterSpec:
    return RegisterSpec(
        id=str(d["id"]),
        description=str(d.get("description", "")),
        max_clauses_per_sentence=int(d.get("max_clauses_per_sentence", 1)),
        connective_pool=tuple(d.get("connective_pool", ()) or ()),
        opener_pool=tuple(d.get("opener_pool", ()) or ()),
        pronoun_after_first=bool(d.get("pronoun_after_first", True)),
        front_reduced=bool(d.get("front_reduced", False)),
        aggregate_copular=bool(d.get("aggregate_copular", True)),
        aggregate_reduced=bool(d.get("aggregate_reduced", True)),
        contractions=bool(d.get("contractions", False)),
        discourse_marker_pool=tuple(d.get("discourse_marker_pool", ()) or ()),
        combine=bool(d.get("combine", False)),
        appose_is_a=bool(d.get("appose_is_a", False)),
        relativize=bool(d.get("relativize", False)),
        combine_max_main=int(d.get("combine_max_main", 2)),
    ).filtered()


def load_registers() -> dict[str, RegisterSpec]:
    """Load register specs from data/fluency/registers.json; fall back to the built-in defaults.
    Every spec passes the closed-vocabulary filter, so a hand-edited JSON cannot inject free text."""
    if REGISTERS_PATH.exists():
        try:
            raw = json.loads(REGISTERS_PATH.read_text(encoding="utf-8"))
            specs = {}
            for d in raw.get("registers", []):
                spec = _spec_from_dict(d)
                specs[spec.id] = spec
            if specs:
                return specs
        except Exception:
            pass
    return {k: v.filtered() for k, v in default_registers().items()}


def build_registers_pack() -> dict[str, Any]:
    """Write the registers pack to data/fluency/registers.json (the DATA surface; mirrors the
    base_brain surface_pack idiom). Returns the written pack."""
    specs = default_registers()
    pack = {
        "pack_id": "fluency_registers_v0",
        "version": "0.1.0",
        "notes": [
            "Register specs are DATA read by packages/fluency/realizer.py; not code branches.",
            "connective_pool/opener_pool/discourse_marker_pool may only reference the approved closed vocabulary.",
            "contractions is a FORM-only function-word transform; it never changes the fact set.",
            "Adding a register is a data edit (append an object here).",
        ],
        "approved_connectives": list(APPROVED_CONNECTIVES),
        "approved_openers": list(APPROVED_OPENERS),
        "approved_discourse_markers": list(APPROVED_DISCOURSE_MARKERS),
        "registers": [
            {
                "id": s.id,
                "description": s.description,
                "max_clauses_per_sentence": s.max_clauses_per_sentence,
                "connective_pool": list(s.connective_pool),
                "opener_pool": list(s.opener_pool),
                "pronoun_after_first": s.pronoun_after_first,
                "front_reduced": s.front_reduced,
                "aggregate_copular": s.aggregate_copular,
                "aggregate_reduced": s.aggregate_reduced,
                "contractions": s.contractions,
                "discourse_marker_pool": list(s.discourse_marker_pool),
                "combine": s.combine,
                "appose_is_a": s.appose_is_a,
                "relativize": s.relativize,
                "combine_max_main": s.combine_max_main,
            }
            for s in specs.values()
        ],
    }
    REGISTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTERS_PATH.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return pack


# ── selection: pick by context, DEFAULT simple ───────────────────────────────────────────────────
_EXPLANATORY_CUES = ("explain", "why", "how does", "how do", "walk me through", "in detail",
                     "elaborate", "mechanism")
# conversational is routed ONLY by an explicit audience/intent signal — never by a query STRING. A
# factual answer path that passes only {"query": ...} (e.g. the workspace surface pass) therefore can
# never land on the contraction/discourse-marker register by accident.
_CONVERSATIONAL_AUDIENCE = ("casual", "friend", "child", "layperson", "conversational")
_CONVERSATIONAL_INTENT = ("chat", "casual", "conversational", "smalltalk")


def select_register(context: dict[str, Any] | None = None,
                    available: dict[str, RegisterSpec] | None = None) -> str:
    """Choose a register id from context. DEFAULT is 'simple'. Precedence:
      1. an explicit context['register'] that exists,
      2. an explanatory audience/intent, or an 'explain/why/how' query cue -> 'explanatory',
      3. an explicit conversational/casual audience or intent -> 'conversational',
      4. otherwise 'simple'.
    Never raises: an unknown/empty context yields the safe default. Conversational is intentionally NOT
    reachable from a query string — only an explicit casual audience/intent selects it."""
    specs = available if available is not None else load_registers()
    ctx = context or {}
    explicit = str(ctx.get("register", "")).strip()
    if explicit and explicit in specs:
        return explicit
    audience = str(ctx.get("audience", "")).lower()
    intent = str(ctx.get("intent", "")).lower()
    query = str(ctx.get("query", "")).lower()
    if "explanatory" in specs and (
        audience in ("expert", "explanatory")
        or intent in ("explain", "explanatory")
        or any(cue in query for cue in _EXPLANATORY_CUES)
    ):
        return "explanatory"
    if "conversational" in specs and (
        audience in _CONVERSATIONAL_AUDIENCE or intent in _CONVERSATIONAL_INTENT
    ):
        return "conversational"
    return "simple" if "simple" in specs else next(iter(specs))
