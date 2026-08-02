from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .models import utc_now_iso
from .storage import SURFACE_ROOT, ensure_dirs, write_json


RepairMode = Literal["default", "grounded", "trace", "research"]
ModeScope = Literal["default_only", "trace_only", "research_only", "all"]
RepairAction = Literal["remove", "replace", "rewrite_sentence", "move_to_trace", "soften", "shorten"]
RepairSeverity = Literal["low", "medium", "high"]
RepairSource = Literal["manual", "answer_quality_feedback", "proof"]


@dataclass(slots=True)
class RepairRule:
    rule_id: str
    name: str
    description: str
    trigger_terms: list[str]
    mode_scope: ModeScope
    action: RepairAction
    replacement: str | None = None
    severity: RepairSeverity = "medium"
    enabled: bool = True
    source: RepairSource = "manual"
    created_from_feedback_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RepairResult:
    original_answer: str
    repaired_answer: str
    applied_rules: list[str] = field(default_factory=list)
    moved_to_trace: list[dict[str, Any]] = field(default_factory=list)
    changed: bool = False
    warnings: list[str] = field(default_factory=list)
    built_in_rules_used: list[str] = field(default_factory=list)
    production_rules_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def stable_rule_id(name: str, terms: list[str]) -> str:
    digest = hashlib.sha256(f"{name}:{'|'.join(terms)}".encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"repair_{digest}"


def builtin_repair_rules() -> list[RepairRule]:
    return [
        RepairRule(
            rule_id="remove_internal_route_arrow",
            name="remove_internal_route_arrow",
            description="Move dumped Local/Cloud/Working Memory route arrows into trace in default answers.",
            trigger_terms=["Local Brain ->", "Local Brain →", "Cloud Brain ->", "Cloud Brain →", "Working Memory"],
            mode_scope="default_only",
            action="move_to_trace",
            severity="high",
        ),
        RepairRule(
            rule_id="replace_cloud_brain_user_facing",
            name="replace_cloud_brain_user_facing",
            description="Replace Cloud Brain implementation wording with user-facing public knowledge wording.",
            trigger_terms=["Cloud Brain 문맥", "Cloud Brain context", "Cloud Brain"],
            mode_scope="default_only",
            action="replace",
            replacement="관련 공개 지식",
            severity="high",
        ),
        RepairRule(
            rule_id="replace_local_brain_user_facing",
            name="replace_local_brain_user_facing",
            description="Replace Local Brain implementation wording with user-facing personal context wording.",
            trigger_terms=["Local Brain"],
            mode_scope="default_only",
            action="replace",
            replacement="저장된 개인 맥락",
            severity="medium",
        ),
        RepairRule(
            rule_id="remove_q_cortex_leakage",
            name="remove_q_cortex_leakage",
            description="Move Q-Cortex and objective details into trace.",
            trigger_terms=["Q-Cortex", "QUBO", "objective"],
            mode_scope="default_only",
            action="move_to_trace",
            severity="high",
        ),
        RepairRule(
            rule_id="remove_source_hash_leakage",
            name="remove_source_hash_leakage",
            description="Move source and node identifiers into trace.",
            trigger_terms=["source_hash", "node_id", "semantic_projection_id"],
            mode_scope="default_only",
            action="move_to_trace",
            severity="high",
        ),
        RepairRule(
            rule_id="soften_attach_language",
            name="soften_attach_language",
            description="Replace attach/detach implementation wording with natural reference wording.",
            trigger_terms=["attach", "detach", "부착", "붙이면", "붙여"],
            mode_scope="default_only",
            action="replace",
            replacement="참고하면",
            severity="medium",
        ),
    ]


def rule_from_dict(payload: dict[str, Any]) -> RepairRule:
    terms = [str(item) for item in payload.get("trigger_terms") or []]
    return RepairRule(
        rule_id=str(payload.get("rule_id") or stable_rule_id(str(payload.get("name") or "repair"), terms)),
        name=str(payload.get("name") or "repair_rule"),
        description=str(payload.get("description") or ""),
        trigger_terms=terms,
        mode_scope=str(payload.get("mode_scope") or "default_only"),  # type: ignore[arg-type]
        action=str(payload.get("action") or "move_to_trace"),  # type: ignore[arg-type]
        replacement=payload.get("replacement"),
        severity=str(payload.get("severity") or "medium"),  # type: ignore[arg-type]
        enabled=bool(payload.get("enabled", True)),
        source=str(payload.get("source") or "manual"),  # type: ignore[arg-type]
        created_from_feedback_id=payload.get("created_from_feedback_id"),
    )


def active_rules(rules: list[RepairRule] | list[dict[str, Any]] | None = None) -> list[RepairRule]:
    if rules is None:
        return builtin_repair_rules()
    normalized: list[RepairRule] = []
    for rule in rules:
        normalized.append(rule if isinstance(rule, RepairRule) else rule_from_dict(rule))
    return [rule for rule in normalized if rule.enabled]


def mode_allows_rule(rule: RepairRule, mode: str) -> bool:
    if rule.mode_scope == "all":
        return True
    if rule.mode_scope == "default_only":
        return mode in {"default", "grounded"}
    if rule.mode_scope == "trace_only":
        return mode == "trace"
    if rule.mode_scope == "research_only":
        return mode == "research"
    return False


def sentence_chunks(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?。])\s+|(?<=[요다까]\.)(?=\S)", text)
    return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]


def strip_empty_sentences(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[,;:\-\s]+", "", text).strip()
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = re.sub(r"^(에 따르면|according to|says|states)\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def persist_repair_run(result: RepairResult, *, run_id: str | None = None) -> Path:
    ensure_dirs()
    name = run_id or f"repair_run_{hashlib.sha256((result.original_answer + utc_now_iso()).encode('utf-8')).hexdigest()[:16]}"
    path = SURFACE_ROOT / "repair_runs" / f"{name}.json"
    write_json(path, result.to_dict())
    return path
