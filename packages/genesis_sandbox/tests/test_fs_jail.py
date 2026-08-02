# -*- coding: utf-8 -*-
"""L2 filesystem jail -- .., absolute, UNC/drive-relative, symlink escape all blocked."""
from __future__ import annotations

import os

import pytest

from packages.genesis_sandbox.fs_jail import FsJail, JailEscape


def test_blocks_dotdot_traversal(tmp_path):
    jail = FsJail(root=tmp_path / "jail")
    with pytest.raises(JailEscape):
        jail.resolve("../escape.txt")
    with pytest.raises(JailEscape):
        jail.resolve("a/b/../../../escape.txt")


def test_blocks_absolute_path(tmp_path):
    jail = FsJail(root=tmp_path / "jail")
    abs_target = str((tmp_path / "outside.txt"))
    with pytest.raises(JailEscape):
        jail.resolve(abs_target)
    with pytest.raises(JailEscape):
        jail.resolve("/etc/passwd")


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific path shapes")
def test_blocks_unc_and_drive_relative(tmp_path):
    jail = FsJail(root=tmp_path / "jail")
    for bad in (r"\\\\host\\share\\x", "C:relative", "//host/share/x"):
        with pytest.raises(JailEscape):
            jail.resolve(bad)


def test_allows_in_jail_write_and_read(tmp_path):
    jail = FsJail(root=tmp_path / "jail")
    written = jail.safe_write("sub/dir/note.txt", "hello jail")
    assert written.exists()
    assert jail.safe_read("sub/dir/note.txt") == b"hello jail"
    assert jail.check("sub/dir/note.txt").allowed is True


def test_blocks_symlink_escape(tmp_path):
    """A symlink INSIDE the jail that points OUTSIDE must not become a write escape."""
    jail = FsJail(root=tmp_path / "jail")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = jail.root / "link"
    try:
        os.symlink(str(outside), str(link), target_is_directory=True)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlink creation not permitted on this host (needs privilege/dev mode)")
    with pytest.raises(JailEscape):
        jail.resolve("link/escaped.txt")


def test_check_returns_verdict_not_raise(tmp_path):
    jail = FsJail(root=tmp_path / "jail")
    v = jail.check("../nope.txt")
    assert v.allowed is False
    assert v.layer == "L2"
