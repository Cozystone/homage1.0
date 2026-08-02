"""Append-only accumulator for ``verified_store_v0``."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Iterable

from .decomposer import DecompositionResult
from .korean_text_quality import validate_korean_sentence
from .source_reader import SourceSentence
from .verification_gate import VerificationDecision, has_mock_signal


DEFAULT_STORE_ROOT = Path(__file__).resolve().parents[4] / "data" / "cloud_brain" / "verified_store_v0"


@dataclass
class AccumulationResult:
    """Counts from one append-only accumulation call."""

    concepts_added: int = 0
    concepts_deduped: int = 0
    relations_added: int = 0
    relations_deduped: int = 0
    evidence_added: int = 0
    evidence_deduped: int = 0
    case_frames_added: int = 0
    case_frames_deduped: int = 0
    rejected_recorded: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "concepts_added": self.concepts_added,
            "concepts_deduped": self.concepts_deduped,
            "relations_added": self.relations_added,
            "relations_deduped": self.relations_deduped,
            "evidence_added": self.evidence_added,
            "evidence_deduped": self.evidence_deduped,
            "case_frames_added": self.case_frames_added,
            "case_frames_deduped": self.case_frames_deduped,
            "rejected_recorded": self.rejected_recorded,
            "errors": self.errors,
        }


class VerifiedStore:
    """Schema-checked append-only writer for verified Cloud Brain data."""

    def __init__(self, root: str | Path = DEFAULT_STORE_ROOT) -> None:
        self.root = Path(root)
        self.paths = {
            "concepts": self.root / "concepts.jsonl",
            "relations": self.root / "relations.jsonl",
            "evidence": self.root / "evidence.jsonl",
            "case_frames": self.root / "case_frames.jsonl",
            "dedupe_index": self.root / "indexes" / "dedupe_index.jsonl",
            "source_index": self.root / "indexes" / "source_index.jsonl",
            "rejected": self.root / "quarantine" / "rejected.jsonl",
            "manifest": self.root / "manifest.json",
            "schema": self.root / "schema.json",
        }
        self._ensure_files()
        self.schema = json.loads(self.paths["schema"].read_text(encoding="utf-8"))
        self.dedupe_keys = self._load_key_set(self.paths["dedupe_index"], "dedupe_key")
        self.source_hashes = self._load_key_set(self.paths["source_index"], "source_hash")

    def _ensure_files(self) -> None:
        for key, path in self.paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if key in {"manifest", "schema"}:
                continue
            if not path.exists():
                path.write_text("", encoding="utf-8")

    @staticmethod
    def _load_key_set(path: Path, field: str) -> set[str]:
        rows: set[str] = set()
        if not path.exists():
            return rows
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line).get(field)
            except json.JSONDecodeError:
                continue
            if value:
                rows.add(str(value))
        return rows

    @staticmethod
    def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def existing_dedupe_keys(self) -> set[str]:
        """Return all known dedupe keys."""

        return set(self.dedupe_keys)

    def _validate_common(self, row: dict[str, Any], required: Iterable[str]) -> None:
        def _is_missing(value: Any) -> bool:
            return value is None or value == ""

        missing = [field for field in required if field not in row or _is_missing(row.get(field))]
        if missing:
            raise ValueError(f"missing required fields: {missing}")
        if has_mock_signal(json.dumps(row, ensure_ascii=False)):
            raise ValueError("mock template signal rejected by verified store")
        if str(row.get("language") or "") == "ko":
            fields: list[tuple[str, bool]] = []
            for field in ("predicate", "text"):
                if row.get(field):
                    fields.append((str(row.get(field)), True))
            for field in ("canonical_name", "canonical_form"):
                if row.get(field):
                    fields.append((str(row.get(field)), False))
            for role in row.get("case_roles") or []:
                if isinstance(role, dict):
                    fields.append((str(role.get("marker") or ""), True))
                    fields.append((str(role.get("head") or ""), False))
            for field_value, expect_korean in fields:
                quality = validate_korean_sentence(field_value, expect_korean=expect_korean)
                if not quality.is_valid:
                    raise ValueError(f"korean text quality rejected: {quality.issues[0]}")
        if "source_type" in row:
            source_type = str(row.get("source_type", ""))
            forbidden = set(self.schema["provenance"]["forbidden_source_types"])
            allowed = set(self.schema["provenance"]["allowed_source_types"])
            if source_type in forbidden or source_type not in allowed:
                raise ValueError(f"invalid source_type: {source_type}")
        provenance = row.get("provenance")
        if provenance is not None:
            source_type = str(provenance.get("source_type", ""))
            forbidden = set(self.schema["provenance"]["forbidden_source_types"])
            allowed = set(self.schema["provenance"]["allowed_source_types"])
            if source_type in forbidden or source_type not in allowed:
                raise ValueError(f"invalid provenance source_type: {source_type}")
            for field in self.schema["provenance"]["required_fields"]:
                if provenance.get(field) in {None, ""}:
                    raise ValueError(f"missing provenance.{field}")
        verification = row.get("verification")
        if verification is not None:
            if verification.get("status") not in set(self.schema["verification"]["allowed_status"]):
                raise ValueError("invalid verification status")
            for field in self.schema["verification"]["required_fields"]:
                if field not in verification:
                    raise ValueError(f"missing verification.{field}")
        dedupe_key = str(row.get("dedupe_key", ""))
        if re.search(r"AtanorSeedConcept\d+|\bsector\s+\d+\b", dedupe_key, re.IGNORECASE):
            raise ValueError("forbidden numeric template dedupe key")

    def _append_unique(self, collection: str, row: dict[str, Any], result: AccumulationResult) -> bool:
        dedupe_key = str(row.get("dedupe_key") or row.get("source_hash") or "")
        if not dedupe_key:
            result.errors.append(f"{collection}: missing dedupe/source key")
            return False
        if collection == "evidence":
            if dedupe_key in self.source_hashes:
                result.evidence_deduped += 1
                return False
            self.source_hashes.add(dedupe_key)
            self._append_jsonl(self.paths["source_index"], {"source_hash": dedupe_key, "indexed_at": utc_now()})
            self._append_jsonl(self.paths["evidence"], row)
            result.evidence_added += 1
            return True
        if dedupe_key in self.dedupe_keys:
            setattr(result, f"{collection}_deduped", getattr(result, f"{collection}_deduped") + 1)
            return False
        self.dedupe_keys.add(dedupe_key)
        self._append_jsonl(self.paths["dedupe_index"], {"dedupe_key": dedupe_key, "collection": collection, "indexed_at": utc_now()})
        self._append_jsonl(self.paths[collection], row)
        setattr(result, f"{collection}_added", getattr(result, f"{collection}_added") + 1)
        return True

    def record_rejection(self, sentence: SourceSentence, decision: VerificationDecision, *, ingest_run_id: str) -> None:
        """Record a rejected sentence in quarantine for observability."""

        row = {
            "text": sentence.text,
            "language": sentence.language,
            "dedupe_key": decision.dedupe_key,
            "reason": decision.reason,
            "verification": decision.to_verification(),
            "provenance": {**sentence.provenance, "ingest_run_id": ingest_run_id},
        }
        self._append_jsonl(self.paths["rejected"], row)

    def accumulate(self, decompositions: Iterable[DecompositionResult], update_manifest: bool = True) -> AccumulationResult:
        """Append schema-valid decomposition rows and update manifest counts.

        ``update_manifest`` defaults to True so every existing caller is unchanged.
        The sharded contributed store passes False to skip the per-batch manifest
        recount (O(store size)) on the peer-merge hot path and flushes on demand."""

        result = AccumulationResult()
        for decomposition in decompositions:
            if decomposition.evidence:
                try:
                    self._validate_common(decomposition.evidence, self.schema["evidence_required_fields"])
                    evidence_row = dict(decomposition.evidence)
                    evidence_row["dedupe_key"] = evidence_row["source_hash"]
                    self._append_unique("evidence", evidence_row, result)
                except ValueError as exc:
                    result.errors.append(f"evidence: {exc}")
            for row in decomposition.concepts:
                try:
                    self._validate_common(row, self.schema["concept_required_fields"])
                    self._append_unique("concepts", row, result)
                except ValueError as exc:
                    result.errors.append(f"concept: {exc}")
            for row in decomposition.relations:
                try:
                    self._validate_common(row, self.schema["relation_required_fields"])
                    self._append_unique("relations", row, result)
                except ValueError as exc:
                    result.errors.append(f"relation: {exc}")
            for row in decomposition.case_frames:
                try:
                    self._validate_common(row, self.schema["case_frame_required_fields"])
                    self._append_unique("case_frames", row, result)
                except ValueError as exc:
                    result.errors.append(f"case_frame: {exc}")
        if update_manifest:
            self.update_manifest()
        return result

    def update_manifest(self) -> None:
        """Refresh manifest counts from append-only files."""

        manifest = json.loads(self.paths["manifest"].read_text(encoding="utf-8"))
        counts = {
            key: sum(1 for line in self.paths[key].read_text(encoding="utf-8").splitlines() if line.strip())
            for key in ("concepts", "relations", "evidence", "case_frames")
        }
        manifest["counts"] = counts
        manifest["status"] = "verified_ingestion_ready" if any(counts.values()) else manifest.get("status", "empty_initialized")
        manifest["updated_at"] = utc_now()
        manifest["honesty"]["external_llm_used"] = False
        manifest["honesty"]["external_sllm_used"] = False
        self.paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def sample_case_frame_candidates(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """Return RHFC-bridge-compatible candidates from stored case frames."""

        candidates: list[dict[str, Any]] = []
        for line in self.paths["case_frames"].read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            canonical = str(row.get("canonical_form") or "")
            frame_id = str(row.get("frame_id") or "")
            candidates.append(
                {
                    "family_id": frame_id,
                    "destination": "rhfc_candidate",
                    "priority_score": 80.0,
                    "reason": "verified_store_v0_case_frame",
                    "selection_source": "verified_cloud_ingestion",
                    "used_evaluation_cases": False,
                    "row": {
                        "family_id": frame_id,
                        "classification": "verified_case_frame",
                        "canonical_form": canonical,
                        "member_count": 1,
                        "reduction_contribution": 0,
                        "fixed_token_count": len(canonical.split()),
                        "surface_diversity": 1.0,
                        "sample_surfaces": [canonical],
                        "sample_examples": [row.get("provenance", {}).get("source_id", "")],
                    },
                }
            )
            if len(candidates) >= limit:
                break
        return candidates


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
