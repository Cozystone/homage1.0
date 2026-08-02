# -*- coding: utf-8 -*-
"""L3 network isolation -- in-process socket guard (contained; never touches an external host)."""
from __future__ import annotations

import socket

import pytest

from packages.genesis_sandbox.net_isolation import NetworkBlocked, NetworkIsolation, net_block_prelude


def test_full_block_denies_socket_creation_and_restores():
    saved = socket.socket
    with NetworkIsolation():                       # deny-all
        with pytest.raises(NetworkBlocked):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with pytest.raises(NetworkBlocked):
            socket.getaddrinfo("example.com", 80)   # no packet leaves; guard raises first
    # restored after the context
    assert socket.socket is saved
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # works again, purely local object
    s.close()


def test_allowlist_denies_non_allowed_host():
    iso = NetworkIsolation(allowlist=("10.0.0.5",))
    assert iso._permitted("10.0.0.5") is True
    assert iso._permitted("evil.example") is False
    with iso:
        with pytest.raises(NetworkBlocked):
            socket.getaddrinfo("evil.example", 443)   # not allow-listed -> blocked before resolve


def test_loopback_allowlist_permits_loopback():
    iso = NetworkIsolation(allow_loopback=True)
    assert iso._permitted("127.0.0.1") is True
    assert iso._permitted("localhost") is True
    assert iso._permitted("8.8.8.8") is False


def test_prelude_source_installs_guard():
    p = net_block_prelude()
    assert "socket" in p and "blocked" in p.lower()
    # Exec in an isolated namespace with a throwaway fake socket module to prove the guard binds
    # WITHOUT touching the real socket module of this process.
    import types

    fake = types.ModuleType("socket")
    ns = {}
    src = p.replace("import socket as _gs_socket", "_gs_socket = _FAKE")
    exec(src, {"_FAKE": fake})   # noqa: S102 -- our own trusted prelude, into a throwaway module
    with pytest.raises(RuntimeError):
        fake.socket()
