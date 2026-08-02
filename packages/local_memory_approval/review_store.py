from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Iterable

from .models import MemoryApprovalDecision, MemoryApprovalSession, MemoryCandidate, MemoryDecision, utc_now_iso
from .policy import recommend_memory_decision


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEW_STORE = PROJECT_ROOT / "data" / "review" / "local_memory_approval"


def _stable_id(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:16]}"


class MemoryApprovalReviewStore:
    """JSON review metadata store. It never writes Local Brain."""

    def __init__(self, root: Path | str = DEFAULT_REVIEW_STORE) -> None:
        self.root = Path(root)

    def _session_path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    def create_memory_review_session(self, candidates: Iterable[MemoryCandidate]) -> MemoryApprovalSession:
        candidate_list = list(candidates)
        session = MemoryApprovalSession(
            session_id=_stable_id("memory_review", [candidate.candidate_id for candidate in candidate_list]),
            candidates=candidate_list,
            decisions=[],
            status="in_review",
            local_brain_mutated=False,
            production_store_mutated=False,
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_session(session)
        return session

    def add_memory_decision(
        self,
        session_id: str,
        candidate_id: str,
        decision: MemoryDecision,
        *,
        reviewer: str = "user",
        edited_summary: str | None = None,
        notes: str | None = None,
    ) -> MemoryApprovalSession:
        session = self.load_memory_review_session(session_id)
        if candidate_id not in {candidate.candidate_id for candidate in session.candidates}:
            raise KeyError(f"unknown memory candidate: {candidate_id}")
        next_decision = MemoryApprovalDecision(
            decision_id=_stable_id(
                "memory_decision",
                {"session_id": session_id, "candidate_id": candidate_id, "decision": decision, "created_at": utc_now_iso()},
            ),
            candidate_id=candidate_id,
            decision=decision,
            reviewer=reviewer,
            edited_summary=edited_summary,
            notes=notes,
            applied_to_local_brain=False,
        )
        updated = replace(
            session,
            decisions=[*session.decisions, next_decision],
            status="completed" if len(session.decisions) + 1 >= len(session.candidates) else "in_review",
        )
        self._write_session(updated)
        return updated

    def load_memory_review_session(self, session_id: str) -> MemoryApprovalSession:
        payload = json.loads(self._session_path(session_id).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{session_id} is not a JSON object")
        return MemoryApprovalSession.from_dict(payload)

    def summarize_memory_review_session(self, session_id: str) -> dict[str, object]:
        session = self.load_memory_review_session(session_id)
        decision_counts: dict[str, int] = {}
        recommendations: dict[str, int] = {}
        for decision in session.decisions:
            decision_counts[decision.decision] = decision_counts.get(decision.decision, 0) + 1
        for candidate in session.candidates:
            recommended = recommend_memory_decision(candidate)
            recommendations[recommended] = recommendations.get(recommended, 0) + 1
        return {
            "session_id": session.session_id,
            "status": session.status,
            "candidates": len(session.candidates),
            "decisions": len(session.decisions),
            "decision_counts": decision_counts,
            "recommendations": recommendations,
            "local_brain_mutated": False,
            "production_store_mutated": False,
        }

    def _write_session(self, session: MemoryApprovalSession) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._session_path(session.session_id).write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
