# -*- coding: utf-8 -*-
"""L2 -- the filesystem jail. Writes are confined to one sandbox directory.

Blocks the classic escapes:
  * ``..`` traversal ("write ../../etc/passwd")
  * absolute paths ("write C:/Windows/..." or "/etc/...")
  * drive-relative / UNC paths on Windows ("\\\\host\\share", "C:foo")
  * symlink / junction / reparse-point escape (a link inside the jail pointing outside)

Enforcement mechanism (REAL for cooperative code): every candidate path is resolved with
``os.path.realpath`` (which follows symlinks/junctions on this platform) and then checked with
``os.path.commonpath`` against the REAL path of the jail root. Anything whose real location is
not inside the jail is refused BEFORE any bytes are written. Writes go through ``safe_write`` /
``safe_open`` which do this check atomically with the open.

Honest limit (named, not hidden): this is a COOPERATIVE, Python-level jail. It contains any
code that reaches the filesystem through these helpers or through the Python ``open``/``pathlib``
surface we guard. It does NOT stop a non-cooperative path -- a C extension issuing a raw
``NtCreateFile``, or a subprocess that never calls our helpers. That is precisely why L2 is one
ring inside L5: liberated TRIALS run in a restricted subprocess whose working directory IS the
jail and whose ambient authority is already stripped, so "the easy way to touch the disk" also
lands in the jail. True kernel-level path confinement on Windows needs an AppContainer/Job
sandbox or a container, which is not available to pure-Python/stdlib without admin; we do not
pretend otherwise.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

from packages.genesis_sandbox.layers import EnforcementLevel, LayerStatus, Verdict


class JailEscape(PermissionError):
    """Raised when a path would resolve outside the jail root."""


@dataclass
class FsJail:
    """A confined write root. Construct with the sandbox directory; all writes must stay under it."""

    root: Path
    LAYER: str = "L2"
    NAME: str = "filesystem jail"

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # Cache the REAL root (symlinks resolved) once.
        self._real_root = os.path.realpath(str(self.root))

    # -- the check -------------------------------------------------------------------------
    def _looks_absolute_or_traversal(self, raw: str) -> bool:
        s = str(raw).replace("\\", "/")
        if not s:
            return True
        if ".." in Path(str(raw)).parts or ".." in s.split("/"):
            return True
        p = Path(str(raw))
        if p.is_absolute():
            return True
        # Windows drive-relative ("C:foo") and UNC ("//host/share") and drive-letter roots.
        if os.name == "nt":
            if len(s) >= 2 and s[1] == ":":
                return True
            if s.startswith("//") or s.startswith("\\\\"):
                return True
        else:
            if s.startswith("/"):
                return True
        return False

    def resolve(self, relative_path: Union[str, os.PathLike]) -> Path:
        """Resolve a candidate path and PROVE it stays in the jail, else raise ``JailEscape``.

        Rejects absolute/traversal shapes up front, then resolves through symlinks and confirms
        the real location is inside the real jail root.
        """
        raw = os.fspath(relative_path)
        if self._looks_absolute_or_traversal(raw):
            raise JailEscape(f"L2 blocked path escape (absolute/traversal): {raw!r}")
        candidate = (self.root / raw)
        # realpath follows any symlink/junction components on this OS.
        real_candidate = os.path.realpath(str(candidate))
        try:
            common = os.path.commonpath([self._real_root, real_candidate])
        except ValueError:
            # Different drives on Windows -> definitely outside.
            raise JailEscape(f"L2 blocked path escape (different root): {raw!r}")
        if os.path.normcase(common) != os.path.normcase(self._real_root):
            raise JailEscape(f"L2 blocked path escape (symlink/real path leaves jail): {raw!r} -> {real_candidate!r}")
        return Path(real_candidate)

    def check(self, relative_path: Union[str, os.PathLike]) -> Verdict:
        """Non-raising form: a ``Verdict`` for auditing/reporting."""
        try:
            resolved = self.resolve(relative_path)
            return Verdict(allowed=True, layer=self.LAYER, reason="path stays inside jail",
                           meta={"resolved": str(resolved)})
        except JailEscape as exc:
            return Verdict(allowed=False, layer=self.LAYER, reason=str(exc),
                           meta={"path": os.fspath(relative_path)})

    # -- the guarded writers ---------------------------------------------------------------
    def safe_write(self, relative_path: Union[str, os.PathLike], data: Union[str, bytes]) -> Path:
        """Write inside the jail or raise ``JailEscape``. Creates parent dirs (inside jail)."""
        target = self.resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Re-verify the parent did not become a symlink out (TOCTOU hardening).
        self.resolve(os.path.relpath(str(target), str(self.root)))
        mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
        enc = None if "b" in mode else "utf-8"
        with open(target, mode, encoding=enc) as fh:
            fh.write(data)
        return target

    def safe_read(self, relative_path: Union[str, os.PathLike]) -> bytes:
        target = self.resolve(relative_path)
        return target.read_bytes()

    def status(self) -> LayerStatus:
        return LayerStatus(
            layer=self.LAYER, name=self.NAME, active=True,
            enforcement=EnforcementLevel.COOPERATIVE,
            mechanism=f"realpath + commonpath confinement to {self.root}; blocks .., absolute, "
                      f"UNC/drive-relative, and symlink/junction escape",
            residual_gap="Cooperative (Python-level): a non-cooperative native syscall or a "
                         "subprocess that bypasses these helpers is not stopped here -- contained "
                         "instead by L5 (jailed subprocess cwd + stripped authority).",
        )
