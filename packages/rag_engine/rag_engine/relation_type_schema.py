"""Relation-type schema loader (4D BLOCKER #1 — functional declaration as DATA).

Replaces the hand-coded ``FUNCTIONAL_RELATIONS`` constant in ``self_correction.py``
with a versioned, provenance-carrying data sidecar
(``data/ontology/relation_type_schema.jsonl``).

It declares ONTOLOGICAL PROPERTIES OF RELATION TYPES (e.g. "capital_of is
functional — one value at a time"), never specific subject→answer mappings.
Instance/answer-bearing fields are forbidden and asserted at load time, so this
file can never drift into an answer table. It is NOT part of the verified-store
``STORE_FILES`` and is never read by the answer path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Default sidecar location (outside any verified-store STORE_FILES).
DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "ontology" / "relation_type_schema.jsonl"
)

# Fields that would turn a type declaration into an instance/answer table.
FORBIDDEN_INSTANCE_FIELDS = frozenset({
    "answer_text", "person", "target_answer", "answer_entity_id",
    "subject_id", "object_id", "entity_id", "specific_value", "valid_subject",
})

ALLOWED_TEMPORAL_POLICIES = frozenset({"immutable", "single_value_at_a_time", "multi_value"})


def load_relation_type_schema(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load and validate the relation-type schema rows. Empty list if absent."""
    p = Path(path) if path else DEFAULT_SCHEMA_PATH
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        _assert_no_instance_fields(row)
        if "relation_type" not in row or not row["relation_type"]:
            raise ValueError("relation_type_schema row missing relation_type")
        tp = row.get("temporal_policy")
        if tp is not None and tp not in ALLOWED_TEMPORAL_POLICIES:
            raise ValueError(f"invalid temporal_policy: {tp}")
        _assert_aliases_are_not_instances(row)
        rows.append(row)
    return rows


# Tokens that signal an alias is sneaking in a subject->answer instance mapping

_INSTANCE_DELIMITERS = ("=", "->", "→", "==", "=>")


def _assert_aliases_are_not_instances(row: dict[str, Any]) -> None:
    for alias in row.get("aliases", []) or []:
        s = str(alias)
        if any(tok in s for tok in _INSTANCE_DELIMITERS):
            raise ValueError(
                f"alias looks like an instance mapping, not a lexical alias (forbidden): {alias!r}"
            )


def _assert_no_instance_fields(row: dict[str, Any]) -> None:
    """Reject any answer/instance-bearing key anywhere in the row (recursive)."""
    def _keys(obj: Any):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from _keys(v)
        elif isinstance(obj, (list, tuple)):
            for it in obj:
                yield from _keys(it)

    leaked = sorted(set(_keys(row)) & FORBIDDEN_INSTANCE_FIELDS)
    if leaked:
        raise ValueError(f"relation_type_schema must declare TYPES only; forbidden instance fields: {leaked}")


def functional_relations(schema: list[dict[str, Any]] | None = None) -> set[str]:
    """Derived view: the set of relation types declared functional."""
    if schema is None:
        schema = load_relation_type_schema()
    return {str(r["relation_type"]) for r in schema if r.get("functional") is True}
