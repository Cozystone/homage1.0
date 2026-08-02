from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class KnowledgeCartridge:
    cartridge_id: str
    cartridge_type: str
    public_only: bool
    content_hash: str
    semantic_tags: list[str]
    provenance: dict[str, Any]
    privacy_grade: str
    license_hint: str
    payload_summary: str
    raw_payload_included: bool = False

    def __post_init__(self) -> None:
        if not self.cartridge_id:
            raise ValueError("cartridge_id is required")
        if self.raw_payload_included:
            raise ValueError("proof-only cartridges must not include raw payload")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PROTOCOL_STAGES = [
    "local private data never leaves",
    "Tabularis privacy check required for structured private data",
    "Atlas Trust Router selects safe public path later",
    "cartridge metadata exchange",
    "compatibility score",
    "sandbox attach",
    "temporary use",
    "detach",
    "no permanent Local Brain mutation without approval",
]


def compatibility_score(
    local_tags: list[str],
    cartridge: KnowledgeCartridge,
    *,
    trust_score: float = 0.8,
    license_risk: float = 0.1,
) -> float:
    local = {tag.lower() for tag in local_tags}
    remote = {tag.lower() for tag in cartridge.semantic_tags}
    overlap = len(local & remote) / max(1, len(local | remote))
    privacy_bonus = 0.2 if cartridge.public_only and cartridge.privacy_grade in {"public", "synthetic"} else 0.0
    license_penalty = min(0.5, max(0.0, license_risk))
    score = (overlap * 0.5) + (trust_score * 0.3) + privacy_bonus - license_penalty
    return max(0.0, min(1.0, round(score, 4)))

