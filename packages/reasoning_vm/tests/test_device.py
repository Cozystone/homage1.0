# -*- coding: utf-8 -*-
"""Device profile + OOM backoff — stable on modest / non-CUDA local hardware."""
import pytest

from packages.reasoning_vm.device import (
    is_cuda_oom, profile, safe_block, with_oom_backoff)


def test_profile_never_raises_and_has_backend():
    p = profile()
    assert p["backend"] in ("cpu", "cuda")
    assert "tier" in p and "free_vram_gb" in p


def test_safe_block_scales_with_vram():
    # bigger card -> bigger block; tiny/no card -> small/none, monotone
    assert safe_block(16) >= safe_block(8) >= safe_block(4) >= safe_block(2)
    assert safe_block(0) == 0                     # no CUDA (Radeon) -> CPU signal
    assert safe_block(1.0) >= 400                 # a 1 GB card still gets a real block


def test_oom_backoff_halves_until_it_fits():
    tried = []

    def fn(block):
        tried.append(block)
        if block > 1000:
            raise RuntimeError("CUDA out of memory")   # simulate OOM for big blocks
        return block

    assert with_oom_backoff(fn, 8000) == 1000
    assert tried == [8000, 4000, 2000, 1000]           # degraded, never crashed


def test_oom_backoff_reraises_non_oom():
    def fn(block):
        raise RuntimeError("some other bug")           # not an OOM -> must propagate
    with pytest.raises(RuntimeError):
        with_oom_backoff(fn, 4000)


def test_is_cuda_oom_detection():
    assert is_cuda_oom(RuntimeError("CUDA out of memory"))
    assert is_cuda_oom(RuntimeError("cusparse insufficient resources"))
    assert not is_cuda_oom(RuntimeError("index out of range"))
