from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from packages.graph_hub.cartridge_format import (
    make_graph_cartridge,
    verify_cartridge_checksum,
    write_cartridge,
)
from packages.graph_hub.checksum_migration import (
    ChecksumMigrationError,
    _masked_checksum_bytes,
    apply_checksum_migration,
    build_checksum_migration_plan,
    write_checksum_migration_plan,
)
from packages.graph_hub.models import checksum_payload, write_json


def _cartridge() -> dict:
    return make_graph_cartridge(
        cartridge_id="checksum-regression",
        name="Checksum regression",
        subtitle="Checksum regression control",
        description="Focused checksum-order regression fixture.",
        category="test",
        pricing={"model": "free"},
        contents={"semantic_graph": {"nodes": [], "edges": []}},
        provenance={"source_type": "test"},
    )


def test_builder_checksum_covers_finalized_size_bytes(tmp_path) -> None:
    cartridge = _cartridge()
    destination = tmp_path / "checksum-regression.graphpack.json"

    write_cartridge(destination, cartridge)

    assert cartridge["metadata"]["checksum"] == checksum_payload(cartridge)
    assert cartridge["metadata"]["size_bytes"] == len(
        json.dumps(cartridge, ensure_ascii=False).encode("utf-8")
    )
    assert verify_cartridge_checksum(destination) is True


def test_recomputed_checksum_is_a_valid_positive_control(tmp_path) -> None:
    cartridge = _cartridge()
    cartridge["metadata"]["checksum"] = checksum_payload(cartridge)
    destination = tmp_path / "checksum-positive-control.graphpack.json"

    write_cartridge(destination, cartridge)

    assert verify_cartridge_checksum(destination) is True


def _legacy_payload(cartridge_id: str) -> dict:
    payload = _cartridge()
    payload["cartridge_id"] = cartridge_id
    legacy_view = copy.deepcopy(payload)
    legacy_view["metadata"]["size_bytes"] = 0
    payload["metadata"]["checksum"] = checksum_payload(legacy_view)
    return payload


def _write_hub(
    root: Path,
    *,
    cartridge_ids: tuple[str, ...] = ("legacy-installed",),
    current: bool = False,
) -> dict[str, Path]:
    for folder in ("authored", "cartridges", "exported", "installed"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "entitlements").mkdir(parents=True, exist_ok=True)

    installed_paths: list[Path] = []
    for cartridge_id in cartridge_ids:
        payload = _cartridge() if current else _legacy_payload(cartridge_id)
        payload["cartridge_id"] = cartridge_id
        if current:
            payload["metadata"]["checksum"] = checksum_payload(payload)
        path = root / "installed" / f"{cartridge_id}.graphpack.json"
        write_json(path, payload)
        installed_paths.append(path)

    registry = {
        cartridge_id: {
            "cartridge_id": cartridge_id,
            "installed_at": "2026-07-01T00:00:00Z",
            "version": "0.1.0",
            "path": str(path.resolve()),
            "enabled": True,
            "entitlement_status": "free",
            "permissions": {
                "read_local_brain": False,
                "write_local_brain": False,
                "attach_to_working_memory": True,
            },
            "safety": {"default_read_only": True},
            "stats": {"semantic_nodes": 0},
            "checksum_valid": current,
            "local_brain_write": False,
        }
        for cartridge_id, path in zip(cartridge_ids, installed_paths)
    }
    registry_path = root / "installed" / "installed_registry.json"
    write_json(registry_path, registry)
    entitlements_path = root / "entitlements" / "entitlements.json"
    write_json(
        entitlements_path,
        {
            cartridge_id: {
                "cartridge_id": cartridge_id,
                "status": "free",
                "entitlement_id": f"ent-{cartridge_id}",
            }
            for cartridge_id in cartridge_ids
        },
    )
    return {
        "graphpack": installed_paths[0],
        "registry": registry_path,
        "entitlements": entitlements_path,
    }


def _without_checksum(payload: dict) -> dict:
    clone = copy.deepcopy(payload)
    clone["metadata"].pop("checksum")
    return clone


def _without_registry_flags(payload: dict) -> dict:
    clone = copy.deepcopy(payload)
    for value in clone.values():
        value.pop("checksum_valid")
    return clone


def test_dry_run_plan_binds_legacy_inputs_without_mutating_them(tmp_path) -> None:
    root = tmp_path / "graph_hub"
    paths = _write_hub(root)
    before = {name: path.read_bytes() for name, path in paths.items()}

    plan = build_checksum_migration_plan(
        root,
        expected_graphpack_count=1,
        expected_installed_count=1,
    )

    assert plan["summary"] == {
        "graphpack_count": 1,
        "installed_count": 1,
        "legacy_reseal_count": 1,
        "already_current_count": 0,
        "unknown_count": 0,
        "graphpack_files_changed": 1,
        "registry_flags_changed": 1,
        "total_files_changed": 2,
        "safe_to_apply": True,
    }
    assert plan["graphpacks"][0]["status"] == "legacy_reseal"
    assert plan["graphpacks"][0]["before_file_sha256"]
    assert plan["installed_registry"]["before_file_sha256"]
    assert plan["entitlements"]["before_file_sha256"]
    assert plan["entitlements"]["before_file_sha256"] == plan["entitlements"][
        "after_file_sha256"
    ]
    assert {name: path.read_bytes() for name, path in paths.items()} == before


