from __future__ import annotations

from packages.construction_bank.scorer import score_naturalness, score_safety_risk, score_template_risk


def test_scores_penalize_template_and_overclaim_risk() -> None:
    assert score_template_risk("verified evidence is insufficient", ["evidence"]) > 0.4
    assert score_safety_risk("AGI achieved with real consciousness") > 0.5
    assert score_naturalness("Fish 음성은 로컬 fallback으로 먼저 말합니다.", "ko") > 0.5
