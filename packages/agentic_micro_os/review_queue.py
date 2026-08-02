from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Literal


ReviewItemType = Literal["cloud_candidate", "skill_draft", "source_summary", "splatra_patch", "tool_trajectory", "construction_candidate"]
ReviewStatus = Literal["pending", "approved", "rejected", "deferred", "needs_more_evidence"]
ApprovedFor = Literal["draft_only", "candidate_queue", "skill_registry_draft", "promotion_request"]

INVARIANTS = {
    "external_llm": False,
    "external_sllm": False,
    "local_brain_write": False,
    "production_store_mutated": False,
    "candidate_promotion": False,
    "skill_auto_promoted": False,
    "auto_commit": False,
    "auto_push": False,
    "human_approval_required": True,
    "proof_only": True,
}

FORBIDDEN_MUTATION_TERMS = (
    "local_brain_direct_write",
    "local brain write",
    "production_store_mutated",
    "production cloud brain",
    "production write",
    "candidate promotion",
    "auto promote",
    "auto-promotion",
    "auto commit",
    "auto push",
    "raw_private_memory",
    "api_key",
    "token",
    "secret",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReviewItem:
    item_id: str
    item_type: ReviewItemType
    title: str
    summary: str
    source_refs: list[str]
    content_hash: str
    risk_level: str
    novelty_score: float
    usefulness_score: float
    duplicate_score: float
    confidence: float
    status: ReviewStatus = "pending"
    created_by_loop_id: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    review_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewDecision:
    item_id: str
    decision: ReviewStatus
    reviewer: str
    reason: str
    approved_for: ApprovedFor = "draft_only"
    mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewQueue:
    items: dict[str, ReviewItem] = field(default_factory=dict)
    decisions: list[ReviewDecision] = field(default_factory=list)

    def import_payload(self, item_type: ReviewItemType, payload: Any, created_by_loop_id: str = "") -> ReviewItem:
        normalized = _normalize_payload(payload)
        title = _title_for(item_type, normalized)
        summary = _summary_for(item_type, normalized)
        source_refs = _source_refs_for(normalized)
        content_hash = str(normalized.get("content_hash") or _hash_payload(item_type, title, summary, source_refs))
        item_id = f"{item_type}_{content_hash[:16]}"
        duplicate_score = self._duplicate_score(item_id, title, content_hash)
        confidence = _confidence_for(normalized, source_refs, summary)
        risk_level = _risk_level_for(item_type, normalized, title, summary, source_refs, confidence)
        item = ReviewItem(
            item_id=item_id,
            item_type=item_type,
            title=title,
            summary=summary,
            source_refs=source_refs,
            content_hash=content_hash,
            risk_level=risk_level,
            novelty_score=_bounded(1.0 - duplicate_score),
            usefulness_score=_usefulness_for(item_type, normalized, summary, source_refs),
            duplicate_score=duplicate_score,
            confidence=confidence,
            created_by_loop_id=created_by_loop_id or str(normalized.get("created_by_loop_id") or ""),
        )
        existing = self.items.get(item_id)
        if existing:
            existing.duplicate_score = max(existing.duplicate_score, duplicate_score)
            existing.novelty_score = min(existing.novelty_score, item.novelty_score)
            if "duplicate import observed" not in existing.review_notes:
                existing.review_notes.append("duplicate import observed")
            return existing
        self.items[item_id] = item
        return item

    def import_web_run(self, run_payload: dict[str, Any]) -> list[ReviewItem]:
        loop_id = str(run_payload.get("run_id") or "")
        imported: list[ReviewItem] = []
        for draft in _list(run_payload.get("candidate_drafts")):
            imported.append(self.import_payload("cloud_candidate", draft, loop_id))
        for draft in _list(run_payload.get("skill_drafts")):
            imported.append(self.import_payload("skill_draft", draft, loop_id))
        for source in _list(run_payload.get("sources")):
            imported.append(self.import_payload("source_summary", source, loop_id))
        trajectory = run_payload.get("trajectory")
        if isinstance(trajectory, dict) and trajectory:
            imported.append(self.import_payload("tool_trajectory", trajectory, loop_id))
        return imported

    def list_items(
        self,
        item_type: str | None = None,
        risk_level: str | None = None,
        status: str | None = None,
    ) -> list[ReviewItem]:
        items = list(self.items.values())
        if item_type:
            items = [item for item in items if item.item_type == item_type]
        if risk_level:
            items = [item for item in items if item.risk_level == risk_level]
        if status:
            items = [item for item in items if item.status == status]
        return sorted(items, key=lambda item: (item.status != "pending", item.risk_level, item.created_at, item.item_id))

    def pending(self) -> list[ReviewItem]:
        return self.list_items(status="pending")

    def get(self, item_id: str) -> ReviewItem | None:
        return self.items.get(item_id)

    def decide(
        self,
        item_id: str,
        decision: ReviewStatus,
        reviewer: str,
        reason: str,
        approved_for: ApprovedFor = "draft_only",
    ) -> ReviewDecision:
        if decision == "pending":
            raise ValueError("review decision must change the item out of pending")
        item = self.items[item_id]
        if decision == "approved" and _is_forbidden_mutation_item(item):
            item.status = "needs_more_evidence"
            item.review_notes.append("approval blocked: forbidden mutation or private payload signal")
            safe_decision = ReviewDecision(item_id, "needs_more_evidence", reviewer, reason, "draft_only", False)
            self.decisions.append(safe_decision)
            return safe_decision
        item.status = decision
        if reason:
            item.review_notes.append(reason)
        review_decision = ReviewDecision(item_id, decision, reviewer, reason, approved_for, False)
        self.decisions.append(review_decision)
        return review_decision

    def status(self) -> dict[str, Any]:
        items = list(self.items.values())
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        high_risk = 0
        duplicate_warnings = 0
        for item in items:
            by_status[item.status] = by_status.get(item.status, 0) + 1
            by_type[item.item_type] = by_type.get(item.item_type, 0) + 1
            if item.risk_level in {"high", "critical"}:
                high_risk += 1
            if item.duplicate_score >= 0.5:
                duplicate_warnings += 1
        return {
            **INVARIANTS,
            "review_queue_available": True,
            "items_total": len(items),
            "pending": by_status.get("pending", 0),
            "approved": by_status.get("approved", 0),
            "rejected": by_status.get("rejected", 0),
            "deferred": by_status.get("deferred", 0),
            "needs_more_evidence": by_status.get("needs_more_evidence", 0),
            "by_type": by_type,
            "high_risk": high_risk,
            "duplicate_warnings": duplicate_warnings,
            "decisions": len(self.decisions),
        }

    def export_review_report(self) -> dict[str, Any]:
        return {
            "status": self.status(),
            "items": [item.to_dict() for item in self.list_items()],
            "decisions": [decision.to_dict() for decision in self.decisions],
            "invariants": INVARIANTS.copy(),
        }

    # ----- persistence (durable web cumulative learning) -------------------------

    def to_state(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items.values()],
            "decisions": [decision.to_dict() for decision in self.decisions],
        }

    def save(self, path: Path | str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic-ish write: temp then replace, so a crash mid-write can't corrupt.
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_state(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)

    @classmethod
    def load(cls, path: Path | str) -> "ReviewQueue":
        queue = cls()
        target = Path(path)
        if not target.exists():
            return queue
        try:
            state = json.loads(target.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - corrupt artifact → start empty
            return queue
        for raw in state.get("items", []) or []:
            if not isinstance(raw, dict) or not raw.get("item_id"):
                continue
            fields = {key: raw.get(key) for key in ReviewItem.__dataclass_fields__ if key in raw}
            try:
                item = ReviewItem(**fields)
            except TypeError:  # pragma: no cover - schema drift tolerance
                continue
            queue.items[item.item_id] = item
        for raw in state.get("decisions", []) or []:
            if not isinstance(raw, dict):
                continue
            fields = {key: raw.get(key) for key in ReviewDecision.__dataclass_fields__ if key in raw}
            try:
                queue.decisions.append(ReviewDecision(**fields))
            except TypeError:  # pragma: no cover
                continue
        return queue

    def _duplicate_score(self, item_id: str, title: str, content_hash: str) -> float:
        if item_id in self.items:
            return 1.0
        title_tokens = set(_tokens(title))
        if not title_tokens:
            return 0.0
        score = 0.0
        for existing in self.items.values():
            if existing.content_hash == content_hash:
                score = max(score, 1.0)
            existing_tokens = set(_tokens(existing.title))
            if existing_tokens:
                overlap = len(title_tokens & existing_tokens) / max(len(title_tokens | existing_tokens), 1)
                score = max(score, overlap)
        return _bounded(score)


def _normalize_payload(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    if is_dataclass(payload):
        return asdict(payload)
    to_dict = getattr(payload, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, dict):
            return converted
    return {"value": str(payload)}


def _title_for(item_type: ReviewItemType, payload: dict[str, Any]) -> str:
    return str(
        payload.get("title")
        or payload.get("name")
        or payload.get("trajectory_id")
        or payload.get("candidate_id")
        or payload.get("draft_id")
        or item_type.replace("_", " ").title()
    )[:160]


def _summary_for(item_type: ReviewItemType, payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or payload.get("compressed_summary") or payload.get("excerpt") or payload.get("trigger") or ""
    if not summary and payload.get("claims"):
        summary = "; ".join(str(claim) for claim in _list(payload.get("claims"))[:3])
    if not summary and payload.get("procedure_steps"):
        summary = "; ".join(str(step) for step in _list(payload.get("procedure_steps"))[:3])
    return str(summary or item_type.replace("_", " "))[:800]


def _source_refs_for(payload: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("source_refs", "source_url", "content_hash"):
        value = payload.get(key)
        if isinstance(value, list):
            refs.extend(str(item) for item in value if item)
        elif value:
            refs.append(str(value))
    return list(dict.fromkeys(refs))[:12]


def _hash_payload(item_type: str, title: str, summary: str, source_refs: list[str]) -> str:
    joined = "\n".join([item_type, title, summary, *source_refs])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _usefulness_for(item_type: ReviewItemType, payload: dict[str, Any], summary: str, source_refs: list[str]) -> float:
    score = 0.15
    if len(summary.split()) >= 8:
        score += 0.25
    if source_refs:
        score += 0.2
    if payload.get("tags"):
        score += 0.15
    if payload.get("claims") or payload.get("procedure_steps"):
        score += 0.15
    if item_type in {"cloud_candidate", "skill_draft", "tool_trajectory", "construction_candidate"}:
        score += 0.1
    return _bounded(score)


def _confidence_for(payload: dict[str, Any], source_refs: list[str], summary: str) -> float:
    raw = payload.get("confidence")
    try:
        base = float(raw) if raw is not None else 0.35
    except (TypeError, ValueError):
        base = 0.35
    if source_refs:
        base += min(len(source_refs), 3) * 0.08
    if len(summary.split()) >= 8:
        base += 0.1
    if _contains_private_or_mutating_signal(payload):
        base -= 0.35
    return _bounded(base)


def _risk_level_for(
    item_type: ReviewItemType,
    payload: dict[str, Any],
    title: str,
    summary: str,
    source_refs: list[str],
    confidence: float,
) -> str:
    text = " ".join([item_type, title, summary, " ".join(source_refs), str(payload)]).lower()
    if any(term in text for term in FORBIDDEN_MUTATION_TERMS):
        return "critical"
    if not source_refs:
        return "high"
    if "unknown" in text or confidence < 0.35:
        return "medium"
    return "low"


def _contains_private_or_mutating_signal(payload: dict[str, Any]) -> bool:
    text = str(payload).lower()
    return any(term in text for term in FORBIDDEN_MUTATION_TERMS)


def _is_forbidden_mutation_item(item: ReviewItem) -> bool:
    text = " ".join([item.title, item.summary, " ".join(item.source_refs), item.risk_level]).lower()
    return item.risk_level == "critical" or any(term in text for term in FORBIDDEN_MUTATION_TERMS)


def _tokens(text: str) -> list[str]:
    return [part.strip(".,:;!?()[]{}").lower() for part in text.split() if len(part.strip(".,:;!?()[]{}")) > 2]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))
