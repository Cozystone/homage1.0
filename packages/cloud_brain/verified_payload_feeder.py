from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from packages.cgsr.cgsr.ingestion.source_reader import clean_source_text, detect_language
from packages.cgsr.cgsr.ingestion.verification_gate import has_mock_signal


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAYLOAD_DIR = PROJECT_ROOT / "data" / "cloud_brain" / "approved_payloads"
ALLOWED_SOURCE_TYPES = {
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


def utc_now() -> str:
    """Return a UTC timestamp for feeder status payloads."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: str) -> str:
    """Return a deterministic SHA-256 hex digest."""

    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LearningPayload:
    """A provenance-carrying Cloud Brain learning payload.

    This schema is deliberately stricter than old proof/mock growth rows.  It
    may carry public evidence into a candidate store, but it must not represent
    generated answers, eval rows, private memories, or mock acceleration rows.
    """

    payload_id: str
    source_type: str
    source_id: str
    text: str
    normalized_text: str
    language: str
    provenance_hash: str
    source_url_or_path: str
    license_hint: str
    collected_at: str
    is_private: bool = False
    is_generated: bool = False
    is_eval_row: bool = False
    is_mock: bool = False
    quality_flags: list[str] = field(default_factory=list)
    target_store: str = "verified_store_v0_candidate"
    learning_mode: str = "semantic_graph"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable payload."""

        return asdict(self)


@dataclass(frozen=True)
class PayloadDecision:
    """Policy decision for a candidate learning payload."""

    accepted: bool
    reason: str


@dataclass(frozen=True)
class PayloadSourcePolicy:
    """Safety policy for continuous Cloud Brain learning sources."""

    source_allowlist: set[str] = field(default_factory=lambda: set(ALLOWED_SOURCE_TYPES))
    require_provenance: bool = True
    require_quality_gate: bool = True
    allow_private: bool = False
    allow_generated: bool = False
    allow_eval: bool = False
    target_store: str = "verified_store_v0_candidate"

    def decide(self, payload: LearningPayload) -> PayloadDecision:
        """Return whether ``payload`` may enter the bounded learning queue."""

        if payload.source_type not in self.source_allowlist:
            return PayloadDecision(False, "source_type_not_allowed")
        if self.require_provenance and (not payload.source_id or not payload.provenance_hash):
            return PayloadDecision(False, "missing_provenance")
        if not payload.license_hint:
            return PayloadDecision(False, "missing_license")
        if payload.is_private and not self.allow_private:
            return PayloadDecision(False, "private_payload_rejected")
        if payload.is_generated and not self.allow_generated:
            return PayloadDecision(False, "generated_payload_rejected")
        if payload.is_eval_row and not self.allow_eval:
            return PayloadDecision(False, "eval_row_rejected")
        if payload.is_mock:
            return PayloadDecision(False, "mock_payload_rejected")
        if has_mock_signal(payload.text, payload.source_id, payload.source_type):
            return PayloadDecision(False, "mock_payload_rejected")
        if re.search(r"AtanorSeedConcept\d+|\bsector\s+\d+\b", payload.normalized_text, re.IGNORECASE):
            return PayloadDecision(False, "mock_template_signal")
        if self.require_quality_gate and "quality_rejected" in set(payload.quality_flags):
            return PayloadDecision(False, "quality_rejected")
        if payload.target_store == "verified_store_v0" and self.target_store != "verified_store_v0":
            return PayloadDecision(False, "production_store_requires_explicit_promotion")
        return PayloadDecision(True, "accepted")


@dataclass
class FeederRunResult:
    """Bounded feeder result for one discovery pass."""

    mode: str
    state: str
    payloads_seen: int = 0
    payloads_accepted: int = 0
    payloads_rejected: int = 0
    approved_payloads_available: int = 0
    accepted_payloads_total: int = 0
    rejected_payloads_total: int = 0
    last_rejection_reasons: list[str] = field(default_factory=list)
    payloads: list[LearningPayload] = field(default_factory=list)
    local_brain_write: bool = False
    external_llm_used: bool = False
    external_sllm_used: bool = False
    mock_growth: bool = False

    def to_dict(self, *, include_payloads: bool = False) -> dict[str, Any]:
        """Return a public status dictionary."""

        data = asdict(self)
        if not include_payloads:
            data.pop("payloads", None)
        else:
            data["payloads"] = [payload.to_dict() for payload in self.payloads]
        return data


def payload_from_mapping(row: dict[str, Any], *, default_target_store: str = "verified_store_v0_candidate") -> LearningPayload:
    """Normalize an untrusted mapping into a ``LearningPayload``."""

    text = clean_source_text(str(row.get("text") or ""))
    language = str(row.get("language") or "").strip() or detect_language(text)
    source_type = str(row.get("source_type") or "unknown_origin")
    source_id = str(row.get("source_id") or row.get("source_url_or_path") or "")
    provenance_hash = str(row.get("provenance_hash") or stable_hash(f"{source_type}:{source_id}:{text}"))
    payload_id = str(row.get("payload_id") or f"payload_{stable_hash(provenance_hash)[:20]}")
    return LearningPayload(
        payload_id=payload_id,
        source_type=source_type,
        source_id=source_id,
        text=str(row.get("text") or ""),
        normalized_text=text,
        language=language,
        provenance_hash=provenance_hash,
        source_url_or_path=str(row.get("source_url_or_path") or row.get("url") or row.get("path") or ""),
        license_hint=str(row.get("license_hint") or row.get("license") or ""),
        collected_at=str(row.get("collected_at") or utc_now()),
        is_private=bool(row.get("is_private", False)),
        is_generated=bool(row.get("is_generated", False)),
        is_eval_row=bool(row.get("is_eval_row", False)),
        is_mock=bool(row.get("is_mock", False)),
        quality_flags=[str(flag) for flag in row.get("quality_flags") or []],
        target_store=str(row.get("target_store") or default_target_store),
        learning_mode=str(row.get("learning_mode") or "semantic_graph"),
    )


def load_payload_rows(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    """Load JSON/JSONL payload rows from explicit allowlisted files."""

    rows: list[dict[str, Any]] = []
    for item in paths:
        path = Path(item)
        if not path.exists() or not path.is_file():
            continue
        if path.suffix.lower() == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        elif path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                rows.extend(row for row in payload if isinstance(row, dict))
            elif isinstance(payload, dict):
                maybe_rows = payload.get("payloads") or payload.get("rows")
                if isinstance(maybe_rows, list):
                    rows.extend(row for row in maybe_rows if isinstance(row, dict))
                else:
                    rows.append(payload)
    return rows


class VerifiedPayloadFeeder:
    """Discover and policy-filter bounded approved Cloud learning payloads."""

    def __init__(
        self,
        *,
        source_paths: Iterable[str | Path] | None = None,
        source_dir: str | Path = DEFAULT_PAYLOAD_DIR,
        policy: PayloadSourcePolicy | None = None,
        max_payloads_per_tick: int = 25,
        max_payloads_per_run: int = 100,
    ) -> None:
        self.source_paths = [Path(path) for path in source_paths or []]
        self.source_dir = Path(source_dir)
        self.policy = policy or PayloadSourcePolicy()
        self.max_payloads_per_tick = max(1, int(max_payloads_per_tick))
        self.max_payloads_per_run = max(1, int(max_payloads_per_run))

    def _discovery_paths(self) -> list[Path]:
        paths = list(self.source_paths)
        if self.source_dir.exists():
            for pattern in ("*.jsonl", "*.json"):
                # top-level approved payloads...
                paths.extend(sorted(self.source_dir.glob(pattern)))
                # ...plus the web producer's output subdir (web_approved_payload_feeder
                # writes to approved_payloads/web_feeds/). Without this the consumer
                # never sees produced payloads -> perpetual no_approved_payload_source.
                paths.extend(sorted(self.source_dir.glob(f"web_feeds/{pattern}")))
        # never consume rejected payloads (approved_payloads/rejected/).
        return [p for p in paths if "rejected" not in {part.casefold() for part in p.parts}]

    def run_once(self, *, dry_run: bool = False) -> FeederRunResult:
        """Discover a bounded batch without fabricating rows."""

        paths = self._discovery_paths()
        if not paths:
            return FeederRunResult(mode="dry_run" if dry_run else "once", state="no_approved_payload_source")
        rows = load_payload_rows(paths)[: self.max_payloads_per_run]
        accepted: list[LearningPayload] = []
        rejected = 0
        reasons: list[str] = []
        for row in rows:
            payload = payload_from_mapping(row, default_target_store=self.policy.target_store)
            decision = self.policy.decide(payload)
            if decision.accepted and len(accepted) < self.max_payloads_per_tick:
                accepted.append(payload)
            else:
                rejected += 1
                reasons.append(decision.reason if not decision.accepted else "tick_batch_full")
        state = "payloads_available" if accepted else "no_approved_payloads_after_policy"
        return FeederRunResult(
            mode="dry_run" if dry_run else "once",
            state=state,
            payloads_seen=len(rows),
            payloads_accepted=len(accepted),
            payloads_rejected=rejected,
            approved_payloads_available=len(accepted),
            accepted_payloads_total=len(accepted),
            rejected_payloads_total=rejected,
            last_rejection_reasons=reasons[-10:],
            payloads=[] if dry_run else accepted,
        )
