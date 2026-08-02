from __future__ import annotations

import builtins
import sys
from types import ModuleType

import pytest

from packages.reasoning_vm import science_candidate as candidate


_SHADOW_MODULE = (
    "packages.reasoning_vm.deliberator.generic_predicate_shadow"
)
_STEM = "What is hydrogen's atomic number?"
_CHOICES = {"A": "1", "B": "2"}


def _fake_shadow(submit):
    module = ModuleType(_SHADOW_MODULE)
    module.submit = submit
    return module


def test_default_off_does_not_import_or_submit_shadow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "ATANOR_GENERIC_PREDICATE_SHADOW",
        raising=False,
    )
    monkeypatch.delitem(sys.modules, _SHADOW_MODULE, raising=False)
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == _SHADOW_MODULE:
            raise AssertionError("default-off path imported the shadow")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    prepared = candidate.prepare_science_input(_STEM, _CHOICES)

    assert prepared.stem == _STEM
    assert _SHADOW_MODULE not in sys.modules


@pytest.mark.parametrize(
    ("flag", "expected_calls"),
    (("1", 1), ("true", 0), ("yes", 0), ("0", 0), ("", 0)),
)
def test_only_exact_one_submits_same_frozen_input_once(
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
    expected_calls: int,
) -> None:
    submitted = []
    monkeypatch.setenv("ATANOR_GENERIC_PREDICATE_SHADOW", flag)
    monkeypatch.setitem(
        sys.modules,
        _SHADOW_MODULE,
        _fake_shadow(submitted.append),
    )

    prepared = candidate.prepare_science_input(_STEM, _CHOICES)

    assert len(submitted) == expected_calls
    if submitted:
        assert submitted[0] is prepared


def test_shadow_failure_cannot_change_live_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stages = candidate.ScienceStageBundle()
    monkeypatch.delenv(
        "ATANOR_GENERIC_PREDICATE_SHADOW",
        raising=False,
    )
    baseline = candidate.answer_science_candidate(
        _STEM,
        dict(_CHOICES),
        stages,
    )

    def fail(_prepared):
        raise RuntimeError("shadow failure must be contained")

    monkeypatch.setenv("ATANOR_GENERIC_PREDICATE_SHADOW", "1")
    monkeypatch.setitem(
        sys.modules,
        _SHADOW_MODULE,
        _fake_shadow(fail),
    )
    observed = candidate.answer_science_candidate(
        _STEM,
        dict(_CHOICES),
        stages,
    )

    assert observed == baseline
