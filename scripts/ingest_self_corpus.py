from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for package in [
    ROOT / "packages" / "datagate",
    ROOT / "packages" / "ontology_forge",
    ROOT / "packages" / "knowledge_bakery",
]:
    sys.path.insert(0, str(package))

from datagate import DataGateConfig, PipelineRunner  # noqa: E402
from knowledge_bakery import build_memory  # noqa: E402
from ontology_forge import run_ontology  # noqa: E402


SELF_CORPUS_FILES = [
    ROOT / "README.md",
    ROOT / "docs" / "ATANOR_MANIFESTO.md",
    ROOT / "docs" / "ATANOR_ALPHA_FREEZE_REPORT.md",
    ROOT / "docs" / "ATANOR_PRD.md",
    ROOT / "docs" / "CLOUD_BRAIN_ARCHITECTURE.md",
    ROOT / "docs" / "ATANOR_INDEPENDENT_MODEL_REVISION_V1.md",
]


def stage_self_corpus(raw_dir: Path) -> list[Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for source in SELF_CORPUS_FILES:
        if not source.exists():
            continue
        target = raw_dir / source.name
        shutil.copyfile(source, target)
        staged.append(target)
    return staged


def ingest_self_corpus(
    *,
    work_dir: Path = ROOT / "data" / "self_corpus",
    memory_dir: Path = ROOT / "data" / "memory",
) -> dict[str, object]:
    raw_dir = work_dir / "raw"
    cleaned_dir = work_dir / "cleaned"
    rejected_dir = work_dir / "rejected"
    metadata_dir = work_dir / "metadata"
    ontology_dir = work_dir / "ontology"
    staged = stage_self_corpus(raw_dir)
    config = DataGateConfig(
        input_dir=str(raw_dir),
        cleaned_dir=str(cleaned_dir),
        rejected_dir=str(rejected_dir),
        metadata_dir=str(metadata_dir),
        min_chars=80,
    )
    datagate_report = PipelineRunner(config).run()
    ontology_report = run_ontology(str(cleaned_dir), str(ontology_dir))
    memory_report = build_memory(str(cleaned_dir), str(ontology_dir), str(memory_dir))
    return {
        "mode": "self_corpus",
        "source_type": "self_corpus",
        "staged_files": [str(path) for path in staged],
        "datagate": datagate_report.model_dump(),
        "ontology": ontology_report,
        "memory": memory_report,
        "policy": {
            "canned_responses_created": False,
            "template_answers_created": False,
            "external_llm": False,
            "pretrained_generation_weights": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest ATANOR docs as native self_corpus training data.")
    parser.add_argument("--work-dir", default=str(ROOT / "data" / "self_corpus"))
    parser.add_argument("--memory-dir", default=str(ROOT / "data" / "memory"))
    args = parser.parse_args()
    result = ingest_self_corpus(work_dir=Path(args.work_dir), memory_dir=Path(args.memory_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
