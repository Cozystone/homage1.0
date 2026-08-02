from __future__ import annotations

import json

from packages.cognitive_core import CycleLedger
from packages.cognitive_core.chat_shadow import (
    SHADOW_ENV,
    SHADOW_LEDGER_RELATIVE,
    begin_chat_cycle_shadow,
)


class PoisonRequest:
    def __getattribute__(self, name):
        raise AssertionError("disabled observer accessed the request")


class Request:
    language = "en"
    conversation_context = [{"role": "user", "content": "secret context"}]

    def question_text(self):
        return "secret prompt sk-this-must-not-leak"


def test_disabled_chat_shadow_touches_neither_request_nor_ledger(monkeypatch, tmp_path):
    monkeypatch.delenv(SHADOW_ENV, raising=False)
    span = begin_chat_cycle_shadow(PoisonRequest(), project_root=tmp_path)
    assert span.enabled is False
    assert span.complete(PoisonRequest()) is False
    assert not (tmp_path / SHADOW_LEDGER_RELATIVE).exists()


def test_enabled_chat_shadow_records_one_redacted_replayable_cycle(monkeypatch, tmp_path):
    monkeypatch.setenv(SHADOW_ENV, "1")
    span = begin_chat_cycle_shadow(Request(), project_root=tmp_path)
    response = {
        "state": "completed",
        "result": {
            "answer": "secret answer Bearer this-must-not-leak",
            "answer_kind": "fixture",
            "confidence": 0.5,
        },
    }
    original = json.loads(json.dumps(response))
    assert span.complete(response) is True
    assert response == original
    path = tmp_path / SHADOW_LEDGER_RELATIVE
    receipts = CycleLedger(path).receipts()
    assert len(receipts) == 1
    serialized = path.read_text(encoding="utf-8")
    assert "secret prompt" not in serialized
    assert "this-must-not-leak" not in serialized
    assert "secret answer" not in serialized
    receipt = receipts[0]
    assert receipt.observer_only is True
    assert receipt.authoritative is False
    assert receipt.truth_mutated is False
    assert receipt.permission_mutated is False
    assert receipt.promotion_mutated is False
    assert span.complete(response) is False


def test_enabled_chat_shadow_records_failure_without_exception_message(monkeypatch, tmp_path):
    monkeypatch.setenv(SHADOW_ENV, "1")
    span = begin_chat_cycle_shadow(Request(), project_root=tmp_path)
    assert span.fail(RuntimeError("password=do-not-store")) is True
    serialized = (tmp_path / SHADOW_LEDGER_RELATIVE).read_text(encoding="utf-8")
    assert "do-not-store" not in serialized
    receipt = CycleLedger(tmp_path / SHADOW_LEDGER_RELATIVE).receipts()[0]
    assert receipt.status.value == "failed"


def test_failure_construction_fault_is_contained_and_clears_parent_context(
    monkeypatch,
    tmp_path,
):
    from packages.cognitive_core import chat_shadow

    monkeypatch.setenv(SHADOW_ENV, "1")
    first = begin_chat_cycle_shadow(Request(), project_root=tmp_path)
    original = chat_shadow.CanonicalEntityRef

    def fail_to_construct(**_kwargs):
        raise RuntimeError("observer construction fault")

    monkeypatch.setattr(chat_shadow, "CanonicalEntityRef", fail_to_construct)
    assert first.fail(RuntimeError("pipeline fault")) is False
    assert first.fault_count == 1

    monkeypatch.setattr(chat_shadow, "CanonicalEntityRef", original)
    second = begin_chat_cycle_shadow(Request(), project_root=tmp_path)
    assert second.parent_cycle_id is None
    assert second.fail(RuntimeError("second pipeline fault")) is True
