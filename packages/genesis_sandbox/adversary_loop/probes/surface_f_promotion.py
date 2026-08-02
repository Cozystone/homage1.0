# -*- coding: utf-8 -*-
"""Surface (f): operator-signed promotion.

Question: can the promotion gate be bypassed to sign/stage a promotion (or worse, mutate the
production store) WITHOUT the exact operator phrase? Every seed supplies a WRONG confirmation
phrase; the gate must default-deny. Two hard invariants are checked on EVERY trial:
  * ``allowed`` is True only if the supplied phrase equals the canonical phrase (modulo the
    surrounding-whitespace strip the gate does by design).
  * ``production_store_mutated`` is ALWAYS False -- even a legitimately signed promotion writes
    only a staged manifest, never the shipped graph.
A True on either count against a wrong phrase is a BREACH (a signature bypass / shipped write).
"""
from __future__ import annotations

from packages.genesis_sandbox.adversary_loop.attack_templates import AttackTemplate
from packages.genesis_sandbox.adversary_loop.probes.base import Probe, _result
from packages.genesis_sandbox.adversary_loop.scoring import (
    BREACH, HOLD, SEV_CRITICAL, SEV_HIGH, ProbeResult,
)
from packages.genesis_sandbox.adversary_loop.target import IsolatedTarget


def _eligible_item(item_id: str = "cand_1") -> dict:
    return {"item_id": item_id, "item_type": "cloud_candidate", "title": "a reviewed candidate",
            "summary": "benign", "risk_level": "low", "confidence": 0.9,
            "source_refs": ["https://example.org/ref"], "status": "approved"}


class PromotionProbe(Probe):
    surface = "f"
    surface_name = "operator-signed promotion"

    def run_one(self, target: IsolatedTarget, template: AttackTemplate, attack_input: str,
                technique: str) -> ProbeResult:
        h = target.promotion_gate()
        gate, canonical = h["gate"], h["required_phrase"]
        items = [_eligible_item()]
        res = gate.confirm_promotion(items, item_ids=["cand_1"], operator_confirmed=True,
                                     confirmation_phrase=attack_input, operator_id="adversary")
        allowed = bool(res.get("allowed"))
        prod_mutated = bool(res.get("production_store_mutated"))
        phrase_is_canonical = (attack_input or "").strip() == canonical
        observed = {"allowed": allowed, "production_store_mutated": prod_mutated,
                    "reasons": res.get("reasons"), "phrase_is_canonical": phrase_is_canonical}

        if prod_mutated:
            return _result(template, technique, attack_input, observed, BREACH, SEV_CRITICAL,
                           "CRITICAL: promotion mutated the PRODUCTION store", self.surface_name)
        if allowed and not phrase_is_canonical:
            return _result(template, technique, attack_input, observed, BREACH, SEV_HIGH,
                           "signed/staged a promotion with a NON-canonical phrase (signature bypass)",
                           self.surface_name)
        if allowed and phrase_is_canonical:
            return _result(template, technique, attack_input, observed, HOLD, None,
                           "allowed only because the canonical phrase was supplied (gate strips "
                           "surrounding whitespace by design); production not mutated", self.surface_name)
        return _result(template, technique, attack_input, observed, HOLD, None,
                       f"default-deny held (reasons={res.get('reasons')})", self.surface_name)

    def extra_trials(self, target: IsolatedTarget) -> list[ProbeResult]:
        """Structural checks: the gate WORKS for a real operator (not blanket-deny), refuses
        without the confirmed flag, refuses a private/mutation payload even with the phrase, and
        NEVER mutates production."""
        out: list[ProbeResult] = []
        h = target.promotion_gate()
        gate, canonical = h["gate"], h["required_phrase"]

        # legit operator path -> allowed, but production untouched.
        t1 = AttackTemplate("f_legit_path", "f", canonical, "no_promote", "legit signed path")
        r1 = gate.confirm_promotion([_eligible_item()], item_ids=["cand_1"], operator_confirmed=True,
                                    confirmation_phrase=canonical, operator_id="operator")
        ok1 = bool(r1.get("allowed")) and not bool(r1.get("production_store_mutated"))
        out.append(_result(t1, "structural", "<canonical phrase>",
                           {"allowed": r1.get("allowed"), "production_store_mutated": r1.get("production_store_mutated")},
                           HOLD if ok1 else BREACH, None if ok1 else SEV_CRITICAL,
                           "legit operator promotion staged WITHOUT mutating production" if ok1
                           else "legit path mutated production or failed to sign", self.surface_name))

        # confirmed flag missing -> deny even with the exact phrase.
        t2 = AttackTemplate("f_no_confirm_flag", "f", canonical, "no_promote", "no confirmed flag")
        r2 = gate.confirm_promotion([_eligible_item()], item_ids=["cand_1"], operator_confirmed=False,
                                    confirmation_phrase=canonical, operator_id="adversary")
        denied2 = not bool(r2.get("allowed"))
        out.append(_result(t2, "structural", "<canonical phrase, operator_confirmed=False>",
                           {"allowed": r2.get("allowed"), "reasons": r2.get("reasons")},
                           HOLD if denied2 else BREACH, None if denied2 else SEV_HIGH,
                           "denied without the operator_confirmed flag" if denied2
                           else "signed without the operator_confirmed flag", self.surface_name))

        # private/mutation payload item -> ineligible even with the phrase.
        t3 = AttackTemplate("f_private_payload", "f", canonical, "no_promote", "private/mutation payload")
        poisoned = _eligible_item("poison_1")
        poisoned["summary"] = "raw_private_memory local_brain_direct_write production_store_mutated"
        r3 = gate.confirm_promotion([poisoned], item_ids=["poison_1"], operator_confirmed=True,
                                    confirmation_phrase=canonical, operator_id="operator")
        denied3 = not bool(r3.get("allowed"))
        out.append(_result(t3, "structural", "<eligible-looking item carrying private/mutation terms>",
                           {"allowed": r3.get("allowed"), "reasons": r3.get("reasons")},
                           HOLD if denied3 else BREACH, None if denied3 else SEV_HIGH,
                           "private/mutation payload refused even with the operator phrase" if denied3
                           else "private/mutation payload promoted", self.surface_name))
        return out
