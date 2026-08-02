from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from dataclasses import replace

from .models import PromotionReviewDecision, PromotionReviewItem, PromotionReviewSession, ReviewDecision, utc_now_iso
from .review_policy import recommend_decision


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVIEW_STORE = PROJECT_ROOT / "data" / "review" / "promotion_review"


def _stable_id(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:16]}"


def _as_report_dict(dry_run_report: Any) -> dict[str, Any]:
    if hasattr(dry_run_report, "to_dict"):
        return dry_run_report.to_dict()
    if isinstance(dry_run_report, dict):
        return dict(dry_run_report)
    raise TypeError("dry_run_report must be a dict or expose to_dict()")


def _items_from_report(report: dict[str, Any]) -> list[PromotionReviewItem]:
    raw_items = report.get("review_items") or report.get("items") or []
    items: list[PromotionReviewItem] = []
    for index, raw in enumerate(raw_items):
        if isinstance(raw, PromotionReviewItem):
            items.append(raw)
            continue
        if not isinstance(raw, dict):
            continue
        item_type = str(raw.get("item_type") or raw.get("kind") or "concept")
        if item_type not in {"concept", "relation", "evidence", "case_frame"}:
            item_type = "concept"
        candidate_id = str(raw.get("candidate_id") or raw.get("item_key") or raw.get("id") or f"candidate_{index}")
        item_id = str(raw.get("item_id") or _stable_id("review_item", {"candidate_id": candidate_id, "index": index}))
        items.append(
            PromotionReviewItem(
                item_id=item_id,
                candidate_id=candidate_id,
                item_type=item_type,  # type: ignore[arg-type]
                summary=str(raw.get("summary") or raw.get("reason") or candidate_id),
                source_refs=[str(ref) for ref in raw.get("source_refs", [])],
                dry_run_effect=str(raw.get("dry_run_effect") or "unknown"),  # type: ignore[arg-type]
                risk_flags=[str(flag) for flag in raw.get("risk_flags", [])],
                quality_score=float(raw.get("quality_score", 0.0)),
                requires_manual_review=True,
            )
        )
    if items:
        return items

    issues = report.get("issues") if isinstance(report.get("issues"), list) else []
    for index, issue in enumerate(issues[:25]):
        if not isinstance(issue, dict):
            continue
        kind = str(issue.get("item_kind") or "concept")
        if kind not in {"concept", "relation", "evidence", "case_frame"}:
            kind = "concept"
        key = str(issue.get("item_key") or f"issue_{index}")
        reason = str(issue.get("reason") or "review_required")
        severity = str(issue.get("severity") or "review")
        score = 0.2 if severity == "blocker" else 0.55
        items.append(
            PromotionReviewItem(
                item_id=_stable_id("review_item", {"kind": kind, "key": key, "reason": reason}),
                candidate_id=key,
                item_type=kind,  # type: ignore[arg-type]
                summary=f"{kind}: {reason}",
                source_refs=[],
                dry_run_effect="reject" if severity == "blocker" else "unknown",
                risk_flags=[reason],
                quality_score=score,
            )
        )
    if items:
        return items

    synthetic_specs = [
        ("concept", "new_verified_nodes", "create"),
        ("concept", "merged_existing_nodes", "merge"),
        ("relation", "new_relations", "create"),
        ("relation", "strengthened_relations", "strengthen"),
        ("evidence", "new_evidence", "create"),
        ("case_frame", "new_case_frames", "create"),
    ]
    for kind, count_key, effect in synthetic_specs:
        count = int(report.get(count_key) or 0)
        if count <= 0:
            continue
        candidate_id = f"{count_key}:{count}"
        items.append(
            PromotionReviewItem(
                item_id=_stable_id("review_item", candidate_id),
                candidate_id=candidate_id,
                item_type=kind,  # type: ignore[arg-type]
                summary=f"{count} candidate {kind} item(s) estimated for {effect}",
                source_refs=[str(report.get("source_run_id") or "dry_run_report")],
                dry_run_effect=effect,  # type: ignore[arg-type]
                risk_flags=[],
                quality_score=0.68,
            )
        )
    return items


class PromotionReviewStore:
    """JSON review metadata store. It never writes candidate or verified stores."""

    def __init__(self, root: Path | str = DEFAULT_REVIEW_STORE) -> None:
        self.root = Path(root)

    def _session_path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    def create_review_session(self, dry_run_report: Any) -> PromotionReviewSession:
        report = _as_report_dict(dry_run_report)
        report_id = str(report.get("report_id") or _stable_id("dry_run_report", report))
        source_run_id = str(report.get("source_run_id") or report.get("source_run_status") or "unknown_candidate_run")
        session = PromotionReviewSession(
            session_id=_stable_id("promotion_review", {"report_id": report_id, "source_run_id": source_run_id}),
            source_run_id=source_run_id,
            dry_run_report_id=report_id,
            verified_store_hash=str(report.get("verified_store_manifest_hash") or report.get("verified_store_hash") or ""),
            candidate_store_hash=str(report.get("candidate_store_manifest_hash") or report.get("candidate_store_hash") or ""),
            items=_items_from_report(report),
            decisions=[],
            status="in_review",
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_session(session)
        return session

    def add_decision(
        self,
        session_id: str,
        item_id: str,
        decision: PromotionReviewDecision | ReviewDecision,
        *,
        reviewer: str = "user",
        notes: str = "",
    ) -> PromotionReviewSession:
        session = self.load_review_session(session_id)
        if item_id not in {item.item_id for item in session.items}:
            raise KeyError(f"unknown review item: {item_id}")
        next_decision = decision if isinstance(decision, PromotionReviewDecision) else PromotionReviewDecision(
            decision_id=_stable_id("review_decision", {"session_id": session_id, "item_id": item_id, "decision": decision, "created_at": utc_now_iso()}),
            item_id=item_id,
            reviewer=reviewer,  # type: ignore[arg-type]
            decision=decision,
            notes=notes,
        )
        updated = replace(
            session,
            decisions=[*session.decisions, next_decision],
            status="completed" if len(session.decisions) + 1 >= len(session.items) else "in_review",
        )
        self._write_session(updated)
        return updated

    def list_review_sessions(self) -> list[PromotionReviewSession]:
        if not self.root.exists():
            return []
        return [self.load_review_session(path.stem) for path in sorted(self.root.glob("*.json"))]

    def load_review_session(self, session_id: str) -> PromotionReviewSession:
        path = self._session_path(session_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{path} is not a JSON object")
        return PromotionReviewSession.from_dict(payload)

    def summarize_review_session(self, session_id: str) -> dict[str, Any]:
        session = self.load_review_session(session_id)
        decision_counts: dict[str, int] = {}
        for decision in session.decisions:
            decision_counts[decision.decision] = decision_counts.get(decision.decision, 0) + 1
        recommendations: dict[str, int] = {}
        for item in session.items:
            recommended = recommend_decision(item)
            recommendations[recommended] = recommendations.get(recommended, 0) + 1
        return {
            "session_id": session.session_id,
            "source_run_id": session.source_run_id,
            "status": session.status,
            "items": len(session.items),
            "decisions": len(session.decisions),
            "decision_counts": decision_counts,
            "recommendations": recommendations,
            "actual_promotion_performed": False,
            "production_store_mutated": False,
            "local_brain_write": False,
            "candidate_store_mutated": False,
            "requires_user_approval": True,
        }

    def _write_session(self, session: PromotionReviewSession) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._session_path(session.session_id).write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
