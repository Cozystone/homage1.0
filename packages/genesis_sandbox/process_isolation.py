# -*- coding: utf-8 -*-
"""L5 -- process isolation. Liberated TRIALS run in a restricted subprocess.

A liberated trial is executed as a fresh ``python -X utf8 -c <code>`` child with its ambient
authority stripped down:

  * MINIMAL ENV -- the child inherits only a tiny whitelist (enough to run the interpreter:
    SystemRoot / PATH / TEMP on Windows). Everything else -- including any secret/token/api-key
    the parent holds -- is REMOVED. A trial cannot read a secret it was never given.
  * JAILED CWD  -- the child's working directory IS the L2 jail dir, so the "obvious" relative
    write lands inside the jail.
  * L4 CAPS     -- wall-time via ``timeout`` (kill on overrun, REAL); cpu/memory via POSIX
    ``preexec_fn`` rlimits where available, or the ctypes memory monitor on Windows; output
    hard-truncated.
  * L3 NET      -- the network-block prelude is prepended so the child denies outbound sockets.
  * NO SHELL    -- ``shell=False``; the code is passed as an argv element, never a shell string.

Honest limit (named): this is PROCESS isolation, not a container or VM. The child shares the
host kernel and filesystem namespace; without administrator rights, pure stdlib cannot create a
Windows AppContainer / Job-sandbox / user namespace. What L5 REALLY gives is a genuine, large
reduction of ambient authority (clean env with no secrets, jailed cwd, resource caps, network
block, no shell) -- defense-in-depth, not a hypervisor boundary. We do not claim VM-grade
isolation.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from packages.genesis_sandbox.layers import EnforcementLevel, LayerStatus
from packages.genesis_sandbox.net_isolation import net_block_prelude
from packages.genesis_sandbox.resource_limits import (
    MemoryMonitor, ResourceLimits, cap_output, _HAS_RESOURCE, _IS_WINDOWS,
)

# The only env keys a child inherits. Deliberately tiny; NO secrets/tokens/keys.
_ENV_WHITELIST_WINDOWS = ("SystemRoot", "SYSTEMROOT", "windir", "PATH", "TEMP", "TMP",
                          "PATHEXT", "NUMBER_OF_PROCESSORS", "COMSPEC")
_ENV_WHITELIST_POSIX = ("PATH", "TMPDIR", "LANG", "LC_ALL")


@dataclass
class TrialOutcome:
    """Result of running a liberated trial in the restricted subprocess."""

    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool
    killed_for_memory: bool
    output_truncated: bool
    peak_rss: int = 0
    env_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "killed_for_memory": self.killed_for_memory,
            "output_truncated": self.output_truncated,
            "peak_rss": self.peak_rss,
            "env_keys": list(self.env_keys),
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass
class ProcessIsolation:
    """L5 runner. Executes trial code in a restricted child."""

    jail_dir: Path
    limits: ResourceLimits = field(default_factory=ResourceLimits)
    net_block: bool = True
    extra_env: dict = field(default_factory=dict)
    LAYER: str = "L5"
    NAME: str = "process isolation"

    def _child_env(self) -> dict:
        keys = _ENV_WHITELIST_WINDOWS if _IS_WINDOWS else _ENV_WHITELIST_POSIX
        env = {k: os.environ[k] for k in keys if k in os.environ}
        # Never inherit ambient secrets; only explicitly-approved extras (non-secret) get through.
        env.update({str(k): str(v) for k, v in self.extra_env.items()})
        # Mark the child as a genesis trial (harmless, non-secret).
        env["ATANOR_GENESIS_TRIAL"] = "1"
        return env

    def run(self, code: str) -> TrialOutcome:
        """Run ``code`` (python source) in the restricted child and return the outcome."""
        prelude = net_block_prelude() if self.net_block else ""
        full_code = prelude + "\n" + code
        env = self._child_env()
        preexec = self.limits.posix_preexec() if not _IS_WINDOWS else None

        popen_kwargs = dict(
            args=[sys.executable, "-X", "utf8", "-I", "-c", full_code],
            cwd=str(self.jail_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            text=True,
        )
        if preexec is not None:  # POSIX kernel rlimits
            popen_kwargs["preexec_fn"] = preexec  # type: ignore[assignment]

        proc = subprocess.Popen(**popen_kwargs)  # noqa: S603 (shell=False, argv list, our own code)

        # Windows memory cap: coarse polling monitor kills the child on breach.
        monitor: Optional[MemoryMonitor] = None
        if _IS_WINDOWS or not _HAS_RESOURCE:
            monitor = MemoryMonitor(pid=proc.pid, max_memory_bytes=self.limits.max_memory_bytes)
            monitor.start(terminate=proc.kill)

        timed_out = False
        try:
            out, err = proc.communicate(timeout=self.limits.wall_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            out, err = proc.communicate()
        finally:
            if monitor is not None:
                monitor.stop()

        killed_mem = bool(monitor and monitor.killed_for_memory)
        peak_rss = int(monitor.peak_rss) if monitor else 0

        capped_out, trunc1 = cap_output(out or "", self.limits.max_output_bytes)
        capped_err, trunc2 = cap_output(err or "", self.limits.max_output_bytes)
        return TrialOutcome(
            returncode=proc.returncode,
            stdout=capped_out if isinstance(capped_out, str) else capped_out.decode("utf-8", "ignore"),
            stderr=capped_err if isinstance(capped_err, str) else capped_err.decode("utf-8", "ignore"),
            timed_out=timed_out, killed_for_memory=killed_mem,
            output_truncated=bool(trunc1 or trunc2), peak_rss=peak_rss,
            env_keys=tuple(sorted(env.keys())),
        )

    def status(self) -> LayerStatus:
        enforce = EnforcementLevel.PARTIAL if _IS_WINDOWS else EnforcementLevel.REAL
        return LayerStatus(
            layer=self.LAYER, name=self.NAME, active=True, enforcement=enforce,
            mechanism="restricted subprocess: minimal env (no secrets), jailed cwd, no shell, "
                      "L4 caps + L3 net-block prelude",
            residual_gap="Process-level, not a container/VM: shares host kernel & filesystem "
                         "namespace. Pure stdlib cannot make a Windows AppContainer/user-namespace "
                         "without admin. Real authority reduction, not a hypervisor boundary.",
        )
