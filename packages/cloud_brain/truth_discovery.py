"""Truth discovery over the consensus ledger — TruthFinder-style EM, No-LLM.

 P2(a): the answer to faithful-to-WRONG-source. Raw consensus counts treat
every source as equally reliable; truth discovery estimates source TRUST and
claim BELIEF jointly, purely from the agreement structure:

 a claim is believable when trusted sources support it;
 a source is trusted when it supports believable claims.

Competing claims are detected automatically: two claims with the same
(subject, predicate) but different objects form an EXCLUSION GROUP (the
functional-predicate reading — "the capital of X" cannot be two things), and
belief is normalized within the group, so a lone unreliable source contradicting
a majority loses. Claims without competitors keep an independent belief.

Pure iterative averaging over the support matrix (Yin et al. TruthFinder /
Knowledge Vault lineage), ~10 rounds to convergence. Scores persist next to the
ledger so promotion and answering can weight evidence by them.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_DAMPING = 0.3          # keep trust away from hard 0/1 (TruthFinder's gamma)
_INIT_TRUST = 0.5
_ROUNDS = 10


@dataclass
class Claim:
    key: str
    subject: str
    predicate: str
    obj: str
    sources: set[str] = field(default_factory=set)
    belief: float = 0.5


@dataclass
class TruthScores:
    claim_belief: dict[str, float]
    source_trust: dict[str, float]
    exclusion_groups: int
    rounds: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_belief": self.claim_belief,
            "source_trust": self.source_trust,
            "exclusion_groups": self.exclusion_groups,
            "rounds": self.rounds,
        }


def _logit_score(trusts: Iterable[float]) -> float:
    """Additive evidence score: independent sources compound (probabilistic OR in log space)."""
    score = 0.0
    for t in trusts:
        t = min(max(t, 0.01), 0.99)
        score += -math.log(1.0 - t)
    return score


def run_truth_discovery(claims: list[Claim], *, rounds: int = _ROUNDS) -> TruthScores:
    sources: dict[str, float] = {}
    for c in claims:
        for s in c.sources:
            sources.setdefault(s, _INIT_TRUST)

    # exclusion groups: same (subject, predicate), different object -> compete
    groups: dict[tuple[str, str], list[Claim]] = {}
    for c in claims:
        groups.setdefault((c.subject.lower(), c.predicate.lower()), []).append(c)
    competing = {k: v for k, v in groups.items() if len(v) > 1}

    for _ in range(max(1, rounds)):
        # claim belief from source trust
        for c in claims:
            c.belief = 1.0 - math.exp(-_logit_score(sources[s] for s in c.sources))
        for members in competing.values():
            total = sum(c.belief for c in members)
            if total > 0:
                for c in members:
                    c.belief = c.belief / total
        # source trust from claim belief (damped mean)
        for s in sources:
            supported = [c.belief for c in claims if s in c.sources]
            if supported:
                mean = sum(supported) / len(supported)
                sources[s] = (1 - _DAMPING) * mean + _DAMPING * _INIT_TRUST

    return TruthScores(
        claim_belief={c.key: round(c.belief, 4) for c in claims},
        source_trust={s: round(t, 4) for s, t in sources.items()},
        exclusion_groups=len(competing),
        rounds=rounds,
    )


def claims_from_ledger(ledger: Any) -> list[Claim]:
    """Build the claim/support structure by replaying the ledger's evidence events.

 Source identity for TRUST purposes is the provenance source_id on each
 evidence event's relation row (falling back to the evidence sentence hash),
 so one website / one feed is ONE voice no matter how many sentences it
 contributed — which is also the Sybil-cap needed later ( ⑧).
 """
    by_key: dict[str, Claim] = {}
    if not ledger.ledger_path.exists():
        return []
    for line in ledger.ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        row = ev.get("row") or {}
        prov = row.get("provenance") or {}
        voice = str(prov.get("source_id") or prov.get("document_id") or ev.get("evidence_id") or "")
        claim = by_key.setdefault(
            ev["key"],
            Claim(
                key=ev["key"],
                subject=str(ev.get("source_label") or ""),
                predicate=str(row.get("relation") or ""),
                obj=str(ev.get("target_label") or ""),
            ),
        )
        if voice:
            claim.sources.add(voice)
    return list(by_key.values())


def score_and_persist(ledger: Any) -> TruthScores:
    scores = run_truth_discovery(claims_from_ledger(ledger))
    out = Path(ledger.root) / "truth_scores.json"
    out.write_text(json.dumps(scores.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    return scores
