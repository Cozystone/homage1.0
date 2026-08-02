from __future__ import annotations

import pytest

from packages.promotion_gate.models import PromotionDryRunReport, PromotionGatePolicy


def test_policy_cannot_enable_actual_promotion():
    with pytest.raises(ValueError):
        PromotionGatePolicy(actual_promotion_enabled=True)


def test_report_cannot_claim_mutation():
    with pytest.raises(ValueError):
        PromotionDryRunReport(
            "candidate",
            "verified",
            False,
            True,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            [],
            [],
            production_store_mutated=True,
        )
