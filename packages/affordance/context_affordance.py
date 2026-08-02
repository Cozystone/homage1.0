# -*- coding: utf-8 -*-
"""Context → affordance engine — the owner's doctrine, made real (2026-07-12).

The rule ATANOR must live by, in the owner's words: don't code each behaviour as a tool
(`if tired → play music`). Perception ONLY perceives — it emits a distilled STATE (a set of
concepts). Separately, AFFORDANCES are laid down: executable PATHS, each living in a semantic
field. Selection is not a condition table — the perceived state RESONATES with the paths through
the graph, and the most resonant path (above a floor) is proposed; below the floor, SILENCE.

Why this isn't `if/then`:
 * perception and action are DECOUPLED — an observation never names an action, an affordance
 never names a trigger predicate; they meet in concept space;
 * matching is GRADED resonance (graph-expanded overlap), not boolean equality, so a state the
 author never enumerated ( near ) still lights up a path — it generalizes;
 * paths are DATA (a registry the owner extends), not branches in code;
 * nothing fires by default — voice-or-silence: no resonance → no proposal.

The engine only LAYS DOWN the walkable paths (grounded, risk-gated). Whether one is walked is the
trust tier's / the human's call — the machine never promotes its own reach. Honesty is built in:
a proposal carries the ACTUAL resonating concepts as its grounding, never a fabricated reason.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.os_action_lane.models import GateOutcome, RiskLevel, TrustTier

_REGISTRY = Path(__file__).resolve().parents[2] / "data" / "affordance" / "affordances.jsonl"
_FLOOR = 0.34            # below this resonance, the path stays unlit — silence, not a stretch


# ── the paths (DATA, not conditions) ─────────────────────────────────────────────────────────
# Seed affordances: each is a PATH with a semantic field (`cues`), an effect channel, and a risk.
# The owner adds more by appending to data/affordance/affordances.jsonl — no code change. These
# encode the owner's examples as fields, but the engine generalizes past them via graph resonance.
_SEED: list[dict[str, Any]] = [
    {"id": "particle_response", "label": "파티클 공간으로 지금 마음을 표현", "effect": "particle",
     "risk": int(RiskLevel.READONLY),
     "cues": ["감정", "기분", "마음", "상태", "분위기", "기쁨", "슬픔", "피곤", "설렘", "평온"]},
    {"id": "warm_good_news", "label": "좋은 일 있는지 물어보기", "effect": "ask",
     "risk": int(RiskLevel.REVERSIBLE), "utter": "표정이 밝아 보여요 — 좋은 일 있으세요?",
     "cues": ["기쁨", "웃음", "행복", "좋은일", "신남", "밝음", "설렘"]},
    {"id": "offer_rest", "label": "쉬거나 음악을 권하기", "effect": "soothe",
     "risk": int(RiskLevel.REVERSIBLE), "utter": "좀 피곤해 보여요 — 잠깐 쉬거나 음악 틀어드릴까요?",
     "cues": ["피곤", "졸림", "지침", "무기력", "하품", "눈감김", "탈진"],
     "action": {"kind": "open_app", "args": {"app": "music"}}},   # concrete enactment = DATA
    {"id": "notice_change", "label": "달라진 점을 알아봐 주기", "effect": "ask",
     "risk": int(RiskLevel.REVERSIBLE), "utter": "뭔가 달라지셨네요 — 잘 어울려요.",
     "cues": ["외형변화", "달라짐", "새로움", "머리색", "변화"]},
    {"id": "quiet_company", "label": "말없이 곁에 있어 주기", "effect": "silence",
     "risk": int(RiskLevel.READONLY),
     "cues": ["차분", "고요", "집중", "슬픔", "지침", "가라앉음"]},
]


@dataclass(frozen=True)
class Observation:
    """What perception distilled — concepts, plus an optional affective read (valence/energy) and
    where it came from. The engine does not know or care HOW these were derived (face emotion,
    fatigue signal, appearance drift…); it only resonates the concepts against the paths. The
    valence/energy ride along for the particle channel, which expresses the felt state."""
    concepts: list[str]
    source: str = ""
    salience: float = 1.0
    note: str = ""
    valence: float = 0.0            # −1 (down) … +1 (up)
    energy: float = 0.5             # 0 (calm/spent) … 1 (charged)


@dataclass(frozen=True)
class Proposal:
    affordance_id: str
    label: str
    effect: str
    risk: int
    resonance: float
    grounding: list[str]            # the ACTUAL resonating concepts — the honest "why"
    outcome: int                    # GateOutcome: EXECUTE / NEEDS_APPROVAL / BLOCKED
    utter: str = ""
    has_action: bool = False        # whether this path declares a concrete OS action to enact

    def to_dict(self) -> dict[str, Any]:
        return {"affordance_id": self.affordance_id, "label": self.label, "effect": self.effect,
                "risk": self.risk, "resonance": round(self.resonance, 3), "grounding": self.grounding,
                "outcome": int(self.outcome), "utter": self.utter, "has_action": self.has_action}


def load_affordances() -> list[dict[str, Any]]:
    """Seed paths + any the owner appended (DATA). Later entries with a seen id override, so a
    file entry can retune a seed path without editing code."""
    out: dict[str, dict[str, Any]] = {a["id"]: dict(a) for a in _SEED}
    try:
        for line in _REGISTRY.read_text(encoding="utf-8").splitlines():
            if line.strip():
                a = json.loads(line)
                if a.get("id"):
                    out[a["id"]] = a
    except Exception:
        pass
    return list(out.values())


def _norm(s: str) -> str:
    return str(s or "").replace(" ", "")


def _neighbors(concept: str) -> set[str]:
    """A concept's graph neighbours (canonical names), so a state can resonate with a path through
 a concept the author never listed ( → ). Best-effort: no graph → empty."""
    out: set[str] = set()
    try:
        from packages.base_brain.neighborhood import gather_neighborhood
        from packages.base_brain.pack_loader import load_base_brain_pack

        pack = load_base_brain_pack().semantic_graph.get("concepts") or []
        for n in gather_neighborhood(concept, pack, limit=5):
            nm = _norm(n.get("canonical_name", ""))
            if nm:
                out.add(nm)
    except Exception:
        pass
    return out


def _overlaps(term: str, field_: set[str]) -> bool:
    if term in field_:
        return True
    return any(len(term) >= 2 and len(c) >= 2 and (term in c or c in term) for c in field_)


def resonance(obs_concepts: list[str], cues: list[str], *, use_graph: bool = True
              ) -> tuple[float, list[str]]:
    """How brightly does the observed state light up a path's semantic field? Observation-RECALL:
    the fraction of what was PERCEIVED that lands in the path's field (directly, by Korean-compound
    overlap, or via a graph neighbour) — so a broad field is easy to light, and a state resonates
    with a path when the state's own concepts belong there. Returns (score, the resonating observed
    concepts) — the hits are the honest grounding. Graph widening only kicks in without a direct hit."""
    base = [_norm(c) for c in obs_concepts if c]
    field_ = {_norm(c) for c in cues if c}
    if not base or not field_:
        return 0.0, []
    hits: list[str] = []
    for oc in base:
        if _overlaps(oc, field_) or (use_graph and any(_overlaps(n, field_) for n in _neighbors(oc))):
            hits.append(oc)
    return len(hits) / len(base), hits


def propose(observation: Observation, *, tier: TrustTier = TrustTier.ASSIST,
            kill_switch: bool = False, use_graph: bool = True) -> dict[str, Any]:
    """Lay down the walkable paths for a perceived state. Returns every path above the floor
    (ranked, grounded, risk-gated) and marks the top as `chosen`; empty when nothing resonates
    (silence). NEVER executes — it proposes; the tier/human walks a path."""
    affs = load_affordances()
    scored: list[Proposal] = []
    for a in affs:
        score, hits = resonance(observation.concepts, a.get("cues") or [], use_graph=use_graph)
        if score < _FLOOR or not hits:
            continue
        risk = RiskLevel(int(a.get("risk", RiskLevel.REVERSIBLE)))
        scored.append(Proposal(
            affordance_id=a["id"], label=a.get("label", a["id"]), effect=a.get("effect", ""),
            risk=int(risk), resonance=score, grounding=hits,
            outcome=int(_gate(risk, TrustTier(tier), kill_switch=kill_switch)),
            utter=str(a.get("utter", "")),
            has_action=bool(isinstance(a.get("action"), dict) and a["action"].get("kind"))))
    scored.sort(key=lambda p: p.resonance, reverse=True)
    return {"paths": [p.to_dict() for p in scored],
            "chosen": scored[0].to_dict() if scored else None,
            "silent": not scored, "source": observation.source,
            "observed": list(observation.concepts)}


def _gate(risk: RiskLevel, tier: TrustTier, *, kill_switch: bool = False) -> GateOutcome:
    """Risk × trust tier → may this path run now? Internal/observational effects (READONLY —
    e.g. moving particles) are always free to run; anything that touches the world outside waits
    for the tier to have earned it, or for an explicit yes. The kill switch stops everything."""
    if kill_switch:
        return GateOutcome.BLOCKED
    if risk <= RiskLevel.READONLY:
        return GateOutcome.EXECUTE                       # internal expression — no external effect
    if risk == RiskLevel.REVERSIBLE:
        return GateOutcome.EXECUTE if tier >= TrustTier.GUARDED else GateOutcome.NEEDS_APPROVAL
    if risk == RiskLevel.DESTRUCTIVE:
        return GateOutcome.EXECUTE if tier >= TrustTier.AUTONOMOUS else GateOutcome.NEEDS_APPROVAL
    return GateOutcome.NEEDS_APPROVAL                     # catastrophic — always confirm once
