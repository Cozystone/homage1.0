from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
from typing import Any, Iterable

from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult


def stable_id(prefix: str, value: str) -> str:
    """Return a compact deterministic identifier."""

    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


@dataclass(frozen=True)
class SurfaceProjectionCandidate:
    """Generation-facing projection derived from verified Cloud Brain data."""

    projection_id: str
    source_concept_ids: list[str]
    source_relation_ids: list[str]
    evidence_refs: list[str]
    language: str
    canonical_language: str
    construction_family: str
    slots: dict[str, str]
    required_slots: list[str]
    case_role_signature: list[str]
    discourse_role: str
    semantic_constraints: dict[str, Any]
    confidence: float
    quality_flags: list[str]
    safe_for_cgsr: bool
    safe_for_rhfc: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable candidate."""

        return asdict(self)


@dataclass(frozen=True)
class SurfaceGraphProjectionResult:
    """Counts and safety invariants from a projection pass."""

    semantic_payloads_used: int = 0
    surface_candidates_created: int = 0
    accepted_surface_candidates: int = 0
    rejected_surface_candidates: int = 0
    cgsr_candidates_added: int = 0
    rhfc_candidates_added: int = 0
    evidence_preservation: bool = True
    unsupported_claims: int = 0
    false_confident: int = 0
    forgetting_count: int = 0
    candidates: list[SurfaceProjectionCandidate] = field(default_factory=list)

    def to_dict(self, *, include_candidates: bool = False) -> dict[str, Any]:
        """Return a public status payload."""

        data = asdict(self)
        if include_candidates:
            data["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        else:
            data.pop("candidates", None)
        return data


def _family_for(predicate: str, roles: list[dict[str, Any]]) -> str:
    if not predicate:
        return "abstention"
    if any(str(role.get("role")) == "OBJ" for role in roles):
        return "evidence_based_claim"
    return "definition"


def _candidate_from_case_frame(
    frame: dict[str, Any],
    *,
    concepts: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    evidence: dict[str, Any] | None,
    verified_evidence_refs: frozenset[str],
) -> SurfaceProjectionCandidate:
    predicate = str(frame.get("predicate") or "")
    roles = [role for role in frame.get("case_roles") or [] if isinstance(role, dict)]
    slots = {str(role.get("role") or "ARG"): str(role.get("head") or "") for role in roles}
    slots["predicate"] = predicate
    evidence_ref = str((evidence or {}).get("source_hash") or frame.get("source_hash") or "")
    if evidence_ref:
        slots["evidence_ref"] = evidence_ref[:16]
    case_signature = sorted(f"{role.get('role')}:{role.get('marker')}:{role.get('head')}" for role in roles)
    value = f"{frame.get('frame_id')}:{'|'.join(case_signature)}:{evidence_ref}"
    source_concepts = [str(row.get("concept_id")) for row in concepts if row.get("concept_id")]
    source_relations = [str(row.get("relation_id")) for row in relations if row.get("relation_id")]
    evidence_refs = [evidence_ref] if evidence_ref else []
    quality_flags: list[str] = []
    evidence_independently_bound = bool(
        evidence_ref and evidence_ref in verified_evidence_refs
    )
    safe = bool(
        predicate
        and roles
        and evidence_refs
        and evidence_independently_bound
    )
    if not predicate:
        quality_flags.append("missing_predicate")
    if not roles:
        quality_flags.append("missing_case_roles")
    if not evidence_refs:
        quality_flags.append("missing_evidence")
    elif not evidence_independently_bound:
        quality_flags.append("evidence_not_independently_bound")
    return SurfaceProjectionCandidate(
        projection_id=stable_id("spc", value),
        source_concept_ids=source_concepts,
        source_relation_ids=source_relations,
        evidence_refs=evidence_refs,
        language=str(frame.get("language") or "unknown"),
        canonical_language="en",
        construction_family=_family_for(predicate, roles),
        slots=slots,
        required_slots=sorted(slots.keys()),
        case_role_signature=case_signature,
        discourse_role="grounded_claim",
        semantic_constraints={
            "grounded_claims_only": True,
            "requires_evidence": True,
            "source_language": str(frame.get("language") or "unknown"),
        },
        confidence=0.8 if safe else 0.0,
        quality_flags=quality_flags,
        safe_for_cgsr=safe,
        safe_for_rhfc=safe,
    )


def project_decompositions_to_surface(
    decompositions: Iterable[DecompositionResult],
    *,
    verified_evidence_refs: Iterable[str] = (),
) -> SurfaceGraphProjectionResult:
    """Project semantics only when an upstream verifier bound their evidence."""

    candidates: list[SurfaceProjectionCandidate] = []
    rejected = 0
    payloads = 0
    verified_refs = frozenset(
        str(value) for value in verified_evidence_refs if str(value)
    )
    for decomposition in decompositions:
        payloads += 1
        for frame in decomposition.case_frames:
            candidate = _candidate_from_case_frame(
                frame,
                concepts=decomposition.concepts,
                relations=decomposition.relations,
                evidence=decomposition.evidence,
                verified_evidence_refs=verified_refs,
            )
            if candidate.safe_for_cgsr and candidate.safe_for_rhfc:
                candidates.append(candidate)
            else:
                rejected += 1
    return SurfaceGraphProjectionResult(
        semantic_payloads_used=payloads,
        surface_candidates_created=len(candidates) + rejected,
        accepted_surface_candidates=len(candidates),
        rejected_surface_candidates=rejected,
        cgsr_candidates_added=len(candidates),
        rhfc_candidates_added=len(candidates),
        evidence_preservation=all(bool(candidate.evidence_refs) for candidate in candidates),
        unsupported_claims=rejected,
        false_confident=0,
        forgetting_count=0,
        candidates=candidates,
    )
