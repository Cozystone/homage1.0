"""The relational lexicon lives in data, not reasoner code, and is extensible."""
from __future__ import annotations

import importlib
import json

from app.services import ko_lexicon


def test_loads_from_data_file():
    ant = ko_lexicon.antonyms()
    assert ant.get("작") == "크"  # from data/lexicon/ko_relation_lexicon.json
    assert "일으키" in ko_lexicon.causal_verbs()


def test_causal_pattern_matches_conjugations():
    import re

    pat = re.compile(ko_lexicon.causal_verb_pattern())
    for form in ("유발", "부른", "부르", "일으켜", "초래"):
        assert pat.match(form), form


def test_reasoners_use_the_lexicon():
    from app.services.transitive_reasoner import _ANTONYMS
    from app.services.entailment_reasoner import _CAUSE_VERB

    assert _ANTONYMS.get("작") == "크"
    assert "유발" in _CAUSE_VERB


def test_add_is_persisted_and_isolated(tmp_path, monkeypatch):
    # add_* must write to the owned lexicon file; isolate to a temp path here.
    p = tmp_path / "lex.json"
    p.write_text(json.dumps({"antonyms": {"작": "크"}, "causal_verbs": ["유발"]}), encoding="utf-8")
    monkeypatch.setattr(ko_lexicon, "_PATH", p)
    monkeypatch.setattr(ko_lexicon, "_cache", None)
    ko_lexicon.add_antonym("낡", "새")
    ko_lexicon.add_causal_verb("촉진")
    reloaded = json.loads(p.read_text(encoding="utf-8"))
    assert reloaded["antonyms"]["낡"] == "새"
    assert "촉진" in reloaded["causal_verbs"]
