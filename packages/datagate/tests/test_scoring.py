"""QualityScorer: determinism, clamping, monotonicity."""

from __future__ import annotations

from datagate import DataGateConfig, Document, QualityScorer, doc_id_for, normalize_text


def _doc(text: str = "doc") -> Document:
    return Document(doc_id=doc_id_for(normalize_text(text)), source_path="x.txt", text=text)


def _metrics(special=0.0, link=0.0, chars=1500):
    return {"special_char_ratio": special, "link_density": link, "char_count": chars}


def test_score_deterministic():
    scorer = QualityScorer(DataGateConfig())
    m = _metrics(special=0.05, link=0.02, chars=1200)
    assert scorer.score(_doc(), m) == scorer.score(_doc(), m)


def test_score_clamped_to_range():
    scorer = QualityScorer(DataGateConfig())
    worst = scorer.score(_doc(), _metrics(special=1.0, link=1.0, chars=200))
    best = scorer.score(_doc(), _metrics(special=0.0, link=0.0, chars=5000))
    assert 0.0 <= worst <= 100.0
    assert 0.0 <= best <= 100.0
    assert best == 100.0


def test_clean_long_doc_scores_high():
    scorer = QualityScorer(DataGateConfig())
    assert scorer.score(_doc(), _metrics(special=0.01, link=0.0, chars=2000)) >= 98.0


def test_monotonic_in_special_chars():
    scorer = QualityScorer(DataGateConfig())
    low = scorer.score(_doc(), _metrics(special=0.05, chars=1500))
    high = scorer.score(_doc(), _metrics(special=0.25, chars=1500))
    assert high <= low


def test_monotonic_in_link_density():
    scorer = QualityScorer(DataGateConfig())
    low = scorer.score(_doc(), _metrics(link=0.05, chars=1500))
    high = scorer.score(_doc(), _metrics(link=0.35, chars=1500))
    assert high <= low


def test_length_penalty_shorter_scores_lower():
    scorer = QualityScorer(DataGateConfig(min_chars=200))
    short = scorer.score(_doc(), _metrics(chars=200))
    long = scorer.score(_doc(), _metrics(chars=1000))
    assert short < long
