"""Validate source-bound critical runtime edges without inferring capability.

This manifest is deliberately narrower than the static import census.  Each
edge records four independent dimensions:

* a literal static import observation;
* a source-confirmed reachable call;
* an immutable exercised trace;
* a bounded decision-authority claim.

No dimension is derived from another.  In particular, an import does not prove
that a call is reachable, a reachable call does not prove that production
exercised it, and a green controlled test does not prove benchmark lift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

RUNTIME_EDGE_SCHEMA = "atanor.architecture.runtime-edge-manifest.v1"

STATIC_IMPORT_STATES = (
    "observed",
    "not_observed_in_bound_source",
    "unknown",
)
REACHABLE_CALL_STATES = (
    "source_confirmed",
    "not_observed_in_bound_source",
    "not_applicable",
    "unknown",
)
EXERCISED_TRACE_STATES = (
    "production_trace",
    "controlled_test",
    "not_recorded",
    "unknown",
)
AUTHORITY_STATES = (
    "unattested",
    "bounded_guard",
    "conditional_decider",
    "staging_only",
    "external_signature_required",
    "unknown",
)
ENABLEMENT_STATES = (
    "default",
    "conditional",
    "controlled_only",
    "external_invocation",
    "unknown",
)
RELATIONS = ("python_call", "artifact_flow", "side_effect_boundary")
BINDING_KINDS = ("live_source", "test_source", "evidence_report")
MECHANISM_STAGES = ("V0", "M1", "M2", "M3")

_TOP_LEVEL_KEYS = {
    "schema_version",
    "schema",
    "claim_scope",
    "definitions",
    "enums",
    "maturity",
    "bindings",
    "edges",
    "canonical_hash",
}
_DEFINITION_KEYS = {
    "static_import",
    "reachable_call",
    "exercised_trace",
    "authority",
    "unknown",
}
_MATURITY_KEYS = {
    "census_stage",
    "capability_claims",
    "e5_claimed",
    "benchmark_lift_claimed",
}
_BINDING_KEYS = {"id", "path", "kind", "sha256", "anchors"}
_EDGE_KEYS = {
    "id",
    "relation",
    "caller",
    "callee",
    "static_import",
    "reachable_call",
    "exercised_trace",
    "authority",
    "enablement",
    "capability",
    "limitations",
}
_ENDPOINT_KEYS = {"owner", "symbol"}
_EVIDENCE_KEYS = {"state", "binding_refs", "note"}
_ENABLEMENT_KEYS = {"state", "note"}
_CAPABILITY_KEYS = {"mechanism_stage", "capability_claims", "e5_claimed"}

_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RuntimeGraphValidationError(ValueError):
    """Raised when a runtime-edge manifest violates the frozen contract."""


class _DuplicateJsonKey(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_manifest_hash(manifest: dict[str, Any]) -> str:
    """Hash the complete manifest except its self-referential hash field."""

    payload = dict(manifest)
    payload.pop("canonical_hash", None)
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def load_runtime_manifest(path: Path) -> dict[str, Any]:
    """Load a JSON object while rejecting duplicate keys and non-finite values."""

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant: {value}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeGraphValidationError(
            f"cannot load runtime-edge manifest {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise RuntimeGraphValidationError("runtime-edge manifest root must be an object")
    return value


def _keys_exact(value: Any, expected: set[str], label: str, issues: list[str]) -> bool:
    if not isinstance(value, dict):
        issues.append(f"{label} must be an object")
        return False
    actual = set(value)
    if actual != expected:
        issues.append(
            f"{label} keys invalid: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
        return False
    return True


def _nonempty_text(value: Any, label: str, issues: list[str]) -> bool:
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{label} must be a non-empty string")
        return False
    return True


def _validate_refs(
    refs: Any,
    *,
    label: str,
    binding_kinds: dict[str, str],
    issues: list[str],
) -> tuple[str, ...]:
    if not isinstance(refs, list):
        issues.append(f"{label} must be a list")
        return ()
    valid: list[str] = []
    seen: set[str] = set()
    for index, ref in enumerate(refs):
        if not isinstance(ref, str) or not ref:
            issues.append(f"{label}[{index}] must be a non-empty string")
            continue
        if ref in seen:
            issues.append(f"{label} contains duplicate binding ref {ref!r}")
            continue
        seen.add(ref)
        if ref not in binding_kinds:
            issues.append(f"{label}[{index}] references unknown binding {ref!r}")
            continue
        valid.append(ref)
    return tuple(valid)


def _validate_binding(
    binding: Any,
    *,
    index: int,
    repo_root: Path,
    known_ids: set[str],
    known_paths: set[str],
    issues: list[str],
) -> tuple[str | None, str | None]:
    label = f"bindings[{index}]"
    if not _keys_exact(binding, _BINDING_KEYS, label, issues):
        return None, None

    binding_id = binding["id"]
    if not isinstance(binding_id, str) or _IDENTIFIER_RE.fullmatch(binding_id) is None:
        issues.append(f"{label}.id must match {_IDENTIFIER_RE.pattern!r}")
        binding_id = None
    elif binding_id in known_ids:
        issues.append(f"duplicate binding id: {binding_id}")
    else:
        known_ids.add(binding_id)

    kind = binding["kind"]
    if kind not in BINDING_KINDS:
        issues.append(f"{label}.kind is invalid: {kind!r}")
        kind = None

    path_value = binding["path"]
    source_path: Path | None = None
    if not isinstance(path_value, str) or not path_value:
        issues.append(f"{label}.path must be a non-empty string")
    elif "\\" in path_value:
        issues.append(f"{label}.path must use repository-relative POSIX separators")
    else:
        relative = Path(path_value)
        if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
            issues.append(f"{label}.path must be a normalized repository-relative path")
        elif path_value in known_paths:
            issues.append(f"duplicate binding path: {path_value}")
        else:
            known_paths.add(path_value)
            candidate = repo_root / relative
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(repo_root)
            except (OSError, ValueError):
                issues.append(f"{label}.path is missing or escapes repository: {path_value}")
            else:
                if candidate.is_symlink() or not resolved.is_file():
                    issues.append(f"{label}.path must be a regular non-symlink file")
                else:
                    source_path = resolved

    digest = binding["sha256"]
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        issues.append(f"{label}.sha256 must be a lowercase SHA-256 digest")
    elif source_path is not None:
        try:
            actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
        except OSError as exc:
            issues.append(f"{label}.path could not be hashed: {type(exc).__name__}")
        else:
            if actual != digest:
                issues.append(
                    f"{label}.sha256 mismatch for {path_value}: expected {digest}, actual {actual}"
                )

    anchors = binding["anchors"]
    if not isinstance(anchors, list) or not anchors:
        issues.append(f"{label}.anchors must be a non-empty list")
    else:
        seen_anchors: set[str] = set()
        source_text: str | None = None
        if source_path is not None:
            try:
                source_text = source_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                issues.append(f"{label}.path is not readable UTF-8: {type(exc).__name__}")
        for anchor_index, anchor in enumerate(anchors):
            anchor_label = f"{label}.anchors[{anchor_index}]"
            if not isinstance(anchor, str) or not anchor.strip():
                issues.append(f"{anchor_label} must be a non-empty string")
                continue
            if anchor in seen_anchors:
                issues.append(f"{label}.anchors contains duplicate anchor {anchor!r}")
                continue
            seen_anchors.add(anchor)
            if source_text is not None:
                count = source_text.count(anchor)
                if count != 1:
                    issues.append(
                        f"{anchor_label} must occur exactly once in {path_value}; found {count}"
                    )

    return binding_id, kind


def _validate_endpoint(value: Any, label: str, issues: list[str]) -> None:
    if not _keys_exact(value, _ENDPOINT_KEYS, label, issues):
        return
    _nonempty_text(value["owner"], f"{label}.owner", issues)
    _nonempty_text(value["symbol"], f"{label}.symbol", issues)


def _validate_evidence_dimension(
    value: Any,
    *,
    label: str,
    states: tuple[str, ...],
    positive_states: set[str],
    empty_states: set[str],
    binding_kinds: dict[str, str],
    used_bindings: set[str],
    issues: list[str],
) -> tuple[str | None, tuple[str, ...]]:
    if not _keys_exact(value, _EVIDENCE_KEYS, label, issues):
        return None, ()
    state = value["state"]
    if state not in states:
        issues.append(f"{label}.state is invalid: {state!r}")
        state = None
    _nonempty_text(value["note"], f"{label}.note", issues)
    refs = _validate_refs(
        value["binding_refs"],
        label=f"{label}.binding_refs",
        binding_kinds=binding_kinds,
        issues=issues,
    )
    used_bindings.update(refs)
    if state in positive_states and not refs:
        issues.append(f"{label}.binding_refs required for state {state!r}")
    if state in empty_states and refs:
        issues.append(f"{label}.binding_refs must be empty for state {state!r}")
    return state, refs


def _validate_capability(value: Any, label: str, issues: list[str]) -> None:
    if not _keys_exact(value, _CAPABILITY_KEYS, label, issues):
        return
    if value["mechanism_stage"] not in MECHANISM_STAGES:
        issues.append(f"{label}.mechanism_stage must be one of {MECHANISM_STAGES!r}")
    if value["capability_claims"] != []:
        issues.append(f"{label}.capability_claims must be empty in the G0 wiring census")
    if value["e5_claimed"] is not False:
        issues.append(f"{label}.e5_claimed must be literal false")


def validate_runtime_manifest(
    manifest: dict[str, Any],
    *,
    repo_root: Path,
) -> list[str]:
    """Return deterministic findings; an empty list means the manifest is valid."""

    issues: list[str] = []
    repo = repo_root.resolve()
    _keys_exact(manifest, _TOP_LEVEL_KEYS, "manifest", issues)

    if type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1:
        issues.append("schema_version must be integer 1")
    if manifest.get("schema") != RUNTIME_EDGE_SCHEMA:
        issues.append(f"schema must equal {RUNTIME_EDGE_SCHEMA!r}")
    _nonempty_text(manifest.get("claim_scope"), "claim_scope", issues)

    definitions = manifest.get("definitions")
    if _keys_exact(definitions, _DEFINITION_KEYS, "definitions", issues):
        for key, value in definitions.items():
            _nonempty_text(value, f"definitions.{key}", issues)

    expected_enums = {
        "static_import": list(STATIC_IMPORT_STATES),
        "reachable_call": list(REACHABLE_CALL_STATES),
        "exercised_trace": list(EXERCISED_TRACE_STATES),
        "authority": list(AUTHORITY_STATES),
        "enablement": list(ENABLEMENT_STATES),
        "relation": list(RELATIONS),
        "binding_kind": list(BINDING_KINDS),
        "mechanism_stage": list(MECHANISM_STAGES),
    }
    if manifest.get("enums") != expected_enums:
        issues.append("enums must exactly match the frozen runtime-edge contract")

    maturity = manifest.get("maturity")
    if _keys_exact(maturity, _MATURITY_KEYS, "maturity", issues):
        if maturity["census_stage"] != "M1":
            issues.append("maturity.census_stage must be 'M1'")
        if maturity["capability_claims"] != []:
            issues.append("maturity.capability_claims must be empty")
        if maturity["e5_claimed"] is not False:
            issues.append("maturity.e5_claimed must be literal false")
        if maturity["benchmark_lift_claimed"] is not False:
            issues.append("maturity.benchmark_lift_claimed must be literal false")

    expected_hash = manifest.get("canonical_hash")
    if not isinstance(expected_hash, str) or _SHA256_RE.fullmatch(expected_hash) is None:
        issues.append("canonical_hash must be a lowercase SHA-256 digest")
    else:
        try:
            actual_hash = canonical_manifest_hash(manifest)
        except (TypeError, ValueError):
            issues.append("manifest is not canonical-JSON serializable")
        else:
            if expected_hash != actual_hash:
                issues.append(
                    f"canonical_hash mismatch: expected {expected_hash}, actual {actual_hash}"
                )

    bindings = manifest.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        issues.append("bindings must be a non-empty list")
        bindings = []
    known_ids: set[str] = set()
    known_paths: set[str] = set()
    binding_kinds: dict[str, str] = {}
    binding_order: list[str] = []
    for index, binding in enumerate(bindings):
        binding_id, kind = _validate_binding(
            binding,
            index=index,
            repo_root=repo,
            known_ids=known_ids,
            known_paths=known_paths,
            issues=issues,
        )
        if binding_id is not None:
            binding_order.append(binding_id)
            if kind is not None:
                binding_kinds[binding_id] = kind
    if binding_order != sorted(binding_order):
        issues.append("bindings must be sorted by id")

    edges = manifest.get("edges")
    if not isinstance(edges, list) or not edges:
        issues.append("edges must be a non-empty list")
        return sorted(set(issues))

    known_edges: set[str] = set()
    edge_order: list[str] = []
    used_bindings: set[str] = set()
    for index, edge in enumerate(edges):
        label = f"edges[{index}]"
        if not _keys_exact(edge, _EDGE_KEYS, label, issues):
            continue
        edge_id = edge["id"]
        if not isinstance(edge_id, str) or _IDENTIFIER_RE.fullmatch(edge_id) is None:
            issues.append(f"{label}.id must match {_IDENTIFIER_RE.pattern!r}")
        elif edge_id in known_edges:
            issues.append(f"duplicate edge id: {edge_id}")
        else:
            known_edges.add(edge_id)
            edge_order.append(edge_id)

        if edge["relation"] not in RELATIONS:
            issues.append(f"{label}.relation is invalid: {edge['relation']!r}")
        _validate_endpoint(edge["caller"], f"{label}.caller", issues)
        _validate_endpoint(edge["callee"], f"{label}.callee", issues)
        if edge["caller"] == edge["callee"]:
            issues.append(f"{label} caller and callee must differ")

        static_state, _ = _validate_evidence_dimension(
            edge["static_import"],
            label=f"{label}.static_import",
            states=STATIC_IMPORT_STATES,
            positive_states={"observed", "not_observed_in_bound_source"},
            empty_states={"unknown"},
            binding_kinds=binding_kinds,
            used_bindings=used_bindings,
            issues=issues,
        )
        call_state, call_refs = _validate_evidence_dimension(
            edge["reachable_call"],
            label=f"{label}.reachable_call",
            states=REACHABLE_CALL_STATES,
            positive_states={"source_confirmed", "not_observed_in_bound_source"},
            empty_states={"not_applicable", "unknown"},
            binding_kinds=binding_kinds,
            used_bindings=used_bindings,
            issues=issues,
        )
        trace_state, trace_refs = _validate_evidence_dimension(
            edge["exercised_trace"],
            label=f"{label}.exercised_trace",
            states=EXERCISED_TRACE_STATES,
            positive_states={"production_trace", "controlled_test"},
            empty_states={"not_recorded", "unknown"},
            binding_kinds=binding_kinds,
            used_bindings=used_bindings,
            issues=issues,
        )
        authority_state, authority_refs = _validate_evidence_dimension(
            edge["authority"],
            label=f"{label}.authority",
            states=AUTHORITY_STATES,
            positive_states={
                "bounded_guard",
                "conditional_decider",
                "staging_only",
                "external_signature_required",
            },
            empty_states={"unattested", "unknown"},
            binding_kinds=binding_kinds,
            used_bindings=used_bindings,
            issues=issues,
        )

        if call_state == "source_confirmed" and call_refs:
            if not any(binding_kinds.get(ref) == "live_source" for ref in call_refs):
                issues.append(
                    f"{label}.reachable_call source confirmation requires a live_source binding"
                )
        if trace_state == "controlled_test" and trace_refs:
            kinds = {binding_kinds.get(ref) for ref in trace_refs}
            if not {"test_source", "evidence_report"}.issubset(kinds):
                issues.append(
                    f"{label}.exercised_trace controlled_test requires test_source and "
                    "evidence_report bindings"
                )
        if trace_state == "production_trace" and trace_refs:
            if not any(binding_kinds.get(ref) == "evidence_report" for ref in trace_refs):
                issues.append(
                    f"{label}.exercised_trace production_trace requires an evidence_report"
                )
        if trace_state == "production_trace" and call_state in {"unknown", "not_applicable"}:
            issues.append(
                f"{label}.exercised_trace cannot be production_trace while reachable_call is "
                f"{call_state!r}"
            )
        if authority_state not in {"unattested", "unknown", None} and authority_refs:
            if not any(binding_kinds.get(ref) == "live_source" for ref in authority_refs):
                issues.append(f"{label}.authority requires a live_source binding")

        enablement = edge["enablement"]
        if _keys_exact(enablement, _ENABLEMENT_KEYS, f"{label}.enablement", issues):
            if enablement["state"] not in ENABLEMENT_STATES:
                issues.append(
                    f"{label}.enablement.state is invalid: {enablement['state']!r}"
                )
            _nonempty_text(enablement["note"], f"{label}.enablement.note", issues)

        _validate_capability(edge["capability"], f"{label}.capability", issues)

        limitations = edge["limitations"]
        if not isinstance(limitations, list) or not limitations:
            issues.append(f"{label}.limitations must be a non-empty list")
        else:
            seen_limitations: set[str] = set()
            for limitation_index, limitation in enumerate(limitations):
                limitation_label = f"{label}.limitations[{limitation_index}]"
                if _nonempty_text(limitation, limitation_label, issues):
                    if limitation in seen_limitations:
                        issues.append(
                            f"{label}.limitations contains duplicate {limitation!r}"
                        )
                    seen_limitations.add(limitation)

        # This explicit no-op documents the contract: static evidence is never used
        # to derive call, trace, authority, enablement, or capability state.
        _ = static_state

    if edge_order != sorted(edge_order):
        issues.append("edges must be sorted by id")
    unused = sorted(set(binding_kinds) - used_bindings)
    if unused:
        issues.append(f"unused source bindings: {unused}")

    return sorted(set(issues))


def assert_runtime_manifest_valid(
    manifest: dict[str, Any],
    *,
    repo_root: Path,
) -> None:
    """Raise with all findings when a runtime-edge manifest is invalid."""

    issues = validate_runtime_manifest(manifest, repo_root=repo_root)
    if issues:
        raise RuntimeGraphValidationError("\n".join(f"- {issue}" for issue in issues))


def load_and_validate_runtime_manifest(
    path: Path,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    manifest = load_runtime_manifest(path)
    assert_runtime_manifest_valid(manifest, repo_root=repo_root)
    return manifest


def format_runtime_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded summary that keeps unknowns and trace gaps visible."""

    edges: Iterable[dict[str, Any]] = manifest["edges"]
    edge_list = list(edges)
    return {
        "schema": manifest["schema"],
        "binding_count": len(manifest["bindings"]),
        "edge_count": len(edge_list),
        "source_confirmed_calls": sum(
            edge["reachable_call"]["state"] == "source_confirmed" for edge in edge_list
        ),
        "unknown_calls": sum(
            edge["reachable_call"]["state"] == "unknown" for edge in edge_list
        ),
        "not_observed_calls": sum(
            edge["reachable_call"]["state"] == "not_observed_in_bound_source"
            for edge in edge_list
        ),
        "not_applicable_calls": sum(
            edge["reachable_call"]["state"] == "not_applicable"
            for edge in edge_list
        ),
        "unresolved_calls": sum(
            edge["reachable_call"]["state"] != "source_confirmed"
            for edge in edge_list
        ),
        "production_traces": sum(
            edge["exercised_trace"]["state"] == "production_trace" for edge in edge_list
        ),
        "e5_claimed": manifest["maturity"]["e5_claimed"],
        "benchmark_lift_claimed": manifest["maturity"]["benchmark_lift_claimed"],
        "canonical_hash": manifest["canonical_hash"],
        "claim_scope": manifest["claim_scope"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="", help="Override the canonical manifest path")
    parser.add_argument("--json", action="store_true", help="Emit the bounded summary as JSON")
    args = parser.parse_args(argv)

    repo = Path(__file__).resolve().parents[2]
    path = (
        Path(args.manifest)
        if args.manifest
        else repo / "data" / "architecture" / "catalog" / "runtime_edges_v1.json"
    )
    try:
        manifest = load_and_validate_runtime_manifest(path, repo_root=repo)
    except RuntimeGraphValidationError as exc:
        print(f"runtime-edge manifest invalid:\n{exc}")
        return 2
    summary = format_runtime_summary(manifest)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "runtime-edge manifest valid: "
            f"{summary['edge_count']} edges, "
            f"source_confirmed_calls={summary['source_confirmed_calls']}, "
            f"unresolved_calls={summary['unresolved_calls']}, "
            f"production_traces={summary['production_traces']}"
        )
        print(summary["claim_scope"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
