from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CodeReuseCandidate:
    classification: str
    source_path: str
    source_commit: str
    license: str
    rationale: str
    modifications_needed: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_code_reuse_plan(source_commit: str, license_name: str = "MIT") -> dict[str, object]:
    candidates = [
        CodeReuseCandidate(
            classification="adapt_rewrite",
            source_path="AGENTS.md",
            source_commit=source_commit,
            license=license_name,
            rationale="Architecture guidance is useful, but ATANOR should rewrite as capability-gated design.",
            modifications_needed=["remove external provider assumptions", "replace model slot with ATANOR model path"],
        ),
        CodeReuseCandidate(
            classification="reject",
            source_path="providers/",
            source_commit=source_commit,
            license=license_name,
            rationale="External LLM/sLLM providers are forbidden in ATANOR core path.",
            modifications_needed=["do not copy into core"],
        ),
        CodeReuseCandidate(
            classification="reject",
            source_path="terminal/shell execution patterns",
            source_commit=source_commit,
            license=license_name,
            rationale="Unrestricted shell is forbidden; use capability-gated sandbox proposals only.",
            modifications_needed=["rewrite behind sandbox wrapper if ever needed"],
        ),
    ]
    return {
        "license_notice_required": True,
        "notice_draft": "Hermes Agent is MIT licensed by Nous Research. No Hermes code is copied in this v0 proof.",
        "candidates": [candidate.to_dict() for candidate in candidates],
    }
