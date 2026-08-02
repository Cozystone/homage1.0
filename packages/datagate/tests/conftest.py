"""Shared fixtures: temp data dirs and a deterministic fixture corpus."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from datagate import DataGateConfig

# A long clean prose document (well over min_chars, low special/link ratios).
CLEAN_LONG = (
    "ATANOR is a transparent neuro-symbolic AI factory. "
    "It collects knowledge from documents, filters out low quality data, "
    "structures the survivors into an ontology and a knowledge graph, and "
    "trains a small language model from scratch. The whole process is shown "
    "on a web dashboard called BakeBoard so that every stage of the pipeline "
    "is visible and inspectable. DataGate is the quality gate that protects "
    "the small model from noisy and low quality training material. "
) * 4

SHORT_DOC = "Too short to keep."

# Two byte-for-byte identical long documents (different filenames), distinct
# from CLEAN_LONG so the dedup scenario is independent of the accepted doc.
DUP_TEXT = (
    "Deduplication keeps the training corpus clean. When the same passage "
    "appears twice it teaches the small model nothing new and skews token "
    "statistics, so DataGate keeps only the first occurrence in a run. "
) * 4
DUP_A = DUP_TEXT
DUP_B = DUP_TEXT

# Symbol soup: long enough to pass min_length, but mostly non-text glyphs.
SYMBOL_SOUP = "?댿뼋?믠뼇@#$%^&*<>{}[]|\\~`?댿뼋?믠뼇@#$%^&*<>{}=+/" * 12

# A document that is almost entirely links.
LINK_LIST = "\n".join(f"https://example.com/page/{i}" for i in range(40))

# Korean prose (Unicode alnum) ??should pass the special-char filter.
KOREAN_DOC = (
    "?몃쭏吏???щ챸???대줈 ?щ낵由??멸났吏??怨듭옣?대떎. "
    "???쒖뒪?쒖? 臾몄꽌?먯꽌 吏?앹쓣 紐⑥쑝怨???덉쭏 ?곗씠?곕? 嫄몃윭?몃떎. "
    "?묒? ?몄뼱 紐⑤뜽??泥섏쓬遺???숈뒿?쒗궎硫?洹?怨쇱젙???뱀뿉??蹂댁뿬以?? "
) * 3

EMPTY_DOC = ""


@pytest.fixture
def config(tmp_path: Path) -> DataGateConfig:
    """A DataGateConfig wired to isolated temp directories."""
    return DataGateConfig(
        input_dir=str(tmp_path / "raw"),
        cleaned_dir=str(tmp_path / "cleaned"),
        rejected_dir=str(tmp_path / "rejected"),
        metadata_dir=str(tmp_path / "metadata"),
    )


def _write(base: Path, rel: str, text: str) -> None:
    target = base / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def corpus(config: DataGateConfig) -> DataGateConfig:
    """Populate data/raw with one document per scenario and return the config."""
    raw = Path(config.input_dir)
    _write(raw, "clean_long.md", CLEAN_LONG)
    _write(raw, "short.txt", SHORT_DOC)
    _write(raw, "dup_a.txt", DUP_A)
    _write(raw, "dup_b.txt", DUP_B)
    _write(raw, "symbols.txt", SYMBOL_SOUP)
    _write(raw, "links.md", LINK_LIST)
    _write(raw, "korean.txt", KOREAN_DOC)
    _write(raw, "empty.txt", EMPTY_DOC)
    return config
