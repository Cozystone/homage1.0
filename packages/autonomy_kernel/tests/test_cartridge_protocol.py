from __future__ import annotations

import pytest

from packages.autonomy_kernel.cartridge_protocol import KnowledgeCartridge, compatibility_score


def test_cartridge_raw_payload_excluded_by_default() -> None:
    cartridge = KnowledgeCartridge("c", "metadata", True, "sha256:x", ["atlas"], {"source": "fixture"}, "public", "permissive", "summary")
    assert cartridge.raw_payload_included is False
    with pytest.raises(ValueError):
        KnowledgeCartridge("bad", "metadata", True, "sha256:x", [], {}, "public", "unknown", "summary", raw_payload_included=True)


def test_compatibility_score_bounded() -> None:
    cartridge = KnowledgeCartridge("c", "metadata", True, "sha256:x", ["atlas"], {"source": "fixture"}, "public", "permissive", "summary")
    score = compatibility_score(["atlas", "graph"], cartridge)
    assert 0.0 <= score <= 1.0

