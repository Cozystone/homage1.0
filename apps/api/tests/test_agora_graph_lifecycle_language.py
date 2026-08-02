"""Agora must not promote fragment/row telemetry into learning claims."""

from __future__ import annotations

import json

import apps.api.app.routers.agora as agora


def test_real_activity_counts_fragment_and_legacy_states_separately(
    tmp_path,
    monkeypatch,
) -> None:
    graph = tmp_path / "data" / "graph_scale"
    graph.mkdir(parents=True)
    (graph / "kg_triples").mkdir()
    (graph / "kg_triples" / "meta.json").write_text(
        '{"count": 7}',
        encoding="utf-8",
    )
    (graph / "abstain_queue.jsonl").write_text(
        "\n".join(
            [
                '{"term":"a","status":"pending"}',
                '{"term":"b","status":"proposal_fragment_written"}',
                '{"term":"c","status":"ingested"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(agora, "_REPO", tmp_path)

    activity = agora._real_activity()

    assert activity["kg_triples"] == 7
    assert activity["abstain_pending"] == 1
    assert activity["abstain_fragment_written"] == 1
    assert activity["abstain_ingested_legacy"] == 1


def test_templates_keep_row_fragment_and_capability_claims_separate() -> None:
    text = json.dumps(
        {
            "topics": agora._TOPICS,
            "private": agora._PRIVATE_DISCUSS,
        },
        ensure_ascii=False,
    )

    assert "{abstain_fragment_written}" in text
    assert "verified triples" not in text
    assert "re-learned the term" not in text
    assert "nothing personal ever enters" not in text
    assert "erase the trace" not in text
