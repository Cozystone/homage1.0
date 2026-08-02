"""Reproducible, bounded baseline recipe orchestrator.

This runner deliberately does not implement benchmark logic.  A versioned catalog
declares bounded commands and their evidence inputs; the runner executes those
commands without a shell and emits digest-only evidence.  Benchmark-owned reports
may be declared, but their contents are never copied into the manifest.

Recipes are intended to be read-only, but no filesystem sandbox is installed.
Writes are detected only on Git-visible and explicitly recorded repository
surfaces; outside-repository and other undeclared ignored writes are unobserved.

The word ``sealed`` has a narrow meaning here: Git tracked/non-ignored state and
the explicitly recorded input surfaces were clean/stable across the run. Ignored
paths outside those surfaces are not observed. It is not a capability claim.
Likewise, ``successful_reproduced`` only means that at least two bounded attempts
completed successfully with stable exit, stdout/stderr, and declared-report
digests.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
RUNNER_SOURCE = Path(__file__).resolve()
DEFAULT_CATALOG = ROOT / "data" / "eval" / "catalog" / "baseline_suite_v1.json"
DEFAULT_EVIDENCE_DIR = ROOT / "reports" / "baseline_evidence"

CATALOG_SCHEMA = "atanor.baseline-suite-catalog.v1"
MANIFEST_SCHEMA = "atanor.baseline-evidence-manifest.v1"
EVIDENCE_KIND = "command_execution_only"
MAX_SMOKE_SECONDS = 120
MAX_PROFILE_SECONDS = 3600
MAX_REPEATS = 10
MAX_COMMAND_ARGS = 128
MAX_COMMAND_CHARS = 32_768
MAX_STREAM_CAPTURE_BYTES = 2 * 1024 * 1024
PROCESS_POLL_SECONDS = 0.05
HASH_CHUNK_BYTES = 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RECIPE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")

# Only these non-secret controls may be copied into evidence.  Process-launch
# essentials (PATH, SYSTEMROOT, TEMP, and similar) are inherited for execution but
# are never serialized.
SAFE_RECORDED_ENV = frozenset(
    {
        "ATANOR_COGNITIVE_SHADOW",
        "ATANOR_CONTINUOUS_SELF_CYCLE_SHADOW",
        "ATANOR_DISABLE_PACK",
        "ATANOR_NETWORK_DISABLED",
        "ATANOR_WORLD4D_SHADOW",
        "CI",
        "CUDA_VISIBLE_DEVICES",
        "OMP_NUM_THREADS",
        "PYTHONHASHSEED",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    }
)
EXECUTION_ENV_KEYS = (
    "APPDATA",
    "COMSPEC",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USERPROFILE",
    "WINDIR",
)
ALLOWED_PLACEHOLDERS = frozenset({"python", "repo", "run_dir"})
PATH_GROUPS = ("suite_paths", "dataset_paths", "artifact_paths", "mutation_sensitive_paths")
DEPENDENCY_FILENAMES = frozenset(
    {
        "package-lock.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pyproject.toml",
        "requirements.txt",
        "requirements-cloud.txt",
        "requirements-edge.txt",
        "requirements-voice.txt",
        "uv.lock",
        "yarn.lock",
    }
)
PYTEST_EXACT_FLAGS = frozenset(
    {
        "-q",
        "-qq",
        "--quiet",
        "-v",
        "-vv",
        "--verbose",
        "--disable-warnings",
        "--strict-config",
        "--strict-markers",
    }
)
PYTEST_VALUE_FLAGS: dict[str, frozenset[str] | None] = {
    "--capture": frozenset({"fd", "sys", "no", "tee-sys"}),
    "--color": frozenset({"yes", "no", "auto"}),
    "--import-mode": frozenset({"prepend", "append", "importlib"}),
    "--maxfail": None,
    "--tb": frozenset({"auto", "long", "short", "line", "native", "no"}),
}


class BaselineError(RuntimeError):
    """Raised for invalid recipes, unsafe paths, or evidence integrity failures."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one canonical JSON representation used for manifest seals."""

    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise BaselineError(f"value is not canonical-JSON serializable: {type(exc).__name__}") from exc
    return text.encode("utf-8")


