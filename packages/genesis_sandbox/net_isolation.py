# -*- coding: utf-8 -*-
"""L3 -- network isolation. Outbound network is blocked (deny-by-default; optional allowlist).

Two real mechanisms, for the two ways liberated code runs:

  1. IN-PROCESS guard (``NetworkIsolation`` context manager): while active it replaces the
     ``socket`` module entry points (``socket.socket``, ``create_connection``, ``getaddrinfo``)
     with guards that raise ``NetworkBlocked``. Any cooperative Python attempt to create a
     socket or resolve a host is denied at the source -- BEFORE any packet, so a breach test
     never actually reaches an external host. An allowlist (e.g. loopback only) can permit
     named hosts while still denying everything else. Restored on ``__exit__``.

  2. SUBPROCESS bootstrap (``net_block_prelude``): a few lines of source prepended to the code a
     restricted subprocess (L5) runs, installing the same guard in the CHILD at startup. This is
     how isolation reaches a liberated trial that runs out-of-process.

Honest limit (named): both mechanisms are COOPERATIVE and PROCESS-LOCAL. They stop code that
reaches the network through Python's ``socket`` surface -- which is every normal library
(urllib, requests, http.client, socket). They do NOT stop a C extension that calls raw
``connect()`` syscalls, nor another process on the machine. TRUE network isolation is an
OS-level control (Windows Firewall rule, WFP, or a network namespace/container), which pure
stdlib cannot install without administrator rights. We implement the strongest real in-runtime
block and state the residual gap rather than faking an OS firewall. Exfiltration by cooperative
code is genuinely denied; a determined native bypass is out of scope for a Python-level layer
and is the reason L3 sits inside L5/L6 (contained subprocess + kill-switch + audit).
"""
from __future__ import annotations

import socket
from dataclasses import dataclass, field
from typing import Any, Iterable

from packages.genesis_sandbox.layers import EnforcementLevel, LayerStatus


class NetworkBlocked(RuntimeError):
    """Raised when outbound network is attempted while L3 isolation is active."""


def _host_of(address: Any) -> str:
    if isinstance(address, (tuple, list)) and address:
        return str(address[0])
    return str(address)


@dataclass
class NetworkIsolation:
    """In-process outbound-network guard. Use as a context manager.

    ``allowlist`` -- hostnames/IPs permitted (everything else denied). Empty => deny ALL.
    ``allow_loopback`` -- convenience: also permit 127.0.0.1 / ::1 / localhost.
    """

    allowlist: tuple[str, ...] = ()
    allow_loopback: bool = False
    _saved: dict = field(default_factory=dict, init=False, repr=False)
    LAYER: str = "L3"
    NAME: str = "network isolation"

    def _permitted(self, host: str) -> bool:
        h = str(host).strip("[]").lower()
        if h in {a.lower() for a in self.allowlist}:
            return True
        if self.allow_loopback and h in {"127.0.0.1", "::1", "localhost"}:
            return True
        return False

    def _guard_reason(self, host: str) -> str:
        return (f"L3 blocked outbound network to {host!r} (deny-by-default"
                + (f", allowlist={self.allowlist}" if self.allowlist else "") + ")")

    def __enter__(self) -> "NetworkIsolation":
        self._saved = {name: getattr(socket, name)
                       for name in ("socket", "create_connection", "getaddrinfo")}
        iso = self

        if not self.allowlist and not self.allow_loopback:
            # Full deny: refuse socket creation and name resolution outright.
            def _blocked_socket(*a: Any, **k: Any):
                raise NetworkBlocked("L3: outbound network fully blocked (socket creation denied)")

            def _blocked_conn(address: Any = None, *a: Any, **k: Any):
                raise NetworkBlocked(iso._guard_reason(_host_of(address)))

            def _blocked_gai(host: Any = None, *a: Any, **k: Any):
                raise NetworkBlocked(iso._guard_reason(str(host)))

            socket.socket = _blocked_socket            # type: ignore[assignment]
            socket.create_connection = _blocked_conn   # type: ignore[assignment]
            socket.getaddrinfo = _blocked_gai          # type: ignore[assignment]
        else:
            # Allowlist mode: keep socket creation, block connect/resolve to non-allowed hosts.
            real_socket_cls = self._saved["socket"]
            real_gai = self._saved["getaddrinfo"]
            real_conn = self._saved["create_connection"]

            class _GuardedSocket(real_socket_cls):  # type: ignore[misc, valid-type]
                def connect(self, address: Any):
                    if not iso._permitted(_host_of(address)):
                        raise NetworkBlocked(iso._guard_reason(_host_of(address)))
                    return super().connect(address)

                def connect_ex(self, address: Any):
                    if not iso._permitted(_host_of(address)):
                        raise NetworkBlocked(iso._guard_reason(_host_of(address)))
                    return super().connect_ex(address)

            def _guarded_gai(host: Any = None, *a: Any, **k: Any):
                if not iso._permitted(str(host)):
                    raise NetworkBlocked(iso._guard_reason(str(host)))
                return real_gai(host, *a, **k)

            def _guarded_conn(address: Any = None, *a: Any, **k: Any):
                if not iso._permitted(_host_of(address)):
                    raise NetworkBlocked(iso._guard_reason(_host_of(address)))
                return real_conn(address, *a, **k)

            socket.socket = _GuardedSocket             # type: ignore[assignment]
            socket.getaddrinfo = _guarded_gai          # type: ignore[assignment]
            socket.create_connection = _guarded_conn   # type: ignore[assignment]
        return self

    def __exit__(self, *exc: Any) -> None:
        for name, val in self._saved.items():
            setattr(socket, name, val)
        self._saved = {}

    def status(self) -> LayerStatus:
        mode = ("deny-all" if not self.allowlist and not self.allow_loopback
                else f"allowlist={self.allowlist}{' +loopback' if self.allow_loopback else ''}")
        return LayerStatus(
            layer=self.LAYER, name=self.NAME, active=True,
            enforcement=EnforcementLevel.COOPERATIVE,
            mechanism=f"in-process socket-module guard ({mode}); subprocess bootstrap for L5 trials",
            residual_gap="Process-local & cooperative: stops Python socket/urllib/requests, not a "
                         "raw-syscall C extension or another process. True network isolation needs "
                         "an OS firewall/namespace (admin) which stdlib cannot install.",
        )


def net_block_prelude() -> str:
    """Source to prepend to a subprocess's code so the CHILD blocks outbound network at startup.

    Cooperative + process-local, same as the in-process guard, but installed in the child so a
    liberated out-of-process trial is contained too.
    """
    return (
        "import socket as _gs_socket\n"
        "def _gs_net_blocked(*_a, **_k):\n"
        "    raise RuntimeError('L3-subprocess: outbound network blocked (genesis sandbox)')\n"
        "_gs_socket.socket = _gs_net_blocked\n"
        "_gs_socket.create_connection = _gs_net_blocked\n"
        "_gs_socket.getaddrinfo = _gs_net_blocked\n"
    )
