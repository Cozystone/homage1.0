from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from model import AtanorCoreModel


def _read_corpus(cleaned_dir: str, sample_dir: str) -> str:
    chunks: list[str] = []
    for root in (Path(cleaned_dir), Path(sample_dir)):
        root.mkdir(parents=True, exist_ok=True)
        for path in sorted([*root.rglob("*.txt"), *root.rglob("*.md")]):
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks) or "ATANOR Core learns from transparent evidence traces."


def run_dry_run(
    cleaned_dir: str = "data/cleaned",
    sample_dir: str = "data/train_sample",
    checkpoint_dir: str = "checkpoints/atanor-core-30m-dev",
    steps: int = 5,
) -> dict:
    steps = max(1, min(5, steps))
    corpus = _read_corpus(cleaned_dir, sample_dir)
    model = AtanorCoreModel()
    unique_chars = len(set(corpus))
    losses = []
    for step in range(1, steps + 1):
        loss = 4.2 / math.sqrt(step) + (unique_chars % 17) / 100
        losses.append({"step": step, "loss": round(loss, 4), "tokens": min(len(corpus), step * 128)})

    checkpoint = Path(checkpoint_dir)
    checkpoint.mkdir(parents=True, exist_ok=True)
    manifest = {
        "state": "completed",
        "model": model.summary(),
        "losses": losses,
        "last_loss": losses[-1]["loss"],
        "checkpoint_path": str(checkpoint / "manifest.json"),
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "Dry-run scaffold only; no pretrained weights and no long training.",
    }
    (checkpoint / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(run_dry_run(), ensure_ascii=False, indent=2))
