"""Machine-check the architecture census without inferring capability.

The registry deliberately records four independent facts:

* ``built``: a source directory exists;
* ``wiring``: current runtime reachability, or ``unknown``;
* ``authority``: attested decision authority, or ``none``;
* ``evidence``: the strongest completed evidence stage.

No field is derived from another. In particular, source presence never proves
runtime wiring, authority, or external capability.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

LIFECYCLES = ("canonical", "adapter", "shadow", "fixture", "archive")
CANONICAL_DOMAINS = (
    "core_spine",
    "world_ledger",
    "semantic_compiler",
    "world_model_4d",
    "unified_deliberator",
    "operational_self",
    "interoception_resource",
    "membrane_governance",
    "language_action",
    "learning_evolution",
    "embodiment",
    "evaluation",
    "platform",
)
EVIDENCE_STAGES = ("V0", "M1", "M2", "M3", "E4", "E5", "E6")
AUTHORITY_LEVELS = ("primary", "secondary", "none")
RUNTIME_STATUSES = (
    "live_default",
    "live_conditional",
    "test_only",
    "unwired",
    "unknown",
)

_TOP_LEVEL_KEYS = {"schema_version", "scope", "definitions", "enums", "organs"}
_ORGAN_KEYS = {
    "name",
    "path",
    "lifecycle",
    "canonical_domain",
    "built",
    "wiring",
    "authority",
    "evidence",
}
_BUILT_KEYS = {"status", "refs"}
_WIRING_KEYS = {"runtime_status", "refs"}
_AUTHORITY_KEYS = {"level", "refs"}
_EVIDENCE_KEYS = {"stage", "refs"}
_DEFINITION_KEYS = {
    "lifecycle",
    "canonical_domain",
    "built",
    "wiring",
    "authority",
    "evidence",
}


class RegistryValidationError(ValueError):
    """Raised when the checked-in catalog does not match its strict contract."""


class _DuplicateJsonKey(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_catalog(path: Path) -> dict[str, Any]:
    """Load a catalog while rejecting duplicate JSON object keys."""

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
        )
    except (OSError, json.JSONDecodeError, _DuplicateJsonKey) as exc:
        raise RegistryValidationError(f"cannot load registry {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RegistryValidationError("registry root must be a JSON object")
    return value


def discover_package_names(package_root: Path) -> tuple[str, ...]:
    """Return all real top-level package directories in deterministic order."""

    return tuple(
        sorted(
            child.name
            for child in package_root.iterdir()
            if child.is_dir() and child.name != "__pycache__"
        )
    )


def _keys_exact(value: Any, expected: set[str], label: str, issues: list[str]) -> bool:
    if not isinstance(value, dict):
        issues.append(f"{label} must be an object")
        return False
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        issues.append(f"{label} keys invalid: missing={missing}, extra={extra}")
        return False
    return True


def _validate_refs(
    refs: Any,
    *,
    label: str,
    repo_root: Path,
    issues: list[str],
) -> None:
    if not isinstance(refs, list):
        issues.append(f"{label} must be a list")
        return
    seen: set[str] = set()
    for index, ref in enumerate(refs):
        item_label = f"{label}[{index}]"
        if not isinstance(ref, str) or not ref:
            issues.append(f"{item_label} must be a non-empty string")
            continue
        if ref in seen:
            issues.append(f"{label} contains duplicate ref {ref!r}")
            continue
        seen.add(ref)
        candidate = Path(ref)
        if candidate.is_absolute() or ".." in candidate.parts:
            issues.append(f"{item_label} must be a repository-relative path")
            continue
        if not (repo_root / candidate).exists():
            issues.append(f"{item_label} does not exist: {ref}")


def _validate_enums(catalog: dict[str, Any], issues: list[str]) -> None:
    expected = {
        "lifecycle": list(LIFECYCLES),
        "canonical_domain": list(CANONICAL_DOMAINS),
        "evidence_stage": list(EVIDENCE_STAGES),
        "authority": list(AUTHORITY_LEVELS),
        "runtime_status": list(RUNTIME_STATUSES),
    }
    enums = catalog.get("enums")
    if not isinstance(enums, dict):
        issues.append("enums must be an object")
        return
    if enums != expected:
        issues.append("enums must exactly match the frozen registry contract")


def validate_catalog(
    catalog: dict[str, Any],
    *,
    package_root: Path,
    repo_root: Path | None = None,
) -> list[str]:
    """Return deterministic validation findings; an empty list means valid."""

    issues: list[str] = []
    repo = repo_root or package_root.parent

    _keys_exact(catalog, _TOP_LEVEL_KEYS, "registry", issues)
    if type(catalog.get("schema_version")) is not int or catalog.get("schema_version") != 1:
        issues.append("schema_version must be integer 1")

    scope = catalog.get("scope")
    if _keys_exact(
        scope,
        {"package_root", "excluded_directories"},
        "scope",
        issues,
    ):
        if scope["package_root"] != "packages":
            issues.append("scope.package_root must be 'packages'")
        if scope["excluded_directories"] != ["__pycache__"]:
            issues.append("scope.excluded_directories must be ['__pycache__']")

    definitions = catalog.get("definitions")
    if _keys_exact(definitions, _DEFINITION_KEYS, "definitions", issues):
        for key, value in definitions.items():
            if not isinstance(value, str) or not value.strip():
                issues.append(f"definitions.{key} must be a non-empty string")

    _validate_enums(catalog, issues)

    organs = catalog.get("organs")
    if not isinstance(organs, list):
        issues.append("organs must be a list")
        return sorted(set(issues))

    actual_names = set(discover_package_names(package_root))
    registered_names: set[str] = set()
    registered_paths: set[str] = set()

    for index, organ in enumerate(organs):
        label = f"organs[{index}]"
        if not _keys_exact(organ, _ORGAN_KEYS, label, issues):
            continue

        name = organ["name"]
        path = organ["path"]
        if not isinstance(name, str) or not name:
            issues.append(f"{label}.name must be a non-empty string")
        elif name in registered_names:
            issues.append(f"duplicate organ name: {name}")
        else:
            registered_names.add(name)

        expected_path = f"packages/{name}" if isinstance(name, str) else None
        if not isinstance(path, str) or path != expected_path:
            issues.append(f"{label}.path must equal {expected_path!r}")
        elif path in registered_paths:
            issues.append(f"duplicate organ path: {path}")
        else:
            registered_paths.add(path)

        if organ["lifecycle"] not in LIFECYCLES:
            issues.append(f"{label}.lifecycle is invalid: {organ['lifecycle']!r}")
        if organ["canonical_domain"] not in CANONICAL_DOMAINS:
            issues.append(
                f"{label}.canonical_domain is invalid: {organ['canonical_domain']!r}"
            )

        built = organ["built"]
        if _keys_exact(built, _BUILT_KEYS, f"{label}.built", issues):
            if type(built["status"]) is not bool:
                issues.append(f"{label}.built.status must be a literal boolean")
            elif built["status"] is not True:
                issues.append(f"{label}.built.status must be true for an in-scope directory")
            _validate_refs(
                built["refs"],
                label=f"{label}.built.refs",
                repo_root=repo,
                issues=issues,
            )
            if (
                isinstance(path, str)
                and isinstance(built["refs"], list)
                and path not in built["refs"]
            ):
                issues.append(f"{label}.built.refs must include its package path")

        wiring = organ["wiring"]
        if _keys_exact(wiring, _WIRING_KEYS, f"{label}.wiring", issues):
            status = wiring["runtime_status"]
            if status not in RUNTIME_STATUSES:
                issues.append(f"{label}.wiring.runtime_status is invalid: {status!r}")
            _validate_refs(
                wiring["refs"],
                label=f"{label}.wiring.refs",
                repo_root=repo,
                issues=issues,
            )
            if status in {"live_default", "live_conditional", "test_only"} and not wiring["refs"]:
                issues.append(f"{label}.wiring.refs required for attested runtime status")

        authority = organ["authority"]
        if _keys_exact(authority, _AUTHORITY_KEYS, f"{label}.authority", issues):
            level = authority["level"]
            if level not in AUTHORITY_LEVELS:
                issues.append(f"{label}.authority.level is invalid: {level!r}")
            _validate_refs(
                authority["refs"],
                label=f"{label}.authority.refs",
                repo_root=repo,
                issues=issues,
            )
            if level in {"primary", "secondary"} and not authority["refs"]:
                issues.append(f"{label}.authority.refs required for attested authority")

        evidence = organ["evidence"]
        if _keys_exact(evidence, _EVIDENCE_KEYS, f"{label}.evidence", issues):
            if evidence["stage"] not in EVIDENCE_STAGES:
                issues.append(f"{label}.evidence.stage is invalid: {evidence['stage']!r}")
            _validate_refs(
                evidence["refs"],
                label=f"{label}.evidence.refs",
                repo_root=repo,
                issues=issues,
            )
            if not evidence["refs"]:
                issues.append(f"{label}.evidence.refs must not be empty")

    missing = sorted(actual_names - registered_names)
    extra = sorted(registered_names - actual_names)
    if missing:
        issues.append(f"unregistered package directories: {missing}")
    if extra:
        issues.append(f"registered package directories not on disk: {extra}")

    names_in_order = [
        organ.get("name")
        for organ in organs
        if isinstance(organ, dict) and isinstance(organ.get("name"), str)
    ]
    if names_in_order != sorted(names_in_order):
        issues.append("organs must be sorted by name")

    return sorted(set(issues))


def assert_catalog_valid(
    catalog: dict[str, Any],
    *,
    package_root: Path,
    repo_root: Path | None = None,
) -> None:
    """Raise with all findings when a catalog is invalid."""

    issues = validate_catalog(catalog, package_root=package_root, repo_root=repo_root)
    if issues:
        raise RegistryValidationError("\n".join(f"- {issue}" for issue in issues))


def load_and_validate(
    catalog_path: Path,
    *,
    package_root: Path,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Load and strictly validate the catalog."""

    catalog = load_catalog(catalog_path)
    assert_catalog_valid(catalog, package_root=package_root, repo_root=repo_root)
    return catalog


def format_summary(catalog: dict[str, Any]) -> str:
    """Return a small deterministic summary after validation."""

    organs: Iterable[dict[str, Any]] = catalog["organs"]
    lifecycle_counts = {
        value: sum(organ["lifecycle"] == value for organ in organs)
        for value in LIFECYCLES
    }
    return (
        f"organ registry valid: {len(catalog['organs'])} directories; "
        + ", ".join(f"{key}={value}" for key, value in lifecycle_counts.items())
    )
