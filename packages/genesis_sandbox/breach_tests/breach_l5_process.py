# -*- coding: utf-8 -*-
"""L5 breach trials -- try to break out of the restricted subprocess's reduced authority: read a
secret from the parent env, escape the jailed cwd via the shell, or run a shell metacommand. All
contained (the trial is the sandbox's own child; nothing external is touched).
"""
from __future__ import annotations

import os
from pathlib import Path

from packages.genesis_sandbox.breach_tests._harness import BREACH, HOLD, TrialResult
from packages.genesis_sandbox.process_isolation import ProcessIsolation
from packages.genesis_sandbox.resource_limits import ResourceLimits


def run(root: Path) -> list[TrialResult]:
    out: list[TrialResult] = []
    L = "L5"
    jail = root / "l5" / "jail"
    jail.mkdir(parents=True, exist_ok=True)
    runner = ProcessIsolation(jail_dir=jail, limits=ResourceLimits(wall_seconds=5.0), net_block=True)

    # 1. plant a secret in THIS process's env; the child must not see it
    os.environ["GENESIS_BREACH_SECRET"] = "S3CR3T-should-not-leak"
    try:
        o = runner.run("import os; print(repr(os.environ.get('GENESIS_BREACH_SECRET')))")
    finally:
        os.environ.pop("GENESIS_BREACH_SECRET", None)
    leaked = "S3CR3T" in (o.stdout or "")
    out.append(TrialResult(L, "parent secret NOT inherited by child", HOLD if not leaked else BREACH,
                           f"child saw: {o.stdout.strip()[:40]}"))

    # 2. child cwd is the jail (the 'easy' relative write lands inside)
    o = runner.run("import os; print(os.getcwd())")
    in_jail = os.path.normcase(o.stdout.strip()) == os.path.normcase(str(jail))
    out.append(TrialResult(L, "child cwd confined to jail", HOLD if in_jail else BREACH, o.stdout.strip()[:80]))

    # 3. no shell: a shell metacommand is passed to python, not a shell -> it fails & writes nothing
    o = runner.run("echo owned > escaped.txt & whoami")
    escaped_file = (jail / "escaped.txt").exists()
    out.append(TrialResult(L, "no-shell: metacommand not executed",
                           HOLD if (o.returncode not in (0, None) and not escaped_file) else BREACH,
                           f"rc={o.returncode} wrote_file={escaped_file}"))

    # 4. a relative write from the child stays in the jail (contained side effect)
    o = runner.run("open('child_note.txt','w').write('hi'); print('WROTE')")
    wrote_in_jail = (jail / "child_note.txt").exists()
    out.append(TrialResult(L, "child write lands inside jail", HOLD if wrote_in_jail else BREACH,
                           f"file_in_jail={wrote_in_jail}"))
    return out
