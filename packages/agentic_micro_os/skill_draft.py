from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib

from .web_collection_store import WebSourceRecord


@dataclass(frozen=True)
class WebSkillDraft:
    skill_id: str
    name: str
    trigger: str
    procedure_steps: list[str]
    required_capabilities: list[str]
    safety_notes: list[str]
    source_refs: list[str]
    status: str = "draft"
    promotion_required: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def draft_skill_from_sources(goal: str, sources: list[WebSourceRecord]) -> WebSkillDraft | None:
    if not sources:
        return None
    joined_refs = "|".join(source.content_hash for source in sources)
    digest = hashlib.sha256(f"{goal}|{joined_refs}".encode("utf-8")).hexdigest()[:12]
    topic = _compact_topic(goal)
    return WebSkillDraft(
        skill_id=f"web_skill_{digest}",
        name=f"Research follow-up: {topic}",
        trigger=f"When ATANOR needs updated public context about {topic}.",
        procedure_steps=[
            "read only public pages that pass URL safety policy",
            "extract title, excerpt, source hash, and confidence",
            "create Cloud Brain candidate drafts through Brain Access Road",
            "request human approval before promotion",
        ],
        required_capabilities=["browser_read", "cloud_brain_candidate_write_draft", "request_human_approval"],
        safety_notes=[
            "draft only",
            "no private credentialed browsing",
            "no Local Brain write",
            "no production Cloud Brain mutation",
            "no auto commit or push",
        ],
        source_refs=[source.content_hash for source in sources],
    )


def _compact_topic(goal: str) -> str:
    words = [word.strip(".,:;!?()[]{}").lower() for word in goal.split()]
    useful = [word for word in words if len(word) > 3][:6]
    return " ".join(useful) or "public research"