def test_plan_rejects_unknown_checksum_before_any_write(tmp_path) -> None:
    root = tmp_path / "graph_hub"
    paths = _write_hub(root)
    payload = json.loads(paths["graphpack"].read_text(encoding="utf-8"))
    payload["metadata"]["checksum"] = "f" * 64
    write_json(paths["graphpack"], payload)
    before = {name: path.read_bytes() for name, path in paths.items()}

    with pytest.raises(
        ChecksumMigrationError,
        match="checksum_neither_current_nor_legacy",
    ):
        build_checksum_migration_plan(
            root,
            expected_graphpack_count=1,
            expected_installed_count=1,
        )

    assert {name: path.read_bytes() for name, path in paths.items()} == before


def test_already_current_input_is_an_idempotent_positive_control(
    tmp_path,
) -> None:
    root = tmp_path / "graph_hub"
    paths = _write_hub(root, current=True)

    plan = build_checksum_migration_plan(
        root,
        expected_graphpack_count=1,
        expected_installed_count=1,
    )

    assert plan["summary"]["legacy_reseal_count"] == 0
    assert plan["summary"]["already_current_count"] == 1
    assert plan["summary"]["unknown_count"] == 0
    assert plan["summary"]["total_files_changed"] == 0
    assert plan["graphpacks"][0]["status"] == "current"
    assert verify_cartridge_checksum(paths["graphpack"]) is True


def test_apply_changes_only_checksums_and_registry_derived_flags(
    tmp_path,
) -> None:
    root = tmp_path / "graph_hub"
    paths = _write_hub(root)
    plan_path = tmp_path / "plan.json"
    apply_path = tmp_path / "apply.json"
    before_graphpack = paths["graphpack"].read_bytes()
    before_payload = json.loads(before_graphpack.decode("utf-8"))
    before_registry_raw = paths["registry"].read_bytes()
    before_registry = json.loads(before_registry_raw.decode("utf-8"))
    before_entitlements = paths["entitlements"].read_bytes()
    write_checksum_migration_plan(
        root,
        plan_path,
        expected_graphpack_count=1,
        expected_installed_count=1,
    )

    receipt = apply_checksum_migration(plan_path, apply_path)

    after_graphpack = paths["graphpack"].read_bytes()
    after_payload = json.loads(after_graphpack.decode("utf-8"))
    after_registry_raw = paths["registry"].read_bytes()
    after_registry = json.loads(after_registry_raw.decode("utf-8"))
    assert _masked_checksum_bytes(after_graphpack) == _masked_checksum_bytes(
        before_graphpack
    )
    assert _without_checksum(after_payload) == _without_checksum(before_payload)
    assert _without_registry_flags(after_registry) == _without_registry_flags(
        before_registry
    )
    assert after_registry["legacy-installed"]["checksum_valid"] is True
    assert paths["entitlements"].read_bytes() == before_entitlements
    assert verify_cartridge_checksum(paths["graphpack"]) is True
    assert receipt["summary"] == {
        "changed_file_count": 2,
        "graphpack_files_changed": 1,
        "registry_changed": True,
        "entitlements_byte_identical": True,
        "reinstall_or_reissue": False,
    }
    assert receipt["graphpacks"][0]["before_file_sha256"]
    assert receipt["graphpacks"][0]["after_file_sha256"]
    assert receipt["installed_registry"]["before_file_sha256"]
    assert receipt["installed_registry"]["after_file_sha256"]
    assert receipt["entitlements"]["before_file_sha256"]
    assert before_registry_raw != after_registry_raw


def test_apply_rejects_source_drift_since_plan_without_migration_write(
    tmp_path,
) -> None:
    root = tmp_path / "graph_hub"
    paths = _write_hub(root)
    plan_path = tmp_path / "plan.json"
    apply_path = tmp_path / "apply.json"
    write_checksum_migration_plan(
        root,
        plan_path,
        expected_graphpack_count=1,
        expected_installed_count=1,
    )
    payload = json.loads(paths["graphpack"].read_text(encoding="utf-8"))
    payload["description"] = "source drift"
    write_json(paths["graphpack"], payload)
    drifted = paths["graphpack"].read_bytes()
    registry_before = paths["registry"].read_bytes()
    entitlements_before = paths["entitlements"].read_bytes()

    with pytest.raises(ChecksumMigrationError):
        apply_checksum_migration(plan_path, apply_path)

    assert paths["graphpack"].read_bytes() == drifted
    assert paths["registry"].read_bytes() == registry_before
    assert paths["entitlements"].read_bytes() == entitlements_before
    assert not apply_path.exists()


def test_apply_rolls_back_if_a_later_atomic_replace_fails(
    tmp_path,
    monkeypatch,
) -> None:
    import packages.graph_hub.checksum_migration as migration

    root = tmp_path / "graph_hub"
    paths = _write_hub(root)
    plan_path = tmp_path / "plan.json"
    apply_path = tmp_path / "apply.json"
    write_checksum_migration_plan(
        root,
        plan_path,
        expected_graphpack_count=1,
        expected_installed_count=1,
    )
    before = {name: path.read_bytes() for name, path in paths.items()}
    real_replace = migration.os.replace
    injected = {"done": False}

    def fail_registry_once(source, destination):
        if (
            not injected["done"]
            and Path(destination).name == "installed_registry.json"
        ):
            injected["done"] = True
            raise OSError("injected registry replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr(migration.os, "replace", fail_registry_once)
    with pytest.raises(ChecksumMigrationError, match="migration_apply_failed"):
        apply_checksum_migration(plan_path, apply_path)

    assert {name: path.read_bytes() for name, path in paths.items()} == before
    assert not apply_path.exists()
