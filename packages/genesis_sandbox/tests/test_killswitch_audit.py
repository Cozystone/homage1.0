# -*- coding: utf-8 -*-
"""L6 kill-switch + tamper-evident audit log."""
from __future__ import annotations

import json

import pytest

from packages.genesis_sandbox.killswitch_audit import AuditLog, KillSwitch, SandboxHalted


def test_killswitch_engage_and_require(tmp_path):
    ks = KillSwitch(path=tmp_path / "KILL")
    assert ks.is_engaged() is False
    ks.require_live()                     # no raise when clear
    ks.engage("test stop")
    assert ks.is_engaged() is True
    with pytest.raises(SandboxHalted):
        ks.require_live()
    assert ks.reset() is True
    assert ks.is_engaged() is False


def test_audit_append_and_chain(tmp_path):
    al = AuditLog(path=tmp_path / "audit.jsonl")
    r1 = al.append("e1", {"a": 1})
    r2 = al.append("e2", {"b": 2})
    assert r1["seq"] == 0 and r2["seq"] == 1
    assert r2["prev"] == r1["hash"]
    ok, bad = al.verify_chain()
    assert ok is True and bad is None
    assert len(al.read_all()) == 2


def test_audit_detects_edited_record(tmp_path):
    al = AuditLog(path=tmp_path / "audit.jsonl")
    al.append("e1", {"a": 1})
    al.append("e2", {"b": 2})
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[0])
    rec["payload"] = {"a": 999}                       # silent edit
    lines[0] = json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    (tmp_path / "audit.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, bad = al.verify_chain()
    assert ok is False and bad == 0


def test_audit_detects_deleted_record(tmp_path):
    al = AuditLog(path=tmp_path / "audit.jsonl")
    al.append("e1", {"a": 1})
    al.append("e2", {"b": 2})
    al.append("e3", {"c": 3})
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    del lines[1]                                       # drop a middle record
    (tmp_path / "audit.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, _ = al.verify_chain()
    assert ok is False
