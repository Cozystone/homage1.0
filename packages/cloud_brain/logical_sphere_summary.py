from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .candidate_read_model import candidate_cloud_status


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VERIFIED_STORE = PROJECT_ROOT / "data" / "cloud_brain" / "verified_store_v0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


@dataclass(frozen=True)
class LogicalSphereVerifiedCounts:
    """Counts from verified production knowledge only."""

    verified_concepts: int
    verified_relations: int
    verified_evidence: int
    verified_case_frames: int
    source: str
    source_status: str


@dataclass(frozen=True)
class LogicalSphereCandidateCounts:
    """Counts from unpromoted candidate learning output only."""

    candidate_concepts: int
    candidate_relations: int
    candidate_evidence: int
    candidate_case_frames: int
    candidate_surface_items: int
    candidate_cgsr_items: int
    candidate_rhfc_items: int
    source: str | None
    source_status: str
    candidate_is_verified: bool


@dataclass(frozen=True)
class LogicalSphereWorkingMemoryCounts:
    """Temporary answer/session context, not persistent knowledge."""

    working_memory_nodes: int | None
    working_memory_relations: int | None
    working_memory_fragments: int | None
    source: str | None
    source_status: str
    temporary: bool


@dataclass(frozen=True)
class LogicalSphereRenderedCounts:
    """Viewport and LOD sample counts, not total graph size."""

    rendered_nodes: int | None
    rendered_edges: int | None
    materialized_nodes: int | None
    materialized_edges: int | None
    active_chunks: int | None
    visible_scale_chunks: int | None
    virtualization_enabled: bool | None
    source: str | None
    source_status: str


