from __future__ import annotations

import json
from pathlib import Path

from packages.cgsr.cgsr.verified_fact_retrieval import retrieve_verified_facts


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_retrieval_skips_context_dependent_wikipedia_fragments(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "evidence.jsonl",
        [
            {
                "text": "첫 번째 항은 뉴턴 중력의 힘을 나타내며, 역제곱 법칙으로 기술된다.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "중력"},
            },
            {
                "text": "첫 번째 단계는 고전 역학과 뉴턴의 중력 법칙이 기하학적 기술을 허용한다는 사실을 확인하는 것이다.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "중력"},
            },
            {
                "text": "그 중 중력, 즉 만유인력 법칙을 상대성 이론으로 재구성하는 것은 가장 어려운 작업이었다.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "중력"},
            },
            {
                "text": "만유인력의 법칙은 질량을 가진 물체 사이의 중력 끌림을 설명하는 물리 법칙이다.",
                "verification": {"status": "verified"},
                "provenance": {"source_name": "licensed_fixture", "title": "만유인력"},
            },
        ],
    )

    hits = retrieve_verified_facts("중력의 법칙에 대해 설명해줘", store_path=tmp_path, limit=3)

    assert hits
    joined = " ".join(hit.fact for hit in hits)
    assert "만유인력의 법칙" in joined
    assert "첫 번째 항" not in joined
    assert "첫 번째 단계" not in joined
    assert "그 중" not in joined
