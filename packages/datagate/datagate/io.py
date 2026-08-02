"""Filesystem I/O for DataGate: discovery, loading, and output writing.

Input is restricted to local ``.txt`` and ``.md`` files under ``data/raw``.
No network, no other formats. Output writing is full-batch overwrite.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import DataGateConfig
from .hashing import content_hash, doc_id_for, normalize_text
from .models import Document

VALID_EXTENSIONS = (".txt", ".md")
JSONL_NAME = "documents.jsonl"


def discover_files(input_dir: str | Path) -> list[str]:
    """Return sorted ``data/raw``-relative paths of all ``.txt``/``.md`` files.

    Sorting guarantees deterministic processing order. If the input directory
    does not exist it is created empty and an empty list is returned (per the
    handoff guardrail).
    """
    base = Path(input_dir)
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
        return []
    matches = [
        p
        for p in base.rglob("*")
        if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS
    ]
    return sorted(p.relative_to(base).as_posix() for p in matches)


def load_document(input_dir: str | Path, rel_path: str) -> Document:
    """Load a single document from disk.

    Raises ``UnicodeDecodeError`` / ``OSError`` on unreadable files; the runner
    catches these and converts them into ``read_error`` rejections.
    """
    full = Path(input_dir) / rel_path
    text = full.read_text(encoding="utf-8")
    normalized = normalize_text(text)
    return Document(doc_id=doc_id_for(normalized), source_path=rel_path, text=text)


def write_outputs(config: DataGateConfig, documents: list[Document]) -> None:
    """Full-batch overwrite of cleaned/, rejected/, and documents.jsonl.

    ``data/cleaned`` and ``data/rejected`` are cleared and rewritten so each run
    reflects only the latest input. ``documents.jsonl`` is rewritten with exactly
    one line per processed document, in processing (sorted-path) order.
    """
    cleaned = Path(config.cleaned_dir)
    rejected = Path(config.rejected_dir)
    metadata = Path(config.metadata_dir)

    for directory in (cleaned, rejected):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)
    metadata.mkdir(parents=True, exist_ok=True)

    for doc in documents:
        meta = doc.metadata
        assert meta is not None, "documents must carry metadata before writing"
        target = cleaned if meta.status == "accepted" else rejected
        (target / f"{meta.doc_id}.txt").write_text(doc.text, encoding="utf-8")

    jsonl_path = metadata / JSONL_NAME
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as fh:
        for doc in documents:
            assert doc.metadata is not None
            fh.write(doc.metadata.model_dump_json() + "\n")