@dataclass(frozen=True)
class LogicalSphereSemanticsSummary:
    """Canonical read-only separation of Logical Sphere count domains."""

    generated_at: str
    store_name: str
    verified: LogicalSphereVerifiedCounts
    candidate: LogicalSphereCandidateCounts
    working_memory: LogicalSphereWorkingMemoryCounts
    rendered: LogicalSphereRenderedCounts
    explanations: dict[str, bool]
    invariants: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable summary payload."""

        return asdict(self)


def load_verified_counts(verified_store: str | Path = DEFAULT_VERIFIED_STORE) -> LogicalSphereVerifiedCounts:
    """Read verified production counts from the manifest without mutating the store."""

    store_path = Path(verified_store)
    manifest = _read_json(store_path / "manifest.json")
    if not manifest:
        return LogicalSphereVerifiedCounts(
            verified_concepts=0,
            verified_relations=0,
            verified_evidence=0,
            verified_case_frames=0,
            source=str(store_path),
            source_status="missing_verified_manifest",
        )

    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    return LogicalSphereVerifiedCounts(
        verified_concepts=_safe_int(counts.get("concepts")),
        verified_relations=_safe_int(counts.get("relations")),
        verified_evidence=_safe_int(counts.get("evidence")),
        verified_case_frames=_safe_int(counts.get("case_frames")),
        source=str(store_path / "manifest.json"),
        source_status="manifest_counts",
    )


def load_candidate_counts(candidate_store_path: str | Path | None = None) -> LogicalSphereCandidateCounts:
    """Read unpromoted candidate counts without promoting or modifying candidates."""

    status = candidate_cloud_status(candidate_store_path)
    return LogicalSphereCandidateCounts(
        candidate_concepts=_safe_int(status.get("candidate_concepts")),
        candidate_relations=_safe_int(status.get("candidate_relations")),
        candidate_evidence=_safe_int(status.get("candidate_evidence")),
        candidate_case_frames=_safe_int(status.get("candidate_case_frames")),
        candidate_surface_items=_safe_int(status.get("surface_candidates")),
        candidate_cgsr_items=_safe_int(status.get("cgsr_frames")),
        candidate_rhfc_items=_safe_int(status.get("rhfc_candidates")),
        source=status.get("candidate_store_path"),
        source_status="unpromoted_candidate_store" if status.get("candidate_available") else str(status.get("reason") or "no_candidate_store_available"),
        candidate_is_verified=bool(status.get("candidate_is_verified", False)),
    )


def normalize_working_memory_counts(payload: dict[str, Any] | None = None) -> LogicalSphereWorkingMemoryCounts:
    """Normalize optional Working Memory counts.

    The Cloud Brain backend does not own Working Memory session state. When no
    payload is supplied, the summary reports unknown temporary counts instead of
    inventing totals.
    """

    if not payload:
        return LogicalSphereWorkingMemoryCounts(
            working_memory_nodes=None,
            working_memory_relations=None,
            working_memory_fragments=None,
            source=None,
            source_status="unknown_not_implemented",
            temporary=True,
        )
    return LogicalSphereWorkingMemoryCounts(
        working_memory_nodes=_safe_int(payload.get("working_memory_nodes")),
        working_memory_relations=_safe_int(payload.get("working_memory_relations")),
        working_memory_fragments=_safe_int(payload.get("working_memory_fragments")),
        source=payload.get("source"),
        source_status=str(payload.get("source_status") or "provided_temporary_counts"),
        temporary=True,
    )


def normalize_rendered_counts(payload: dict[str, Any] | None = None) -> LogicalSphereRenderedCounts:
    """Normalize optional rendered viewport counts.

    Viewport materialization is UI/render-model state. If the backend caller does
    not provide it, values remain null/unknown so they cannot be mistaken for
    total graph size.
    """

    if not payload:
        return LogicalSphereRenderedCounts(
            rendered_nodes=None,
            rendered_edges=None,
            materialized_nodes=None,
            materialized_edges=None,
            active_chunks=None,
            visible_scale_chunks=None,
            virtualization_enabled=None,
            source=None,
            source_status="unknown_ui_owned",
        )
    return LogicalSphereRenderedCounts(
        rendered_nodes=_safe_int(payload.get("rendered_nodes")),
        rendered_edges=_safe_int(payload.get("rendered_edges")),
        materialized_nodes=_safe_int(payload.get("materialized_nodes")),
        materialized_edges=_safe_int(payload.get("materialized_edges")),
        active_chunks=_safe_int(payload.get("active_chunks")),
        visible_scale_chunks=_safe_int(payload.get("visible_scale_chunks")),
        virtualization_enabled=bool(payload.get("virtualization_enabled")),
        source=payload.get("source"),
        source_status=str(payload.get("source_status") or "provided_viewport_sample"),
    )


def build_logical_sphere_summary(
    *,
    verified_store: str | Path = DEFAULT_VERIFIED_STORE,
    candidate_store_path: str | Path | None = None,
    working_memory_counts: dict[str, Any] | None = None,
    rendered_counts: dict[str, Any] | None = None,
    store_name: str = "verified_store_v0",
) -> LogicalSphereSemanticsSummary:
    """Build a read-only Logical Sphere count semantics summary."""

    return LogicalSphereSemanticsSummary(
        generated_at=_utc_now_iso(),
        store_name=store_name,
        verified=load_verified_counts(verified_store),
        candidate=load_candidate_counts(candidate_store_path),
        working_memory=normalize_working_memory_counts(working_memory_counts),
        rendered=normalize_rendered_counts(rendered_counts),
        explanations={
            "verified_counts_change_only_after_promotion": True,
            "candidate_counts_are_unpromoted_learning": True,
            "rendered_counts_are_view_budget_not_total_graph": True,
            "working_memory_is_temporary": True,
            "local_brain_write_default": False,
        },
        invariants={
            "production_store_mutated": False,
            "local_brain_write": False,
            "candidate_promotion": False,
            "external_llm_used": False,
            "mock_growth": False,
            "real_p2p_used": False,
            "generated_code_executed": False,
        },
    )
