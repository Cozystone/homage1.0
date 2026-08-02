from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import time
from typing import Any, Iterable

from packages.cgsr.cgsr.cloud_surface_adapter import surface_candidates_to_frames
from packages.cgsr.cgsr.ingestion.accumulator import VerifiedStore
from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult, decompose_sentence
from packages.cgsr.cgsr.ingestion.source_reader import SourceSentence
from packages.cgsr.cgsr.ingestion.verification_gate import verify_sentence

from .surface_projection import SurfaceGraphProjectionResult, project_decompositions_to_surface
from .verified_payload_feeder import (
    FeederRunResult,
    LearningPayload,
    PayloadSourcePolicy,
    VerifiedPayloadFeeder,
    utc_now,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VERIFIED_STORE = PROJECT_ROOT / "data" / "cloud_brain" / "verified_store_v0"
DEFAULT_CANDIDATE_STORE = PROJECT_ROOT / "data" / "cloud_brain" / "verified_store_v0_candidate"
_CANDIDATE_SOURCE_TYPES = {
    "wikipedia",
    "approved_public_corpus",
    "public_web_feed",
    "local_public_corpus_file",
    "local_public_corpus_shard",
    "wikipedia_dump_shard",
    "public_domain_archive",
    "open_access_paper",
    "graph_hub_verified",
    "manual_public_sentence",
    "verified_store_rebuild",
    "user_provided_allowed",
    "community_social",
}


@dataclass(frozen=True)
class SemanticLearningBatchResult:
    """Counts and invariants from one semantic candidate ingestion batch."""

    payloads_seen: int = 0
    payloads_accepted: int = 0
    payloads_rejected: int = 0
    concepts_added: int = 0
    relations_added: int = 0
    evidence_added: int = 0
    case_frames_added: int = 0
    target_store: str = "verified_store_v0_candidate"
    mock_growth: bool = False
    local_brain_write: bool = False
    eval_rows_used_for_learning: bool = False
    external_llm_used: bool = False
    rejection_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable batch result."""

        return asdict(self)


@dataclass(frozen=True)
class CloudSurfaceLearningResult:
    """One bounded tick of Cloud Brain -> Surface Graph -> CGSR/RHFC learning."""

    active_learning_state: str
    current_learning_phase: str
    last_tick_at: str
    last_tick_duration_ms: float
    feeder: dict[str, Any]
    semantic: SemanticLearningBatchResult
    surface: SurfaceGraphProjectionResult
    cgsr_rhfc: dict[str, Any]
    candidate_ready_for_review: bool
    false_confident: int
    forgetting_count: int
    idle_waiting_seconds: int
    cumulative_learning_seconds: int
    production_store_mutated: bool
    pair_edges_sent: int = 0
    private_data_used_for_cloud_learning: bool = False
    consensus: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a public status payload."""

        return {
            "consensus": self.consensus,
            "active_learning_state": self.active_learning_state,
            "current_learning_phase": self.current_learning_phase,
            "last_tick_at": self.last_tick_at,
            "last_tick_duration_ms": self.last_tick_duration_ms,
            "feeder": self.feeder,
            "semantic": self.semantic.to_dict(),
            "surface": self.surface.to_dict(),
            "cgsr_rhfc": self.cgsr_rhfc,
            "candidate_ready_for_review": self.candidate_ready_for_review,
            "false_confident": self.false_confident,
            "forgetting_count": self.forgetting_count,
            "idle_waiting_seconds": self.idle_waiting_seconds,
            "cumulative_learning_seconds": self.cumulative_learning_seconds,
            "production_store_mutated": self.production_store_mutated,
            "pair_edges_sent": self.pair_edges_sent,
            "private_data_used_for_cloud_learning": self.private_data_used_for_cloud_learning,
            "invariants": {
                "false_confident": self.false_confident,
                "forgetting_count": self.forgetting_count,
                "eval_rows_used_for_learning": self.semantic.eval_rows_used_for_learning,
                "external_llm_used_for_reasoning": self.semantic.external_llm_used,
                "local_brain_write": self.semantic.local_brain_write,
                "mock_growth": self.semantic.mock_growth,
                "pair_edges_sent": self.pair_edges_sent,
                "private_data_used_for_cloud_learning": self.private_data_used_for_cloud_learning,
            },
        }


def source_sentence_from_payload(payload: LearningPayload) -> SourceSentence:
    """Convert a server-selected payload into the existing CGSR schema.

    This function does not independently bind source, license, or provenance.
    Public routers therefore refuse caller-supplied payload objects; direct use
    here is limited to the existing trusted in-process feeder/producer paths.
    """

    return SourceSentence(
        text=payload.normalized_text,
        language=payload.language,
        source_id=payload.source_id,
        source_name=payload.source_type,
        source_type=payload.source_type,
        source_hash=payload.provenance_hash,
        document_id=payload.source_id,
        title=payload.source_id,
        url=payload.source_url_or_path,
        license=payload.license_hint,
        usage_allowed=True,
        collected_at=payload.collected_at,
    )


def _empty_candidate_manifest() -> dict[str, Any]:
    """Return a production-safe empty manifest for candidate-only learning."""

    now = utc_now()
    return {
        "store_id": "cloud_brain_verified_store_v0_candidate",
        "created_at": now,
        "updated_at": now,
        "status": "candidate_initialized",
        "purpose": "review-gated verified Cloud Brain candidate store",
        "mock_acceleration_batches_allowed": False,
        "requires_provenance": True,
        "requires_language_tag": True,
        "requires_dedupe_key": True,
        "requires_verification_status": True,
        "allowed_verification_status": ["pending", "verified", "rejected", "quarantined"],
        "files": {
            "concepts": "concepts.jsonl",
            "relations": "relations.jsonl",
            "evidence": "evidence.jsonl",
            "case_frames": "case_frames.jsonl",
            "dedupe_index": "indexes/dedupe_index.jsonl",
            "source_index": "indexes/source_index.jsonl",
        },
        "counts": {"concepts": 0, "relations": 0, "evidence": 0, "case_frames": 0},
        "honesty": {
            "global_cloud_claim": False,
            "proof_store_only": True,
            "external_llm_used": False,
            "external_sllm_used": False,
            "local_brain_write": False,
            "production_store_mutated": False,
            "eval_rows_used_for_learning": False,
            "mock_growth": False,
        },
    }


def ensure_candidate_store_initialized(root: str | Path) -> None:
    """Create schema/manifest for a review-gated candidate store if absent.

    The production ``verified_store_v0`` manifest is never copied wholesale:
    candidate counts start at zero and only the schema shape is reused. Source
    types are widened only for this candidate path so approved public payloads
    can be reviewed before any production promotion.
    """

    target = Path(root)
    target.mkdir(parents=True, exist_ok=True)
    schema_path = target / "schema.json"
    if not schema_path.exists():
        source_schema_path = DEFAULT_VERIFIED_STORE / "schema.json"
        if source_schema_path.exists():
            schema = json.loads(source_schema_path.read_text(encoding="utf-8"))
        else:
            schema = {
                "version": "verified_cloud_store_v0",
                "provenance": {
                    "required_fields": ["source_id", "source_hash", "source_type", "collected_at", "ingest_run_id"],
                    "allowed_source_types": [],
                    "forbidden_source_types": ["local_semantic_acceleration_batch", "mock_template", "unknown_origin"],
                },
                "verification": {
                    "required_fields": ["status", "checked_at", "method", "rejection_reason"],
                    "allowed_status": ["pending", "verified", "rejected", "quarantined"],
                },
                "concept_required_fields": [
                    "concept_id",
                    "canonical_name",
                    "language",
                    "dedupe_key",
                    "provenance",
                    "verification",
                    "created_at",
                    "updated_at",
                ],
                "relation_required_fields": [
                    "relation_id",
                    "source_concept_id",
                    "relation",
                    "target_concept_id",
                    "language",
                    "dedupe_key",
                    "provenance",
                    "verification",
                    "created_at",
                    "updated_at",
                ],
                "evidence_required_fields": [
                    "source_id",
                    "source_hash",
                    "source_type",
                    "title",
                    "url",
                    "license",
                    "usage_allowed",
                    "collected_at",
                    "verification",
                ],
                "case_frame_required_fields": [
                    "frame_id",
                    "language",
                    "predicate",
                    "case_roles",
                    "canonical_form",
                    "dedupe_key",
                    "source_hash",
                    "verification",
                ],
            }
        provenance = schema.setdefault("provenance", {})
        allowed = set(provenance.get("allowed_source_types") or [])
        provenance["allowed_source_types"] = sorted(allowed | _CANDIDATE_SOURCE_TYPES)
        schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = target / "manifest.json"
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps(_empty_candidate_manifest(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class CloudSurfaceLearningLoop:
    """Bounded safe loop for verified Cloud Brain candidate learning.

    This service is candidate-only.  Production promotion belongs to the
    separately reviewed promotion boundary; neither API callers nor alternate
    direct-payload call sites may turn this ingestion loop into that boundary.
    """

    def __init__(
        self,
        *,
        feeder: VerifiedPayloadFeeder | None = None,
        candidate_store_root: str | Path = DEFAULT_CANDIDATE_STORE,
        promote_to_verified: bool = False,
        update_surface_graph: bool = True,
        update_rhfc_candidate: bool = True,
        require_review_before_production: bool = True,
    ) -> None:
        if promote_to_verified:
            raise ValueError("CloudSurfaceLearningLoop is candidate-only; use the reviewed promotion boundary")
        selected_feeder = feeder or VerifiedPayloadFeeder(policy=PayloadSourcePolicy())
        if selected_feeder.policy.target_store != "verified_store_v0_candidate":
            raise ValueError("CloudSurfaceLearningLoop requires a candidate-only source policy")
        selected_root = Path(candidate_store_root)
        if selected_root.resolve() == DEFAULT_VERIFIED_STORE.resolve():
            raise ValueError("CloudSurfaceLearningLoop cannot target the verified production store")
        self.feeder = selected_feeder
        self.candidate_store_root = selected_root
        self.promote_to_verified = False
        self.update_surface_graph = bool(update_surface_graph)
        self.update_rhfc_candidate = bool(update_rhfc_candidate)
        self.require_review_before_production = bool(require_review_before_production)

    def run_once(
        self,
        *,
        dry_run: bool = False,
        payloads: Iterable[LearningPayload] | None = None,
        max_accepted_per_run: int = 25,
    ) -> CloudSurfaceLearningResult:
        """Run a single bounded tick.

        Production promotion is intentionally unavailable here.  Direct
        payloads cross the feeder's shape/source policy just like discovered
        payloads, but that policy is not a cryptographic source binding. Public
        API adapters must not expose this argument to request data.
        """

        started = time.perf_counter()
        now = utc_now()
        if payloads is None:
            feeder_result = self.feeder.run_once(dry_run=dry_run)
            batch_payloads = feeder_result.payloads
        else:
            rows = list(payloads)[: max(1, int(max_accepted_per_run))]
            accepted_rows: list[LearningPayload] = []
            rejection_reasons: list[str] = []
            for payload in rows:
                decision = self.feeder.policy.decide(payload)
                if decision.accepted:
                    accepted_rows.append(payload)
                else:
                    rejection_reasons.append(decision.reason)
            state = "payloads_available" if accepted_rows else (
                "no_approved_payloads_after_policy" if rows else "no_approved_payload_source"
            )
            feeder_result = FeederRunResult(
                mode="dry_run" if dry_run else "once",
                state=state,
                payloads_seen=len(rows),
                payloads_accepted=len(accepted_rows),
                payloads_rejected=len(rejection_reasons),
                approved_payloads_available=len(accepted_rows),
                accepted_payloads_total=len(accepted_rows),
                rejected_payloads_total=len(rejection_reasons),
                last_rejection_reasons=rejection_reasons[-10:],
                payloads=[] if dry_run else accepted_rows,
            )
            batch_payloads = [] if dry_run else accepted_rows
        if not batch_payloads:
            duration = round((time.perf_counter() - started) * 1000, 3)
            semantic = SemanticLearningBatchResult(
                payloads_seen=feeder_result.payloads_seen,
                payloads_accepted=0,
                payloads_rejected=feeder_result.payloads_rejected,
                rejection_reasons=feeder_result.last_rejection_reasons,
            )
            return CloudSurfaceLearningResult(
                active_learning_state="waiting_for_payloads",
                current_learning_phase=feeder_result.state,
                last_tick_at=now,
                last_tick_duration_ms=duration,
                feeder=feeder_result.to_dict(),
                semantic=semantic,
                surface=SurfaceGraphProjectionResult(),
                cgsr_rhfc={
                    "frames_added": 0,
                    "rhfc_candidates_added": 0,
                    "recall_accuracy": 1.0,
                    "false_confident": 0,
                    "forgetting_count": 0,
                },
                candidate_ready_for_review=False,
                false_confident=0,
                forgetting_count=0,
                idle_waiting_seconds=max(1, int(duration / 1000)),
                cumulative_learning_seconds=0,
                production_store_mutated=False,
            )

        if not self.promote_to_verified:
            ensure_candidate_store_initialized(self.candidate_store_root)
        store = VerifiedStore(self.candidate_store_root)

        # only enter the candidate store once independently re-confirmed. Concepts,
        # evidence, surface graph and frames keep flowing directly as before.
        consensus_gate = os.environ.get("ATANOR_CONSENSUS_GATE", "1") != "0"
        ledger = None
        if consensus_gate:
            from .consensus_ledger import ConsensusLedger

            min_sources = max(1, int(os.environ.get("ATANOR_CONSENSUS_MIN_SOURCES", "2")))
            ledger = ConsensusLedger(self.candidate_store_root / "consensus_ledger", min_sources=min_sources)
        decompositions: list[DecompositionResult] = []
        verified_surface_evidence_refs: set[str] = set()
        rejected = 0
        reasons: list[str] = []
        accepted = 0
        for payload in batch_payloads[: max(1, int(max_accepted_per_run))]:
            sentence = source_sentence_from_payload(payload)
            decision = verify_sentence(sentence, existing_dedupe_keys=store.existing_dedupe_keys())
            if decision.status != "verified":
                rejected += 1
                reasons.append(decision.reason)
                if not dry_run:
                    store.record_rejection(sentence, decision, ingest_run_id=f"cloud_surface_learning_{now}")
                continue
            accepted += 1
            decompositions.append(decompose_sentence(sentence, decision, ingest_run_id=f"cloud_surface_learning_{now}"))
            verified_surface_evidence_refs.add(sentence.source_hash)

        accumulation = None
        consensus_stats: dict[str, Any] | None = None
        if decompositions and not dry_run:
            if ledger is not None:
                # record relations as quarantined evidence, then strip them from the
                # direct write; consensus promotion re-adds the confirmed ones.
                for dec in decompositions:
                    ledger.record_decomposition(dec)
                stripped = [
                    DecompositionResult(concepts=d.concepts, relations=[], case_frames=d.case_frames, evidence=d.evidence)
                    for d in decompositions
                ]
                accumulation = store.accumulate(stripped)
                promotion = ledger.promote_into(store)
                if promotion.promoted:
                    store.update_manifest()
                consensus_stats = {**ledger.stats(), **promotion.to_dict()}
            else:
                accumulation = store.accumulate(decompositions)
        surface = (
            project_decompositions_to_surface(
                decompositions,
                verified_evidence_refs=verified_surface_evidence_refs,
            )
            if self.update_surface_graph
            else SurfaceGraphProjectionResult()
        )
        cgsr = surface_candidates_to_frames(surface.candidates) if self.update_rhfc_candidate else None
        cgsr_status = cgsr.to_dict() if cgsr else {
            "frames_added": 0,
            "rhfc_candidates_added": 0,
            "recall_accuracy": 1.0,
            "false_confident": 0,
            "forgetting_count": 0,
        }
        concepts_added = int(getattr(accumulation, "concepts_added", 0) or 0)
        relations_added = int(getattr(accumulation, "relations_added", 0) or 0)
        if consensus_stats:
            # under the consensus gate, relations enter the store only via promotion
            relations_added += int(consensus_stats.get("promoted") or 0)
        evidence_added = int(getattr(accumulation, "evidence_added", 0) or 0)
        case_frames_added = int(getattr(accumulation, "case_frames_added", 0) or 0)
        semantic = SemanticLearningBatchResult(
            payloads_seen=feeder_result.payloads_seen or len(batch_payloads),
            payloads_accepted=accepted,
            payloads_rejected=rejected + feeder_result.payloads_rejected,
            concepts_added=concepts_added,
            relations_added=relations_added,
            evidence_added=evidence_added,
            case_frames_added=case_frames_added,
            target_store="verified_store_v0" if self.promote_to_verified else "verified_store_v0_candidate",
            rejection_reasons=[*feeder_result.last_rejection_reasons, *reasons][-20:],
        )
        duration = round((time.perf_counter() - started) * 1000, 3)
        active_seconds = max(1, int(duration / 1000)) if accepted else 0
        false_confident = int(cgsr_status.get("false_confident") or 0)
        forgetting_count = int(cgsr_status.get("forgetting_count") or 0)
        return CloudSurfaceLearningResult(
            active_learning_state="learning" if accepted else "waiting_for_payloads",
            current_learning_phase="candidate_ready_for_review" if accepted else "no_accepted_payloads",
            last_tick_at=now,
            last_tick_duration_ms=duration,
            feeder=feeder_result.to_dict(),
            semantic=semantic,
            surface=surface,
            cgsr_rhfc=cgsr_status,
            candidate_ready_for_review=accepted > 0 and false_confident == 0 and forgetting_count == 0,
            false_confident=false_confident,
            forgetting_count=forgetting_count,
            idle_waiting_seconds=0 if accepted else max(1, int(duration / 1000)),
            cumulative_learning_seconds=active_seconds,
            production_store_mutated=self.promote_to_verified and not self.require_review_before_production,
            consensus=consensus_stats,
        )
