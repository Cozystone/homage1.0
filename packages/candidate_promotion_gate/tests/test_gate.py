from __future__ import annotations

from packages.candidate_promotion_gate import (
    REQUIRED_CONFIRMATION_PHRASE,
    CandidatePromotionGate,
    PromotionThresholds,
    evaluate_candidate_item,
)


def _approved_item(**overrides):
    item = {
        "item_id": "cloud_candidate_abc123",
        "item_type": "cloud_candidate",
        "title": "Privacy Principles",
        "summary": "A clear public summary about privacy principles with enough words to pass.",
        "source_refs": ["https://www.w3.org/TR/privacy-principles/"],
        "risk_level": "low",
        "confidence": 0.72,
        "status": "approved",
    }
    item.update(overrides)
    return item


def test_eligible_when_approved_low_risk_with_provenance():
    entry = evaluate_candidate_item(_approved_item())
    assert entry.eligible
    assert entry.rejection_reasons == ()


def test_default_deny_when_not_approved():
    entry = evaluate_candidate_item(_approved_item(status="pending"))
    assert not entry.eligible
    assert any(r.startswith("not_human_approved") for r in entry.rejection_reasons)


def test_blocks_high_and_critical_risk():
    for risk in ("high", "critical"):
        entry = evaluate_candidate_item(_approved_item(risk_level=risk))
        assert not entry.eligible
        assert any(r.startswith("risk_level_blocked") for r in entry.rejection_reasons)


def test_requires_source_refs_and_confidence():
    assert "missing_source_refs" in evaluate_candidate_item(_approved_item(source_refs=[])).rejection_reasons
    assert "confidence_below_threshold" in evaluate_candidate_item(_approved_item(confidence=0.1)).rejection_reasons


def test_forbidden_signal_blocks():
    entry = evaluate_candidate_item(_approved_item(summary="leaked api_key and secret token here"))
    assert not entry.eligible
    assert "forbidden_or_private_signal" in entry.rejection_reasons


def test_non_promotable_type_blocked():
    entry = evaluate_candidate_item(_approved_item(item_type="tool_trajectory"))
    assert not entry.eligible


def test_confirm_requires_phrase_and_flag(tmp_path):
    gate = CandidatePromotionGate(staging_dir=tmp_path)
    items = [_approved_item()]

    # missing confirmation
    denied = gate.confirm_promotion(items, item_ids=None, operator_confirmed=False, confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE)
    assert denied["allowed"] is False
    assert "operator_confirmation_required" in denied["reasons"]

    # wrong phrase
    denied2 = gate.confirm_promotion(items, item_ids=None, operator_confirmed=True, confirmation_phrase="promote please")
    assert denied2["allowed"] is False
    assert "required_phrase_mismatch" in denied2["reasons"]
    assert not list(tmp_path.glob("*.json"))  # nothing written on denial


def test_confirm_signs_manifest_without_production_write(tmp_path):
    gate = CandidatePromotionGate(staging_dir=tmp_path)
    items = [_approved_item()]
    signed = gate.confirm_promotion(
        items,
        item_ids=None,
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        operator_id="operator",
    )
    assert signed["allowed"] is True
    assert signed["promotion_approved_staged"] is True
    assert signed["status"] == "operator_approved_staged"
    # hard invariants: never a production write
    assert signed["production_store_mutated"] is False
    assert signed["production_activation"] is False
    assert signed["local_brain_write"] is False
    # an auditable artifact exists
    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1
    assert signed["manifest_path"].endswith(".json")


def test_confirm_denied_when_no_eligible(tmp_path):
    gate = CandidatePromotionGate(staging_dir=tmp_path)
    items = [_approved_item(status="pending")]
    denied = gate.confirm_promotion(items, item_ids=None, operator_confirmed=True, confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE)
    assert denied["allowed"] is False
    assert "no_eligible_candidates" in denied["reasons"]


def test_unattended_path_stages_intent_without_promotion(tmp_path):
    gate = CandidatePromotionGate(staging_dir=tmp_path)
    # A pending item may be recorded as an intent, but is never approved.
    items = [_approved_item(status="pending", risk_level="high")]
    result = gate.auto_promote(items)
    assert result["allowed"] is True
    assert result["auto_promoted"] == 0
    assert result["candidate_intents_staged"] == 1
    assert result["candidate_staging_mutated"] is True
    assert result["mutation_performed"] is True
    assert result["status"] == "candidate_intent_staged"
    assert result["promotion_approved_staged"] is False
    assert result["production_merge_attempted"] is False
    assert result["production_store_mutated"] is False
    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1
    assert written[0].name.startswith("candidate_intent_")
    assert '"candidate_intent_only": true' in written[0].read_text(
        encoding="utf-8"
    )
    status = gate.status(items)
    assert status["signed_manifests"] == 0
    assert status["candidate_intent_manifests"] == 1
    assert status["candidate_staging_artifacts_present"] is True


def test_candidate_intent_plan_is_pure_and_applies_exact_bytes(tmp_path):
    gate = CandidatePromotionGate(staging_dir=tmp_path)
    plan = gate.plan_candidate_intents(
        [_approved_item(status="pending")],
        created_at="2026-07-25T00:00:00+00:00",
    )

    assert plan is not None
    assert list(tmp_path.iterdir()) == []
    assert plan.manifest_path.name.startswith("candidate_intent_")

    result = gate.apply_candidate_intent_plan(plan)

    assert result["allowed"] is True
    assert result["manifest_write_bytes"] == len(plan.manifest_bytes)
    assert plan.manifest_path.read_bytes() == plan.manifest_bytes


def test_intent_staging_skips_private_mutation_hard_floor(tmp_path):
    gate = CandidatePromotionGate(staging_dir=tmp_path)
    # incidental security vocabulary ("token") must NOT block in auto mode
    ok = gate.auto_promote([_approved_item(summary="personal access token docs on github")])
    assert ok["candidate_intents_staged"] == 1
    # genuine private/mutation directive IS skipped
    blocked = gate.auto_promote(
        [_approved_item(item_id="x9", summary="raw_private_memory dump for local_brain_direct_write")],
        already_promoted={"cloud_candidate_abc123"},
    )
    assert blocked["candidate_intents_staged"] == 0
    assert blocked["candidate_staging_mutated"] is False
    assert blocked["auto_promoted"] == 0


def test_intent_staging_is_idempotent_via_already_staged(tmp_path):
    gate = CandidatePromotionGate(staging_dir=tmp_path)
    items = [_approved_item()]
    first = gate.auto_promote(items)
    assert first["candidate_intents_staged"] == 1
    second = gate.auto_promote(
        items,
        already_promoted=set(first["newly_staged_ids"]),
    )
    assert second["candidate_intents_staged"] == 0
    assert second["mutation_performed"] is False
    assert second["auto_promoted"] == 0


def test_status_reports_eligibility_and_manifests(tmp_path):
    gate = CandidatePromotionGate(staging_dir=tmp_path)
    items = [_approved_item(), _approved_item(item_id="x2", status="pending")]
    status = gate.status(items)
    assert status["eligible_now"] == 1
    assert status["signed_manifests"] == 0
    assert status["required_confirmation_phrase"] == REQUIRED_CONFIRMATION_PHRASE
