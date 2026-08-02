# -*- coding: utf-8 -*-
"""Comprehensive review — ATANOR shows a frontier model (GPT-5.4 via openclaw) its REAL code and
utterances and asks for a broad critique: fluency, structure, architecture, and — crucially —
flaws ATANOR did NOT catch itself. The two then work the fix together through the constitution.

Owner (2026-07-21): don't limit GPT to narrow residual questions; let it comprehensively critique
our whole model (speech, structure, whatever) and surface flaws we missed; the two of them talk it
out and fix the code. This widens the advisor loop from 'answer my metric gap' to 'audit my body.'

Boundary (BINDING, unchanged): the critique is broad; the FIX still passes the constitution —
patch_intake refuses any change to the moral core / gates, and a surviving candidate faces staging
tests + sealed-gate no-regression. GPT advises the BODY; nothing it says enters the brain as fact.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.advisor_loop.advisor_session import ask_cli
from packages.advisor_loop.patch_intake import intake
from packages.realizer_struct.frame_realizer import realize

REPO = Path(__file__).resolve().parents[2]
LOG = REPO / "data" / "advisor_loop" / "comprehensive_review.jsonl"

# real utterances ATANOR produces, for the model to critique on naturalness/faithfulness
SPEECH_PROBES = [
    [["penguins", "is_a", "bird"], ["penguins", "capable_of", "swim"]],
    [["Einstein", "is_a", "physicist"], ["Einstein", "has_property", "german"]],
    [["coffee", "is_a", "beverage"], ["coffee", "made_of", "beans"]],
]


def _speech_samples() -> list[str]:
    return [s for s in (realize(b) for b in SPEECH_PROBES) if s]


def build_prompt(source_path: str, source_head: str, speech: list[str]) -> str:
    return (
        "You are auditing ATANOR — a No-LLM, graph-native local AI. Its philosophy: STRUCTURAL "
        "generation (relation frames + copy), NOT weight-memorization; hallucination-zero (only "
        "input facts may surface); generation is the minimal final step. It runs on ultra-low "
        "hardware.\n\n"
        "Sample utterances its structural realizer produced:\n" + "\n".join(f"  - {s}" for s in speech)
        + f"\n\nAnd the head of one real source file ({source_path}):\n```python\n{source_head}\n```\n\n"
        "The utterances and code above ARE the material to audit — do NOT ask for more, do NOT "
        "restate the task. Critique what is shown, right now, as a plain-text numbered list of "
        "EXACTLY four items: (1) a specific fluency/naturalness weakness in the utterances above "
        "(quote the bad phrase), (2) a structural/architectural flaw you infer from the code, "
        "(3) ONE concrete code-level fix (name the file/function), (4) a flaw ATANOR likely MISSED. "
        "Start item 1 immediately; no preamble, no praise, no meta."
    )


def run_review(advisor: str = "openclaw", source_rel: str = "packages/realizer_struct/frame_realizer.py",
               now_utc: float = 0.0) -> dict[str, Any]:
    """One comprehensive review round. Returns the critique + how it routed through the constitution."""
    speech = _speech_samples()
    src = (REPO / source_rel)
    head = "\n".join(src.read_text(encoding="utf-8").splitlines()[:55]) if src.exists() else ""
    prompt = build_prompt(source_rel, head, speech)
    ex = ask_cli(advisor, prompt, timeout_s=240)
    cand = intake(advisor, ex.reply, summary=f"comprehensive review by {advisor} of {source_rel}")
    rec = {
        "advisor": advisor, "source": source_rel, "speech": speech,
        "critique": ex.reply, "injection_findings": ex.injection_findings,
        "intake_status": cand.status, "intake_paths": cand.paths, "intake_reason": cand.reason,
        "ts": now_utc,
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec
