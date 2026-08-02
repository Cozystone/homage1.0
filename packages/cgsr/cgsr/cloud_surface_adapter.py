from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from packages.cloud_brain.surface_projection import SurfaceProjectionCandidate

from .english.canonical_frames import EnglishConstructionFrame
from .english.rhfc_bridge import EnglishConstructionStore, store_english_frames


@dataclass(frozen=True)
class CloudSurfaceAdapterResult:
    """Result of converting Surface Graph candidates into CGSR/RHFC frames."""

    candidates_seen: int
    frames_added: int
    rejected: int
    rhfc_candidates_added: int
    false_confident: int
    forgetting_count: int
    recall_accuracy: float
    frames: list[EnglishConstructionFrame]
    rejection_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return a compact status dictionary."""

        return {
            "candidates_seen": self.candidates_seen,
            "frames_added": self.frames_added,
            "rejected": self.rejected,
            "rhfc_candidates_added": self.rhfc_candidates_added,
            "false_confident": self.false_confident,
            "forgetting_count": self.forgetting_count,
            "recall_accuracy": self.recall_accuracy,
            "frame_ids": [frame.frame_id for frame in self.frames],
            "rejection_reasons": self.rejection_reasons[-10:],
        }


def candidate_to_english_frame(candidate: SurfaceProjectionCandidate) -> EnglishConstructionFrame:
    """Convert a safe Surface Graph candidate into an English construction frame."""

    if not candidate.safe_for_cgsr:
        raise ValueError("surface candidate is not safe for CGSR")
    if not candidate.evidence_refs:
        raise ValueError("surface candidate lacks evidence refs")
    slots = sorted(set(candidate.required_slots + ["evidence_ref", "uncertainty", "example"]))
    subject_slot = "SUBJ" if "SUBJ" in slots else "TOPIC" if "TOPIC" in slots else None
    if candidate.construction_family == "evidence_based_claim":
        if subject_slot:
            template = f"Based on {{evidence_ref}}, {{{subject_slot}}} has relation {{predicate}}."
            required = [slot for slot in [subject_slot, "predicate", "evidence_ref"] if slot in slots]
        else:
            template = "Based on {evidence_ref}, there is verified evidence for {predicate}."
            required = [slot for slot in ["predicate", "evidence_ref"] if slot in slots]
    elif candidate.construction_family == "definition":
        if subject_slot:
            template = f"{{{subject_slot}}} is associated with {{predicate}}."
            required = [slot for slot in [subject_slot, "predicate"] if slot in slots]
        else:
            template = "There is verified evidence for {predicate}."
            required = [slot for slot in ["predicate"] if slot in slots]
    else:
        template = "I do not have enough verified evidence for {predicate}."
        required = ["predicate"]
    if not required:
        raise ValueError("surface candidate has no usable required slots")
    frame = EnglishConstructionFrame(
        frame_id=f"cloud_surface_{candidate.projection_id}",
        family=candidate.construction_family,
        slots=slots,
        required_slots=required,
        optional_slots=[slot for slot in slots if slot not in required],
        semantic_constraints={
            **candidate.semantic_constraints,
            "evidence_refs": candidate.evidence_refs,
            "surface_projection_id": candidate.projection_id,
        },
        surface_template=template,
        style_tags=["cloud_surface", "canonical_en", candidate.construction_family],
        evidence_required=True,
        abstention_allowed=candidate.construction_family == "abstention",
    )
    frame.validate()
    return frame


def surface_candidates_to_frames(candidates: Iterable[SurfaceProjectionCandidate]) -> CloudSurfaceAdapterResult:
    """Build generation-ready CGSR frames and a bounded RHFC candidate memory."""

    rows = list(candidates)
    frames: list[EnglishConstructionFrame] = []
    reasons: list[str] = []
    for candidate in rows:
        try:
            if not (candidate.safe_for_cgsr and candidate.safe_for_rhfc):
                raise ValueError("candidate_not_safe")
            frames.append(candidate_to_english_frame(candidate))
        except ValueError as exc:
            reasons.append(str(exc))
    recall_accuracy = 1.0
    if frames:
        store: EnglishConstructionStore = store_english_frames(frames, shard_count=4)
        recall = store.exact_recall_accuracy()
        recall_accuracy = float(recall.get("accuracy") or 0.0)
        forgetting = int(recall.get("forgetting_count") or 0)
    else:
        forgetting = 0
    return CloudSurfaceAdapterResult(
        candidates_seen=len(rows),
        frames_added=len(frames),
        rejected=len(rows) - len(frames),
        rhfc_candidates_added=len(frames),
        false_confident=0,
        forgetting_count=forgetting,
        recall_accuracy=recall_accuracy,
        frames=frames,
        rejection_reasons=reasons,
    )
