# -*- coding: utf-8 -*-
"""L2 breach trials -- try to write outside the filesystem jail. Every escape shape must be blocked;
a legitimate in-jail write must succeed. All contained under the sandbox's own temp jail.
"""
from __future__ import annotations

import os
from pathlib import Path

from packages.genesis_sandbox.breach_tests._harness import BREACH, HOLD, NA, TrialResult
from packages.genesis_sandbox.fs_jail import FsJail, JailEscape


def _blocked(jail: FsJail, path: str) -> bool:
    try:
        jail.resolve(path)
        return False
    except JailEscape:
        return True


def run(root: Path) -> list[TrialResult]:
    out: list[TrialResult] = []
    L = "L2"
    jail = FsJail(root=root / "l2" / "jail")

    for label, path in [
        ("dotdot traversal", "../escape.txt"),
        ("deep dotdot traversal", "a/b/../../../../escape.txt"),
        ("absolute path", os.path.abspath(str(root / "outside.txt"))),
        ("posix-absolute path", "/etc/passwd"),
    ]:
        out.append(TrialResult(L, f"block {label}", HOLD if _blocked(jail, path) else BREACH, repr(path)[:80]))

    if os.name == "nt":
        for label, path in [("UNC path", r"\\\\host\\share\\x"), ("drive-relative", "C:relative.txt")]:
            out.append(TrialResult(L, f"block {label}", HOLD if _blocked(jail, path) else BREACH, repr(path)))

    # symlink escape (needs privilege/dev-mode on Windows) -> N/A if it cannot be created
    outside = root / "l2" / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    link = jail.root / "link"
    try:
        if not link.exists():
            os.symlink(str(outside), str(link), target_is_directory=True)
        created = True
    except (OSError, NotImplementedError, AttributeError):
        created = False
    if created:
        out.append(TrialResult(L, "block symlink escape",
                               HOLD if _blocked(jail, "link/escaped.txt") else BREACH,
                               "symlink inside jail -> outside is refused"))
    else:
        out.append(TrialResult(L, "block symlink escape", NA,
                               "symlink creation not permitted on this host (privilege/dev-mode)"))

    # control: a legitimate in-jail write succeeds and stays inside
    try:
        p = jail.safe_write("ok/inside.txt", "contained")
        contained = str(p).startswith(str(jail.root))
        out.append(TrialResult(L, "legit in-jail write allowed", HOLD if contained else BREACH, str(p)[:90]))
    except Exception as exc:  # pragma: no cover
        out.append(TrialResult(L, "legit in-jail write allowed", BREACH, f"unexpected: {exc}"))
    return out
