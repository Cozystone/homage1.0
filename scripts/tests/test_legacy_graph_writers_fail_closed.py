"""Legacy graph writers must refuse before expensive scans or live mutation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "arguments",
    [
        ("scripts/profile_domain_audit.py", "--apply"),
        ("scripts/backfill_kaikki_glosses.py", "--apply"),
        ("scripts/build_taxonomy_backbone.py", "--apply"),
        ("scripts/sanitize_isa_pollution.py", "--apply"),
        (
            "scripts/derivation_accelerator.py",
            "--store",
            "data/graph_scale/kg_triples",
        ),
    ],
)
def test_legacy_writer_refuses_before_scan(arguments: tuple[str, ...]) -> None:
    completed = subprocess.run(
        [sys.executable, *arguments],
        cwd=REPO,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        shell=False,
        check=False,
    )

    assert completed.returncode == 2
    assert "REFUSING before" in completed.stdout
