# -*- coding: utf-8 -*-
"""Human-readable blind-verdict report. Carries the undecidability header first, states the honest
delta vs the self-audit plainly, and never makes a bare consciousness claim.
"""
from __future__ import annotations

from typing import Any

from packages.consciousness_blind.result import UNDECIDABILITY_HEADER, PRESENT, PARTIAL, ABSENT, CAUGHT

_SYMBOL = {PRESENT: "[PRESENT-under-blind]", PARTIAL: "[partial]", ABSENT: "[ABSENT]",
           CAUGHT: "[FALSELY-PRESENT-CAUGHT]"}


def render_report(v: dict[str, Any]) -> str:
    L: list[str] = []
    L.append("# ATANOR Consciousness-Indicator — External Blind Assessment (C-E v1)")
    L.append("")
    L.append("> **Epistemic status — read first.** " + UNDECIDABILITY_HEADER)
    L.append("")
    L.append(f"_Generated {v.get('generated_at')} — {v.get('reference')}_")
    L.append("")
    p = v["protocol"]
    L.append("## Protocol (why this is harder than the self-audit)")
    L.append("")
    L.append(f"- **Author/judge separation.** {p['author_judge_separation']}.")
    L.append(f"- **Held-out stimuli.** {p['held_out_stimuli']}.")
    L.append(f"- **Adversarial falsification.** {p['adversarial_falsification']}.")
    L.append("")
    agg = v["aggregate_blind_score"]
    L.append(f"**Aggregate blind score: {agg['present']}/{agg['of']} present-under-blind** "
             f"· {agg['partial']} partial · {agg['absent']} absent · "
             f"{agg['falsely_present_caught']} falsely-present-caught.")
    L.append("")

    # ---- the delta (the honest finding) ----
    d = v["delta_vs_self_audit"]
    L.append("## Honest delta vs the self-audit")
    L.append("")
    L.append(f"Self-audit present: **{d['self_audit_present']}/14** ({d['self_audit_source']}). "
             f"Blind present: **{d['blind_present']}/14**. Net: **{d['net']:+d}**.")
    L.append("")
    L.append(f"_{d['reading']}._")
    L.append("")
    if d["drops"]:
        L.append("Indicators the harder bar knocked from **present -> partial** (this is the honest "
                 "win, not a rubber-stamped 14/14):")
        L.append("")
        for drop in d["drops"]:
            L.append(f"- **{drop['id']}** ({drop['theory']}): self-audit `{drop['self_audit']}` -> "
                     f"blind `{drop['blind']}`. {drop['reason']}")
        L.append("")
    else:
        L.append("_No present->partial drops: the blind bar reproduced the self-audit's present set. "
                 "The value below is in the adversarial catches._")
        L.append("")

    # ---- adversarial catches (the value the self-audit could not provide) ----
    a = v["adversarial"]
    L.append("## Adversarial pass — falsifications CAUGHT")
    L.append("")
    L.append(f"**{a['caught']}/{a['of']} falsification attempts caught.** {a['note']}. Each row is a "
             "frozen/degenerate organ that reproduces a present-shaped reading; a genuinely-present "
             "indicator's control rejects it (the self-audit ran no such pass).")
    L.append("")
    L.append("| Indicator | Falsification attempt | Verdict on the stub | Caught? |")
    L.append("|---|---|---|---|")
    for row in a["details"]:
        L.append(f"| {row['id']} | {row['stub']} | `{row['adversarial_verdict']}` | "
                 f"{'yes' if row['caught'] else 'NO (judge bug)'} |")
    L.append("")

    # ---- by theory ----
    L.append("## By theory")
    L.append("")
    L.append("| Theory | Present | Partial | Absent | Caught | Present indicators |")
    L.append("|---|---|---|---|---|---|")
    for th, row in v["by_theory"].items():
        L.append(f"| {th} | {row[PRESENT]}/{row['total']} | {row[PARTIAL]} | {row[ABSENT]} | "
                 f"{row[CAUGHT]} | {', '.join(row['present_ids']) or '—'} |")
    L.append("")

    # ---- per indicator ----
    L.append("## Indicators (blind)")
    L.append("")
    for r in v["results"]:
        L.append(f"### {_SYMBOL.get(r['verdict'], r['verdict'])} {r['id']} · {r['theory']}"
                 + (f" · _{r['strength']}_" if r["verdict"] == PRESENT else ""))
        L.append(f"*{r['statement']}*")
        L.append("")
        L.append(f"- **Held-out stimulus:** {r['stimulus']}")
        L.append(f"- **Positive probe:** {r['positive_detail']} "
                 f"(strict pass={r['positive_pass']}, core/partial={r['positive_partial']})")
        L.append(f"- **Falsification control:** {r['control_detail']} "
                 f"(rejected the falsification={r['control_rejected']})")
        L.append(f"- **Integrity:** {r['integrity_reason']}.")
        L.append(f"- **Notes:** {r['notes']}")
        L.append(f"- **Organs:** " + ", ".join(f"`{p}`" for p in r["organ_paths"]))
        L.append("")

    L.append("---")
    L.append("_This instrument reports indicator properties under an adversarial developer-blind "
             "protocol. It is not, and cannot be, a measurement of phenomenal consciousness._")
    return "\n".join(L)
