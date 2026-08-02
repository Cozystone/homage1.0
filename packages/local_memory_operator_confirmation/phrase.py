from __future__ import annotations

import hashlib
import re


def _token(manifest_id: str, write_plan_id: str) -> str:
    payload = f"{manifest_id}|{write_plan_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12].upper()


def generate_required_phrase(manifest_id: str, write_plan_id: str) -> str:
    """Generate a deterministic phrase for preparation-only confirmation."""

    if not manifest_id or not write_plan_id:
        raise ValueError("manifest_id and write_plan_id are required")
    return f"I UNDERSTAND LOCAL BRAIN WRITE PREPARATION { _token(manifest_id, write_plan_id) }"


def normalize_phrase(text: str | None) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def phrase_matches(required: str, typed: str | None) -> bool:
    """Require an exact normalized phrase match; partials and typos fail."""

    required_normalized = normalize_phrase(required)
    typed_normalized = normalize_phrase(typed)
    if not required_normalized or not typed_normalized:
        return False
    return required_normalized == typed_normalized
