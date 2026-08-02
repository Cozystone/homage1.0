from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Literal


ManifestStatus = Literal["draft", "review_ready", "signed", "rejected", "expired"]


@dataclass(frozen=True)
class ConstructionPromotionEntry:
    candidate_id: str
    construction_family: str
    route_type: str
    language: str
    source_refs: tuple[str, ...]
    review_status: str
    scores: dict[str, float]
    allowed_modes: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    activation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RollbackManifest:
    rollback_manifest_id: str
    previous_active_set: tuple[str, ...]
    candidate_ids_to_disable: tuple[str, ...]
    route_scopes: tuple[str, ...]
    reason: str
    executable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConstructionPromotionManifest:
    manifest_id: str
    created_at: str
    created_by: str
    candidate_ids: tuple[str, ...]
    route_scopes: tuple[str, ...]
    language_scopes: tuple[str, ...]
    product_mode_allowed: bool
    lab_mode_allowed: bool
    min_naturalness_score: float
    min_grounding_score: float
    max_template_risk: float
    max_safety_risk: float
    regression_set: tuple[str, ...]
    rollback_manifest_id: str
    operator_signature: str | None = None
    status: ManifestStatus = "draft"
    production_activation: bool = False
    entries: tuple[ConstructionPromotionEntry, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "production_active": False,
            "production_construction_activation": False,
            "signed_manifest_required": True,
            "rollback_required": True,
            "proof_only": True,
        }


_MANIFESTS: dict[str, ConstructionPromotionManifest] = {}
_ROLLBACKS: dict[str, RollbackManifest] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_manifest_id(candidate_ids: tuple[str, ...], route_scopes: tuple[str, ...], created_by: str) -> str:
    seed = "\n".join(candidate_ids + route_scopes + (created_by, utc_now()))
    return f"construction_manifest_{sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def make_rollback_manifest(
    *,
    candidate_ids: tuple[str, ...],
    route_scopes: tuple[str, ...],
    reason: str = "proof_only_rollback_plan",
) -> RollbackManifest:
    seed = "\n".join(candidate_ids + route_scopes + (reason, utc_now()))
    rollback = RollbackManifest(
        rollback_manifest_id=f"construction_rollback_{sha256(seed.encode('utf-8')).hexdigest()[:16]}",
        previous_active_set=(),
        candidate_ids_to_disable=candidate_ids,
        route_scopes=route_scopes,
        reason=reason,
        executable=False,
    )
    _ROLLBACKS[rollback.rollback_manifest_id] = rollback
    return rollback


def store_manifest(manifest: ConstructionPromotionManifest) -> ConstructionPromotionManifest:
    _MANIFESTS[manifest.manifest_id] = manifest
    return manifest


def get_manifest(manifest_id: str) -> ConstructionPromotionManifest | None:
    return _MANIFESTS.get(manifest_id)


def list_manifests() -> list[ConstructionPromotionManifest]:
    return sorted(_MANIFESTS.values(), key=lambda item: item.created_at, reverse=True)


def get_rollback(rollback_manifest_id: str) -> RollbackManifest | None:
    return _ROLLBACKS.get(rollback_manifest_id)


def sign_preview(manifest_id: str, operator_signature: str) -> ConstructionPromotionManifest:
    manifest = _MANIFESTS[manifest_id]
    next_status: ManifestStatus = "signed" if operator_signature.strip() else "review_ready"
    updated = replace(
        manifest,
        operator_signature=operator_signature.strip() or None,
        status=next_status,
        production_activation=False,
    )
    _MANIFESTS[manifest_id] = updated
    return updated
