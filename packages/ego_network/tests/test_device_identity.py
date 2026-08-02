# -*- coding: utf-8 -*-
import re

from packages.ego_network.device_identity import (
    get_or_create_device_identity,
    mint_device_identity,
    register_device,
)

_AI_ID = re.compile(r"ATANOR-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}")


def test_mint_format_and_fields():
    m = mint_device_identity()
    assert _AI_ID.fullmatch(m["ai_id"]), m["ai_id"]
    assert m["did"].startswith("did:atanor:proof:")
    assert m["model"] == "atanor-graph-native"
    assert m["proof_only"] is True
    assert m["created_at"].endswith("Z")


def test_idempotent_after_first_launch(tmp_path):
    a = get_or_create_device_identity(tmp_path)
    b = get_or_create_device_identity(tmp_path)
    assert a == b  # the id never changes once minted
    assert (tmp_path / "data" / "identity" / "device_identity.json").exists()


def test_two_installs_differ(tmp_path):
    a = get_or_create_device_identity(tmp_path / "install_a")
    b = get_or_create_device_identity(tmp_path / "install_b")
    assert a["ai_id"] != b["ai_id"]  # per-install unique, not hardware-derived


def test_register_appends(tmp_path):
    r1 = register_device(tmp_path, note="first launch")
    r2 = register_device(tmp_path, note="second")
    assert r1["registrations"] == 1
    assert r2["registrations"] == 2
    # registration reuses the SAME identity
    assert r1["identity"]["ai_id"] == r2["identity"]["ai_id"]


def test_corrupt_store_remints(tmp_path):
    path = tmp_path / "data" / "identity" / "device_identity.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json", encoding="utf-8")
    ident = get_or_create_device_identity(tmp_path)  # must not raise
    assert _AI_ID.fullmatch(ident["ai_id"])
