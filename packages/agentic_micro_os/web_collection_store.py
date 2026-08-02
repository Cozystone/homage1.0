from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class WebSourceRecord:
    source_url: str
    title: str
    content_hash: str
    excerpt: str
    collected_at: str
    confidence: float
    summary: str = ""
    claims: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    candidate_status: str = "draft"

    @classmethod
    def from_visible_text(cls, source_url: str, title: str, visible_text: str, confidence: float = 0.62) -> "WebSourceRecord":
        normalized = " ".join(visible_text.split())
        excerpt = normalized[:500] if normalized else "empty public snapshot"
        digest = hashlib.sha256(f"{source_url}\n{title}\n{excerpt}".encode("utf-8")).hexdigest()
        summary = summarize_public_text(excerpt)
        return cls(
            source_url=source_url,
            title=title or source_url,
            content_hash=digest,
            excerpt=excerpt,
            summary=summary,
            claims=extract_claims(excerpt),
            tags=extract_tags(f"{title} {excerpt}"),
            collected_at=utc_now_iso(),
            confidence=max(0.0, min(confidence, 1.0)),
        )


@dataclass(frozen=True)
class CloudBrainCandidateDraft:
    draft_id: str
    source_url: str
    title: str
    content_hash: str
    excerpt: str
    confidence: float
    summary: str = ""
    claims: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    candidate_status: str = "draft"
    production_mutation: bool = False
    approval_required: bool = True


@dataclass(frozen=True)
class ToolUseTrajectory:
    trajectory_id: str
    goal: str
    observations: list[str]
    actions: list[str]
    outcomes: list[str]
    compressed_summary: str
    no_private_raw_data: bool = True


@dataclass
class WebCollectionStore:
    sources: list[WebSourceRecord] = field(default_factory=list)
    candidate_drafts: list[CloudBrainCandidateDraft] = field(default_factory=list)
    trajectories: list[ToolUseTrajectory] = field(default_factory=list)

    def add_source(self, source: WebSourceRecord) -> WebSourceRecord:
        if not any(existing.content_hash == source.content_hash for existing in self.sources):
            self.sources.append(source)
        return source

    def create_candidate_draft(self, source: WebSourceRecord) -> CloudBrainCandidateDraft:
        draft = CloudBrainCandidateDraft(
            draft_id=f"cloud_candidate_{len(self.candidate_drafts)}",
            source_url=source.source_url,
            title=source.title,
            content_hash=source.content_hash,
            excerpt=source.excerpt,
            summary=source.summary,
            claims=source.claims,
            tags=source.tags,
            confidence=source.confidence,
        )
        self.candidate_drafts.append(draft)
        return draft

    def add_trajectory(self, trajectory: ToolUseTrajectory) -> ToolUseTrajectory:
        self.trajectories.append(trajectory)
        return trajectory

    def to_dict(self) -> dict[str, object]:
        return {
            "sources": [asdict(source) for source in self.sources],
            "candidate_drafts": [asdict(draft) for draft in self.candidate_drafts],
            "trajectories": [asdict(trajectory) for trajectory in self.trajectories],
        }


def summarize_public_text(text: str) -> str:
    sentences = [part.strip() for part in text.replace("\n", " ").split(".") if part.strip()]
    return ". ".join(sentences[:2])[:360] or text[:240]


def extract_claims(text: str, max_claims: int = 3) -> list[str]:
    candidates = [part.strip(" -\t\r\n") for part in text.replace(";", ".").split(".")]
    return [part[:220] for part in candidates if len(part.split()) >= 5][:max_claims]


def extract_tags(text: str) -> list[str]:
    lowered = text.lower()
    tags: list[str] = []
    mapping = {
        "fish": "fish",
        "tts": "tts",
        "speech": "speech",
        "splatra": "splatra",
        "particle": "particles",
        "webgpu": "webgpu",
        "webgl": "webgl",
        "compression": "compression",
        "quantization": "quantization",
        "mcp": "mcp",
        "security": "security",
        "agent": "agents",
        "privacy": "privacy",
        "local-first": "local-first",
    }
    for needle, tag in mapping.items():
        if needle in lowered and tag not in tags:
            tags.append(tag)
    return tags[:8] or ["public-web"]
