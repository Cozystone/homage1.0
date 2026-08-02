# -*- coding: utf-8 -*-
"""Next-fact prediction: propose the most probable MISSING edge as a labeled
hypothesis (never a fact), excluding what the store already knows."""
import numpy as np


class _StubStore:
    def __init__(self, facts=None):
        self._facts = facts or {}
        self.writes = 0
    def facts_about(self, term, limit=80):
        return self._facts.get(term, [])
    def add(self, *a, **k):
        self.writes += 1


def _inject(monkeypatch, subject="서울", obj="도시", pred="is_a"):
    """A tiny trained space where subject+relation lands squarely on obj."""
    from packages.graph_scale import phase_space, fact_prediction
    terms = [subject, obj, "코끼리", "행성", "바다"]
    rng = np.random.default_rng(0)
    phases = rng.uniform(0, 2 * np.pi, size=(len(terms), phase_space.DIM)).astype(np.float32)
    rel = rng.uniform(0, 2 * np.pi, size=(1, phase_space.DIM)).astype(np.float32)
    # make θ_subject + r ≈ θ_obj so obj is the clear prediction for `pred`
    rel[0] = np.mod(phases[1] - phases[0], 2 * np.pi)
    phase_space._SPACE["phases"] = phases
    phase_space._SPACE["terms"] = terms
    phase_space._SPACE["idx"] = {t: i for i, t in enumerate(terms)}
    monkeypatch.setattr(phase_space, "_load", lambda: True)
    monkeypatch.setattr(fact_prediction, "_load_relations", lambda: (rel, [pred]))
    return terms


def test_predicts_the_probable_missing_edge(tmp_path, monkeypatch):
    from packages.graph_scale import fact_prediction as fp
    _inject(monkeypatch)
    monkeypatch.setattr(fp, "LEDGER", tmp_path / "pred.jsonl")
    preds = fp.predict_missing_edges("서울", store=_StubStore(), k=3)
    assert preds and preds[0]["object"] == "도시" and preds[0]["predicate"] == "is_a"
    assert 0.0 <= preds[0]["model_score"] <= 1.0


def test_excludes_already_known_edges(monkeypatch):
    """If the store ALREADY holds is_a , that's retrieval — don't
 'predict' it. (Nothing else clears the floor here, so predictions is empty.)"""
    from packages.graph_scale import fact_prediction as fp
    _inject(monkeypatch)
    store = _StubStore({"서울": [("서울", "is_a", "도시")]})
    preds = fp.predict_missing_edges("서울", store=store, k=3)
    assert all(p["object"] != "도시" for p in preds)


def test_mint_is_hedged_labeled_and_never_writes_store(tmp_path, monkeypatch):
    from packages.graph_scale import fact_prediction as fp
    _inject(monkeypatch)
    monkeypatch.setattr(fp, "LEDGER", tmp_path / "pred.jsonl")
    store = _StubStore()
    out = fp.mint_predicted_fact("서울", store=store, language="ko")
    assert out and out["hypothesis"] is True and out["source"] == "predicted_hypothesis"
    assert "유추됩니다" in out["text"] and "확인된" in out["text"]   # hedged, not asserted
    assert store.writes == 0                                        # never a production write
    # minted to the hypothesis ledger, idempotent
    assert (tmp_path / "pred.jsonl").exists()
    fp.mint_predicted_fact("서울", store=store, language="ko")
    lines = (tmp_path / "pred.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1                                          # same triple not doubled


def test_unknown_subject_yields_no_prediction(monkeypatch):
    from packages.graph_scale import fact_prediction as fp
    _inject(monkeypatch)
    assert fp.predict_missing_edges("존재하지않는것", store=_StubStore()) == []


def test_settle_confirms_when_evidence_arrives_and_retires_stale(tmp_path, monkeypatch):
    """The closed loop: a predicted hypothesis CONFIRMS once the store holds the
    exact edge; a stale unverified one RETIRES. Never promotes from here."""
    import json
    from packages.graph_scale import fact_prediction as fp
    ledger = tmp_path / "pred.jsonl"
    rows = [
        {"subject": "서울", "predicate": "is_a", "object": "도시", "status": "unverified",
         "question": "q1", "minted_at": "2026-07-09T00:00:00"},           # will confirm
        {"subject": "화성", "predicate": "is_a", "object": "행성", "status": "unverified",
         "question": "q2", "minted_at": "2000-01-01T00:00:00"},           # stale -> retire
    ]
    ledger.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                      encoding="utf-8")
    monkeypatch.setattr(fp, "LEDGER", ledger)
    store = _StubStore({"서울": [("서울", "is_a", "도시")]})   # evidence for row 1 only
    out = fp.settle(store=store, max_age_days=14.0)
    assert out["confirmed"] == 1 and out["retired"] == 1 and out["checked"] == 2
    after = {r["subject"]: r["status"] for r in
             [json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines()]}
    assert after["서울"] == "confirmed" and after["화성"] == "retired"


def test_investigate_pushes_questions_to_evidence_queue(tmp_path, monkeypatch):
    import json
    from packages.graph_scale import fact_prediction as fp
    from packages.graph_scale import abstain_queue
    ledger = tmp_path / "pred.jsonl"
    ledger.write_text(json.dumps({"subject": "서울", "predicate": "is_a", "object": "도시",
                                  "status": "unverified", "question": "서울은 도시인가?",
                                  "minted_at": "2026-07-09T00:00:00"}, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    monkeypatch.setattr(fp, "LEDGER", ledger)
    pushed = []
    monkeypatch.setattr(abstain_queue, "record_abstain", lambda q: pushed.append(q) or [q])
    assert fp.investigate(limit=5) == 1 and pushed == ["서울은 도시인가?"]
