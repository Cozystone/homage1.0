from __future__ import annotations

import inspect
import sys
import threading
from types import ModuleType

from app.routers import agentic_micro_os as router_module
from packages.agentic_micro_os.review_queue import ReviewItem, ReviewQueue
from packages.candidate_promotion_gate import CandidatePromotionGate


def _eligible_pending_item() -> ReviewItem:
    return ReviewItem(
        item_id="cloud_candidate_autonomy_boundary",
        item_type="cloud_candidate",
        title="Public systems reference",
        summary="A grounded public systems reference for later operator review.",
        source_refs=["https://example.org/public-systems-reference"],
        content_hash="a" * 64,
        risk_level="low",
        novelty_score=0.8,
        usefulness_score=0.8,
        duplicate_score=0.0,
        confidence=0.9,
        status="pending",
        created_by_loop_id="autonomy_boundary_test",
    )


def test_daemon_intent_staging_cannot_reach_production_merge(
    tmp_path,
    monkeypatch,
) -> None:
    queue = ReviewQueue()
    item = _eligible_pending_item()
    queue.items[item.item_id] = item
    merge_calls: list[bool] = []
    poison_cloud_brain = ModuleType("apps.api.app.routers.cloud_brain")

    def forbidden_merge() -> dict[str, object]:
        merge_calls.append(True)
        raise AssertionError("unattended production merge was reached")

    poison_cloud_brain.merge_candidates_to_production_now = forbidden_merge
    monkeypatch.setitem(
        sys.modules,
        "apps.api.app.routers.cloud_brain",
        poison_cloud_brain,
    )
    monkeypatch.setenv("ATANOR_ALLOW_LOCAL_PROMOTION", "1")
    monkeypatch.setattr(router_module, "REVIEW_QUEUE", queue)
    monkeypatch.setattr(
        router_module,
        "REVIEW_QUEUE_PATH",
        tmp_path / "review_queue.json",
    )
    monkeypatch.setattr(
        router_module,
        "CANDIDATE_PROMOTION_GATE",
        CandidatePromotionGate(staging_dir=tmp_path / "intent_staging"),
    )
    monkeypatch.setattr(router_module, "AUTO_STAGED_INTENT_IDS", set())

    result = router_module._auto_promote_review_queue()

    assert merge_calls == []
    assert result["auto_promoted"] == 0
    assert result["candidate_promotion"] is False
    assert result["candidate_intents_staged"] == 1
    assert result["candidate_staging_mutated"] is True
    assert result["review_queue_staging_mutated"] is True
    assert result["mutation_performed"] is True
    assert result["production_merge_attempted"] is False
    assert result["production_store_mutated"] is False
    assert item.status == "pending"
    assert item.review_notes == [
        "autonomous candidate intent staged; not promoted"
    ]
    manifests = list((tmp_path / "intent_staging").glob("*.json"))
    assert len(manifests) == 1
    assert (tmp_path / "review_queue.json").is_file()


def test_unattended_promotion_source_has_no_production_merge_seam() -> None:
    source = inspect.getsource(
        router_module._auto_promote_review_queue
    ) + inspect.getsource(router_module.AutonomousDaemon._run)

    assert "merge_candidates_to_production_now" not in source
    assert "ATANOR_ALLOW_LOCAL_PROMOTION" not in source
    assert "cloud_brain" not in source


class _StoppedSchedulerState:
    def to_dict(self) -> dict[str, object]:
        return {"enabled": False, "stopped_reason": "bounded_test"}


class _OneTickScheduler:
    def tick(self) -> dict[str, object]:
        return {
            "scheduler_id": "autonomy_boundary_test",
            "cycle_count": 1,
            "enabled": False,
            "ran": False,
            "reason": "bounded_test",
            "last_result": {},
            "last_emotion": {},
            "last_policy": {},
            "next_delay_sec": 0,
        }

    def state(self) -> _StoppedSchedulerState:
        return _StoppedSchedulerState()

    def stop(self, **kwargs) -> dict[str, object]:
        return {"allowed": True, **kwargs}


def test_daemon_activity_telemetry_reports_candidate_staging(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        router_module,
        "_authorize_agentic_action",
        lambda *args, **kwargs: {
            "allowed": True,
            "reason": "test_authorized",
        },
    )
    monkeypatch.setattr(
        router_module,
        "_persist_review_queue_under_lease",
        lambda **kwargs: {
            "allowed": True,
            "reason": "test_persisted",
            "persisted": True,
        },
    )
    monkeypatch.setattr(
        router_module,
        "_finish_agentic_run_lease",
        lambda reason, **kwargs: {"finished": True, "reason": reason},
    )
    monkeypatch.setattr(
        router_module,
        "_run_wikipedia_grounded_learning",
        lambda: {"ingested": False},
    )
    monkeypatch.setattr(
        router_module,
        "_run_abstain_drain",
        lambda: {"drained": False},
    )
    monkeypatch.setattr(
        router_module,
        "_stage_candidate_intents_exact",
        lambda **kwargs: {
            "allowed": True,
            "candidate_intents_staged": 2,
            "candidate_staging_mutated": True,
            "review_queue_staging_mutated": True,
            "review_queue_persisted": True,
            "mutation_performed": True,
            "production_merge_attempted": False,
            "production_store_mutated": False,
            "reserved_scratch_write_bytes": 1024,
            "candidate_write_authorization": {
                "allowed": True,
                "reason": "test_authorized",
            },
        },
    )
    daemon = router_module.AutonomousDaemon()
    daemon._scheduler = _OneTickScheduler()
    daemon._lease_id = "test-daemon-lease"

    daemon._run()
    status = daemon.status()

    assert status["candidate_intents_staged"] == 2
    assert status["candidate_staging_mutated"] is True
    assert status["mutation_performed"] is True
    assert status["production_merge_attempted"] is False
    assert status["production_store_mutated"] is False
    record = status["activity_log"][0]
    assert record["candidate_intents_staged"] == 2
    assert record["candidate_staging_mutated"] is True
    assert record["review_queue_staging_mutated"] is True
    assert record["mutation_performed"] is True
    assert record["production_merge_attempted"] is False
    assert record["production_store_mutated"] is False


def test_daemon_stop_does_not_finish_lease_while_thread_is_alive(
    monkeypatch,
) -> None:
    release = threading.Event()
    thread = threading.Thread(
        target=lambda: release.wait(timeout=2),
        daemon=True,
    )
    thread.start()
    finish_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        router_module,
        "_finish_agentic_run_lease",
        lambda reason, **kwargs: finish_calls.append(
            {"reason": reason, **kwargs}
        ),
    )
    daemon = router_module.AutonomousDaemon()
    daemon.STOP_JOIN_TIMEOUT_SEC = 0.01
    daemon._thread = thread
    daemon._scheduler = _OneTickScheduler()
    daemon._lease_id = "still-running-lease"

    stopped = daemon.stop(reason="bounded_stop_probe")

    assert stopped["daemon_running"] is True
    assert stopped["reason"] == "daemon_stop_pending"
    assert finish_calls == []
    release.set()
    thread.join(timeout=1)
