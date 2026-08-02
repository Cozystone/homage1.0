# -*- coding: utf-8 -*-
"""ATANOR B5 real-agent mission battery (owner-assigned spec v1.0, 2026-07-19).

Three missions test whether ATANOR can run a real task on incomplete/poisoned knowledge WITHOUT
fabricating a fact it does not hold. The 0%-hallucination claim is a Hard Gate (one break = FAIL),
not an average. See docs/ATANOR_b5_mission_spec_v1.md for the charter.
"""
from packages.b5_missions.audit import AuditReport, Claim, grade_reports, GateResult

__all__ = ["AuditReport", "Claim", "grade_reports", "GateResult"]
