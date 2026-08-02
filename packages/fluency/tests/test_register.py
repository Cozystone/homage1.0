# -*- coding: utf-8 -*-
"""Register lever: selects clause complexity, is chosen by context (default simple), and is DATA —
a register spec is loaded from JSON and its surface vocabulary is filtered to a closed approved list.
Faithfulness/copy safety are preserved across every register (only the surface changes)."""
import json
import re

import packages.fluency.register as reg
from packages.fluency.register import (
    APPROVED_OPENERS,
    RegisterSpec,
    build_registers_pack,
    default_registers,
    load_registers,
    select_register,
)
from packages.fluency.realizer import realize
from packages.fluency.delex import Grounding
from packages.fluency.fluency_v1 import faithfulness, slot_copy_accuracy

_ENGINE = [["engine", "is_a", "machine"], ["engine", "made_of", "metal"],
           ["engine", "used_for", "propulsion"], ["engine", "capable_of", "burn fuel"],
           ["engine", "has_a", "piston"], ["engine", "capable_of", "generate power"]]


def _n_sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()])


def test_three_registers_available():
    specs = load_registers()
    assert {"simple", "neutral", "explanatory"} <= set(specs)


def test_select_register_defaults_to_simple():
    assert select_register({}) == "simple"
    assert select_register(None) == "simple"


def test_select_register_routes_explain_query_to_explanatory():
    assert select_register({"query": "explain how a heart works"}) == "explanatory"
    assert select_register({"audience": "expert"}) == "explanatory"
    assert select_register({"register": "neutral"}) == "neutral"     # explicit wins


def test_register_changes_clause_complexity():
    """simple splits one clause per sentence; neutral groups two; so simple yields MORE sentences.
    Both split the run-on that a single-register realizer would keep in one sentence."""
    simple = realize(_ENGINE, register="simple")
    neutral = realize(_ENGINE, register="neutral")
    assert _n_sentences(simple) > _n_sentences(neutral) > 1
    assert simple != neutral


def test_explanatory_raises_clause_complexity():
    """explanatory fronts a reduced clause and opens continuation sentences with a discourse
    connective — surface markers a plain register does not use."""
    expl = realize(_ENGINE, register="explanatory")
    simple = realize(_ENGINE, register="simple")
    assert expl != simple
    assert any(op in expl for op in APPROVED_OPENERS)                # discourse opener present


def test_every_register_stays_faithful_and_copy_safe():
    grounding = Grounding.from_bones(_ENGINE)
    for rid in ("simple", "neutral", "explanatory"):
        text = realize(_ENGINE, register=rid)
        faith, fab = faithfulness(text, grounding)
        assert faith == 1.0, (rid, fab)                              # no fabrication in any register
        assert slot_copy_accuracy(_ENGINE, text) == 1.0, rid        # every grounded entity copied


def test_registers_are_data_driven_with_closed_vocab(tmp_path, monkeypatch):
    """A register loaded from JSON drives behavior, and the closed-vocabulary gate strips any
    connective/opener not on the approved lists (register data cannot inject free text)."""
    custom = tmp_path / "registers.json"
    custom.write_text(json.dumps({"registers": [{
        "id": "terse", "description": "test", "max_clauses_per_sentence": 1,
        "connective_pool": ["and", "FAKE_CONNECTIVE"], "opener_pool": ["NOT_APPROVED"],
        "pronoun_after_first": True, "front_reduced": False,
    }]}), encoding="utf-8")
    monkeypatch.setattr(reg, "REGISTERS_PATH", custom)
    specs = load_registers()
    assert "terse" in specs
    assert specs["terse"].connective_pool == ("and",)               # FAKE_CONNECTIVE filtered
    assert specs["terse"].opener_pool == ()                         # NOT_APPROVED filtered


def test_build_registers_pack_writes_json(tmp_path, monkeypatch):
    out = tmp_path / "registers.json"
    monkeypatch.setattr(reg, "REGISTERS_PATH", out)
    pack = build_registers_pack()
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert {d["id"] for d in loaded["registers"]} == {"simple", "neutral", "explanatory", "conversational", "composed"}
    assert pack["approved_connectives"]                             # the closed vocab is recorded
    assert pack["approved_discourse_markers"]                       # the conversational closed vocab too


def test_default_registers_pass_closed_vocab_filter():
    for spec in default_registers().values():
        assert isinstance(spec, RegisterSpec)
        f = spec.filtered()
        assert f.connective_pool == spec.connective_pool           # defaults already approved
        assert f.opener_pool == spec.opener_pool
