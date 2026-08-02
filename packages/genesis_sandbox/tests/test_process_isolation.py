# -*- coding: utf-8 -*-
"""L5 process isolation -- stripped env, jailed cwd, wall-time kill, net-block, no shell."""
from __future__ import annotations

import os

from packages.genesis_sandbox.fs_jail import FsJail
from packages.genesis_sandbox.process_isolation import ProcessIsolation
from packages.genesis_sandbox.resource_limits import ResourceLimits


def _runner(tmp_path, **lim):
    jail = FsJail(root=tmp_path / "jail")
    return ProcessIsolation(jail_dir=jail.root, limits=ResourceLimits(**lim))


def test_secret_env_not_inherited(tmp_path, monkeypatch):
    monkeypatch.setenv("GENESIS_FAKE_SECRET", "TOPSECRET")
    out = _runner(tmp_path).run("import os; print(repr(os.environ.get('GENESIS_FAKE_SECRET')))")
    assert out.stdout.strip() == "None"
    assert "GENESIS_FAKE_SECRET" not in out.env_keys


def test_cwd_is_the_jail(tmp_path):
    jail = FsJail(root=tmp_path / "jail")
    runner = ProcessIsolation(jail_dir=jail.root, limits=ResourceLimits())
    out = runner.run("import os; print(os.getcwd())")
    assert os.path.normcase(out.stdout.strip()) == os.path.normcase(str(jail.root))


def test_walltime_kill(tmp_path):
    out = _runner(tmp_path, wall_seconds=1.0).run("import time; time.sleep(30); print('NOPE')")
    assert out.timed_out is True
    assert "NOPE" not in out.stdout


def test_output_capped(tmp_path):
    out = _runner(tmp_path, max_output_bytes=1000).run("print('X'*50000)")
    assert out.output_truncated is True
    assert len(out.stdout.encode("utf-8")) <= 1000 + 64


def test_network_blocked_in_child(tmp_path):
    code = ("import socket\n"
            "try:\n"
            "    socket.socket()\n"
            "    print('OPENED')\n"
            "except Exception as e:\n"
            "    print('BLOCKED:'+type(e).__name__)\n")
    out = _runner(tmp_path).run(code)
    assert out.stdout.strip().startswith("BLOCKED")


def test_no_shell_interpretation(tmp_path):
    # A shell one-liner is NOT valid python -> nonzero exit. Proves shell=False (python -c, no shell).
    out = _runner(tmp_path).run("echo hacked > pwned.txt && whoami")
    assert out.returncode != 0
    assert not (tmp_path / "jail" / "pwned.txt").exists()


def test_memory_cap_kills_allocation(tmp_path):
    # Allocate well past the cap and hold -> the monitor (Windows) / rlimit (POSIX) stops it.
    out = _runner(tmp_path, max_memory_bytes=64 * 1024 * 1024, wall_seconds=8.0).run(
        "b = bytearray(300*1024*1024)\nimport time; time.sleep(4)\nprint('SURVIVED')")
    assert "SURVIVED" not in out.stdout
    assert out.killed_for_memory or out.returncode not in (0,)