def compute_manifest_hash(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_hash", None)
    return sha256_bytes(canonical_json_bytes(unsigned))


def _json_without_duplicate_keys(raw: bytes, *, source: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise BaselineError(f"duplicate JSON key in {source}: {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except BaselineError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError(f"invalid UTF-8 JSON catalog {source}: {type(exc).__name__}") from exc


def _inside(base: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath((os.path.normcase(str(base)), os.path.normcase(str(candidate)))) == os.path.normcase(
            str(base)
        )
    except ValueError:
        return False


def _canonical_repo_root(repo_root: Path) -> Path:
    try:
        root = Path(repo_root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BaselineError(f"repository root cannot be resolved: {type(exc).__name__}") from exc
    if not root.is_dir():
        raise BaselineError(f"repository root is not a directory: {root}")
    return root


def _repo_path(repo_root: Path, relative: str, *, field: str, must_exist: bool = False) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise BaselineError(f"{field} must contain non-empty relative paths")
    path_obj = Path(relative)
    if path_obj.is_absolute():
        raise BaselineError(f"{field} path must be relative to the repository: {relative!r}")
    base = _canonical_repo_root(repo_root)
    candidate = Path(os.path.abspath(base / path_obj))
    if not _inside(base, candidate):
        raise BaselineError(f"{field} path escapes the repository: {relative!r}")
    if must_exist and not candidate.exists():
        raise BaselineError(f"{field} path does not exist: {relative!r}")
    return candidate


def _is_link_or_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except OSError:
        # Metadata that cannot be inspected is not a safe execution path.
        return True


def _secure_repo_path(repo_root: Path, relative: str, *, field: str, must_exist: bool = True) -> Path:
    """Resolve an execution target and reject link/reparse traversal below the root."""

    base = _canonical_repo_root(repo_root)
    lexical = _repo_path(base, relative, field=field, must_exist=must_exist)
    current = base
    try:
        parts = lexical.relative_to(base).parts
    except ValueError as exc:
        raise BaselineError(f"{field} path escapes the repository: {relative!r}") from exc
    for part in parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if _is_link_or_reparse(current):
                raise BaselineError(f"{field} traverses a symlink or reparse point: {relative!r}")
    try:
        resolved = lexical.resolve(strict=must_exist)
    except (OSError, RuntimeError) as exc:
        raise BaselineError(f"{field} cannot be resolved: {relative!r}") from exc
    if not _inside(base, resolved):
        raise BaselineError(f"{field} resolves outside the repository: {relative!r}")
    return resolved


def _secure_command_target(
    repo_root: Path,
    cwd: Path,
    target: str,
    *,
    field: str,
) -> Path:
    if not target or "\x00" in target or Path(target).is_absolute() or "{" in target or "}" in target:
        raise BaselineError(f"{field} must be a literal relative repository path")
    base = _canonical_repo_root(repo_root)
    candidate = Path(os.path.abspath(cwd / target))
    if not _inside(base, candidate):
        raise BaselineError(f"{field} path escapes the repository: {target!r}")
    relative = candidate.relative_to(base).as_posix()
    return _secure_repo_path(base, relative, field=field, must_exist=True)


def _reject_link_descendants(path: Path, *, field: str) -> None:
    """Reject links/reparse points under a pytest directory target."""

    if not path.is_dir():
        return
    for current, dir_names, file_names in os.walk(path, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in [*dir_names, *file_names]:
            child = current_path / name
            if _is_link_or_reparse(child):
                raise BaselineError(f"{field} contains a symlink or reparse point")


def _relative_posix(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def hash_repo_path(repo_root: Path, relative: str, *, require_exists: bool = False) -> dict[str, Any]:
    """Hash a declared repository path without following directory symlinks."""

    repo_root = _canonical_repo_root(repo_root)
    path = _repo_path(repo_root, relative, field="declared", must_exist=require_exists)
    normalized = _relative_posix(repo_root, path)

    if not path.exists() and not path.is_symlink():
        marker = b"MISSING\0" + normalized.encode("utf-8", errors="surrogateescape")
        return {"path": normalized, "kind": "missing", "sha256": sha256_bytes(marker), "bytes": 0, "files": 0}

    if path.is_symlink():
        target = os.readlink(path)
        payload = b"SYMLINK\0" + normalized.encode("utf-8", errors="surrogateescape") + b"\0" + os.fsencode(target)
        return {"path": normalized, "kind": "symlink", "sha256": sha256_bytes(payload), "bytes": len(payload), "files": 0}

    if path.is_file():
        digest, size = _hash_file(path)
        return {"path": normalized, "kind": "file", "sha256": digest, "bytes": size, "files": 1}

    if not path.is_dir():
        raise BaselineError(f"unsupported declared path type: {normalized!r}")

    digest = hashlib.sha256()
    total_bytes = 0
    file_count = 0
    base = path
    for current, dir_names, file_names in os.walk(base, topdown=True, followlinks=False):
        current_path = Path(current)
        dir_names.sort()
        file_names.sort()

        kept_dirs: list[str] = []
        for name in dir_names:
            child = current_path / name
            rel = child.relative_to(base).as_posix()
            if child.is_symlink():
                target = os.readlink(child)
                entry = b"L\0" + rel.encode("utf-8", errors="surrogateescape") + b"\0" + os.fsencode(target) + b"\0"
                digest.update(entry)
                total_bytes += len(entry)
            else:
                digest.update(b"D\0" + rel.encode("utf-8", errors="surrogateescape") + b"\0")
                kept_dirs.append(name)
        dir_names[:] = kept_dirs

        for name in file_names:
            child = current_path / name
            rel = child.relative_to(base).as_posix()
            if child.is_symlink():
                target = os.readlink(child)
                entry = b"L\0" + rel.encode("utf-8", errors="surrogateescape") + b"\0" + os.fsencode(target) + b"\0"
                digest.update(entry)
                total_bytes += len(entry)
                continue
            if not child.is_file():
                raise BaselineError(f"unsupported entry in declared directory: {(Path(normalized) / rel).as_posix()}")
            child_digest, child_size = _hash_file(child)
            digest.update(
                b"F\0"
                + rel.encode("utf-8", errors="surrogateescape")
                + b"\0"
                + str(child_size).encode("ascii")
                + b"\0"
                + child_digest.encode("ascii")
                + b"\0"
            )
            total_bytes += child_size
            file_count += 1
    return {
        "path": normalized,
        "kind": "directory",
        "sha256": digest.hexdigest(),
        "bytes": total_bytes,
        "files": file_count,
    }


def hash_declared_paths(
    repo_root: Path,
    paths: Iterable[str],
    *,
    require_exists: bool,
) -> list[dict[str, Any]]:
    unique = sorted(set(paths))
    return [hash_repo_path(repo_root, path, require_exists=require_exists) for path in unique]


def _run_git(repo_root: Path, args: Sequence[str], *, allow_failure: bool = False) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        shell=False,
        check=False,
    )
    if completed.returncode != 0 and not allow_failure:
        raise BaselineError(f"git command failed ({args[0]}): exit {completed.returncode}")
    return completed.stdout


def _count_status_records(blob: bytes) -> int:
    # In porcelain-v1 -z, rename/copy records add an origin path without an XY
    # prefix.  Count only records with the documented ``XY `` prefix.
    return sum(1 for part in blob.split(b"\0") if len(part) >= 3 and part[2:3] == b" ")


def collect_git_state(
    repo_root: Path,
    *,
    exclude_untracked_paths: Iterable[str] = (),
) -> dict[str, Any]:
    repo_root = _canonical_repo_root(repo_root)
    if not (repo_root / ".git").exists():
        # Worktrees may use a .git file, so the existence test intentionally
        # accepts both files and directories.
        raise BaselineError(f"repository root has no .git metadata: {repo_root}")

    head = _run_git(repo_root, ["rev-parse", "HEAD"]).decode("ascii", errors="strict").strip()
    branch_raw = _run_git(repo_root, ["symbolic-ref", "--quiet", "--short", "HEAD"], allow_failure=True)
    branch = branch_raw.decode("utf-8", errors="replace").strip() or None
    tracked_diff = _run_git(repo_root, ["diff", "--no-ext-diff", "--binary", "HEAD", "--"])
    dirty_paths = _run_git(repo_root, ["status", "--porcelain=v1", "-z", "--untracked-files=no"])
    excluded: set[str] = set()
    for relative in exclude_untracked_paths:
        path = _repo_path(repo_root, relative, field="git-state exclusion", must_exist=False)
        excluded.add(_relative_posix(repo_root, path))
    untracked_paths_raw = _run_git(repo_root, ["ls-files", "--others", "--exclude-standard", "-z"])
    included_untracked_raw: list[bytes] = []
    for raw in untracked_paths_raw.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        if relative not in excluded:
            included_untracked_raw.append(raw)
    untracked_paths = (
        b"\0".join(included_untracked_raw) + (b"\0" if included_untracked_raw else b"")
    )
    untracked_records: list[dict[str, Any]] = []
    for raw in untracked_paths.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        untracked_records.append(hash_repo_path(repo_root, relative, require_exists=False))
    untracked_records.sort(key=lambda item: str(item["path"]))
    # Keep both the exact path-to-content binding and a content-only digest.
    # Neither exposes untracked names or bytes in the manifest.
    untracked_content_records = [
        {key: record.get(key) for key in ("kind", "sha256", "bytes", "files")}
        for record in untracked_records
    ]
    untracked_content_records.sort(key=canonical_json_bytes)
    untracked_content_digest = sha256_bytes(canonical_json_bytes(untracked_records))
    untracked_content_only_digest = sha256_bytes(canonical_json_bytes(untracked_content_records))
    return {
        "head": head,
        "branch": branch,
        "tracked_diff": {"sha256": sha256_bytes(tracked_diff), "bytes": len(tracked_diff)},
        "dirty_tracked_paths": {
            "sha256": sha256_bytes(dirty_paths),
            "entry_count": _count_status_records(dirty_paths),
        },
        "untracked_paths": {
            "sha256": sha256_bytes(untracked_paths),
            "content_sha256": untracked_content_digest,
            "content_only_sha256": untracked_content_only_digest,
            "entry_count": sum(1 for item in untracked_paths.split(b"\0") if item),
            "bytes": sum(int(item.get("bytes", 0)) for item in untracked_records),
        },
        "clean": not dirty_paths and not untracked_paths,
    }


def _output_exclusion(repo_root: Path, output_path: Path) -> str | None:
    """Return a safe exact untracked-output exclusion for an in-repo manifest."""

    repo_root = _canonical_repo_root(repo_root)
    lexical_output = Path(os.path.abspath(output_path))
    if not _inside(repo_root, lexical_output):
        return None
    relative = lexical_output.relative_to(repo_root).as_posix()
    tracked = _run_git(
        repo_root,
        ["ls-files", "-z", "--", f":(literal){relative}"],
        allow_failure=True,
    )
    if tracked:
        raise BaselineError(
            "evidence output is a tracked repository path; refusing to exclude it from source state"
        )
    return relative


def collect_runner_source(repo_root: Path) -> dict[str, Any]:
    """Bind the executing baseline implementation independently of the catalog."""

    repo_root = _canonical_repo_root(repo_root)
    try:
        source = Path(RUNNER_SOURCE).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BaselineError(f"baseline runner source cannot be resolved: {type(exc).__name__}") from exc
    if not source.is_file():
        raise BaselineError("baseline runner source is not a regular file")
    digest, size = _hash_file(source)
    inside_repository = _inside(repo_root, source)
    return {
        "implementation": "scripts.baseline_suite",
        "location": "repository" if inside_repository else "outside_target_repository",
        "path": _relative_posix(repo_root, source) if inside_repository else None,
        "sha256": digest,
        "bytes": size,
    }


def collect_dependency_paths(repo_root: Path) -> list[str]:
    """Return tracked dependency descriptors without scanning generated data trees."""
    tracked = _run_git(repo_root, ["ls-files", "-z"])
    paths: list[str] = []
    for raw in tracked.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        if Path(relative).name in DEPENDENCY_FILENAMES:
            paths.append(relative)
    return sorted(set(paths))


def collect_hardware_state() -> dict[str, Any]:
    """Record bounded hardware facts; absence stays explicit rather than inferred."""
    memory_bytes: int | None = None
    memory_probe = "unavailable"
    if os.name == "nt":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                memory_bytes = int(status.total_physical)
                memory_probe = "windows_global_memory_status"
        except Exception:
            memory_bytes = None
    elif hasattr(os, "sysconf"):
        try:
            pages = int(os.sysconf("SC_PHYS_PAGES"))
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            if pages > 0 and page_size > 0:
                memory_bytes = pages * page_size
                memory_probe = "posix_sysconf"
        except (OSError, TypeError, ValueError):
            memory_bytes = None
    return {
        "processor": platform.processor() or None,
        "logical_cpu_count": os.cpu_count(),
        "physical_memory_bytes": memory_bytes,
        "memory_probe": memory_probe,
        "gpu": {
            "status": "not_probed",
            "reason": "baseline runner does not invoke vendor-specific tooling",
        },
    }


def collect_python_environment() -> dict[str, Any]:
    """Bind the interpreter binary and installed distribution name/version set."""

    try:
        executable = Path(sys.executable).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BaselineError(f"Python executable cannot be resolved: {type(exc).__name__}") from exc
    if not executable.is_file():
        raise BaselineError("Python executable is not a regular file")
    executable_digest, executable_size = _hash_file(executable)

    distributions: list[dict[str, str]] = []
    try:
        for distribution in importlib.metadata.distributions():
            name = distribution.metadata.get("Name")
            version = distribution.version
            if not isinstance(name, str) or not name.strip() or not isinstance(version, str):
                continue
            distributions.append({"name": name.strip().lower(), "version": version})
    except Exception as exc:
        raise BaselineError(
            f"installed Python distributions cannot be enumerated: {type(exc).__name__}"
        ) from exc
    distributions.sort(key=lambda item: (item["name"], item["version"]))
    return {
        "executable": {
            "name": executable.name,
            "sha256": executable_digest,
            "bytes": executable_size,
        },
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "cache_tag": getattr(sys.implementation, "cache_tag", None),
        "installed_distributions": {
            "name_version_sha256": sha256_bytes(canonical_json_bytes(distributions)),
            "entry_count": len(distributions),
            "scope": "normalized_distribution_name_and_version_only",
        },
    }


def _validate_string_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise BaselineError(f"{field} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise BaselineError(f"{field} contains duplicate entries")
    return value


def _validate_placeholders(values: Iterable[str], *, field: str) -> None:
    for value in values:
        found = set(PLACEHOLDER_RE.findall(value))
        unknown = found - ALLOWED_PLACEHOLDERS
        if unknown:
            raise BaselineError(f"{field} uses unsupported placeholders: {sorted(unknown)}")
        # Unmatched braces are almost always a malformed recipe and can obscure
        # what was actually executed.
        stripped = PLACEHOLDER_RE.sub("", value)
        if "{" in stripped or "}" in stripped:
            raise BaselineError(f"{field} contains unmatched braces")


def _validate_recipe_command(recipe_id: str, command: list[str]) -> None:
    if not command or len(command) > MAX_COMMAND_ARGS:
        raise BaselineError(f"recipe {recipe_id!r} command must contain 1..{MAX_COMMAND_ARGS} arguments")
    if any(not isinstance(arg, str) or not arg or "\x00" in arg or "\n" in arg or "\r" in arg for arg in command):
        raise BaselineError(f"recipe {recipe_id!r} command arguments must be non-empty single-line strings")
    if sum(len(arg) for arg in command) > MAX_COMMAND_CHARS:
        raise BaselineError(f"recipe {recipe_id!r} command is too large")
    _validate_placeholders(command, field=f"recipe {recipe_id!r} command")
    if command[0] != "{python}":
        raise BaselineError(f"recipe {recipe_id!r} must use the pinned {{python}} executable")
    if len(command) < 2:
        raise BaselineError(f"recipe {recipe_id!r} has no Python entry point")
    if command[1] == "-c" or command[1] == "-":
        raise BaselineError(f"recipe {recipe_id!r} may not execute inline or stdin Python")
    if command[1] == "-m":
        if len(command) < 3 or command[2] != "pytest":
            raise BaselineError(f"recipe {recipe_id!r} may only invoke the approved pytest module")
    elif not command[1].endswith(".py") or "{" in command[1]:
        raise BaselineError(f"recipe {recipe_id!r} Python entry point must be a repository .py file")


def _validate_pytest_arguments(
    recipe_id: str,
    command: Sequence[str],
    *,
    repo_root: Path,
    cwd: Path,
) -> None:
    targets = 0
    for argument in command[3:]:
        if argument in PYTEST_EXACT_FLAGS:
            continue
        if argument.startswith("-"):
            flag, separator, value = argument.partition("=")
            allowed_values = PYTEST_VALUE_FLAGS.get(flag)
            if not separator or flag not in PYTEST_VALUE_FLAGS:
                raise BaselineError(f"recipe {recipe_id!r} uses unapproved pytest flag: {argument!r}")
            if flag == "--maxfail":
                if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 100:
                    raise BaselineError(f"recipe {recipe_id!r} has invalid pytest --maxfail")
            elif allowed_values is None or value not in allowed_values:
                raise BaselineError(f"recipe {recipe_id!r} has invalid pytest flag value: {argument!r}")
            continue

        path_text = argument.split("::", 1)[0]
        target = _secure_command_target(
            repo_root,
            cwd,
            path_text,
            field=f"recipe {recipe_id!r} pytest target",
        )
        if not target.is_dir() and not (target.is_file() and target.suffix == ".py"):
            raise BaselineError(
                f"recipe {recipe_id!r} pytest target must be a repository directory or .py file"
            )
        _reject_link_descendants(
            target,
            field=f"recipe {recipe_id!r} pytest target",
        )
        targets += 1
    if targets == 0:
        raise BaselineError(f"recipe {recipe_id!r} pytest command requires an explicit repository test target")


def load_catalog(catalog_path: Path, repo_root: Path = ROOT) -> tuple[dict[str, Any], str, str]:
    repo_root = _canonical_repo_root(repo_root)
    lexical_catalog = Path(os.path.abspath(catalog_path))
    if not _inside(repo_root, lexical_catalog):
        raise BaselineError("catalog must be inside the repository")
    relative_catalog = lexical_catalog.relative_to(repo_root).as_posix()
    catalog_path = _secure_repo_path(
        repo_root,
        relative_catalog,
        field="catalog",
        must_exist=True,
    )
    if not catalog_path.is_file():
        raise BaselineError(f"catalog does not exist: {catalog_path}")
    raw = catalog_path.read_bytes()
    parsed = _json_without_duplicate_keys(raw, source=catalog_path)
    if not isinstance(parsed, dict) or parsed.get("schema") != CATALOG_SCHEMA:
        raise BaselineError(f"catalog schema must be {CATALOG_SCHEMA!r}")
    profiles = parsed.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise BaselineError("catalog profiles must be a non-empty object")
    return parsed, sha256_bytes(raw), _relative_posix(repo_root, catalog_path)


def validate_profile(catalog: Mapping[str, Any], profile_name: str, repo_root: Path) -> dict[str, Any]:
    repo_root = _canonical_repo_root(repo_root)
    profiles = catalog.get("profiles")
    profile = profiles.get(profile_name) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        raise BaselineError(f"unknown baseline profile: {profile_name!r}")

    max_total = profile.get("max_total_seconds")
    if not isinstance(max_total, int) or isinstance(max_total, bool) or not 1 <= max_total <= MAX_PROFILE_SECONDS:
        raise BaselineError(f"profile {profile_name!r} has invalid max_total_seconds")
    if profile_name == "smoke" and max_total > MAX_SMOKE_SECONDS:
        raise BaselineError(f"smoke profile exceeds {MAX_SMOKE_SECONDS} seconds")

    env_allowlist = _validate_string_list(profile.get("env_allowlist", []), field="env_allowlist")
    disallowed_env = set(env_allowlist) - SAFE_RECORDED_ENV
    if disallowed_env:
        raise BaselineError(f"profile requests unsafe recorded environment keys: {sorted(disallowed_env)}")
    environment = profile.get("environment", {})
    if not isinstance(environment, dict):
        raise BaselineError("profile environment must be an object")
    if set(environment) - SAFE_RECORDED_ENV:
        raise BaselineError(f"profile sets unsafe environment keys: {sorted(set(environment) - SAFE_RECORDED_ENV)}")
    if any(not isinstance(value, str) or "\x00" in value for value in environment.values()):
        raise BaselineError("profile environment values must be strings without NUL bytes")
    if environment.get("ATANOR_DISABLE_PACK", "1") != "1":
        raise BaselineError(
            "bounded baseline profiles cannot enable the asynchronous world-pack warmer"
        )

    recipes = profile.get("recipes")
    if not isinstance(recipes, list) or not recipes:
        raise BaselineError(f"profile {profile_name!r} recipes must be a non-empty list")
    seen_ids: set[str] = set()
    worst_case = 0
    normalized_recipes: list[dict[str, Any]] = []
    for raw_recipe in recipes:
        if not isinstance(raw_recipe, dict):
            raise BaselineError("every recipe must be an object")
        recipe_id = raw_recipe.get("id")
        if not isinstance(recipe_id, str) or not RECIPE_ID_RE.fullmatch(recipe_id) or recipe_id in seen_ids:
            raise BaselineError(f"invalid or duplicate recipe id: {recipe_id!r}")
        seen_ids.add(recipe_id)
        if raw_recipe.get("network_required", False) is not False:
            raise BaselineError(f"recipe {recipe_id!r} requires network access")

        command = raw_recipe.get("command")
        if not isinstance(command, list):
            raise BaselineError(f"recipe {recipe_id!r} command must be a list")
        _validate_recipe_command(recipe_id, command)

        cwd = raw_recipe.get("cwd", ".")
        cwd_path = _secure_repo_path(
            repo_root,
            cwd,
            field=f"recipe {recipe_id!r} cwd",
            must_exist=True,
        )
        if not cwd_path.is_dir():
            raise BaselineError(f"recipe {recipe_id!r} cwd is not a directory")
        if command[1] == "-m":
            _validate_pytest_arguments(
                recipe_id,
                command,
                repo_root=repo_root,
                cwd=cwd_path,
            )
        else:
            entry_point = _secure_command_target(
                repo_root,
                cwd_path,
                command[1],
                field=f"recipe {recipe_id!r} Python entry point",
            )
            if not entry_point.is_file() or entry_point.suffix != ".py":
                raise BaselineError(
                    f"recipe {recipe_id!r} Python entry point must be a regular repository .py file"
                )

        timeout = raw_recipe.get("timeout_seconds")
        repeat = raw_recipe.get("repeat", 1)
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= max_total:
            raise BaselineError(f"recipe {recipe_id!r} has invalid timeout_seconds")
        if not isinstance(repeat, int) or isinstance(repeat, bool) or not 1 <= repeat <= MAX_REPEATS:
            raise BaselineError(f"recipe {recipe_id!r} has invalid repeat")
        worst_case += timeout * repeat

        normalized = dict(raw_recipe)
        normalized["cwd"] = _relative_posix(repo_root, cwd_path)
        normalized["timeout_seconds"] = timeout
        normalized["repeat"] = repeat
        for group in PATH_GROUPS:
            entries = _validate_string_list(raw_recipe.get(group, []), field=f"recipe {recipe_id!r} {group}")
            for entry in entries:
                _repo_path(repo_root, entry, field=f"recipe {recipe_id!r} {group}")
            normalized[group] = entries

        reports = _validate_string_list(raw_recipe.get("report_paths", []), field=f"recipe {recipe_id!r} report_paths")
        _validate_placeholders(reports, field=f"recipe {recipe_id!r} report_paths")
        for report in reports:
            if "{repo}" in report or Path(report.replace("{run_dir}", ".")).is_absolute():
                raise BaselineError(f"recipe {recipe_id!r} report path must stay in its unique run directory")
        normalized["report_paths"] = reports
        normalized_recipes.append(normalized)

    if worst_case > max_total:
        raise BaselineError(
            f"profile {profile_name!r} worst-case command budget {worst_case}s exceeds {max_total}s"
        )

    normalized_profile = dict(profile)
    normalized_profile["env_allowlist"] = env_allowlist
    normalized_profile["environment"] = environment
    normalized_profile["recipes"] = normalized_recipes
    normalized_profile["worst_case_seconds"] = worst_case
    return normalized_profile


def _expand_argument(value: str, *, repo_root: Path, run_dir: Path) -> str:
    replacements = {
        "{python}": sys.executable,
        "{repo}": str(repo_root),
        "{run_dir}": str(run_dir),
    }
    result = value
    for token, replacement in replacements.items():
        result = result.replace(token, replacement)
    return result


def _child_environment(profile: Mapping[str, Any]) -> dict[str, str]:
    child: dict[str, str] = {}
    for key in EXECUTION_ENV_KEYS:
        value = os.environ.get(key)
        if value is not None:
            child[key] = value
    child.update(
        {
            "ATANOR_NETWORK_DISABLED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        }
    )
    child.update(profile.get("environment", {}))
    # Importing graph_scale.answer_bridge otherwise starts an asynchronous read
    # of the 115M-row world pack. A bounded baseline recipe must never trigger
    # that undeclared background workload, even if the parent environment or a
    # malformed catalog asks for it.
    child["ATANOR_DISABLE_PACK"] = "1"
    return child


def _recorded_environment(profile: Mapping[str, Any], child_env: Mapping[str, str]) -> dict[str, Any]:
    keys = sorted(set(profile.get("env_allowlist", [])))
    return {
        "allowlist": keys,
        "values": {key: child_env[key] if key in child_env else None for key in keys},
    }


def _kill_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            # Exact PID, no shell. /T closes descendants so a timed-out recipe
            # cannot leave helpers writing after evidence collection.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                shell=False,
                check=False,
            )
            if process.poll() is None:
                process.kill()
    except (OSError, ProcessLookupError):
        pass


def _bounded_stream_reader(
    stream: Any,
    *,
    limit_bytes: int,
    overflow_event: threading.Event,
) -> tuple[threading.Thread, dict[str, Any]]:
    result: dict[str, Any] = {}

    def consume() -> None:
        digest = hashlib.sha256()
        captured = 0
        observed = 0
        capture_error: str | None = None
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                observed += len(chunk)
                remaining = max(0, limit_bytes - captured)
                if remaining:
                    prefix = chunk[:remaining]
                    digest.update(prefix)
                    captured += len(prefix)
                if observed > limit_bytes:
                    overflow_event.set()
                    # Closing the read end applies backpressure immediately;
                    # the supervisor then terminates the whole process group.
                    break
        except (OSError, ValueError) as exc:
            capture_error = type(exc).__name__
        finally:
            try:
                stream.close()
            except OSError:
                pass
            result.update(
                {
                    "sha256": digest.hexdigest(),
                    "bytes": captured,
                    "observed_bytes": observed,
                    "limit_bytes": limit_bytes,
                    "truncated": observed > limit_bytes,
                    "capture_error": capture_error,
                }
            )

    thread = threading.Thread(target=consume, name="baseline-output-reader", daemon=True)
    thread.start()
    return thread, result


def _empty_stream_digest() -> dict[str, Any]:
    return {
        "sha256": sha256_bytes(b""),
        "bytes": 0,
        "observed_bytes": 0,
        "limit_bytes": MAX_STREAM_CAPTURE_BYTES,
        "truncated": False,
        "capture_error": None,
    }


def _resolve_report_path(run_dir: Path, template: str) -> tuple[Path, str]:
    expanded = template.replace("{run_dir}", str(run_dir))
    path_obj = Path(expanded)
    candidate = path_obj if path_obj.is_absolute() else run_dir / path_obj
    candidate = Path(os.path.abspath(candidate))
    run_root = Path(os.path.abspath(run_dir))
    if not _inside(run_root, candidate) or candidate == run_root:
        raise BaselineError(f"report path escapes unique run directory: {template!r}")
    try:
        display = candidate.relative_to(run_root).as_posix()
    except ValueError as exc:  # Defensive; _inside already guards this.
        raise BaselineError(f"report path is not relative to run directory: {template!r}") from exc
    return candidate, display


def _report_path_is_safe(run_dir: Path, candidate: Path) -> bool:
    try:
        run_root = Path(run_dir).resolve(strict=True)
        lexical = Path(os.path.abspath(candidate))
        if not _inside(run_root, lexical) or lexical == run_root:
            return False
        current = run_root
        for part in lexical.relative_to(run_root).parts:
            current = current / part
            if current.exists() or current.is_symlink():
                if _is_link_or_reparse(current):
                    return False
        resolved = lexical.resolve(strict=False)
        return _inside(run_root, resolved) and resolved != run_root
    except (OSError, RuntimeError, ValueError):
        return False


def _hash_reports(run_dir: Path, report_templates: Sequence[str]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for template in report_templates:
        path, display = _resolve_report_path(run_dir, template)
        if not _report_path_is_safe(run_dir, path):
            reports.append(
                {
                    "path": display,
                    "exists": path.exists(),
                    "regular_file": False,
                    "unsafe_path": True,
                    "sha256": None,
                    "bytes": 0,
                }
            )
            continue
        if not path.exists():
            reports.append({"path": display, "exists": False, "sha256": None, "bytes": 0})
            continue
        if not path.is_file() or path.is_symlink():
            reports.append({"path": display, "exists": True, "regular_file": False, "sha256": None, "bytes": 0})
            continue
        digest, size = _hash_file(path)
        reports.append(
            {"path": display, "exists": True, "regular_file": True, "sha256": digest, "bytes": size}
        )
    return reports


def _execute_attempt(
    recipe: Mapping[str, Any],
    *,
    repo_root: Path,
    profile: Mapping[str, Any],
    attempt_index: int,
    run_dir: Path,
) -> dict[str, Any]:
    report_templates = recipe.get("report_paths", [])
    for template in report_templates:
        report_path, _ = _resolve_report_path(run_dir, template)
        if report_path.exists():
            raise BaselineError("unique run report path unexpectedly already exists")
        report_path.parent.mkdir(parents=True, exist_ok=True)

    command_template = list(recipe["command"])
    resolved_command = [
        _expand_argument(arg, repo_root=repo_root, run_dir=run_dir) for arg in command_template
    ]
    cwd = _secure_repo_path(
        repo_root,
        recipe["cwd"],
        field=f"recipe {recipe['id']!r} cwd",
        must_exist=True,
    )
    timeout = int(recipe["timeout_seconds"])
    started = time.monotonic()
    timed_out = False
    output_limit_exceeded = False
    launch_error: str | None = None
    exit_code: int | None = None
    stdout_digest = _empty_stream_digest()
    stderr_digest = _empty_stream_digest()
    process: subprocess.Popen[bytes] | None = None
    reader_threads: list[threading.Thread] = []
    reader_results: list[dict[str, Any]] = []
    overflow_event = threading.Event()
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            resolved_command,
            cwd=cwd,
            env=_child_environment(profile),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=(os.name == "posix"),
            creationflags=creationflags,
        )
        if process.stdout is None or process.stderr is None:
            raise OSError("subprocess output pipes unavailable")
        stdout_thread, stdout_result = _bounded_stream_reader(
            process.stdout,
            limit_bytes=MAX_STREAM_CAPTURE_BYTES,
            overflow_event=overflow_event,
        )
        stderr_thread, stderr_result = _bounded_stream_reader(
            process.stderr,
            limit_bytes=MAX_STREAM_CAPTURE_BYTES,
            overflow_event=overflow_event,
        )
        reader_threads = [stdout_thread, stderr_thread]
        reader_results = [stdout_result, stderr_result]
        deadline = started + timeout
        while process.poll() is None:
            if overflow_event.is_set():
                output_limit_exceeded = True
                _kill_process(process)
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                _kill_process(process)
                break
            try:
                process.wait(timeout=min(PROCESS_POLL_SECONDS, remaining))
            except subprocess.TimeoutExpired:
                continue
        if process.poll() is None:
            _kill_process(process)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _kill_process(process)
        for thread in reader_threads:
            thread.join(timeout=10)
        if any(thread.is_alive() for thread in reader_threads):
            launch_error = "OutputReaderDidNotStop"
        output_limit_exceeded = output_limit_exceeded or overflow_event.is_set()
        if len(reader_results) == 2:
            stdout_digest = reader_results[0] or _empty_stream_digest()
            stderr_digest = reader_results[1] or _empty_stream_digest()
        exit_code = process.returncode
    except OSError as exc:
        launch_error = type(exc).__name__
        if process is not None:
            _kill_process(process)
    duration = round(time.monotonic() - started, 6)
    reports = _hash_reports(run_dir, report_templates)
    reports_complete = all(
        report.get("exists") is True
        and report.get("regular_file", True) is True
        and isinstance(report.get("sha256"), str)
        for report in reports
    )
    capture_error = any(
        digest.get("capture_error") is not None for digest in (stdout_digest, stderr_digest)
    )
    successful = (
        exit_code == 0
        and not timed_out
        and not output_limit_exceeded
        and not capture_error
        and launch_error is None
        and reports_complete
    )
    outcome = {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "output_limit_exceeded": output_limit_exceeded,
        "output_capture_error": capture_error,
        "launch_error": launch_error,
        "stdout_sha256": stdout_digest["sha256"],
        "stderr_sha256": stderr_digest["sha256"],
        "reports": [{"path": item["path"], "sha256": item.get("sha256")} for item in reports],
    }
    return {
        "attempt": attempt_index,
        "command": command_template,
        "cwd": recipe["cwd"],
        "timeout_seconds": timeout,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "output_limit_exceeded": output_limit_exceeded,
        "output_capture_error": capture_error,
        "launch_error": launch_error,
        "duration_seconds": duration,
        "stdout": stdout_digest,
        "stderr": stderr_digest,
        "reports": reports,
        "outcome_sha256": sha256_bytes(canonical_json_bytes(outcome)),
        "successful": successful,
    }


def _repeat_summary(attempts: Sequence[Mapping[str, Any]], requested: int) -> dict[str, Any]:
    successful = [attempt for attempt in attempts if attempt.get("successful") is True]
    fingerprints: dict[str, int] = {}
    for attempt in attempts:
        fingerprint = str(attempt.get("outcome_sha256"))
        fingerprints[fingerprint] = fingerprints.get(fingerprint, 0) + 1
    stable_success = (
        requested >= 2
        and len(attempts) == requested
        and len(successful) == requested
        and len(fingerprints) == 1
    )
    return {
        "evidence_kind": EVIDENCE_KIND,
        "attempts_requested": requested,
        "attempts_completed": len(attempts),
        "successful_attempts": len(successful),
        "timeouts": sum(1 for attempt in attempts if attempt.get("timed_out") is True),
        "output_limit_exceeded_attempts": sum(
            1 for attempt in attempts if attempt.get("output_limit_exceeded") is True
        ),
        "failed_attempts": sum(1 for attempt in attempts if attempt.get("successful") is not True),
        "outcome_digest_counts": dict(sorted(fingerprints.items())),
        "stable_outcome": len(fingerprints) == 1 and len(attempts) == requested,
        "successful_reproduced": stable_success,
        "benchmark_metrics": {
            "status": "not_parsed_by_recipe_orchestrator",
            "accuracy": None,
            "coverage": None,
            "firing_rate": None,
            "latency_ms": None,
            "resource_use": None,
        },
    }


def _collect_input_paths(profile: Mapping[str, Any], group: str) -> list[str]:
    result: set[str] = set()
    for recipe in profile["recipes"]:
        result.update(recipe.get(group, []))
    return sorted(result)


def _same_git_fingerprint(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    return all(
        before.get(field) == after.get(field)
        for field in ("head", "branch", "tracked_diff", "dirty_tracked_paths", "untracked_paths")
    )


def _default_output_path() -> Path:
    DEFAULT_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    suffix = uuid.uuid4().hex[:12]
    return DEFAULT_EVIDENCE_DIR / f"baseline_{stamp}_{suffix}.manifest.json"


def write_manifest_exclusive(path: Path, manifest: Mapping[str, Any]) -> None:
    """Write evidence exactly once; an existing path is never replaced."""

    path = Path(os.path.abspath(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    except BaseException:
        # The exclusive file may be partial, but preserving it is safer than
        # deleting evidence at a path another operator may now be inspecting.
        raise


def run_suite(
    *,
    profile_name: str = "smoke",
    catalog_path: Path = DEFAULT_CATALOG,
    repo_root: Path = ROOT,
    output_path: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    repo_root = _canonical_repo_root(repo_root)
    catalog_path = Path(os.path.abspath(catalog_path))
    output_path = Path(os.path.abspath(output_path or _default_output_path()))
    if output_path.exists() or output_path.is_symlink():
        raise BaselineError(f"evidence path already exists; refusing overwrite: {output_path}")

    catalog, catalog_digest, catalog_relative = load_catalog(catalog_path, repo_root)
    profile = validate_profile(catalog, profile_name, repo_root)
    evidence_output_exclusion = _output_exclusion(repo_root, output_path)
    git_exclusions = [evidence_output_exclusion] if evidence_output_exclusion is not None else []
    runner_before = collect_runner_source(repo_root)
    python_environment_before = collect_python_environment()
    git_before = collect_git_state(repo_root, exclude_untracked_paths=git_exclusions)
    dependency_paths = collect_dependency_paths(repo_root)
    suite_paths = _collect_input_paths(profile, "suite_paths")
    dataset_paths = _collect_input_paths(profile, "dataset_paths")
    artifact_paths = _collect_input_paths(profile, "artifact_paths")
    input_hashes = {
        "suites": hash_declared_paths(
            repo_root, suite_paths, require_exists=True
        ),
        "datasets": hash_declared_paths(
            repo_root, dataset_paths, require_exists=True
        ),
        "artifacts": hash_declared_paths(
            repo_root, artifact_paths, require_exists=True
        ),
        "dependencies": hash_declared_paths(
            repo_root, dependency_paths, require_exists=True
        ),
    }
    explicit_mutation_paths = _collect_input_paths(profile, "mutation_sensitive_paths")
    automatic_mutation_paths = sorted(
        set(
            suite_paths
            + dataset_paths
            + artifact_paths
            + dependency_paths
            + [catalog_relative]
        )
    )
    mutation_paths = sorted(set(explicit_mutation_paths + automatic_mutation_paths))
    mutation_before = hash_declared_paths(repo_root, mutation_paths, require_exists=False)
    child_env = _child_environment(profile)

    recipe_results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="atanor-baseline-") as temp_root_raw:
        temp_root = Path(temp_root_raw)
        for recipe in profile["recipes"]:
            attempts: list[dict[str, Any]] = []
            for attempt_index in range(1, int(recipe["repeat"]) + 1):
                attempt_run_dir = temp_root / recipe["id"] / f"attempt-{attempt_index}"
                attempt_run_dir.mkdir(parents=True, exist_ok=False)
                attempts.append(
                    _execute_attempt(
                        recipe,
                        repo_root=repo_root,
                        profile=profile,
                        attempt_index=attempt_index,
                        run_dir=attempt_run_dir,
                    )
                )
            recipe_results.append(
                {
                    "id": recipe["id"],
                    "attempts": attempts,
                    "repeat_metrics": _repeat_summary(attempts, int(recipe["repeat"])),
                }
            )

    mutation_after = hash_declared_paths(repo_root, mutation_paths, require_exists=False)
    observed_path_mutation_detected = mutation_before != mutation_after
    git_after = collect_git_state(repo_root, exclude_untracked_paths=git_exclusions)
    repository_mutation_detected = not _same_git_fingerprint(git_before, git_after)
    runner_after = collect_runner_source(repo_root)
    runner_mutation_detected = runner_before != runner_after
    python_environment_after = collect_python_environment()
    python_environment_mutation_detected = (
        python_environment_before != python_environment_after
    )
    mutation_detected = (
        observed_path_mutation_detected
        or repository_mutation_detected
        or runner_mutation_detected
        or python_environment_mutation_detected
    )
    reproduced = (
        bool(recipe_results)
        and all(item["repeat_metrics"]["successful_reproduced"] is True for item in recipe_results)
        and not mutation_detected
    )
    successful = (
        bool(recipe_results)
        and all(
            attempt["successful"] is True
            for recipe_result in recipe_results
            for attempt in recipe_result["attempts"]
        )
        and not mutation_detected
    )

    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "evidence_kind": EVIDENCE_KIND,
        "created_at_utc": utc_now(),
        "catalog": {
            "path": catalog_relative,
            "sha256": catalog_digest,
            "catalog_id": catalog.get("catalog_id"),
        },
        "profile": {
            "name": profile_name,
            "max_total_seconds": profile["max_total_seconds"],
            "worst_case_seconds": profile["worst_case_seconds"],
        },
        "source": {
            "excluded_evidence_output": evidence_output_exclusion,
            "runner": runner_before,
            "runner_after": runner_after,
            "runner_mutation_detected": runner_mutation_detected,
            "git": git_before,
            "git_after": git_after,
            "repository_mutation_detected": repository_mutation_detected,
            "sealed": git_before["clean"] is True and not mutation_detected,
            "sealed_scope": (
                "git_tracked_and_nonignored_untracked_plus_recorded_input_surfaces_and_"
                "python_environment; "
                "ignored_paths_outside_recorded_surfaces_unobserved"
            ),
        },
        "environment": _recorded_environment(profile, child_env),
        "network_control": {
            "requested": "offline",
            "mechanism": "cooperative_environment_flag_only",
            "enforced": False,
            "environment_flag": "ATANOR_NETWORK_DISABLED",
            "note": (
                "The runner strips nonessential environment variables and sets an offline flag, "
                "but it does not install an OS firewall or network namespace."
            ),
        },
        "filesystem_control": {
            "requested": "repository_read_only",
            "mechanism": "catalog_policy_plus_post_hoc_observation",
            "enforced": False,
            "note": (
                "The runner installs no filesystem sandbox. Git-visible and recorded repository "
                "surfaces are checked after execution; undeclared ignored paths and writes outside "
                "the repository are not observed."
            ),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "python_environment": python_environment_before,
            "python_environment_after": python_environment_after,
            "python_environment_mutation_detected": python_environment_mutation_detected,
            "hardware": collect_hardware_state(),
        },
        "inputs": input_hashes,
        "mutation_sensitive": {
            "paths": mutation_paths,
            "explicit_paths": explicit_mutation_paths,
            "automatic_input_paths": automatic_mutation_paths,
            "before": mutation_before,
            "after": mutation_after,
            "observed_path_mutation_detected": observed_path_mutation_detected,
            "observation_scope": (
                "All declared suites, datasets, artifacts, dependency descriptors, the catalog, "
                "and explicit mutation-sensitive paths. Git tracked and non-ignored untracked "
                "state is also fingerprinted; ignored paths outside these surfaces are not observed."
            ),
        },
        "recipes": recipe_results,
        "successful": successful,
        "successful_reproduced": reproduced,
        "claim_scope": (
            "Command execution evidence only. Stable exit/output/report digests are not benchmark "
            "capability evidence; metrics remain null until a benchmark-owned report parser and "
            "independent capability gate populate them. Mutation claims cover only the explicitly "
            "recorded observation surfaces."
        ),
        "catalog_trust": (
            "The catalog is a reviewed recipe input, not an authority boundary. Runner-owned "
            "validation and the automatic runner-source binding are independent of catalog fields."
        ),
    }
    manifest["manifest_hash"] = compute_manifest_hash(manifest)
    write_manifest_exclusive(output_path, manifest)
    return manifest, output_path


def _read_manifest(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    parsed = _json_without_duplicate_keys(raw, source=path)
    if not isinstance(parsed, dict):
        raise BaselineError("manifest root must be an object")
    return parsed


def _compare_hash_records(expected: Any, actual: Any) -> bool:
    return isinstance(expected, list) and expected == actual


def _verify_digest_record(record: Any) -> bool:
    return (
        isinstance(record, dict)
        and isinstance(record.get("sha256"), str)
        and SHA256_RE.fullmatch(record["sha256"]) is not None
        and isinstance(record.get("bytes"), int)
        and record["bytes"] >= 0
    )


def _verify_stream_digest_record(record: Any) -> bool:
    if not _verify_digest_record(record):
        return False
    limit = record.get("limit_bytes")
    observed = record.get("observed_bytes")
    truncated = record.get("truncated")
    capture_error = record.get("capture_error")
    return (
        isinstance(limit, int)
        and not isinstance(limit, bool)
        and limit == MAX_STREAM_CAPTURE_BYTES
        and isinstance(observed, int)
        and not isinstance(observed, bool)
        and observed >= record["bytes"]
        and 0 <= record["bytes"] <= limit
        and isinstance(truncated, bool)
        and truncated is (observed > limit)
        and (capture_error is None or isinstance(capture_error, str))
    )


def _verify_execution_semantics(manifest: Mapping[str, Any]) -> bool:
    if manifest.get("evidence_kind") != EVIDENCE_KIND:
        return False
    recipes = manifest.get("recipes")
    if not isinstance(recipes, list) or not recipes:
        return False
    reproduced_flags: list[bool] = []
    all_attempts_successful = True
    for recipe in recipes:
        if not isinstance(recipe, dict):
            return False
        attempts = recipe.get("attempts")
        repeat_metrics = recipe.get("repeat_metrics")
        if not isinstance(attempts, list) or not attempts or not isinstance(repeat_metrics, dict):
            return False
        requested = repeat_metrics.get("attempts_requested")
        if not isinstance(requested, int) or isinstance(requested, bool) or requested < 1:
            return False
        for attempt in attempts:
            if not isinstance(attempt, dict):
                return False
            stdout = attempt.get("stdout")
            stderr = attempt.get("stderr")
            reports = attempt.get("reports")
            if not _verify_stream_digest_record(stdout) or not _verify_stream_digest_record(stderr):
                return False
            if not isinstance(reports, list):
                return False
            expected_output_limit = stdout["truncated"] is True or stderr["truncated"] is True
            expected_capture_error = (
                stdout.get("capture_error") is not None or stderr.get("capture_error") is not None
            )
            if attempt.get("output_limit_exceeded") is not expected_output_limit:
                return False
            if attempt.get("output_capture_error") is not expected_capture_error:
                return False
            reports_complete = all(
                isinstance(report, dict)
                and report.get("exists") is True
                and report.get("regular_file", True) is True
                and isinstance(report.get("sha256"), str)
                for report in reports
            )
            expected_attempt_success = (
                attempt.get("exit_code") == 0
                and attempt.get("timed_out") is False
                and not expected_output_limit
                and not expected_capture_error
                and attempt.get("launch_error") is None
                and reports_complete
            )
            if attempt.get("successful") is not expected_attempt_success:
                return False
            outcome = {
                "exit_code": attempt.get("exit_code"),
                "timed_out": attempt.get("timed_out"),
                "output_limit_exceeded": attempt.get("output_limit_exceeded"),
                "output_capture_error": attempt.get("output_capture_error"),
                "launch_error": attempt.get("launch_error"),
                "stdout_sha256": stdout["sha256"],
                "stderr_sha256": stderr["sha256"],
                "reports": [
                    {"path": report.get("path"), "sha256": report.get("sha256")}
                    for report in reports
                ],
            }
            if attempt.get("outcome_sha256") != sha256_bytes(canonical_json_bytes(outcome)):
                return False
            if not expected_attempt_success:
                all_attempts_successful = False
        recomputed = _repeat_summary(attempts, requested)
        for field in (
            "evidence_kind",
            "attempts_requested",
            "attempts_completed",
            "successful_attempts",
            "timeouts",
            "output_limit_exceeded_attempts",
            "failed_attempts",
            "outcome_digest_counts",
            "stable_outcome",
            "successful_reproduced",
        ):
            if repeat_metrics.get(field) != recomputed[field]:
                return False
        reproduced_flags.append(recomputed["successful_reproduced"] is True)

    source = manifest.get("source")
    mutation = manifest.get("mutation_sensitive")
    if not isinstance(source, dict) or not isinstance(mutation, dict):
        return False
    runner_before = source.get("runner")
    runner_after = source.get("runner_after")
    if not isinstance(runner_before, dict) or not isinstance(runner_after, dict):
        return False
    if source.get("runner_mutation_detected") is not (runner_before != runner_after):
        return False
    git_before = source.get("git")
    git_after = source.get("git_after")
    if not isinstance(git_before, dict) or not isinstance(git_after, dict):
        return False
    if source.get("repository_mutation_detected") is not (
        not _same_git_fingerprint(git_before, git_after)
    ):
        return False
    mutation_before = mutation.get("before")
    mutation_after = mutation.get("after")
    if not isinstance(mutation_before, list) or not isinstance(mutation_after, list):
        return False
    if mutation.get("observed_path_mutation_detected") is not (mutation_before != mutation_after):
        return False
    platform_record = manifest.get("platform")
    if not isinstance(platform_record, dict):
        return False
    python_environment_before = platform_record.get("python_environment")
    python_environment_after = platform_record.get("python_environment_after")
    if not isinstance(python_environment_before, dict) or not isinstance(
        python_environment_after, dict
    ):
        return False
    if platform_record.get("python_environment_mutation_detected") is not (
        python_environment_before != python_environment_after
    ):
        return False
    mutation_detected = (
        source.get("repository_mutation_detected") is True
        or source.get("runner_mutation_detected") is True
        or mutation.get("observed_path_mutation_detected") is True
        or platform_record.get("python_environment_mutation_detected") is True
    )
    expected_sealed = git_before.get("clean") is True and not mutation_detected
    expected_success = all_attempts_successful and not mutation_detected
    expected_reproduced = all(reproduced_flags) and not mutation_detected
    return (
        source.get("sealed") is expected_sealed
        and manifest.get("successful") is expected_success
        and manifest.get("successful_reproduced") is expected_reproduced
    )


def verify_manifest(manifest_path: Path, *, repo_root: Path = ROOT) -> dict[str, Any]:
    """Verify manifest integrity and whether the recorded source is still present."""

    try:
        repo_root = _canonical_repo_root(repo_root)
    except BaselineError as exc:
        return {
            "valid": False,
            "manifest_hash_valid": False,
            "source_matches": False,
            "errors": [f"repo_root_invalid:{type(exc).__name__}"],
        }
    manifest_path = Path(os.path.abspath(manifest_path))
    errors: list[str] = []
    try:
        manifest = _read_manifest(manifest_path)
    except (OSError, BaselineError) as exc:
        return {
            "valid": False,
            "manifest_hash_valid": False,
            "source_matches": False,
            "errors": [f"manifest_read_failed:{type(exc).__name__}"],
        }

    schema_valid = manifest.get("schema") == MANIFEST_SCHEMA
    if not schema_valid:
        errors.append("schema_mismatch")
    recorded_hash = manifest.get("manifest_hash")
    try:
        computed_hash = compute_manifest_hash(manifest)
    except BaselineError:
        computed_hash = None
    manifest_hash_valid = isinstance(recorded_hash, str) and recorded_hash == computed_hash
    if not manifest_hash_valid:
        errors.append("manifest_hash_mismatch")

    digest_shapes_valid = True
    recipes_value = manifest.get("recipes")
    recipes_for_digest_check = recipes_value if isinstance(recipes_value, list) else []
    if not isinstance(recipes_value, list):
        digest_shapes_valid = False
    for recipe in recipes_for_digest_check:
        if not isinstance(recipe, dict):
            digest_shapes_valid = False
            break
        attempts_value = recipe.get("attempts")
        if not isinstance(attempts_value, list):
            digest_shapes_valid = False
            break
        for attempt in attempts_value:
            if not isinstance(attempt, dict) or not _verify_stream_digest_record(attempt.get("stdout")):
                digest_shapes_valid = False
                break
            if not _verify_stream_digest_record(attempt.get("stderr")):
                digest_shapes_valid = False
                break
            reports_value = attempt.get("reports")
            if not isinstance(reports_value, list):
                digest_shapes_valid = False
                break
            for report in reports_value:
                if not isinstance(report, dict):
                    digest_shapes_valid = False
                    break
                if report.get("exists") is True and report.get("regular_file", True) is True:
                    if not _verify_digest_record(report):
                        digest_shapes_valid = False
                        break
    if not digest_shapes_valid:
        errors.append("digest_record_invalid")

    execution_semantics_valid = _verify_execution_semantics(manifest)
    if not execution_semantics_valid:
        errors.append("execution_semantics_invalid")

    source_matches = True
    try:
        catalog_record = manifest["catalog"]
        catalog_path = _repo_path(repo_root, catalog_record["path"], field="catalog", must_exist=True)
        catalog_matches = sha256_bytes(catalog_path.read_bytes()) == catalog_record["sha256"]
    except (KeyError, OSError, BaselineError, TypeError):
        catalog_matches = False
    if not catalog_matches:
        source_matches = False
        errors.append("catalog_mismatch")

    try:
        recorded_runner = manifest["source"]["runner"]
        runner_source_matches = recorded_runner == collect_runner_source(repo_root)
    except (KeyError, TypeError, OSError, BaselineError):
        runner_source_matches = False
    if not runner_source_matches:
        source_matches = False
        errors.append("runner_source_mismatch")

    try:
        recorded_python_environment = manifest["platform"]["python_environment"]
        python_environment_matches = recorded_python_environment == collect_python_environment()
    except (KeyError, TypeError, OSError, BaselineError):
        python_environment_matches = False
    if not python_environment_matches:
        source_matches = False
        errors.append("python_environment_mismatch")

    inputs = manifest.get("inputs", {})
    for key in ("suites", "datasets", "artifacts", "dependencies"):
        expected = inputs.get(key, []) if isinstance(inputs, dict) else []
        try:
            paths = [record["path"] for record in expected]
            actual = hash_declared_paths(repo_root, paths, require_exists=True)
            matches = _compare_hash_records(expected, actual)
        except (KeyError, TypeError, OSError, BaselineError):
            matches = False
        if not matches:
            source_matches = False
            errors.append(f"{key}_mismatch")

    try:
        output_exclusion = manifest["source"].get("excluded_evidence_output")
        if output_exclusion is not None and not isinstance(output_exclusion, str):
            raise BaselineError("invalid evidence-output exclusion")
        current_git = collect_git_state(
            repo_root,
            exclude_untracked_paths=[output_exclusion] if output_exclusion is not None else [],
        )
        recorded_git = manifest["source"]["git"]
        git_matches = _same_git_fingerprint(recorded_git, current_git)
    except (KeyError, TypeError, OSError, BaselineError):
        git_matches = False
    if not git_matches:
        source_matches = False
        errors.append("git_state_mismatch")

    try:
        mutation_after = manifest["mutation_sensitive"]["after"]
        mutation_paths = [record["path"] for record in mutation_after]
        current_mutation = hash_declared_paths(repo_root, mutation_paths, require_exists=False)
        mutation_state_matches = mutation_after == current_mutation
    except (KeyError, TypeError, OSError, BaselineError):
        mutation_state_matches = False
    if not mutation_state_matches:
        source_matches = False
        errors.append("mutation_sensitive_state_mismatch")

    valid = (
        schema_valid
        and manifest_hash_valid
        and digest_shapes_valid
        and execution_semantics_valid
        and source_matches
    )
    return {
        "valid": valid,
        "manifest_hash_valid": manifest_hash_valid,
        "source_matches": source_matches,
        "execution_semantics_valid": execution_semantics_valid,
        "catalog_matches": catalog_matches,
        "runner_source_matches": runner_source_matches,
        "python_environment_matches": python_environment_matches,
        "git_state_matches": git_matches,
        "mutation_sensitive_state_matches": mutation_state_matches,
        "errors": errors,
        "manifest_hash": recorded_hash,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    run_parser = subparsers.add_parser("run", help="run a bounded baseline profile")
    run_parser.add_argument("--profile", default="smoke")
    run_parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    run_parser.add_argument("--repo-root", type=Path, default=ROOT)
    run_parser.add_argument("--output", type=Path)

    verify_parser = subparsers.add_parser("verify", help="verify an existing evidence manifest")
    verify_parser.add_argument("manifest", type=Path)
    verify_parser.add_argument("--repo-root", type=Path, default=ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.action == "run":
            manifest, output_path = run_suite(
                profile_name=args.profile,
                catalog_path=args.catalog,
                repo_root=args.repo_root,
                output_path=args.output,
            )
            print(
                json.dumps(
                    {
                        "manifest": str(output_path),
                        "manifest_hash": manifest["manifest_hash"],
                        "sealed": manifest["source"]["sealed"],
                        "successful": manifest["successful"],
                        "successful_reproduced": manifest["successful_reproduced"],
                    },
                    sort_keys=True,
                )
            )
            return 0 if manifest["successful"] else 1
        result = verify_manifest(args.manifest, repo_root=args.repo_root)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["valid"] else 1
    except BaselineError as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
