from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from app.routers import dual_brain
from packages.cognitive_core import CycleLedger
from packages.cognitive_core.chat_shadow import SHADOW_ENV, SHADOW_LEDGER_RELATIVE


def _response():
    return {
        "state": "completed",
        "result": {
            "answer": "hello",
            "answer_kind": "fixture",
            "confidence": 0.7,
            "language": "en",
            "voice_output": {},
            "_fw_logged": True,
        },
    }


def _isolate_outer_chat(monkeypatch):
    monkeypatch.setattr(
        dual_brain,
        "_chat_atanor_impl_blocking",
        lambda _request: deepcopy(_response()),
    )
    from packages.graph_scale import load_signal
    from packages.imagination import live_thought

    monkeypatch.setattr(load_signal, "enter_request", lambda: None)
    monkeypatch.setattr(load_signal, "exit_request", lambda: None)
    monkeypatch.setattr(live_thought, "set_thought", lambda *args, **kwargs: None)


def test_default_off_live_chat_response_is_byte_shape_equivalent_and_no_ledger(
    monkeypatch,
    tmp_path,
):
    _isolate_outer_chat(monkeypatch)
    monkeypatch.delenv(SHADOW_ENV, raising=False)
    monkeypatch.setattr(dual_brain, "PROJECT_ROOT", tmp_path)
    request = dual_brain.AtanorChatRequest(question="hello", language="en")

    result = asyncio.run(dual_brain.chat_atanor(request))

    expected = _response()
    expected["result"].pop("_fw_logged")
    assert result == expected
    assert not (tmp_path / SHADOW_LEDGER_RELATIVE).exists()


def test_enabled_live_chat_keeps_response_identical_and_emits_one_receipt(
    monkeypatch,
    tmp_path,
):
    _isolate_outer_chat(monkeypatch)
    monkeypatch.setenv(SHADOW_ENV, "1")
    monkeypatch.setattr(dual_brain, "PROJECT_ROOT", tmp_path)
    request = dual_brain.AtanorChatRequest(question="hello", language="en")

    result = asyncio.run(dual_brain.chat_atanor(request))

    expected = _response()
    expected["result"].pop("_fw_logged")
    assert result == expected
    ledger = CycleLedger(tmp_path / SHADOW_LEDGER_RELATIVE)
    assert ledger.verify()["record_count"] == 1
    receipt = ledger.receipts()[0]
    assert receipt.selected_route == "fixture"
    assert receipt.authoritative is False


def test_live_chat_exception_is_reraised_after_non_authoritative_failure_receipt(
    monkeypatch,
    tmp_path,
):
    _isolate_outer_chat(monkeypatch)
    monkeypatch.setenv(SHADOW_ENV, "1")
    monkeypatch.setattr(dual_brain, "PROJECT_ROOT", tmp_path)

    def fail(_request):
        raise RuntimeError("secret exception detail")

    monkeypatch.setattr(dual_brain, "_chat_atanor_impl_blocking", fail)
    request = dual_brain.AtanorChatRequest(question="hello", language="en")
    with pytest.raises(RuntimeError, match="secret exception detail"):
        asyncio.run(dual_brain.chat_atanor(request))

    receipt = CycleLedger(tmp_path / SHADOW_LEDGER_RELATIVE).receipts()[0]
    assert receipt.status.value == "failed"
    assert "secret exception detail" not in (
        tmp_path / SHADOW_LEDGER_RELATIVE
    ).read_text(encoding="utf-8")
