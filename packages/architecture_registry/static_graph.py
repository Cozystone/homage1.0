"""Deterministic static import census for architecture wiring investigation.

Static references are not runtime reachability, authority, or capability. This
module keeps production and test references separate, records parse failures, and
never mutates the checked-in organ registry. Its output is evidence for deciding
which ``unknown`` organs deserve a later runtime trace and E4 wiring probe.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import tokenize
from pathlib import Path
from typing import Any, Iterable

STATIC_GRAPH_SCHEMA = "atanor.architecture.static-import-graph.v1"
DEFAULT_SCAN_ROOTS = ("packages", "apps/api/app", "scripts")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _source_owner(relative: Path, package_names: set[str]) -> tuple[str, bool]:
    parts = relative.parts
    is_test = (
        "tests" in parts
        or relative.name.startswith("test_")
        or relative.name.endswith("_test.py")
    )
    if len(parts) >= 2 and parts[0] == "packages" and parts[1] in package_names:
        return f"packages.{parts[1]}", is_test
    if len(parts) >= 2 and parts[0] == "apps" and parts[1] == "api":
        return "apps.api", is_test
    if parts and parts[0] == "scripts":
        return "scripts", is_test
    return "other", is_test


def _module_package(module: str, package_names: set[str]) -> str | None:
    parts = str(module or "").split(".")
    if len(parts) >= 2 and parts[0] == "packages" and parts[1] in package_names:
        return parts[1]
    if parts and parts[0] in package_names:
        return parts[0]
    return None


def _literal_dynamic_import(node: ast.Call) -> str | None:
    is_importlib = (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "importlib"
        and node.func.attr == "import_module"
    )
    is_builtin = isinstance(node.func, ast.Name) and node.func.id == "__import__"
    if not (is_importlib or is_builtin) or not node.args:
        return None
    first = node.args[0]
    return first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None


def _imports(tree: ast.AST) -> Iterable[tuple[str, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, "import"
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module, "from_import"
        elif isinstance(node, ast.Call):
            module = _literal_dynamic_import(node)
            if module is not None:
                yield module, "dynamic_literal"


def _python_files(repo_root: Path, scan_roots: Iterable[str]) -> list[Path]:
    files: set[Path] = set()
    for relative in scan_roots:
        root = repo_root / relative
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" not in path.parts and path.is_file() and not path.is_symlink():
                files.add(path)
    return sorted(files, key=lambda path: path.relative_to(repo_root).as_posix())


def build_static_graph(
    repo_root: Path,
    package_names: Iterable[str],
    *,
    scan_roots: Iterable[str] = DEFAULT_SCAN_ROOTS,
) -> dict[str, Any]:
    """Build a deterministic graph with no inference beyond literal source references."""
    repo = repo_root.resolve()
    names = tuple(sorted(set(package_names)))
    name_set = set(names)
    inbound_production: dict[str, list[dict[str, str]]] = {name: [] for name in names}
    inbound_test: dict[str, list[dict[str, str]]] = {name: [] for name in names}
    outbound: dict[str, set[str]] = {name: set() for name in names}
    parse_failures: list[dict[str, str]] = []
    scanned_files = 0

    for path in _python_files(repo, scan_roots):
        relative = path.relative_to(repo)
        source = relative.as_posix()
        owner, is_test = _source_owner(relative, name_set)
        try:
            with tokenize.open(path) as handle:
                source_text = handle.read()
            tree = ast.parse(source_text, filename=source)
        except (OSError, SyntaxError, UnicodeError) as exc:
            parse_failures.append({"source": source, "error": type(exc).__name__})
            continue
        scanned_files += 1
        seen_edges: set[tuple[str, str]] = set()
        for module, import_kind in _imports(tree):
            callee = _module_package(module, name_set)
            if callee is None or owner == f"packages.{callee}":
                continue
            edge_key = (callee, import_kind)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            record = {
                "source": source,
                "owner": owner,
                "import_kind": import_kind,
            }
            target = inbound_test if is_test else inbound_production
            target[callee].append(record)
            if owner.startswith("packages."):
                caller = owner.split(".", 1)[1]
                if caller in name_set:
                    outbound[caller].add(callee)

    organs: list[dict[str, Any]] = []
    for name in names:
        production_refs = sorted(
            inbound_production[name],
            key=lambda row: (row["source"], row["owner"], row["import_kind"]),
        )
        test_refs = sorted(
            inbound_test[name],
            key=lambda row: (row["source"], row["owner"], row["import_kind"]),
        )
        if production_refs:
            status = "production_static_reference"
        elif test_refs:
            status = "test_static_reference_only"
        else:
            status = "no_external_static_reference"
        organs.append(
            {
                "name": name,
                "static_status": status,
                "production_inbound": production_refs,
                "test_inbound": test_refs,
                "outbound_packages": sorted(outbound[name]),
            }
        )

    graph: dict[str, Any] = {
        "schema": STATIC_GRAPH_SCHEMA,
        "claim_scope": (
            "Literal Python import references only. This does not establish runtime reachability, "
            "default enablement, decision authority, integration quality, or capability."
        ),
        "scan_roots": list(scan_roots),
        "scanned_files": scanned_files,
        "parse_failures": sorted(
            parse_failures,
            key=lambda row: (row["source"], row["error"]),
        ),
        "organs": organs,
    }
    graph["canonical_hash"] = hashlib.sha256(_canonical_bytes(graph)).hexdigest()
    return graph


def summarize_static_graph(graph: dict[str, Any]) -> dict[str, Any]:
    counts = {
        status: sum(organ["static_status"] == status for organ in graph["organs"])
        for status in (
            "production_static_reference",
            "test_static_reference_only",
            "no_external_static_reference",
        )
    }
    return {
        "schema": graph["schema"],
        "organ_count": len(graph["organs"]),
        "scanned_files": graph["scanned_files"],
        "parse_failure_count": len(graph["parse_failures"]),
        "status_counts": counts,
        "canonical_hash": graph["canonical_hash"],
        "claim_scope": graph["claim_scope"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit the bounded summary as JSON")
    args = parser.parse_args(argv)

    from .registry import discover_package_names

    repo = Path(__file__).resolve().parents[2]
    graph = build_static_graph(repo, discover_package_names(repo / "packages"))
    summary = summarize_static_graph(graph)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        counts = summary["status_counts"]
        print(
            "static import census: "
            f"{summary['organ_count']} organs, {summary['scanned_files']} files, "
            f"production_refs={counts['production_static_reference']}, "
            f"test_only={counts['test_static_reference_only']}, "
            f"no_external_ref={counts['no_external_static_reference']}, "
            f"parse_failures={summary['parse_failure_count']}"
        )
        print(summary["claim_scope"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
