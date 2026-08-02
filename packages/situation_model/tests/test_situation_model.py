# -*- coding: utf-8 -*-
"""Situation model (G3): build a world from unfamiliar text and reason over it — across UNRELATED
domains (the transfer test) — and abstain, never fabricate, when the passage is silent."""
from packages.situation_model.builder import build
from packages.situation_model.reasoner import answer, comprehend


def test_builds_entities_and_ordered_events():
    text = ("Mara opened the vault. Then she moved the ledger to the annex. "
            "Finally the auditor sealed the room.")
    sit = build(text)
    assert "mara" in sit.entities and "auditor" in sit.entities
    assert len(sit.events) >= 3
    assert any(e.time_cue == "finally" for e in sit.events)


def test_who_and_what_traversal():
    text = "Mara opened the vault. Then she moved the ledger to the annex."
    assert "mara" in comprehend(text, "Who opened the vault?")["answer"].lower()
    assert "ledger" in comprehend(text, "What did Mara move?")["answer"].lower()


def test_yes_no_respects_negation():
    text = "The technician did not restart the pump. The valve stayed closed."
    r = comprehend(text, "Did the technician restart the pump?")
    assert r["supported"] and r["answer"].startswith("No")


def test_order_questions():
    text = "First the reactor cooled. Then the crew vented the gas. Finally the alarm cleared."
    assert "cool" in comprehend(text, "What happened first?")["answer"].lower()
    assert "alarm" in comprehend(text, "What happened last?")["answer"].lower()


def test_abstains_when_the_passage_is_silent():
    text = "Mara opened the vault."
    r = comprehend(text, "Who owns the building?")
    assert not r["supported"] and r["answer"] is None
    assert "does not say" in r["reply"]


def test_transfers_across_unrelated_domains_same_mechanism():
    # a chemistry passage and a logistics passage parse through the SAME mechanism (no domain code)
    chem = "The catalyst lowered the barrier. Then the reaction released heat."
    logi = "The driver loaded the crates. Then the depot dispatched the truck."
    assert "catalyst" in comprehend(chem, "Who lowered the barrier?")["answer"].lower()
    assert "driver" in comprehend(logi, "Who loaded the crates?")["answer"].lower()
    # and both abstain honestly on an unstated detail
    assert not comprehend(chem, "What color was the flask?")["supported"]
    assert not comprehend(logi, "Where does the driver live?")["supported"]
