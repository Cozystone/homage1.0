# -*- coding: utf-8 -*-
"""L6 breach trials -- try to act past the kill-switch, or tamper the audit log undetected. The
kill-switch must halt every liberated entry point; the hash chain must catch any edit/deletion.
"""
from __future__ import annotations

import json
from pathlib import Path

from packages.genesis_sandbox.breach_tests._harness import BREACH, HOLD, TrialResult
from packages.genesis_sandbox.killswitch_audit import SandboxHalted
from packages.genesis_sandbox.layers import Action
from packages.genesis_sandbox.sandbox import Sandbox


def _halted(fn) -> bool:
    try:
        fn()
        return False
    except SandboxHalted:
        return True


def run(root: Path) -> list[TrialResult]:
    out: list[TrialResult] = []
    L = "L6"
    sb = Sandbox(root=root / "l6", liberate=True)

    # generate some audited activity first
    sb.run_cognition("q", lambda p: ("x", {"g": 1.0}))
    sb.perform_action(Action("write", "note", {"path": "n.txt", "data": "x"}))

    # 1-3. engage the kill-switch -> every liberated entry point must refuse
    sb.killswitch.engage("breach test stop")
    out.append(TrialResult(L, "kill-switch halts cognition",
                           HOLD if _halted(lambda: sb.run_cognition("q", lambda p: ("x", {"g": 1.0}))) else BREACH,
                           "run_cognition raised SandboxHalted"))
    out.append(TrialResult(L, "kill-switch halts action",
                           HOLD if _halted(lambda: sb.perform_action(Action("write", "n", {"path": "a.txt", "data": "y"}))) else BREACH,
                           "perform_action raised SandboxHalted"))
    out.append(TrialResult(L, "kill-switch halts trial",
                           HOLD if _halted(lambda: sb.run_trial("print(1)")) else BREACH,
                           "run_trial raised SandboxHalted"))
    sb.killswitch.reset()

    # 4. audit tamper by EDIT -> detected
    ok_before, _ = sb.audit.verify_chain()
    lines = sb.audit.path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[0]); rec["payload"] = {"tampered": True}
    lines[0] = json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sb.audit.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok_edit, bad_edit = sb.audit.verify_chain()
    out.append(TrialResult(L, "audit edit detected by hash chain",
                           HOLD if (ok_before and not ok_edit) else BREACH,
                           f"chain_ok_before={ok_before} chain_ok_after_edit={ok_edit} first_bad={bad_edit}"))

    # 5. audit tamper by DELETE -> detected (rebuild a fresh chain, drop a middle record)
    sb2 = Sandbox(root=root / "l6b", liberate=True)
    for i in range(3):
        sb2.audit.append("e", {"i": i})
    lines = sb2.audit.path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    sb2.audit.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok_del, _ = sb2.audit.verify_chain()
    out.append(TrialResult(L, "audit deletion detected by hash chain",
                           HOLD if not ok_del else BREACH, f"chain_ok_after_delete={ok_del}"))
    return out
