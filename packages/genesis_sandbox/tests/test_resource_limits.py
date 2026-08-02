# -*- coding: utf-8 -*-
"""L4 resource limits -- output cap REAL everywhere; platform reporting honest."""
from __future__ import annotations

import os

from packages.genesis_sandbox.layers import EnforcementLevel
from packages.genesis_sandbox.resource_limits import (
    ResourceLimits, cap_output, rss_bytes, status,
)


def test_cap_output_truncates_over_limit():
    capped, trunc = cap_output("A" * 10_000, 1024)
    assert trunc is True
    assert len(capped.encode("utf-8")) <= 1024 + 64   # + short truncation marker
    assert capped.endswith("[L4 output truncated]")


def test_cap_output_passthrough_under_limit():
    capped, trunc = cap_output("short", 1024)
    assert trunc is False
    assert capped == "short"


def test_cap_output_bytes():
    capped, trunc = cap_output(b"B" * 5000, 100)
    assert trunc is True
    assert isinstance(capped, bytes)


def test_rss_bytes_self_is_positive_or_none():
    v = rss_bytes(os.getpid())
    # On Windows via ctypes and on Linux via /proc this returns a positive int; None is an
    # honest "unavailable" that the monitor tolerates.
    assert v is None or v > 0


def test_status_reports_platform_honestly():
    st = status(ResourceLimits())
    if os.name == "nt":
        assert st.enforcement == EnforcementLevel.PARTIAL
        assert "Job Object" in st.residual_gap or "polling" in st.residual_gap
    else:
        assert st.enforcement == EnforcementLevel.REAL


def test_posix_preexec_none_on_windows():
    pe = ResourceLimits().posix_preexec()
    if os.name == "nt":
        assert pe is None            # honest: no kernel rlimit on Windows
    else:
        assert callable(pe)
