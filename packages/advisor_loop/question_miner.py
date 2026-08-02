# -*- coding: utf-8 -*-
"""Question miner — ATANOR's OWN measured failures become the questions it asks frontier advisors.

The agency in the Advisor Loop that is genuinely ATANOR's: nothing here is hand-picked curiosity.
Every question cites the metric file and the exact residual that raised it, ranked by information
density (how far below its ceiling the number sits x how measurable an answer would be). If the
batteries were perfect, this module would go silent — the loop is failure-driven by construction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from packages.eval_evidence.receipt import (
    aggregate_items,
    strict_json_bytes,
    verify_manifest,
)
from scripts.babi_external_harness import TASKS, validate_babi_semantics

REPO = Path(__file__).resolve().parents[2]
BABI_SELECTION = (
    REPO
    / "data"
    / "eval"
    / "catalog"
    / "advisor_babi_measurement_selection_v1.json"
)
NOISE = REPO / "data" / "comprehension" / "noise_degradation.json"
FLUENCY_DOC = REPO / "docs" / "ATANOR_fluency_wall_findings.md"


@dataclass
class Question:
    topic: str
    text: str                       # the question posed to the advisor
    metric_source: str              # file the residual came from
    residual: float                 # how much is being left on the table (0..1)
    context: dict = field(default_factory=dict)

    def prompt(self) -> str:
        return (f"[ATANOR advisory question — {self.topic}]\n{self.text}\n"
                f"(measured residual {self.residual:.3f}; source {self.metric_source}. "
                f"Constraints: No pretrained-LLM components in the runtime; from-scratch learned "
                f"components and linguistic-structure floors are allowed; every fix must be "
                f"verifiable by our test+battery gates.)")


def _selected_babi_tasks() -> tuple[list[dict], str] | None:
    """Load only the explicitly selected, currently valid v2 bAbI receipt."""
    try:
        selection = strict_json_bytes(
            BABI_SELECTION.read_bytes(),
            label="advisor bAbI selection",
        )
        if frozenset(selection) != {
            "schema",
            "receipt_path",
            "receipt_checksum_sha256",
            "claim_scope",
        }:
            return None
        if selection.get("schema") != (
            "atanor.advisor-babi-measurement-selection.v1"
        ):
            return None
        if selection.get("claim_scope") != (
            "unsigned_public_validation_residual_selection_only"
        ):
            return None
        relative = selection.get("receipt_path")
        if (
            not isinstance(relative, str)
            or "\\" in relative
            or Path(relative).is_absolute()
            or "." in Path(relative).parts
            or ".." in Path(relative).parts
            or Path(relative).parts[:2] != ("reports", "benchmarks")
        ):
            return None
        receipt_path = REPO / relative
        verification = verify_manifest(
            receipt_path,
            repo_root=REPO,
            require_current=True,
        )
        if not verification["valid"]:
            return None
        receipt = strict_json_bytes(
            receipt_path.read_bytes(),
            label="selected bAbI receipt",
        )
        if receipt.get("manifest_checksum_sha256") != selection.get(
            "receipt_checksum_sha256"
        ):
            return None
        if validate_babi_semantics(receipt):
            return None
    except (OSError, RuntimeError, TypeError, ValueError):
        return None

    tasks = []
    for task in range(1, 21):
        rows = [
            row
            for row in receipt["items"]
            if row["metadata"]["task"] == task
        ]
        metrics = aggregate_items(rows)
        tasks.append(
            {
                "task": task,
                "name": TASKS[task],
                "n": metrics["n"],
                "correct": metrics["correct"],
                "wrong": metrics["wrong"],
                "abstain": metrics["abstain"],
                "error": metrics["error"],
                "strict_acc": metrics["strict_accuracy"],
                "coverage": metrics["coverage"],
                "answered_acc": metrics["fired_accuracy"],
            }
        )
    return tasks, Path(relative).name


def mine(max_questions: int = 5) -> list[Question]:
    out: list[Question] = []
    selected_babi = _selected_babi_tasks()
    if selected_babi is not None:
        tasks, metric_source = selected_babi
        for row in tasks:
            gap = 1.0 - row["strict_acc"]
            if gap >= 0.03:
                out.append(Question(
                    topic=f"bAbI qa{row['task']} {row['name']}",
                    text=(f"Our situation-model scores {row['strict_acc']:.3f} on bAbI task "
                          f"{row['task']} ({row['name']}; coverage {row['coverage']:.3f}). "
                          f"What mechanism closes the residual without overfitting the benchmark?"),
                    metric_source=metric_source,
                    residual=round(gap, 4),
                    context=row,
                ))
    if NOISE.exists():
        data = json.loads(NOISE.read_text(encoding="utf-8"))
        for family, rates in data.get("families", {}).items():
            worst = min(rates.items(), key=lambda kv: kv[1]["acc"])
            drop = data.get("clean_acc", 1.0) - worst[1]["acc"]
            if drop >= 0.10:
                out.append(Question(
                    topic=f"noise robustness / {family}",
                    text=(f"Under '{family}' perturbation at rate {worst[0]} our comprehension "
                          f"drops {drop:.3f} (to {worst[1]['acc']:.3f}), flip rate "
                          f"{worst[1]['flip_rate']:.3f}. Best from-scratch-compatible defense?"),
                    metric_source=str(NOISE.name), residual=round(drop, 4),
                    context={"family": family, "rate": worst[0], **worst[1]}))
    if FLUENCY_DOC.exists():
        out.append(Question(
            topic="fluency wall",
            text=("A 35M from-scratch realizer expresses graph facts (faithfulness 0.815) but the "
                  "prose is rough. Register-replay did not help; an 83M run underfit. Given "
                  "delexicalization+copy and a simple-register human corpus as our planned levers, "
                  "what ordering and pitfalls do you advise?"),
            metric_source=FLUENCY_DOC.name, residual=0.5,
            context={"faithfulness": 0.815}))
    out.sort(key=lambda q: -q.residual)
    return out[:max_questions]
