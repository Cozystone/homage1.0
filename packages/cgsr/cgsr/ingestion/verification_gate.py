"""Deterministic verification gate for licensed raw sentences.

This gate does not claim to prove factual truth.  Without external LLMs or
multi-source corroboration, ATANOR can only verify that a sentence is licensed,
traceable, structurally usable, non-mock, and not a duplicate.  Cross-source
truth verification is a later pipeline stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Iterable

from .korean_text_quality import HANGUL_RE, normalize_korean_text, validate_korean_sentence
from .source_reader import SourceSentence, clean_source_text, stable_hash


MOCK_PATTERNS = [
    re.compile(r"local_semantic_acceleration_batch", re.IGNORECASE),
    re.compile(r"mock_template", re.IGNORECASE),
    re.compile(r"AtanorSeedConcept\d+", re.IGNORECASE),
    re.compile(r"\bsector\s+\d+\b", re.IGNORECASE),
]
ALLOWED_SOURCE_TYPES = {
    "wikipedia",
    "approved_public_corpus",
    "public_web_feed",
    "local_public_corpus_file",
    "local_public_corpus_shard",
    "wikipedia_dump_shard",
    "public_domain_archive",
    "open_access_paper",
    "user_provided_allowed",
    "manual_public_sentence",
    "graph_hub_verified",
    "verified_store_rebuild",
    "local_proof_seed",
    "community_social",
}
FORBIDDEN_SOURCE_TYPES = {"local_semantic_acceleration_batch", "mock_template", "unknown_origin"}
ENGLISH_FACT_RE = re.compile(
    r"\b("
    r"is|are|was|were|has|have|had|uses|used|provides|supports|manages|contains|includes|"
    r"refers|describes|represents|enables|allows|requires|consists|became|becomes|means|"
    r"defines|connects|stores|records|tracks|verifies|validates"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VerificationDecision:
    """Sentence-level verification decision and reason."""

    status: str
    reason: str
    dedupe_key: str
    checked_at: str
    method: str = "deterministic_provenance_structure_dedupe_v0"

    def to_verification(self) -> dict[str, str]:
        """Return the schema-level verification block."""

        return {
            "status": self.status,
            "checked_at": self.checked_at,
            "method": self.method,
            "rejection_reason": "" if self.status == "verified" else self.reason,
        }


def checked_now() -> str:
    """Return a UTC timestamp for verification checks."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_for_dedupe(text: str) -> str:
    """Normalize sentence text for source-independent dedupe."""

    value = normalize_korean_text(clean_source_text(text)).casefold()
    value = re.sub(r"[^\w가-힣]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def sentence_dedupe_key(text: str, language: str) -> str:
    """Return a deterministic sentence dedupe key."""

    return stable_hash(f"sentence:{language}:{normalize_for_dedupe(text)}", prefix="dedupe:")


def has_mock_signal(*values: object) -> bool:
    """Return whether any value contains forbidden mock/template signals."""

    joined = " ".join(str(value or "") for value in values)
    return any(pattern.search(joined) for pattern in MOCK_PATTERNS)


def _is_english_fact_statement(text: str) -> bool:
    """Return whether English text is structurally usable as evidence.

    This is not truth verification. It only rejects fragments, headings, and
    list-like residue while allowing licensed English public corpus sentences
    into the candidate-only learning path without using an external model.
    """

    if not re.search(r"[A-Za-z]", text):
        return False
    if not re.search(r"[.!?]$", text.strip()):
        return False
    alpha_ratio = len(re.findall(r"[A-Za-z]", text)) / max(1, len(text))
    if alpha_ratio < 0.55:
        return False
    return bool(ENGLISH_FACT_RE.search(text))


def verify_sentence(
    sentence: SourceSentence,
    *,
    existing_dedupe_keys: Iterable[str] | None = None,
) -> VerificationDecision:
    """Verify whether a source sentence may enter decomposition."""

    existing = set(existing_dedupe_keys or [])
    dedupe_key = sentence_dedupe_key(sentence.text, sentence.language)
    checked_at = checked_now()
    if sentence.source_type in FORBIDDEN_SOURCE_TYPES:
        return VerificationDecision("rejected", "forbidden_source_type", dedupe_key, checked_at)
    if sentence.source_type not in ALLOWED_SOURCE_TYPES:
        return VerificationDecision("rejected", "unsupported_source_type", dedupe_key, checked_at)
    if not sentence.license or not sentence.usage_allowed:
        return VerificationDecision("rejected", "missing_or_disallowed_license", dedupe_key, checked_at)
    if not sentence.source_id or not sentence.source_hash:
        return VerificationDecision("rejected", "incomplete_provenance", dedupe_key, checked_at)
    if has_mock_signal(sentence.text, sentence.source_id, sentence.source_name, sentence.source_type):
        return VerificationDecision("rejected", "mock_template_signal", dedupe_key, checked_at)
    if dedupe_key in existing:
        return VerificationDecision("rejected", "duplicate_sentence", dedupe_key, checked_at)
    text = clean_source_text(sentence.text)
    if sentence.language == "ko":
        quality = validate_korean_sentence(text, expect_korean=True)
        if not quality.is_valid:
            return VerificationDecision("rejected", f"korean_text_quality:{quality.issues[0]}", dedupe_key, checked_at)
    if sentence.language == "ko" and not HANGUL_RE.search(text):
        return VerificationDecision("rejected", "language_tag_text_mismatch", dedupe_key, checked_at)
    if len(text) < 12:
        return VerificationDecision("rejected", "too_short_fragment", dedupe_key, checked_at)
    if len(text) > 260:
        return VerificationDecision("rejected", "too_long_for_small_stage", dedupe_key, checked_at)
    symbol_ratio = len(re.findall(r"[^0-9A-Za-z가-힣\s.,!?]", text)) / max(1, len(text))
    digit_ratio = len(re.findall(r"\d", text)) / max(1, len(text))
    if symbol_ratio > 0.18:
        return VerificationDecision("rejected", "markup_or_symbol_noise", dedupe_key, checked_at)
    if digit_ratio > 0.35:
        return VerificationDecision("rejected", "numeric_heavy_fragment", dedupe_key, checked_at)
    if sentence.language == "en" and not _is_english_fact_statement(text):
        return VerificationDecision("rejected", "not_fact_statement_shape", dedupe_key, checked_at)
    if sentence.language != "en" and not re.search(r"[가-힣].*(다|요|죠|함|됨|한다|했다|된다|있다|없다)", text):
        return VerificationDecision("rejected", "not_fact_statement_shape", dedupe_key, checked_at)
    return VerificationDecision("verified", "verified", dedupe_key, checked_at)
