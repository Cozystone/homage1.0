from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .capabilities import CapabilityKernel
from .models import CapabilityToken
from .splatra_cell import SplatraCosmosCell
from packages.splatra_turbovec.proof import run_emotion_proof, run_orb_proof


@dataclass(frozen=True)
class SplatraEvaluationRequest:
    candidate_id: str = "splatra_candidate_0"
    particle_budget: int = 200_000
    target_fps: int = 60
    include_city_proof: bool = False
    emotion_probe: dict[str, float] = field(default_factory=lambda: {"valence": 0.2, "arousal": 0.6, "audio_energy": 0.0})


@dataclass(frozen=True)
class SplatraEvaluationResult:
    allowed: bool
    candidate_id: str
    status: str
    score: float
    metrics: dict[str, Any]
    decision: str
    proof_only: bool = True
    patch_applied: bool = False
    generated_code_executed: bool = False
    local_brain_write: bool = False
    production_store_mutated: bool = False
    external_llm: bool = False
    external_sllm: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SplatraCosmosEvaluator:
    """Scores SPLATRA candidates while keeping all changes proposal-only."""

    def __init__(self, kernel: CapabilityKernel | None = None, cell: SplatraCosmosCell | None = None) -> None:
        self.kernel = kernel or CapabilityKernel()
        self.cell = cell or SplatraCosmosCell()

    def status(self) -> dict[str, object]:
        return {
            "available": True,
            "proof_only": True,
            "patch_applied": False,
            "generated_code_executed": False,
            "max_generated_particles_proof": self.cell.max_generated_particles_proof,
        }

    def evaluate(self, request: SplatraEvaluationRequest, token: CapabilityToken | None) -> SplatraEvaluationResult:
        decision = self.kernel.decide("splatra_cosmos_evaluate", token)
        if not decision.allowed:
            return SplatraEvaluationResult(False, request.candidate_id, "denied", 0.0, {}, decision.reason)

        orb = run_orb_proof()
        emotion = run_emotion_proof()
        controls = self.cell.map_emotion_to_visual_controls(
            float(request.emotion_probe.get("valence", 0.0)),
            float(request.emotion_probe.get("arousal", 0.5)),
            float(request.emotion_probe.get("audio_energy", 0.0)),
        )
        city: dict[str, Any] | None = self.cell.run_particle_compression_eval()["city"] if request.include_city_proof else None

        compression_ratio = float(orb["compression"]["compression_ratio"])
        position_error = float(orb["error"]["max_position_error"])
        budget_ok = request.particle_budget <= self.cell.max_generated_particles_proof
        fps_ok = request.target_fps >= 24
        compression_score = min(1.0, compression_ratio / 2.0)
        error_score = 1.0 if position_error < 0.004 else 0.0
        budget_score = 1.0 if budget_ok and fps_ok else 0.0
        emotion_score = 1.0 if emotion.get("passed") else 0.0
        score = round((compression_score + error_score + budget_score + emotion_score) / 4.0, 4)
        passed = orb.get("passed") is True and emotion_score == 1.0 and budget_ok and fps_ok
        metrics: dict[str, Any] = {
            "orb_particles": orb["particles"],
            "orb_compression_ratio": compression_ratio,
            "orb_max_position_error": position_error,
            "emotion_controls": controls,
            "emotion_proof_passed": emotion.get("passed"),
            "particle_budget_ok": budget_ok,
            "target_fps_ok": fps_ok,
        }
        if city is not None:
            metrics["city"] = city
        return SplatraEvaluationResult(
            allowed=True,
            candidate_id=request.candidate_id,
            status="evaluated",
            score=score,
            metrics=metrics,
            decision="proposal_review_ready" if passed else "needs_revision",
        )
