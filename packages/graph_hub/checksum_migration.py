from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from .models import checksum_payload, utc_now_iso


PLAN_SCHEMA = "atanor.graph_hub.checksum_migration.plan.v1"
APPLY_SCHEMA = "atanor.graph_hub.checksum_migration.apply.v1"
GRAPH_PACK_FOLDERS = ("authored", "cartridges", "exported", "installed")
CHECKSUM_PATTERN = re.compile(rb'("checksum"\s*:\s*")([0-9a-f]{64})(")')
REGISTRY_FLAG_PATTERN = re.compile(rb'("checksum_valid"\s*:\s*)(true|false)')


class ChecksumMigrationError(RuntimeError):
    """Fail-closed checksum migration contract violation."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _receipt_checksum(payload: dict[str, Any]) -> str:
    clone = copy.deepcopy(payload)
    clone.pop("receipt_checksum_sha256", None)
    return _canonical_sha256(clone)


def _without_checksum(payload: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(payload)
    metadata = clone.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("checksum", None)
    return clone


def _without_registry_flags(payload: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(payload)
    for value in clone.values():
        if isinstance(value, dict):
            value.pop("checksum_valid", None)
    return clone


def _legacy_checksum(payload: dict[str, Any]) -> str:
    clone = copy.deepcopy(payload)
    metadata = clone.get("metadata")
    if not isinstance(metadata, dict):
        raise ChecksumMigrationError("missing_metadata")
    metadata["size_bytes"] = 0
    return checksum_payload(clone)


def _replace_checksum_bytes(raw: bytes, old: str, new: str) -> bytes:
    matches = list(CHECKSUM_PATTERN.finditer(raw))
    if len(matches) != 1:
        raise ChecksumMigrationError(
            f"checksum_field_occurrences:{len(matches)}"
        )
    match = matches[0]
    if match.group(2).decode("ascii") != old:
        raise ChecksumMigrationError("raw_checksum_does_not_match_json")
    return raw[: match.start(2)] + new.encode("ascii") + raw[match.end(2) :]


def _masked_checksum_bytes(raw: bytes) -> bytes:
    matches = list(CHECKSUM_PATTERN.finditer(raw))
    if len(matches) != 1:
        raise ChecksumMigrationError(
            f"checksum_field_occurrences:{len(matches)}"
        )
    match = matches[0]
    return raw[: match.start(2)] + (b"0" * 64) + raw[match.end(2) :]


def _read_json_object(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChecksumMigrationError(f"invalid_json:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise ChecksumMigrationError(f"json_root_not_object:{path}")
    return raw, payload


def _graphpack_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for folder in GRAPH_PACK_FOLDERS:
        directory = root / folder
        if not directory.is_dir():
            raise ChecksumMigrationError(f"missing_graphpack_folder:{folder}")
        paths.extend(sorted(directory.glob("*.graphpack.json")))
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def _inspect_graphpack(path: Path, root: Path) -> tuple[dict[str, Any], bytes]:
    raw, payload = _read_json_object(path)
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise ChecksumMigrationError(f"missing_metadata:{path}")
    stored = metadata.get("checksum")
    if not isinstance(stored, str) or not re.fullmatch(r"[0-9a-f]{64}", stored):
        raise ChecksumMigrationError(f"invalid_stored_checksum:{path}")
    if not isinstance(metadata.get("size_bytes"), int):
        raise ChecksumMigrationError(f"invalid_size_bytes:{path}")
    cartridge_id = payload.get("cartridge_id")
    if not isinstance(cartridge_id, str) or not cartridge_id:
        raise ChecksumMigrationError(f"invalid_cartridge_id:{path}")

    current = checksum_payload(payload)
    legacy = _legacy_checksum(payload)
    if stored == current:
        status = "current"
        new_checksum = stored
    elif stored == legacy:
        status = "legacy_reseal"
        new_checksum = current
    else:
        raise ChecksumMigrationError(
            f"checksum_neither_current_nor_legacy:{path.relative_to(root).as_posix()}"
        )

    candidate = _replace_checksum_bytes(raw, stored, new_checksum)
    candidate_payload = json.loads(candidate.decode("utf-8"))
    if _without_checksum(candidate_payload) != _without_checksum(payload):
        raise ChecksumMigrationError(f"non_checksum_json_changed:{path}")
    if _masked_checksum_bytes(candidate) != _masked_checksum_bytes(raw):
        raise ChecksumMigrationError(f"non_checksum_raw_bytes_changed:{path}")
    if checksum_payload(candidate_payload) != candidate_payload["metadata"]["checksum"]:
        raise ChecksumMigrationError(f"candidate_checksum_invalid:{path}")

    relative_path = path.relative_to(root).as_posix()
    entry = {
        "path": relative_path,
        "cartridge_id": cartridge_id,
        "status": status,
        "old_checksum": stored,
        "new_checksum": new_checksum,
        "legacy_checksum_sha256": legacy,
        "before_file_sha256": _sha256_bytes(raw),
        "after_file_sha256": _sha256_bytes(candidate),
        "non_checksum_json_sha256": _canonical_sha256(
            _without_checksum(payload)
        ),
        "before_masked_raw_sha256": _sha256_bytes(
            _masked_checksum_bytes(raw)
        ),
        "after_masked_raw_sha256": _sha256_bytes(
            _masked_checksum_bytes(candidate)
        ),
        "raw_size_bytes": len(raw),
    }
    return entry, candidate


def _registry_candidate(
    root: Path,
    installed_entries: list[dict[str, Any]],
) -> tuple[dict[str, Any], bytes, bytes]:
    registry_path = root / "installed" / "installed_registry.json"
    raw, payload = _read_json_object(registry_path)
    installed_ids = {entry["cartridge_id"] for entry in installed_entries}
    registry_ids = set(payload)
    if registry_ids != installed_ids:
        missing = sorted(installed_ids - registry_ids)
        extra = sorted(registry_ids - installed_ids)
        raise ChecksumMigrationError(
            f"installed_registry_id_mismatch:missing={missing}:extra={extra}"
        )

    changed_ids: list[str] = []
    for cartridge_id, record in payload.items():
        if not isinstance(record, dict):
            raise ChecksumMigrationError(
                f"installed_registry_record_not_object:{cartridge_id}"
            )
        if record.get("cartridge_id") != cartridge_id:
            raise ChecksumMigrationError(
                f"installed_registry_cartridge_id_mismatch:{cartridge_id}"
            )
        expected_path = (
            root / "installed" / f"{cartridge_id}.graphpack.json"
        ).resolve()
        try:
            recorded_path = Path(str(record["path"])).resolve()
        except (KeyError, OSError) as exc:
            raise ChecksumMigrationError(
                f"installed_registry_invalid_path:{cartridge_id}"
            ) from exc
        if recorded_path != expected_path:
            raise ChecksumMigrationError(
                f"installed_registry_path_mismatch:{cartridge_id}"
            )
        if not isinstance(record.get("checksum_valid"), bool):
            raise ChecksumMigrationError(
                f"installed_registry_invalid_checksum_flag:{cartridge_id}"
            )
        if record["checksum_valid"] is not True:
            changed_ids.append(cartridge_id)

    flag_matches = list(REGISTRY_FLAG_PATTERN.finditer(raw))
    if len(flag_matches) != len(payload):
        raise ChecksumMigrationError(
            "installed_registry_checksum_flag_occurrences:"
            f"{len(flag_matches)}"
        )
    candidate = REGISTRY_FLAG_PATTERN.sub(rb"\1true", raw)
    candidate_payload = json.loads(candidate.decode("utf-8"))
    if _without_registry_flags(candidate_payload) != _without_registry_flags(
        payload
    ):
        raise ChecksumMigrationError("installed_registry_non_flag_data_changed")
    if any(
        not isinstance(record, dict)
        or record.get("checksum_valid") is not True
        for record in candidate_payload.values()
    ):
        raise ChecksumMigrationError("installed_registry_candidate_not_true")

    entry = {
        "path": registry_path.relative_to(root).as_posix(),
        "entry_count": len(payload),
        "changed_cartridge_ids": sorted(changed_ids),
        "before_file_sha256": _sha256_bytes(raw),
        "after_file_sha256": _sha256_bytes(candidate),
        "non_checksum_flag_json_sha256": _canonical_sha256(
            _without_registry_flags(payload)
        ),
    }
    return entry, raw, candidate


def _entitlements_receipt(root: Path) -> dict[str, Any]:
    path = root / "entitlements" / "entitlements.json"
    if not path.is_file():
        raise ChecksumMigrationError("missing_entitlements")
    raw = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "before_file_sha256": _sha256_bytes(raw),
        "after_file_sha256": _sha256_bytes(raw),
        "byte_identical_required": True,
    }


def _binding_payload(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": plan["schema"],
        "graph_hub_root": plan["graph_hub_root"],
        "constraints": plan["constraints"],
        "graphpacks": plan["graphpacks"],
        "installed_registry": plan["installed_registry"],
        "entitlements": plan["entitlements"],
        "summary": plan["summary"],
    }


def _build_state(
    graph_hub_root: str | Path,
    *,
    expected_graphpack_count: int,
    expected_installed_count: int,
) -> tuple[dict[str, Any], dict[Path, bytes], dict[Path, bytes]]:
    root = Path(graph_hub_root).resolve()
    paths = _graphpack_paths(root)
    if len(paths) != expected_graphpack_count:
        raise ChecksumMigrationError(
            f"graphpack_count:{len(paths)}:expected:{expected_graphpack_count}"
        )

    entries: list[dict[str, Any]] = []
    candidates: dict[Path, bytes] = {}
    originals: dict[Path, bytes] = {}
    for path in paths:
        entry, candidate = _inspect_graphpack(path, root)
        entries.append(entry)
        raw = path.read_bytes()
        originals[path] = raw
        candidates[path] = candidate

    installed_entries = [
        entry for entry in entries if entry["path"].startswith("installed/")
    ]
    if len(installed_entries) != expected_installed_count:
        raise ChecksumMigrationError(
            "installed_graphpack_count:"
            f"{len(installed_entries)}:expected:{expected_installed_count}"
        )
    installed_ids = [entry["cartridge_id"] for entry in installed_entries]
    if len(installed_ids) != len(set(installed_ids)):
        raise ChecksumMigrationError("duplicate_installed_cartridge_id")

    registry_entry, registry_raw, registry_candidate = _registry_candidate(
        root, installed_entries
    )
    registry_path = root / registry_entry["path"]
    originals[registry_path] = registry_raw
    candidates[registry_path] = registry_candidate
    entitlements_entry = _entitlements_receipt(root)

    legacy_count = sum(entry["status"] == "legacy_reseal" for entry in entries)
    current_count = sum(entry["status"] == "current" for entry in entries)
    files_changed = sum(
        entry["before_file_sha256"] != entry["after_file_sha256"]
        for entry in entries
    )
    if (
        registry_entry["before_file_sha256"]
        != registry_entry["after_file_sha256"]
    ):
        files_changed += 1

    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "mode": "plan",
        "generated_at": utc_now_iso(),
        "graph_hub_root": str(root),
        "constraints": {
            "expected_graphpack_count": expected_graphpack_count,
            "expected_installed_count": expected_installed_count,
            "allowed_graphpack_folders": list(GRAPH_PACK_FOLDERS),
            "legacy_precondition": (
                "stored checksum must equal the canonical payload digest "
                "with metadata.size_bytes reset to 0"
            ),
            "current_precondition": (
                "already-current checksum is accepted only for idempotence"
            ),
            "graphpack_mutation": "metadata.checksum_64_hex_only",
            "installed_registry_mutation": "checksum_valid_derived_flag_only",
            "entitlements_mutation": "forbidden",
            "reinstall_or_reissue": False,
        },
        "graphpacks": entries,
        "installed_registry": registry_entry,
        "entitlements": entitlements_entry,
        "summary": {
            "graphpack_count": len(entries),
            "installed_count": len(installed_entries),
            "legacy_reseal_count": legacy_count,
            "already_current_count": current_count,
            "unknown_count": 0,
            "graphpack_files_changed": sum(
                entry["status"] == "legacy_reseal" for entry in entries
            ),
            "registry_flags_changed": len(
                registry_entry["changed_cartridge_ids"]
            ),
            "total_files_changed": files_changed,
            "safe_to_apply": True,
        },
    }
    plan["binding_sha256"] = _canonical_sha256(_binding_payload(plan))
    plan["receipt_checksum_sha256"] = _receipt_checksum(plan)
    return plan, originals, candidates


def build_checksum_migration_plan(
    graph_hub_root: str | Path,
    *,
    expected_graphpack_count: int = 36,
    expected_installed_count: int = 11,
) -> dict[str, Any]:
    plan, _originals, _candidates = _build_state(
        graph_hub_root,
        expected_graphpack_count=expected_graphpack_count,
        expected_installed_count=expected_installed_count,
    )
    return plan


def _write_receipt_exclusive(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ChecksumMigrationError(f"receipt_already_exists:{path}")
    raw = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def write_checksum_migration_plan(
    graph_hub_root: str | Path,
    receipt_path: str | Path,
    *,
    expected_graphpack_count: int = 36,
    expected_installed_count: int = 11,
) -> dict[str, Any]:
    plan = build_checksum_migration_plan(
        graph_hub_root,
        expected_graphpack_count=expected_graphpack_count,
        expected_installed_count=expected_installed_count,
    )
    _write_receipt_exclusive(Path(receipt_path), plan)
    return plan


def _load_plan_receipt(path: Path) -> dict[str, Any]:
    _raw, plan = _read_json_object(path)
    if plan.get("schema") != PLAN_SCHEMA or plan.get("mode") != "plan":
        raise ChecksumMigrationError("invalid_plan_schema")
    if plan.get("receipt_checksum_sha256") != _receipt_checksum(plan):
        raise ChecksumMigrationError("plan_receipt_checksum_invalid")
    if plan.get("binding_sha256") != _canonical_sha256(_binding_payload(plan)):
        raise ChecksumMigrationError("plan_binding_invalid")
    if plan.get("summary", {}).get("safe_to_apply") is not True:
        raise ChecksumMigrationError("plan_not_safe_to_apply")
    return plan


def _stage_bytes(path: Path, raw: bytes) -> Path:
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".checksum-migration.tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, stat.S_IMODE(path.stat().st_mode))
        return temp_path
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _replace_transaction(
    originals: dict[Path, bytes],
    candidates: dict[Path, bytes],
) -> list[Path]:
    changed = [
        path for path in sorted(candidates) if candidates[path] != originals[path]
    ]
    staged: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for path in changed:
            staged[path] = _stage_bytes(path, candidates[path])
        for path in changed:
            os.replace(staged[path], path)
            replaced.append(path)
        return changed
    except BaseException as exc:
        rollback_errors: list[str] = []
        for path in reversed(replaced):
            try:
                rollback_temp = _stage_bytes(path, originals[path])
                os.replace(rollback_temp, path)
            except BaseException as rollback_exc:
                rollback_errors.append(f"{path}:{rollback_exc}")
        if rollback_errors:
            raise ChecksumMigrationError(
                "migration_failed_and_rollback_incomplete:"
                + "|".join(rollback_errors)
            ) from exc
        raise ChecksumMigrationError(f"migration_apply_failed:{exc}") from exc
    finally:
        for temp_path in staged.values():
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass


def apply_checksum_migration(
    plan_receipt_path: str | Path,
    apply_receipt_path: str | Path,
) -> dict[str, Any]:
    plan_path = Path(plan_receipt_path).resolve()
    plan = _load_plan_receipt(plan_path)
    constraints = plan["constraints"]
    fresh, originals, candidates = _build_state(
        plan["graph_hub_root"],
        expected_graphpack_count=int(
            constraints["expected_graphpack_count"]
        ),
        expected_installed_count=int(
            constraints["expected_installed_count"]
        ),
    )
    if fresh["binding_sha256"] != plan["binding_sha256"]:
        raise ChecksumMigrationError("source_drift_since_plan")

    root = Path(plan["graph_hub_root"])
    entitlements_path = root / plan["entitlements"]["path"]
    entitlement_before = entitlements_path.read_bytes()
    changed = _replace_transaction(originals, candidates)
    try:
        for path, expected_raw in candidates.items():
            if path.read_bytes() != expected_raw:
                raise ChecksumMigrationError(f"post_apply_hash_mismatch:{path}")
        if entitlements_path.read_bytes() != entitlement_before:
            raise ChecksumMigrationError("entitlements_changed")

        applied_graphpacks = [
            entry
            for entry in plan["graphpacks"]
            if entry["before_file_sha256"] != entry["after_file_sha256"]
        ]
        receipt: dict[str, Any] = {
            "schema": APPLY_SCHEMA,
            "mode": "apply",
            "applied_at": utc_now_iso(),
            "plan_receipt_path": str(plan_path),
            "plan_receipt_file_sha256": _sha256_bytes(plan_path.read_bytes()),
            "plan_binding_sha256": plan["binding_sha256"],
            "graph_hub_root": str(root),
            "summary": {
                "changed_file_count": len(changed),
                "graphpack_files_changed": len(applied_graphpacks),
                "registry_changed": (
                    plan["installed_registry"]["before_file_sha256"]
                    != plan["installed_registry"]["after_file_sha256"]
                ),
                "entitlements_byte_identical": True,
                "reinstall_or_reissue": False,
            },
            "graphpacks": applied_graphpacks,
            "installed_registry": plan["installed_registry"],
            "entitlements": plan["entitlements"],
        }
        receipt["receipt_checksum_sha256"] = _receipt_checksum(receipt)
        _write_receipt_exclusive(Path(apply_receipt_path), receipt)
        return receipt
    except BaseException:
        rollback_candidates = {
            path: originals[path]
            for path in changed
        }
        rollback_originals = {
            path: path.read_bytes()
            for path in changed
        }
        _replace_transaction(rollback_originals, rollback_candidates)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or apply the bounded Graph Hub checksum migration."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--root", required=True)
    plan_parser.add_argument("--receipt", required=True)
    plan_parser.add_argument("--expected-graphpacks", type=int, default=36)
    plan_parser.add_argument("--expected-installed", type=int, default=11)

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--plan-receipt", required=True)
    apply_parser.add_argument("--receipt", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "plan":
        receipt = write_checksum_migration_plan(
            args.root,
            args.receipt,
            expected_graphpack_count=args.expected_graphpacks,
            expected_installed_count=args.expected_installed,
        )
    else:
        receipt = apply_checksum_migration(
            args.plan_receipt,
            args.receipt,
        )
    print(json.dumps(receipt["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
