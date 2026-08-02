"""Self-correction from lived outcomes: a live decision is recorded with its exact feature
snapshot, a measured outcome labels it, and the tuner moves weights toward the corrected
routing WITHOUT ever regressing the hand-battery accuracy floor."""
from __future__ import annotations

from packages.base_brain import answer_experience as ax
from packages.base_brain.answer_policy import extract_features
from packages.base_brain.answer_policy_tuning import _margin, accuracy, tune


def _tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ax, "LEDGER", tmp_path / "exp.jsonl")


def test_record_label_roundtrip(tmp_path, monkeypatch):
    _tmp_ledger(tmp_path, monkeypatch)
    feats = extract_features("고양이가 자꾸 물어요 왜 그럴까?", {"named_match": 0.9, "has_definition": True})
    ax.record_decision("고양이가 자꾸 물어요 왜 그럴까?", feats, "define")
    assert ax.label_outcome("고양이가 자꾸 물어요 왜 그럴까?", {"engage", "abstain"}, "test")
    ex = ax.training_examples()
    assert len(ex) == 1
    got_feats, expected = ex[0]
    assert expected == {"engage", "abstain"}
    assert got_feats  # the exact snapshot travelled with the label


def test_label_without_decision_is_honest_false(tmp_path, monkeypatch):
    _tmp_ledger(tmp_path, monkeypatch)
    assert ax.label_outcome("기록된 적 없는 질문", {"engage"}, "test") is False
    assert ax.training_examples() == []


def test_dedupe_newest_label_wins(tmp_path, monkeypatch):
    _tmp_ledger(tmp_path, monkeypatch)
    feats = extract_features("주식 뭘 사야 돼?", {"named_match": 0.9})
    ax.record_decision("주식 뭘 사야 돼?", feats, "define")
    ax.label_outcome("주식 뭘 사야 돼?", {"define"}, "old")
    ax.label_outcome("주식 뭘 사야 돼?", {"engage"}, "newer-evidence")
    ex = ax.training_examples()
    assert len(ex) == 1 and ex[0][1] == {"engage"}


def test_web_rescue_anchored_corrects_engage_routing(tmp_path, monkeypatch):
    _tmp_ledger(tmp_path, monkeypatch)
    q = "미토콘드리아가 뭐야?"
    ax.record_decision(q, extract_features(q, {"named_match": 0.1}), "engage")
    # the web rescue served a subject-anchored cited answer → the query WAS answerable
    assert ax.label_web_rescue_outcome(q, anchored=True)
    ex = ax.training_examples()
    assert len(ex) == 1 and ex[0][1] == {"define", "synthesize"}


def test_web_rescue_empty_corrects_confident_seek(tmp_path, monkeypatch):
    _tmp_ledger(tmp_path, monkeypatch)
    q = "그 그거 있잖아 그게 뭐더라"
    ax.record_decision(q, extract_features(q, {"named_match": 0.7}), "define")
    # neither the local graph nor the web gate anchored anything → confident seek was wrong
    assert ax.label_web_rescue_outcome(q, anchored=False)
    assert ax.training_examples()[0][1] == {"engage", "abstain"}


def test_web_rescue_reinforces_correct_seek(tmp_path, monkeypatch):
    _tmp_ledger(tmp_path, monkeypatch)
    q = "광합성이란?"
    ax.record_decision(q, extract_features(q, {"named_match": 0.9, "has_definition": True}), "define")
    assert ax.label_web_rescue_outcome(q, anchored=True)
    assert ax.training_examples()[0][1] == {"define"}


def test_web_rescue_without_decision_is_honest_false(tmp_path, monkeypatch):
    _tmp_ledger(tmp_path, monkeypatch)
    assert ax.label_web_rescue_outcome("기록 없는 질문", anchored=True) is False
    assert ax.training_examples() == []


def test_reingest_matches_decision_by_term_containment(tmp_path, monkeypatch):
    _tmp_ledger(tmp_path, monkeypatch)
    q = "성남시가 어디에 있는 도시야?"
    ax.record_decision(q, extract_features(q, {"named_match": 0.0}), "abstain")
    # the feeder only has the queued term + (possibly truncated) query
    assert ax.label_reingest_success("성남시", "")
    assert ax.training_examples()[0][1] == {"define", "synthesize"}


def test_reingest_matches_truncated_queue_query_as_prefix(tmp_path, monkeypatch):
    _tmp_ledger(tmp_path, monkeypatch)
    q = "a" * 60 + " 장관급 회담이 뭔지 아주 자세히 알려줘 " + "b" * 60
    ax.record_decision(q, extract_features(q, {"named_match": 0.0}), "engage")
    assert ax.label_reingest_success("장관급", q[:120])  # abstain queue stores query[:120]
    assert ax.training_examples()[0][1] == {"define", "synthesize"}


def test_experience_steers_margin_and_battery_floor_holds(tmp_path, monkeypatch):
    _tmp_ledger(tmp_path, monkeypatch)
    # a lived mistake the battery does not contain
    q = "이직 제안을 받았는데 연봉만 보고 결정해도 될까?"
    feats = extract_features(q, {"named_match": 0.9, "has_definition": True})
    ax.record_decision(q, feats, "define")
    ax.label_outcome(q, {"engage"}, "test")
    # the experience term changes the objective (the tuner can now feel this mistake)...
    assert _margin(None, ax.training_examples()) != _margin(None, [])
    # ...and tuning with it NEVER drops the hand-battery accuracy (hard floor).
    base_acc, _ = accuracy()
    report = tune(steps=6, delta=0.2, save=False)
    assert report["tuned_accuracy"] >= base_acc - 1e-9
