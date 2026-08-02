from __future__ import annotations

import csv
import io
from dataclasses import dataclass

import pytest

from packages.eval_evidence.receipt import BenchmarkEvidenceError
from scripts import deliberator_benchmark_receipt as receipt


@dataclass
class _Compilation:
    compiled: bool
    status: str
    surface_family: str | None
    reason: str
    schema_version: str = "atanor.deliberator.mcq_compiler.v1"
    goals: tuple = ()


def _item() -> dict:
    return {
        "ordinal": 0,
        "q": "Which one is a mammal?",
        "choices": {"A": "whale", "B": "granite"},
        "gold": "A",
        "category": "biology",
    }


def test_isolated_measurement_reuses_one_compilation_and_separates_correctness() -> None:
    compilation = _Compilation(
        compiled=True,
        status="compiled",
        surface_family="category_membership",
        reason="typed_goal_candidates_emitted",
    )
    calls = {"compile": 0}

    def compile_once(_):
        calls["compile"] += 1
        return compilation

    def engine(*_, compilation=None):
        assert compilation is not None
        return {
            "choice_key": "B",
            "mode": "grounded",
            "hops": 2,
            "multistep_fired": True,
            "compiler_schema": compilation.schema_version,
        }

    result = receipt._measure_item(
        _item(),
        compile_goals=compile_once,
        engine_pick=engine,
        facts_about=lambda _: [],
    )

    assert calls["compile"] == 1
    assert result["metadata"]["compiled"] is True
    assert result["fired"] is True
    assert result["status"] == "wrong"
    assert result["correct"] is False
    assert result["metadata"]["grounded"] is True
    assert result["metadata"]["hops"] == 2


def test_compiler_abstention_is_not_engine_error_or_capability() -> None:
    compilation = _Compilation(
        compiled=False,
        status="abstain",
        surface_family=None,
        reason="unsupported_surface_family",
    )

    result = receipt._measure_item(
        _item(),
        compile_goals=lambda _: compilation,
        engine_pick=lambda *_, **__: None,
        facts_about=lambda _: [],
    )

    assert result["status"] == "abstain"
    assert result["fired"] is False
    assert result["metadata"]["compiled"] is False
    assert result["metadata"]["compiler_reason"] == "unsupported_surface_family"


def test_gpqa_shuffle_uses_evaluator_nonce_not_question_only_seed() -> None:
    choices_a, gold_a = receipt._shuffled(
        "private stem",
        "correct",
        ["wrong 1", "wrong 2", "wrong 3"],
        ordinal=7,
        nonce=b"a" * 32,
    )
    choices_b, gold_b = receipt._shuffled(
        "private stem",
        "correct",
        ["wrong 1", "wrong 2", "wrong 3"],
        ordinal=7,
        nonce=b"a" * 32,
    )
    orders = {
        tuple(
            receipt._permutation_order(
                "private stem",
                ordinal=7,
                nonce=bytes([value]) * 32,
            )
        )
        for value in range(8)
    }

    assert choices_a == choices_b
    assert gold_a == gold_b
    assert choices_a[gold_a] == "correct"
    assert len(orders) > 1


def test_dataset_loaders_fail_closed_and_enforce_exact_census() -> None:
    mmlu = receipt._load_mmlu_pro_bytes(
        (receipt.MMLU_PRO / "slice_5.jsonl").read_bytes(),
        slice_size=5,
    )

    assert len(mmlu) == 40
    assert {row["category"] for row in mmlu} == receipt._MMLU_CATEGORIES
    with pytest.raises(BenchmarkEvidenceError, match="row 89"):
        receipt._load_gpqa_bytes(
            receipt.GPQA.read_bytes(),
            nonce=b"n" * 32,
        )
    source = io.StringIO(receipt.GPQA.read_text(encoding="utf-8"))
    reader = csv.DictReader(source)
    rows = list(reader)
    truncated = io.StringIO(newline="")
    writer = csv.DictWriter(truncated, fieldnames=reader.fieldnames)
    writer.writeheader()
    writer.writerows(rows[:-1])
    with pytest.raises(BenchmarkEvidenceError, match="198"):
        receipt._load_gpqa_bytes(
            truncated.getvalue().encode("utf-8"),
            nonce=b"n" * 32,
        )
    with pytest.raises(BenchmarkEvidenceError, match="8"):
        receipt._load_mmlu_pro_bytes(
            b"\n".join(
                (receipt.MMLU_PRO / "slice_5.jsonl").read_bytes().splitlines()[:-1]
            ),
            slice_size=5,
        )


def test_repository_source_output_is_refused_before_store_or_dataset_work() -> None:
    forbidden = receipt.REPO / "packages" / "forbidden_deliberator_receipt.json"
    with pytest.raises(BenchmarkEvidenceError, match="reports/benchmarks"):
        receipt.run(
            benchmark="mmlu-pro",
            slice_size=5,
            store_name="world_pack_full",
            output=forbidden,
        )
    assert not forbidden.exists()


def test_derived_diagnostics_are_computed_from_items() -> None:
    wrong = receipt._measure_item(
        _item(),
        compile_goals=lambda _: _Compilation(
            compiled=True,
            status="compiled",
            surface_family="category_membership",
            reason="typed_goal_candidates_emitted",
        ),
        engine_pick=lambda *_, **__: {
            "choice_key": "B",
            "mode": "grounded",
            "hops": 3,
            "multistep_fired": True,
        },
        facts_about=lambda _: [],
    )
    diagnostics = receipt._derived_engine_diagnostics([wrong])

    assert diagnostics == {
        "compiled_items": 1,
        "compiled_rate": 1.0,
        "grounded_fires": 1,
        "grounded_firing_rate": 1.0,
        "multistep_fires": 1,
        "multistep_firing_rate": 1.0,
        "max_proof_hops": 3,
    }
