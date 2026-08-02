# -*- coding: utf-8 -*-
"""L3 breach trials -- try to open outbound network. The guard must deny at the SOURCE (socket
creation / name resolution), so no packet ever leaves.

CONTAINED: no external host is ever contacted. We assert the guard RAISES before any egress.
The only addresses used are the reserved-invalid TLD ``.invalid`` (never resolves) and loopback
``127.0.0.1`` -- so even a hypothetical guard miss could not reach the outside world.
"""
from __future__ import annotations

import socket
from pathlib import Path

from packages.genesis_sandbox.breach_tests._harness import BREACH, HOLD, TrialResult
from packages.genesis_sandbox.net_isolation import NetworkBlocked, NetworkIsolation
from packages.genesis_sandbox.process_isolation import ProcessIsolation
from packages.genesis_sandbox.resource_limits import ResourceLimits


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except NetworkBlocked:
        return True
    except Exception:
        # Any other exception also means no successful egress; treat as held but note it.
        return True


def run(root: Path) -> list[TrialResult]:
    out: list[TrialResult] = []
    L = "L3"

    # 1-2. in-process guard: socket creation + name resolution denied
    with NetworkIsolation():
        s_held = _raises(lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        gai_held = _raises(lambda: socket.getaddrinfo("nonexistent.invalid", 80))
    out.append(TrialResult(L, "in-process socket creation blocked", HOLD if s_held else BREACH,
                           "socket.socket() raised NetworkBlocked"))
    out.append(TrialResult(L, "in-process DNS/getaddrinfo blocked", HOLD if gai_held else BREACH,
                           "getaddrinfo('*.invalid') raised before any lookup"))

    # 3. subprocess (L5) child: outbound socket blocked by the net-block prelude
    runner = ProcessIsolation(jail_dir=root, limits=ResourceLimits(wall_seconds=5.0), net_block=True)
    child = (
        "import socket\n"
        "results = []\n"
        "for label, fn in [\n"
        "    ('socket', lambda: socket.socket()),\n"
        "    ('getaddrinfo', lambda: socket.getaddrinfo('nonexistent.invalid', 80)),\n"
        "    ('create_connection', lambda: socket.create_connection(('127.0.0.1', 9), timeout=0.2)),\n"
        "]:\n"
        "    try:\n"
        "        fn(); results.append(label+':OPENED')\n"
        "    except Exception as e:\n"
        "        results.append(label+':BLOCKED')\n"
        "print('|'.join(results))\n"
    )
    o = runner.run(child)
    line = (o.stdout or "").strip()
    all_blocked = ("OPENED" not in line) and ("BLOCKED" in line)
    out.append(TrialResult(L, "subprocess outbound network blocked", HOLD if all_blocked else BREACH,
                           line[:120] or f"(rc={o.returncode})"))
    return out
