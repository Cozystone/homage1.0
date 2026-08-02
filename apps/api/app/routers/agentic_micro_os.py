from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from packages.agentic_micro_os.action_bus import DashboardActionBus
from packages.agentic_micro_os.brain_access import BrainAccessRequest, BrainAccessRoad
from packages.agentic_micro_os.browser_read import BrowserReadConnector, BrowserReadRequest
from packages.agentic_micro_os.capabilities import CapabilityKernel
from packages.agentic_micro_os.host_executor import HostExecutionRequest, HostExecutor
from packages.agentic_micro_os.loop import BoundedAgentLoop, draft_skill_from_loop
from packages.agentic_micro_os.mcp_allowlist import MCPAllowlistGateway, MCPValidationRequest, default_descriptors
from packages.agentic_micro_os.policy_loop import PolicyDrivenAutonomousLoop, PolicyLoopConfig
from packages.agentic_micro_os.policy_scheduler import PolicyDrivenAutonomousScheduler, SchedulerConfig
from packages.agentic_micro_os.permission_gate import (
    AutonomySubSwitches,
    AutonomyTier,
    PermissionGate,
    PermissionScope,
)
from packages.agentic_micro_os.review_queue import ReviewQueue, ReviewStatus
from packages.candidate_promotion_gate import (
    CandidateIntentPlan,
    CandidatePromotionGate,
)
from packages.agentic_micro_os.scoped_patch_executor import (
    ScopedPatchExecutor,
    ScopedPatchRequest,
    ScopedPatchRollbackRequest,
)
from packages.agentic_micro_os.splatra_evaluator import SplatraCosmosEvaluator, SplatraEvaluationRequest
from packages.agentic_micro_os.web_explorer_loop import (
    FixtureOpenWebFetcher,
    HermesWebExplorerLoop,
    OpenWebExplorerConfig,
    OpenWebExplorerLoop,
    WebExplorerConfig,
    WebPageInput,
)
from packages.autonomy_envelope.run_lease import (
    AGENTIC_POLICY_DAEMON_RUNNER_ID,
    RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
    RunLeaseStore,
)
from packages.hermes_intake.scanner import scan_repo
from packages.neural_emotion import emit_runtime_event
from packages.neural_emotion.event_bus import EVENT_BUS
from packages.splatra_imagination import (
    ARCHETYPES,
    ImaginationGenerator,
    ImaginationSeed,
    analyze_scene_choreography,
    build_candidate_cartridge_queue,
    compile_scene_choreography,
    compile_scene_choreography_commands,
    compile_splatra_command,
    default_safety_flags,
    dispatch_candidate_queue_to_sidecar,
    SplatraSidecarDispatchResult,
    run_imagination_proof,
)


router = APIRouter(prefix="/api/agentic-os", tags=["agentic-micro-os"])

PROJECT_ROOT = Path(__file__).resolve().parents[4]
HERMES_REPO = PROJECT_ROOT / "external_repos" / "hermes-agent"


SAFETY_FLAGS = {
    "agentic_micro_os_available": True,
    "proof_only": True,
    "hermes_runtime_executed": False,
    "hermes_code_copied": False,
    "external_llm": False,
    "external_sllm": False,
    "local_brain_direct_write": False,
    "local_brain_write": False,
    "production_store_direct_write": False,
    "production_store_mutated": False,
    "candidate_promotion": False,
    "skill_auto_promoted": False,
    "unrestricted_shell": False,
    "arbitrary_js_eval": False,
    "auto_commit": False,
    "auto_push": False,
    "human_approval_required": True,
}

MODULE_STATUS = {
    "capability_kernel": "available",
    "virtual_fs": "available",
    "brain_access_road": "available",
    "splatra_cosmos_cell": "available",
    "dashboard_action_bus": "available",
    "tool_gateway": "mock_only",
    "mcp_gateway_mock": "available",
    "browser_gateway_mock": "available",
    "browser_read": "proof_only",
    "mcp_allowlist_gateway": "proof_only",
    "splatra_evaluator": "proof_only",
    "splatra_imagination_field": "proof_only",
    "web_explorer_loop": "proof_only",
    "cloud_gateway_mock": "available",
    "hermes_intake": "architecture_extracted",
}

WEB_EXPLORER_RUNS: dict[str, dict[str, Any]] = {}
WEB_EXPLORER_SKILL_DRAFTS: list[dict[str, Any]] = []
OPEN_WEB_EXPLORER_RUNS: dict[str, dict[str, Any]] = {}
REVIEW_QUEUE_PATH = PROJECT_ROOT / "runtime" / "agentic_micro_os" / "review_queue.json"
REVIEW_QUEUE = ReviewQueue.load(REVIEW_QUEUE_PATH)
PERMISSION_GATE = PermissionGate()


def _serialize_review_queue_state(state: dict[str, Any]) -> bytes:
    return json.dumps(
        state,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")


def _review_queue_snapshot_bytes() -> bytes:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        return _serialize_review_queue_state(REVIEW_QUEUE.to_state())


def _persist_review_queue_bytes(payload: bytes) -> dict[str, Any]:
    target = Path(REVIEW_QUEUE_PATH)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary_write_attempted = False
    temporary_write_completed = False
    temporary_cleanup_attempted = False
    temporary_cleanup_succeeded = False
    target_replaced = False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_write_attempted = True
        temporary.write_bytes(payload)
        temporary_write_completed = True
        temporary.replace(target)
        target_replaced = True
        return {
            "persisted": True,
            "mutation_performed": True,
            "temporary_write_attempted": True,
            "temporary_write_completed": True,
            "temporary_cleanup_attempted": False,
            "temporary_cleanup_succeeded": False,
            "temporary_path_present": False,
            "target_replaced": True,
        }
    except Exception as exc:  # persistence must not break the API
        try:
            temporary_cleanup_attempted = temporary.exists()
            if temporary_cleanup_attempted:
                temporary.unlink()
                temporary_cleanup_succeeded = True
        except Exception:  # pragma: no cover - telemetry reports residue
            temporary_cleanup_succeeded = False
        try:
            temporary_path_present = temporary.exists()
        except Exception:  # pragma: no cover - conservative telemetry
            temporary_path_present = True
        return {
            "persisted": False,
            # A completed temp write is still a real filesystem mutation even
            # when replacement fails and cleanup later removes it.
            "mutation_performed": bool(
                temporary_write_completed
                or target_replaced
                or temporary_cleanup_attempted
            ),
            "temporary_write_attempted": temporary_write_attempted,
            "temporary_write_completed": temporary_write_completed,
            "temporary_cleanup_attempted": temporary_cleanup_attempted,
            "temporary_cleanup_succeeded": (
                temporary_cleanup_succeeded
            ),
            "temporary_path_present": temporary_path_present,
            "target_replaced": target_replaced,
            "persistence_error": type(exc).__name__,
        }


def _persist_review_queue() -> bool:
    """Durable web cumulative learning: never lose autonomously-learned candidates
    or operator decisions on restart. Best-effort; never breaks a request."""
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        result = _persist_review_queue_bytes(
            _review_queue_snapshot_bytes()
        )
        return bool(result.get("persisted"))


# Track staged intent ids so the autonomous loop writes each candidate intent
# once per process. These ids are not approved or promoted candidates.
AUTO_STAGED_INTENT_IDS: set[str] = set()

# Wikipedia-grounded cumulative learning: the loop accumulates real concepts via
# the clean grounding path rather than tokenising raw HTML. Bounded to a small
# batch on a slow cadence so it stays a polite background reader.
WIKIPEDIA_GROUNDED_MIN_INTERVAL_SEC = 90.0
WIKIPEDIA_GROUNDED_TOPICS_PER_TICK = 2
_LAST_WIKIPEDIA_GROUNDED_AT = 0.0
_LAST_WIKIPEDIA_GROUNDED_RESULT: dict[str, Any] = {}


def _run_wikipedia_grounded_learning(*, force: bool = False) -> dict[str, Any]:
    """Ingest a bounded batch of clean Wikipedia-grounded concepts.

    Cadence-gated and offline-safe: on a network miss it records an honest
    "no_grounded_payloads" rather than inventing growth. Never raises."""
    global _LAST_WIKIPEDIA_GROUNDED_AT, _LAST_WIKIPEDIA_GROUNDED_RESULT
    now = time.monotonic()
    if not force and (now - _LAST_WIKIPEDIA_GROUNDED_AT) < WIKIPEDIA_GROUNDED_MIN_INTERVAL_SEC:
        return {"ingested": False, "reason": "cadence_throttled"}
    _LAST_WIKIPEDIA_GROUNDED_AT = now
    try:
        from app.services.wikipedia_grounded_learning import ingest_wikipedia_grounded_once

        result = ingest_wikipedia_grounded_once(max_topics=WIKIPEDIA_GROUNDED_TOPICS_PER_TICK)
    except Exception as exc:  # pragma: no cover - learning must never break the loop
        result = {"ingested": False, "reason": f"wikipedia_grounded_error:{type(exc).__name__}"}
    _LAST_WIKIPEDIA_GROUNDED_RESULT = result
    return result


# ── abstain -> ingest closed loop ─────────────────────────────────────────────

# already logged the missing terms. This tick DRAINS that queue: it fetches
# attributed evidence (national dictionary / search API, judge-gated, k-source)
# and ingests it, so the SAME question becomes answerable next time. Coverage
# rises WITHOUT lowering truth — the drain only stores gated, attributed facts.
ABSTAIN_DRAIN_MIN_INTERVAL_SEC = 75.0
ABSTAIN_DRAIN_TERMS_PER_TICK = 3
_LAST_ABSTAIN_DRAIN_AT = 0.0
_LAST_ABSTAIN_DRAIN_RESULT: dict[str, Any] = {}


def _run_abstain_drain(*, force: bool = False) -> dict[str, Any]:
    """Advance a bounded abstain batch into non-authoritative proposals.

    Cadence-gated, bounded web budget, judge-gated inside ``drain()``. A
    fragment is not shipped knowledge and is never credited as staged/applied.
    """
    global _LAST_ABSTAIN_DRAIN_AT, _LAST_ABSTAIN_DRAIN_RESULT
    now = time.monotonic()
    if not force and (now - _LAST_ABSTAIN_DRAIN_AT) < ABSTAIN_DRAIN_MIN_INTERVAL_SEC:
        return {"drained": False, "reason": "cadence_throttled"}
    _LAST_ABSTAIN_DRAIN_AT = now
    try:
        from packages.graph_scale import abstain_feeder, abstain_queue

        pending_before = len(abstain_queue.pending(limit=200))
        if pending_before == 0:
            result = {
                "drained": True,
                "terms": 0,
                "detected": 0,
                "fragment_written": 0,
                "proposed": 0,
                "staged": 0,
                "applied": 0,
                "pending_before": 0,
            }
        else:
            counters = abstain_feeder.drain(limit=ABSTAIN_DRAIN_TERMS_PER_TICK,
                                            log=lambda *a, **k: None)
            result = {"drained": True, "pending_before": pending_before, **counters}
    except Exception as exc:  # pragma: no cover - learning must never break the loop
        result = {"drained": False, "reason": f"abstain_drain_error:{type(exc).__name__}"}
    _LAST_ABSTAIN_DRAIN_RESULT = result
    return result


def _auto_promote_review_queue() -> dict[str, Any]:
    """Stage candidate intents without granting promotion authority.

    The legacy function name is retained for local callers, but the unattended
    path can only write a non-authoritative staging artifact and an audit note.
    It never imports or invokes a production merge path.
    """
    try:
        return _stage_candidate_intents_exact()
    except Exception as exc:  # pragma: no cover - never break the loop
        return {
            "allowed": False,
            "auto_promoted": 0,
            "candidate_promotion": False,
            "candidate_intents_staged": 0,
            "candidate_staging_mutated": False,
            "review_queue_staging_mutated": False,
            "mutation_performed": False,
            "production_merge_attempted": False,
            "production_store_mutated": False,
            "reason": f"candidate_intent_staging_error:{type(exc).__name__}",
        }
CANDIDATE_PROMOTION_GATE = CandidatePromotionGate(
    staging_dir=PROJECT_ROOT / "runtime" / "agentic_micro_os" / "promotions"
)
POLICY_LOOP_RUNS: dict[str, dict[str, Any]] = {}
POLICY_SCHEDULER_RUNS: dict[str, dict[str, Any]] = {}
POLICY_SCHEDULER = PolicyDrivenAutonomousScheduler(
    SchedulerConfig(scheduler_id="agentic_policy_scheduler_v1", enabled=False),
    event_bus=EVENT_BUS,
    review_queue=REVIEW_QUEUE,
    permission_gate=PERMISSION_GATE,
)

# The API process never owns a lease signer. Deployment bootstrap may inject a
# store that was built from an externally provisioned public-key boundary.
# Until then the runnable mechanism remains visible but has no live authority.
AGENTIC_RUN_LEASE_STORE: RunLeaseStore | None = None
AGENTIC_RUN_LEASE_RUNTIME_INSTANCE_ID = ""
AGENTIC_RUN_LEASE_SCRATCH_ROOT: Path | None = None
AGENTIC_ACTIVE_RUN_LEASE: dict[str, Any] | None = None
AGENTIC_LAST_RUN_LEASE: dict[str, Any] = {}
_AGENTIC_RUN_LEASE_LOCK = threading.RLock()
_AGENTIC_RUN_EXECUTION_LOCK = threading.RLock()
_AGENTIC_REVIEW_QUEUE_LOCK = threading.RLock()

_AGENTIC_ACTION_CLASSES = [
    "agentic.candidate_write",
    "agentic.scratch_write",
    "agentic.tick",
]
_AGENTIC_RUNNER_ARTIFACTS = (
    Path(__file__).resolve(),
    PROJECT_ROOT / "packages" / "autonomy_envelope" / "run_lease.py",
    PROJECT_ROOT / "packages" / "autonomy_envelope" / "operator_trust.py",
)
_AGENTIC_RUNNER_ARTIFACT_ROOTS = (
    PROJECT_ROOT / "packages" / "agentic_micro_os",
    PROJECT_ROOT / "packages" / "candidate_promotion_gate",
    PROJECT_ROOT / "packages" / "inner_voice",
    PROJECT_ROOT / "packages" / "neural_emotion",
    PROJECT_ROOT / "packages" / "splatra_imagination",
    PROJECT_ROOT / "packages" / "splatra_turbovec",
)


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _resolved_runtime_path(path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def configure_agentic_run_lease_store(
    store: RunLeaseStore,
    *,
    runtime_instance_id: str,
    scratch_root: Path | str,
) -> dict[str, Any]:
    """Install an externally provisioned verifier into this API process.

    This is a process/bootstrap seam, not an HTTP authority shortcut. It accepts
    no private key and no signing callback. The live context is still rebuilt
    from loaded code, exact scheduler configuration, current input state, and
    the installed external trust boundary for every activation.
    """

    if type(store) is not RunLeaseStore:
        raise TypeError("RunLeaseStore is required")
    if (
        type(runtime_instance_id) is not str
        or not runtime_instance_id
        or len(runtime_instance_id) > 256
    ):
        raise ValueError("runtime_instance_id is required")
    root = Path(scratch_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("scratch_root must be a provisioned directory")
    review_path = _resolved_runtime_path(REVIEW_QUEUE_PATH)
    candidate_path = _resolved_runtime_path(
        CANDIDATE_PROMOTION_GATE.staging_dir
    )
    if not _path_is_within(review_path, root) or not _path_is_within(
        candidate_path,
        root,
    ):
        raise ValueError(
            "review and candidate staging paths must stay inside scratch_root"
        )
    global AGENTIC_RUN_LEASE_STORE
    global AGENTIC_RUN_LEASE_RUNTIME_INSTANCE_ID
    global AGENTIC_RUN_LEASE_SCRATCH_ROOT
    with _AGENTIC_RUN_LEASE_LOCK:
        if AGENTIC_ACTIVE_RUN_LEASE is not None:
            raise RuntimeError("cannot replace run-lease store during a run")
        AGENTIC_RUN_LEASE_STORE = store
        AGENTIC_RUN_LEASE_RUNTIME_INSTANCE_ID = runtime_instance_id
        AGENTIC_RUN_LEASE_SCRATCH_ROOT = root
    return {
        "configured": True,
        "runner_id": AGENTIC_POLICY_DAEMON_RUNNER_ID,
        "runtime_instance_id": runtime_instance_id,
        "deployment_id": store.boundary.deployment_id,
        "signer_present_in_api": False,
    }


def _reset_agentic_run_lease_runtime_for_tests() -> None:
    """Test isolation only; production callers close a run through stop()."""

    global AGENTIC_RUN_LEASE_STORE
    global AGENTIC_RUN_LEASE_RUNTIME_INSTANCE_ID
    global AGENTIC_RUN_LEASE_SCRATCH_ROOT
    global AGENTIC_ACTIVE_RUN_LEASE
    global AGENTIC_LAST_RUN_LEASE
    with _AGENTIC_RUN_LEASE_LOCK:
        AGENTIC_RUN_LEASE_STORE = None
        AGENTIC_RUN_LEASE_RUNTIME_INSTANCE_ID = ""
        AGENTIC_RUN_LEASE_SCRATCH_ROOT = None
        AGENTIC_ACTIVE_RUN_LEASE = None
        AGENTIC_LAST_RUN_LEASE = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summarize_tick(payload: dict[str, Any]) -> dict[str, Any]:
    """A compact, honest activity record for one server-side tick."""

    result = payload.get("last_result") if isinstance(payload.get("last_result"), dict) else {}
    states = result.get("states") if isinstance(result, dict) else None
    last_state = states[-1] if isinstance(states, list) and states else {}
    actions = last_state.get("actions_taken") if isinstance(last_state, dict) else None
    emotion = payload.get("last_emotion") if isinstance(payload.get("last_emotion"), dict) else {}
    vector = emotion.get("vector") if isinstance(emotion, dict) else {}
    policy = payload.get("last_policy") if isinstance(payload.get("last_policy"), dict) else {}
    reasons = policy.get("reasons") if isinstance(policy, dict) else None
    return {
        "at": _utc_now_iso(),
        "cycle": payload.get("cycle_count"),
        "ran": bool(payload.get("ran")),
        "reason": payload.get("reason"),
        "actions": list(actions) if isinstance(actions, list) else [],
        "candidate_drafts": (result or {}).get("candidate_drafts", 0),
        "splatra_frames": (result or {}).get("splatra_frames", 0),
        "review_items": (result or {}).get("review_items", 0),
        "next_delay_sec": payload.get("next_delay_sec"),
        "curiosity": (vector or {}).get("curiosity"),
        "fatigue": (vector or {}).get("fatigue"),
        "policy_reason": (reasons or [None])[0] if isinstance(reasons, list) else None,
    }


class AutonomousDaemon:
    """Opt-in, operator-confirmed background driver.

    Ticks the (already operator-confirmed) scheduler on its own next_delay_sec
    cadence in a daemon thread, so the loop keeps running with no browser tab.
    Fully stoppable; bounded by the scheduler's own max_runtime/max_cycles. Never
    autostarts. A tick may durably stage candidate intent/audit artifacts, and
    reports those mutations explicitly, but it has no production merge path.
    """

    # Clamp the engine cadence to a sane server-side window.
    MIN_SLEEP = 2.0
    MAX_SLEEP = 30.0
    STOP_JOIN_TIMEOUT_SEC = 5.0
    LOG_CAP = 50

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._scheduler: PolicyDrivenAutonomousScheduler | None = None
        self._log: deque[dict[str, Any]] = deque(maxlen=self.LOG_CAP)
        self._started_at = ""
        self._stopped_at = ""
        self._stopped_reason = ""
        self._lease_id = ""

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, scheduler: PolicyDrivenAutonomousScheduler) -> dict[str, Any]:
        with self._lock:
            if self.is_running():
                return {"daemon_running": True, "reason": "already_running"}
            if not scheduler.enabled:
                # The scheduler must already be operator-confirmed/started.
                return {"daemon_running": False, "reason": scheduler.stopped_reason or "scheduler_not_enabled"}
            with _AGENTIC_RUN_LEASE_LOCK:
                active = (
                    dict(AGENTIC_ACTIVE_RUN_LEASE)
                    if AGENTIC_ACTIVE_RUN_LEASE is not None
                    else None
                )
            if active is None or active.get("mode") != "daemon":
                return {
                    "daemon_running": False,
                    "reason": "signed_operator_run_lease_required",
                }
            self._scheduler = scheduler
            self._stop.clear()
            self._log.clear()
            self._started_at = _utc_now_iso()
            self._stopped_at = ""
            self._stopped_reason = ""
            self._lease_id = str(active["lease_id"])
            self._thread = threading.Thread(target=self._run, name="atanor-autonomous-daemon", daemon=True)
            try:
                self._thread.start()
            except Exception as exc:
                self._thread = None
                self._scheduler = None
                self._lease_id = ""
                self._stop.set()
                self._stopped_at = _utc_now_iso()
                self._stopped_reason = (
                    f"daemon_thread_start_error:{type(exc).__name__}"
                )
                return {
                    "daemon_running": False,
                    "reason": self._stopped_reason,
                    "started_at": self._started_at,
                }
            return {"daemon_running": True, "reason": "daemon_started", "started_at": self._started_at}

    def reset_failed_start(
        self,
        *,
        expected_lease_id: str,
        reason: str,
    ) -> bool:
        """Discard non-running partial state owned by one failed start."""

        with self._lock:
            if self.is_running():
                return False
            if self._lease_id not in {"", expected_lease_id}:
                return False
            self._thread = None
            self._scheduler = None
            self._lease_id = ""
            self._stop.set()
            self._stopped_at = _utc_now_iso()
            self._stopped_reason = reason
            return True

    def stop(self, reason: str = "operator_stop") -> dict[str, Any]:
        self._stop.set()
        scheduler = self._scheduler
        if scheduler is not None:
            try:
                scheduler.stop(reason=reason, create_stop_file=False)
            except Exception:  # pragma: no cover - defensive
                pass
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=self.STOP_JOIN_TIMEOUT_SEC)
        running = self.is_running()
        if running:
            return {
                "daemon_running": True,
                "reason": "daemon_stop_pending",
                "requested_reason": reason,
                "stopped_at": "",
            }
        if self._lease_id:
            _finish_agentic_run_lease(
                reason,
                expected_lease_id=self._lease_id,
                expected_mode="daemon",
            )
        self._stopped_at = self._stopped_at or _utc_now_iso()
        self._stopped_reason = self._stopped_reason or reason
        return {
            "daemon_running": False,
            "reason": self._stopped_reason,
            "requested_reason": reason,
            "stopped_at": self._stopped_at,
        }

    def status(self) -> dict[str, Any]:
        scheduler = self._scheduler
        with _AGENTIC_REVIEW_QUEUE_LOCK:
            state = (
                scheduler.state().to_dict()
                if scheduler is not None
                else {}
            )
        activity = list(self._log)
        candidate_intents_staged = sum(
            int(record.get("candidate_intents_staged") or 0)
            for record in activity
        )
        candidate_staging_mutated = any(
            record.get("candidate_staging_mutated") is True
            or record.get("review_queue_staging_mutated") is True
            for record in activity
        )
        mutation_performed = any(
            record.get("mutation_performed") is True
            or (
                isinstance(record.get("review_queue_persistence"), dict)
                and record["review_queue_persistence"].get(
                    "mutation_performed"
                )
                is True
            )
            for record in activity
        )
        return {
            "daemon_running": self.is_running(),
            "started_at": self._started_at,
            "stopped_at": self._stopped_at,
            "stopped_reason": self._stopped_reason,
            "activity_log": activity,
            "scheduler_state": state,
            "candidate_intents_staged": candidate_intents_staged,
            "candidate_staging_mutated": candidate_staging_mutated,
            "mutation_performed": mutation_performed,
            "production_merge_attempted": False,
            "production_store_mutated": False,
        }

    def _run_leased_cycle(
        self,
        scheduler: PolicyDrivenAutonomousScheduler,
        lease_id: str,
    ) -> float | None:
        authorization = _authorize_agentic_action(
            "agentic.tick",
            expected_lease_id=lease_id,
            expected_mode="daemon",
        )
        if not authorization.get("allowed"):
            self._stopped_reason = str(
                authorization.get("reason")
                or "run_lease_tick_denied"
            )
            self._log.append(
                {
                    "at": _utc_now_iso(),
                    "ran": False,
                    "reason": self._stopped_reason,
                    "run_lease_authorization": authorization,
                }
            )
            return None

        with _AGENTIC_REVIEW_QUEUE_LOCK:
            queue_digest_before = _review_queue_digest()
            try:
                payload = scheduler.tick()
            except Exception as exc:  # pragma: no cover - defensive
                self._stopped_reason = (
                    f"tick_error:{type(exc).__name__}"
                )
                self._log.append(
                    {
                        "at": _utc_now_iso(),
                        "ran": False,
                        "reason": self._stopped_reason,
                    }
                )
                return None

            record = _summarize_tick(payload)
            record["run_lease_authorization"] = authorization
            self._log.append(record)
            if isinstance(payload.get("last_result"), dict):
                POLICY_SCHEDULER_RUNS[
                    str(payload.get("scheduler_id"))
                ] = payload

            persistence = _persist_review_queue_under_lease(
                previous_digest=queue_digest_before,
                expected_lease_id=lease_id,
                expected_mode="daemon",
            )
            record["review_queue_persistence"] = persistence
            if not persistence.get("allowed") or (
                persistence.get("persisted") is False
                and persistence.get("reason")
                == "review_queue_persistence_failed"
            ):
                self._stopped_reason = str(
                    persistence.get("reason")
                    or "review_queue_persistence_denied"
                )
                return None

            # AUT-0 has no network action class. The policy loop remains
            # functional with local fixtures only.
            record["wikipedia_grounded"] = {
                "executed": False,
                "reason": "run_lease_network_budget_zero",
            }
            record["abstain_drain"] = {
                "executed": False,
                "reason": "run_lease_network_budget_zero",
            }

            intent_stage = _stage_candidate_intents_exact(
                expected_lease_id=lease_id,
                expected_mode="daemon",
                require_lease=True,
            )
            record["candidate_write_authorization"] = (
                intent_stage.get("candidate_write_authorization")
            )
            record["candidate_write_reserved_bytes"] = int(
                intent_stage.get("reserved_scratch_write_bytes") or 0
            )
            record["candidate_intents_staged"] = int(
                intent_stage.get("candidate_intents_staged") or 0
            )
            record["candidate_staging_mutated"] = bool(
                intent_stage.get("candidate_staging_mutated")
            )
            record["review_queue_staging_mutated"] = bool(
                intent_stage.get("review_queue_staging_mutated")
            )
            record["review_queue_staging_persisted"] = bool(
                intent_stage.get("review_queue_persisted")
            )
            record["mutation_performed"] = bool(
                persistence.get("mutation_performed")
                or intent_stage.get("mutation_performed")
            )
            record["production_merge_attempted"] = False
            record["production_store_mutated"] = False
            if (
                not intent_stage.get("allowed")
                and intent_stage.get("reason") != "no_new_eligible"
            ):
                self._stopped_reason = str(
                    intent_stage.get("reason")
                    or "candidate_write_denied"
                )
                return None

        if not payload.get("enabled") or not payload.get("ran"):
            self._stopped_reason = str(
                payload.get("reason") or "scheduler_stopped"
            )
            return None
        delay = payload.get("next_delay_sec")
        try:
            delay_sec = float(delay)
        except (TypeError, ValueError):
            delay_sec = 5.0
        return max(self.MIN_SLEEP, min(self.MAX_SLEEP, delay_sec))

    def _run(self) -> None:
        scheduler = self._scheduler
        lease_id = self._lease_id
        if scheduler is None or not lease_id:
            return
        try:
            while not self._stop.is_set():
                with _AGENTIC_RUN_EXECUTION_LOCK:
                    if self._stop.is_set():
                        break
                    sleep_for = self._run_leased_cycle(
                        scheduler,
                        lease_id,
                    )
                if sleep_for is None:
                    break
                self._stop.wait(timeout=sleep_for)
        finally:
            self._stopped_at = _utc_now_iso()
            finish_reason = self._stopped_reason or (
                "operator_stop" if self._stop.is_set() else "daemon_exit"
            )
            self._stopped_reason = finish_reason
            if getattr(scheduler, "enabled", False):
                scheduler.stop(
                    reason=_safe_finish_reason(finish_reason),
                    create_stop_file=False,
                )
            _finish_agentic_run_lease(
                finish_reason,
                expected_lease_id=lease_id,
                expected_mode="daemon",
            )


AUTONOMOUS_DAEMON = AutonomousDaemon()


def _make_host_executor(base_path: Path | None = None) -> HostExecutor:
    root = base_path or PROJECT_ROOT
    return HostExecutor(
        gate=PERMISSION_GATE,
        project_root=PROJECT_ROOT,
        runtime_tmp_dir=root / "runtime" / "agentic_micro_os" / "tmp",
    )


HOST_EXECUTOR = _make_host_executor()


def _make_scoped_patch_executor(base_path: Path | None = None) -> ScopedPatchExecutor:
    root = base_path or PROJECT_ROOT
    return ScopedPatchExecutor(
        gate=PERMISSION_GATE,
        project_root=PROJECT_ROOT,
        backup_dir=root / "runtime" / "agentic_micro_os" / "scoped_patch_backups",
    )


SCOPED_PATCH_EXECUTOR = _make_scoped_patch_executor()


class DashboardActionRequest(BaseModel):
    action_type: str = Field(..., examples=["set_orb_state"])
    payload: dict[str, Any] = Field(default_factory=dict)


class BrainAccessApiRequest(BaseModel):
    target: str = "local_brain"
    operation: str = "local_brain_read_redacted_summary"
    query: str = ""
    scope: str = "proof"
    redaction_level: str = "redacted"
    purpose: str = "proof-only API request"
    requested_by_loop_id: str = "agentic_os_api"


class LoopProposeRequest(BaseModel):
    goal: str = "Inspect SPLATRA Cosmos Cell and draft a safe proposal."
    max_cycles: int = 1


class BrowserReadApiRequest(BaseModel):
    url: str = "http://127.0.0.1:3041/?section=agent-os"
    visible_text: str = "Agentic Micro-OS proof-only status"
    metadata: dict[str, Any] = Field(default_factory=dict)
    max_chars: int = 1200


class MCPValidateApiRequest(BaseModel):
    descriptor: str = "render_preview"
    descriptor_hash: str | None = None
    method: str = "render_preview"
    payload: dict[str, Any] = Field(default_factory=lambda: {"scene": "orb"})


class SplatraEvaluateApiRequest(BaseModel):
    candidate_id: str = "splatra_candidate_0"
    particle_budget: int = 50_000
    target_fps: int = 60
    include_city_proof: bool = False
    emotion_probe: dict[str, float] = Field(default_factory=lambda: {"valence": 0.2, "arousal": 0.6, "audio_energy": 0.0})


class SplatraImaginationGenerateApiRequest(BaseModel):
    seed_id: str = "api_imagination_0"
    archetype: str = "constellation"
    randomness: float = 0.5
    valence: float = 0.0
    arousal: float = 0.45
    curiosity: float = 0.5
    speaking_energy: float = 0.0
    fatigue: float = 0.0
    review_pressure: float = 0.0
    novelty_found: float = 0.0
    reduced_motion: bool = False
    state: str = "imagining"
    particle_budget: int = 1600
    lod_target: int = 0
    include_particles: bool = True


class SplatraImaginationEvaluateApiRequest(BaseModel):
    particle_budget: int = 900


class SplatraImaginationCommandApiRequest(BaseModel):
    command: str
    particle_budget: int = 1600
    mode: str = "product"
    include_particles: bool = True
    scene_command: str = "spawn_object"
    archetype: str | None = None


class ImagineGenerativeApiRequest(BaseModel):
    concept: str
    count: int = 2200
    controls: dict[str, float] = Field(default_factory=dict)


class SplatraSceneChoreographyApiRequest(BaseModel):
    stage_layout: str = "conversation"
    orb_anchor: str = "center"
    primary_surface: str = "conversation"
    beats: list[dict[str, Any]] = Field(default_factory=list)
    dispatch_sidecar: bool = False
    sidecar_poll_ticks: int = 2


class WebExplorerPageApiInput(BaseModel):
    url: str
    title: str = ""
    visible_text: str = ""
    depth: int = 0


class WebExplorerRunOnceApiRequest(BaseModel):
    goal: str = "research local TTS alternatives and SPLATRA particle rendering"
    allowed_domains: list[str] = Field(default_factory=lambda: ["docs.local", "127.0.0.1", "localhost"])
    pages: list[WebExplorerPageApiInput] = Field(default_factory=list)
    max_pages: int = 30
    max_depth: int = 2
    max_runtime_sec: int = 21600
    max_candidate_drafts: int = 100
    max_skill_drafts: int = 20


class OpenWebFixtureApiInput(BaseModel):
    url: str
    html: str


class OpenWebExplorerRunApiRequest(BaseModel):
    goal: str = "open web research for ATANOR local TTS, SPLATRA, Turbovec, MCP security, Hermes-style agents"
    seed_urls: list[str] = Field(default_factory=lambda: ["https://example.com/fish"])
    fixtures: list[OpenWebFixtureApiInput] = Field(default_factory=lambda: [
        OpenWebFixtureApiInput(
            url="https://example.com/fish",
            html="<html><title>Fish S2 runtime</title><body>Fish Speech local TTS runtime requires isolated Python and model weights outside the repository. <a href='https://example.com/splatra'>SPLATRA particles</a></body></html>",
        ),
        OpenWebFixtureApiInput(
            url="https://example.com/splatra",
            html="<html><title>SPLATRA particles</title><body>SPLATRA WebGPU particle rendering uses compression, quantization, and bounded LOD budgets.</body></html>",
        ),
    ])
    max_pages: int = 300
    max_depth: int = 3
    max_runtime_sec: int = 21600
    max_bytes_per_page: int = 250_000
    per_domain_delay_sec: float = 3.0
    max_pages_per_domain: int = 50
    max_candidate_drafts: int = 200
    max_skill_drafts: int = 50
    live_web: bool = False


class ReviewDecideApiRequest(BaseModel):
    item_id: str
    decision: ReviewStatus
    reviewer: str = "operator"
    reason: str = ""
    approved_for: str = "draft_only"


def _require_bound_review_operator(
    token: str | None = Header(
        default=None,
        alias="X-Atanor-Operator-Delegation",
    ),
) -> str:
    """Resolve reviewer identity from the server-owned operator boundary."""

    authorization = PERMISSION_GATE.verify_bound_operator_action(
        PermissionScope.REVIEW_DRAFT_WRITE,
        signed_token=token,
        action="agentic_review_decide",
    )
    if not authorization.get("allowed"):
        raise HTTPException(
            status_code=403,
            detail={
                "reason": authorization.get("reason")
                or "server_bound_operator_required",
                "required_boundary": "agentic_micro_os_permission_gate",
                "required_scope": PermissionScope.REVIEW_DRAFT_WRITE.value,
            },
        )
    operator_id = authorization.get("bound_operator_id")
    if not isinstance(operator_id, str) or not operator_id:
        raise HTTPException(
            status_code=403,
            detail={
                "reason": "server_bound_operator_identity_missing",
                "required_boundary": "agentic_micro_os_permission_gate",
                "required_scope": PermissionScope.REVIEW_DRAFT_WRITE.value,
            },
        )
    return operator_id


class ReviewImportWebRunApiRequest(BaseModel):
    run_id: str | None = None
    run_payload: dict[str, Any] | None = None


class PermissionTierSetApiRequest(BaseModel):
    tier: str = "DRAFT_PROPOSAL"
    operator_id: str = "operator"


class FullHostEnableApiRequest(BaseModel):
    enabled_by: str = "operator"
    typed_phrase: str = ""
    duration_sec: int = 600
    sub_switches: dict[str, bool] = Field(default_factory=dict)


class FullHostDisableApiRequest(BaseModel):
    operator_id: str = "operator"
    reason: str = "operator disabled"


class PermissionVerifyActionApiRequest(BaseModel):
    scope: str = "read_summary"
    action: str = "status check"
    operator_id: str = "operator"
    signed_token: str | None = None


class EmergencyStopApiRequest(BaseModel):
    operator_id: str = "operator"
    reason: str = "operator emergency stop"


class HostExecutorExecuteApiRequest(BaseModel):
    action_type: str = "echo"
    path: str = ""
    content: str = ""
    max_bytes: int = 4096
    max_entries: int = 50
    safe_test_token: str = ""
    operator_id: str = "operator"


class PolicyLoopRunOnceApiRequest(BaseModel):
    loop_id: str = ""
    max_cycles: int = 1
    max_runtime_sec: int = 30
    base_web_pages: int = 3
    base_review_batch: int = 6
    base_splatra_frames: int = 1
    base_host_actions: int = 1
    allow_host_executor: bool = False
    review_queue_pressure: float = 0.0
    recent_failures: int = 0
    unsafe_request: bool = False
    voice_available: bool = False


class PolicySchedulerStartApiRequest(BaseModel):
    # Retained as a UI-intent hint for compatibility. It is never authority;
    # only a verified, consumed run_lease can start the live scheduler.
    operator_confirmed: bool = False
    scheduler_id: str = "agentic_policy_scheduler_v1"
    max_runtime_sec: int = Field(default=600, ge=1, le=3600)
    max_cycles: int = Field(default=5, ge=1, le=2000)
    max_actions: int = Field(default=32, ge=1, le=30_000)
    max_scratch_write_bytes: int = Field(
        default=16 * 1024 * 1024,
        ge=1,
        le=64 * 1024 * 1024,
    )
    min_interval_sec: float = 5.0
    max_interval_sec: float = 120.0
    allow_web_explorer: bool = True
    allow_review_import: bool = True
    allow_splatra_generation: bool = True
    allow_host_executor_status_only: bool = True
    live_web: bool = False
    execution_mode: str = Field(
        default="manual",
        pattern="^(manual|daemon)$",
    )
    run_lease: dict[str, Any] | None = None


class PolicySchedulerStopApiRequest(BaseModel):
    reason: str = "operator_stop"


class PromotionDraftApiRequest(BaseModel):
    item_ids: list[str] = Field(default_factory=list)
    created_by: str = "operator"


class PromotionConfirmApiRequest(BaseModel):
    operator_confirmed: bool = False
    confirmation_phrase: str = ""
    item_ids: list[str] = Field(default_factory=list)
    operator_id: str = "operator"


class PolicySchedulerDaemonStartApiRequest(PolicySchedulerStartApiRequest):
    # The daemon keeps ticking server-side until stopped/bounded, so allow a
    # longer default horizon than a single manual run.
    max_runtime_sec: int = Field(default=3600, ge=1, le=3600)
    max_cycles: int = Field(default=2000, ge=1, le=2000)
    max_actions: int = Field(default=6000, ge=1, le=30_000)
    max_scratch_write_bytes: int = Field(
        default=64 * 1024 * 1024,
        ge=1,
        le=64 * 1024 * 1024,
    )
    execution_mode: str = Field(
        default="daemon",
        pattern="^daemon$",
    )


class ScopedPatchApiRequest(BaseModel):
    target_path: str
    expected_old_text: str = ""
    replacement_text: str = ""
    reason: str = "operator scoped patch"
    operator_confirmation: str = ""
    tier_session_id: str = ""
    required_subswitches: list[str] = Field(default_factory=lambda: ["full_file_write"])
    dry_run: bool = True
    operator_id: str = "operator"


class ScopedPatchRollbackApiRequest(BaseModel):
    target_path: str
    backup_path: str
    operator_confirmation: str = ""
    tier_session_id: str = ""
    operator_id: str = "operator"


@router.get("/abstain/status")
def abstain_status() -> dict[str, Any]:
    """The abstain->ingest loop's state: how many terms are pending re-learning
    and the last drain's result."""
    from packages.graph_scale import abstain_queue

    return {
        "pending": len(abstain_queue.pending(limit=200)),
        "pending_terms": abstain_queue.pending(limit=20),
        "last_drain": _LAST_ABSTAIN_DRAIN_RESULT,
    }


@router.post("/abstain/drain")
def abstain_drain() -> dict[str, Any]:
    """On-demand: close the abstain->ingest loop now (fetch attributed evidence
    for pending abstained terms and ingest it). Bounded + judge-gated inside."""
    return _run_abstain_drain(force=True)


_IMAGINE_STORE: Any = None


def _imagine_store() -> Any:
    """Cached TripleStore — opening the 25M-fact store costs ~7s, so open ONCE
    and reuse across /imagine calls (fresh-open per request would hang)."""
    global _IMAGINE_STORE
    if _IMAGINE_STORE is None:
        from packages.graph_scale.graph_paths import SHIPPED_GRAPH_ROOT
        from packages.graph_scale.triple_store import TripleStore

        _IMAGINE_STORE = TripleStore(SHIPPED_GRAPH_ROOT)
    return _IMAGINE_STORE


def _concept_graph_features(concept: str) -> dict[str, Any]:
    """The concept's knowledge signature (degree, relation diversity, hierarchy),
    so its imagined form reflects what ATANOR actually KNOWS about it. Defensive:
    an empty/unknown concept just yields a hash-only (still unique) form."""
    try:
        store = _imagine_store()
        facts = store.facts_about(concept, limit=80)
        preds = [p for (_s, p, _o) in facts]
        is_a = any(p in ("is_a", "defined_as", "종류", "일종") for p in preds)
        part_of = sum(1 for p in preds if "part" in p.lower() or p in ("부분", "구성", "구성요소"))
        return {"degree": len(facts), "relation_types": len(set(preds)),
                "is_a": is_a, "part_of": part_of}
    except Exception:
        return {}


@router.post("/imagine")
def imagine(req: ImagineGenerativeApiRequest) -> dict[str, Any]:
    """Generative particle synthesis: ANY concept -> its OWN animated form,
    synthesised (not selected) from the concept's graph signature. Unlimited,
    deterministic, No-LLM/No-image-model. This is the real-time generative
    replacement for the fixed 9-archetype path."""
    from packages.splatra_imagination.generative import synthesize_form, form_descriptor

    concept = (req.concept or "").strip()
    if not concept:
        return {"error": "concept_required", "particles": [], "particle_count": 0}
    gf = _concept_graph_features(concept)
    particles = synthesize_form(concept, count=req.count, controls=req.controls,
                                graph_features=gf or None)
    return {
        "concept": concept,
        "source": "generative",
        "descriptor": form_descriptor(concept, gf or None),
        "particle_count": len(particles),
        "particles": [p.to_dict() for p in particles],
        "safety_flags": {"external_llm": False, "external_sllm": False,
                         "image_model_used": False, "proof_only": True},
    }


@router.get("/status")
def status() -> dict[str, Any]:
    browser = BrowserReadConnector()
    mcp = MCPAllowlistGateway()
    splatra = SplatraCosmosEvaluator()
    return {
        **SAFETY_FLAGS,
        "modules": MODULE_STATUS,
        "tool_gateway_phase1": {
            "browser_read": browser.status(),
            "mcp_allowlist": mcp.status(),
            "splatra_evaluator": splatra.status(),
            "web_explorer_loop": {
                "available": True,
                "proof_only": True,
                "real_long_daemon": False,
                "private_credentialed_browsing": False,
                "aggressive_crawling": False,
                "open_web_v1": True,
                "fixed_allowlist_required": False,
            },
        },
        "blocked_actions": [
            "unrestricted_shell",
            "arbitrary_js_eval",
            "local_brain_direct_write",
            "production_store_direct_write",
            "candidate_promotion",
            "auto_commit",
            "auto_push",
        ],
        "permission_gate": PERMISSION_GATE.status(),
    }


@router.get("/permission/tier")
def permission_tier() -> dict[str, Any]:
    return {**SAFETY_FLAGS, **PERMISSION_GATE.status()}


@router.post("/permission/tier/set")
def permission_tier_set(request: PermissionTierSetApiRequest) -> dict[str, Any]:
    try:
        result = PERMISSION_GATE.set_tier(AutonomyTier(request.tier), operator_id=request.operator_id)
    except ValueError as exc:
        return {**SAFETY_FLAGS, "allowed": False, "reason": str(exc), **PERMISSION_GATE.status()}
    emit_runtime_event(
        source="permission_gate",
        event_type="permission_tier_changed",
        payload_summary=f"tier={request.tier}",
        intensity=0.7,
    )
    return {**SAFETY_FLAGS, **result}


@router.post("/permission/full-host/enable")
def permission_full_host_enable(request: FullHostEnableApiRequest) -> dict[str, Any]:
    # A public phrase, boolean, bearer token, or environment flag is not an
    # operator identity. Preserve the lower-level mechanism for isolated tests,
    # but remove its live API authority until a purpose-specific signed run
    # lease is verified by the common AUT-0 boundary.
    result = {
        "allowed": False,
        "reason": "signed_operator_run_lease_required",
        "required_boundary": "common_operator_run_lease_gate",
        **PERMISSION_GATE.status(),
    }
    emit_runtime_event(
        source="permission_gate",
        event_type="host_action_denied",
        payload_summary=f"tier4 enable allowed={result.get('allowed')}",
        intensity=1.0,
    )
    return {**SAFETY_FLAGS, **result}


@router.post("/permission/full-host/disable")
def permission_full_host_disable(request: FullHostDisableApiRequest) -> dict[str, Any]:
    result = PERMISSION_GATE.disable_full_host(operator_id=request.operator_id, reason=request.reason)
    emit_runtime_event(
        source="permission_gate",
        event_type="tier4_disabled",
        payload_summary="tier4 disabled",
        intensity=0.7,
    )
    return {**SAFETY_FLAGS, **result}


@router.get("/permission/full-host/status")
def permission_full_host_status() -> dict[str, Any]:
    return {**SAFETY_FLAGS, **PERMISSION_GATE.status()}


@router.post("/permission/full-host/emergency-stop")
def permission_full_host_emergency_stop(request: EmergencyStopApiRequest) -> dict[str, Any]:
    result = PERMISSION_GATE.trigger_emergency_stop(operator_id=request.operator_id, reason=request.reason)
    emit_runtime_event(
        source="permission_gate",
        event_type="unsafe_request",
        payload_summary="emergency stop",
        intensity=1.35,
    )
    return {**SAFETY_FLAGS, **result}


@router.post("/permission/verify-action")
def permission_verify_action(request: PermissionVerifyActionApiRequest) -> dict[str, Any]:
    try:
        result = PERMISSION_GATE.verify_action(
            PermissionScope(request.scope),
            action=request.action,
            operator_id=request.operator_id,
            signed_token=request.signed_token,
        )
    except ValueError as exc:
        return {**SAFETY_FLAGS, "allowed": False, "reason": str(exc), **PERMISSION_GATE.status()}
    return {**SAFETY_FLAGS, **result}


@router.get("/host-executor/status")
def host_executor_status() -> dict[str, Any]:
    return {**SAFETY_FLAGS, **HOST_EXECUTOR.status()}


def _make_policy_loop(config: PolicyLoopConfig | None = None) -> PolicyDrivenAutonomousLoop:
    return PolicyDrivenAutonomousLoop(
        config=config or PolicyLoopConfig(),
        event_bus=EVENT_BUS,
        review_queue=REVIEW_QUEUE,
        permission_gate=PERMISSION_GATE,
    )


@router.get("/policy-loop/status")
def policy_loop_status() -> dict[str, Any]:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        loop = _make_policy_loop()
        return {
            **SAFETY_FLAGS,
            **loop.status(),
            "runs": len(POLICY_LOOP_RUNS),
        }


@router.post("/policy-loop/run-once")
def policy_loop_run_once(request: PolicyLoopRunOnceApiRequest) -> dict[str, Any]:
    config = PolicyLoopConfig(
        loop_id=request.loop_id,
        max_cycles=request.max_cycles,
        max_runtime_sec=request.max_runtime_sec,
        base_web_pages=request.base_web_pages,
        base_review_batch=request.base_review_batch,
        base_splatra_frames=request.base_splatra_frames,
        base_host_actions=request.base_host_actions,
        allow_host_executor=request.allow_host_executor,
        review_queue_pressure=request.review_queue_pressure,
        recent_failures=request.recent_failures,
        unsafe_request=request.unsafe_request,
        voice_available=request.voice_available,
    )
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        queue_digest_before = _review_queue_digest()
        result = _make_policy_loop(config).run_once().to_dict()
        review_queue_mutated = (
            _review_queue_digest() != queue_digest_before
        )
    POLICY_LOOP_RUNS[result["loop_id"]] = result
    if result.get("stopped_reason") in {"review_requested", "emergency_stop", "rest_requested", "fatigue", "repeated_failure"}:
        emit_runtime_event(
            source="review_queue" if result.get("stopped_reason") == "review_requested" else "user_action",
            event_type="review_queue_pressure" if result.get("stopped_reason") == "review_requested" else "resting",
            payload_summary=f"policy loop stopped={result.get('stopped_reason')}",
            intensity=0.5,
        )
    return {
        **SAFETY_FLAGS,
        **result,
        "mutation_performed": review_queue_mutated,
        "review_queue_mutated": review_queue_mutated,
        "review_queue_persisted": False,
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "auto_commit": False,
        "auto_push": False,
    }


@router.get("/policy-loop/runs/{loop_id}")
def policy_loop_run(loop_id: str) -> dict[str, Any]:
    return {**SAFETY_FLAGS, "run": POLICY_LOOP_RUNS.get(loop_id)}


def _agentic_runner_artifact_paths() -> tuple[Path, ...]:
    paths = {path.resolve(strict=True) for path in _AGENTIC_RUNNER_ARTIFACTS}
    for root in _AGENTIC_RUNNER_ARTIFACT_ROOTS:
        resolved_root = root.resolve(strict=True)
        for path in resolved_root.rglob("*.py"):
            relative_parts = path.relative_to(resolved_root).parts
            if (
                "__pycache__" in relative_parts
                or "tests" in relative_parts
                or path.name.startswith("test_")
            ):
                continue
            paths.add(path.resolve(strict=True))
    return tuple(sorted(paths, key=lambda item: str(item)))


def _agentic_runner_artifact_sha256() -> str:
    digest = hashlib.sha256()
    for resolved in _agentic_runner_artifact_paths():
        digest.update(str(resolved.relative_to(PROJECT_ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(resolved.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _agentic_scheduler_config(
    request: PolicySchedulerStartApiRequest,
) -> SchedulerConfig:
    if AGENTIC_RUN_LEASE_STORE is None or AGENTIC_RUN_LEASE_SCRATCH_ROOT is None:
        raise RuntimeError("run_lease_store_unconfigured")
    return SchedulerConfig(
        scheduler_id=request.scheduler_id,
        enabled=False,
        max_runtime_sec=request.max_runtime_sec,
        max_cycles=request.max_cycles,
        min_interval_sec=request.min_interval_sec,
        max_interval_sec=request.max_interval_sec,
        stop_file=str(
            AGENTIC_RUN_LEASE_SCRATCH_ROOT / "policy_scheduler.stop"
        ),
        emergency_stop_file=str(
            AGENTIC_RUN_LEASE_STORE.boundary.emergency_stop_path
        ),
        allow_web_explorer=request.allow_web_explorer,
        allow_review_import=request.allow_review_import,
        allow_splatra_generation=request.allow_splatra_generation,
        allow_host_executor_status_only=(
            request.allow_host_executor_status_only
        ),
        # AUT-0's signed action vocabulary has no external-request class.
        live_web=False,
    )


def _agentic_scratch_boundary(config: SchedulerConfig) -> dict[str, Any]:
    assert AGENTIC_RUN_LEASE_SCRATCH_ROOT is not None
    root = AGENTIC_RUN_LEASE_SCRATCH_ROOT
    targets = {
        "review_queue": str(_resolved_runtime_path(REVIEW_QUEUE_PATH)),
        "candidate_staging": str(
            _resolved_runtime_path(CANDIDATE_PROMOTION_GATE.staging_dir)
        ),
        "scheduler_stop": str(_resolved_runtime_path(config.stop_file)),
    }
    for target in targets.values():
        if not _path_is_within(Path(target), root):
            raise RuntimeError("agentic_scratch_target_outside_boundary")
    identity = {
        "schema_version": "atanor.agentic-scratch-boundary.v1",
        "resolved_root": str(root),
        "targets": targets,
    }
    root_digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
    return {
        "boundary_id": f"agentic-scratch:{root_digest[:24]}",
        "resolved_root_sha256": root_digest,
        "identity_manifest_sha256": _canonical_sha256(identity),
    }


def _agentic_capability_manifest(
    config: SchedulerConfig,
    scratch_boundary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
        "action_classes": list(_AGENTIC_ACTION_CLASSES),
        "filesystem_policy_sha256": _canonical_sha256(
            {
                "scratch": scratch_boundary,
                "writes": ["candidate_intent", "review_queue", "stop"],
                "production": False,
            }
        ),
        "network_policy_sha256": _canonical_sha256(
            {
                "external_requests": 0,
                "live_web": config.live_web,
                "fixture_web": bool(config.allow_web_explorer),
                "network_helpers": False,
            }
        ),
        "child_task_policy_sha256": _canonical_sha256(
            {"child_tasks": 0, "concurrent_child_tasks": 0}
        ),
    }


def _agentic_input_manifest_sha256() -> str:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        manifest = {
            "schema_version": "atanor.agentic-input-manifest.v1",
            "review_queue": REVIEW_QUEUE.to_state(),
            "auto_staged_intent_ids": sorted(
                AUTO_STAGED_INTENT_IDS
            ),
            "candidate_staging_manifests": (
                CANDIDATE_PROMOTION_GATE.list_manifests(limit=50)
            ),
            "emotion_snapshot": EVENT_BUS.engine.snapshot().to_dict(),
            "permission_tier": PERMISSION_GATE.status().get("tier"),
        }
    return _canonical_sha256(manifest)


def _build_agentic_run_lease_context(
    request: PolicySchedulerStartApiRequest,
) -> tuple[dict[str, Any], SchedulerConfig]:
    store = AGENTIC_RUN_LEASE_STORE
    if (
        store is None
        or AGENTIC_RUN_LEASE_SCRATCH_ROOT is None
        or not AGENTIC_RUN_LEASE_RUNTIME_INSTANCE_ID
    ):
        raise RuntimeError("run_lease_store_unconfigured")
    if request.live_web:
        raise ValueError("run_lease_network_capability_denied")
    if request.max_actions < request.max_cycles:
        raise ValueError("run_lease_max_actions_below_cycles")
    config = _agentic_scheduler_config(request)
    scratch_boundary = _agentic_scratch_boundary(config)
    capability_manifest = _agentic_capability_manifest(
        config,
        scratch_boundary,
    )
    limits = {
        "max_runtime_sec": int(request.max_runtime_sec),
        "max_cycles": int(request.max_cycles),
        "max_actions": int(request.max_actions),
        "max_external_requests": 0,
        "max_external_response_bytes": 0,
        "max_scratch_write_bytes": int(
            request.max_scratch_write_bytes
        ),
        "max_child_tasks": 0,
        "max_concurrent_child_tasks": 0,
    }
    config_binding = {
        "schema_version": "atanor.agentic-policy-config.v1",
        "execution_mode": request.execution_mode,
        "scheduler": config.to_dict(),
        "network_helpers": {
            "wikipedia_grounded": False,
            "abstain_drain": False,
        },
        "candidate_intent_only": True,
        "production_merge": False,
    }
    return (
        {
            "runner_id": AGENTIC_POLICY_DAEMON_RUNNER_ID,
            "deployment_id": store.boundary.deployment_id,
            "runtime_instance_id": (
                AGENTIC_RUN_LEASE_RUNTIME_INSTANCE_ID
            ),
            "runner_artifact_sha256": (
                _agentic_runner_artifact_sha256()
            ),
            "config_sha256": _canonical_sha256(config_binding),
            "input_manifest_sha256": (
                _agentic_input_manifest_sha256()
            ),
            "capability_manifest": capability_manifest,
            "limits": limits,
            "scratch_boundary": scratch_boundary,
            "operator_boundary_id": (
                store.boundary.operator_boundary_id
            ),
            "operator_boundary_config_sha256": (
                store.boundary.operator_boundary_config_sha256
            ),
            "nonce_replay_domain": store.boundary.replay_domain,
        },
        config,
    )


def _agentic_run_lease_status() -> dict[str, Any]:
    store = AGENTIC_RUN_LEASE_STORE
    store_status = store.status() if store is not None else None
    active = AGENTIC_ACTIVE_RUN_LEASE
    return {
        "configured": store is not None,
        "runner_id": AGENTIC_POLICY_DAEMON_RUNNER_ID,
        "runtime_instance_id": (
            AGENTIC_RUN_LEASE_RUNTIME_INSTANCE_ID or None
        ),
        "active": active is not None,
        "active_lease_id": (
            active.get("lease_id") if active is not None else None
        ),
        "active_mode": (
            active.get("mode") if active is not None else None
        ),
        "active_payload_sha256": (
            active.get("payload_sha256") if active is not None else None
        ),
        "last_run": dict(AGENTIC_LAST_RUN_LEASE),
        "store": store_status,
        "signer_present_in_api": False,
        "authority_mechanism": "externally_signed_bounded_run_lease",
        "network_authority": False,
        "production_write_authority": False,
    }


def _activate_agentic_run_lease(
    request: PolicySchedulerStartApiRequest,
    *,
    mode: str,
) -> tuple[dict[str, Any], SchedulerConfig | None]:
    if request.execution_mode != mode:
        return {
            "allowed": False,
            "reason": "run_lease_execution_mode_mismatch",
            "expected_mode": mode,
            "requested_mode": request.execution_mode,
        }, None
    if request.run_lease is None:
        return {
            "allowed": False,
            "reason": "signed_operator_run_lease_required",
        }, None
    try:
        context, config = _build_agentic_run_lease_context(request)
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "allowed": False,
            "reason": str(exc) or type(exc).__name__,
        }, None
    store = AGENTIC_RUN_LEASE_STORE
    assert store is not None
    global AGENTIC_ACTIVE_RUN_LEASE
    with _AGENTIC_RUN_LEASE_LOCK:
        if AGENTIC_ACTIVE_RUN_LEASE is not None:
            return {
                "allowed": False,
                "reason": "agentic_run_already_active",
                "lease_id": AGENTIC_ACTIVE_RUN_LEASE.get("lease_id"),
            }, None
        activation = store.activate(
            document=request.run_lease,
            live_context=context,
        )
        payload = activation.to_dict()
        if not activation.allowed:
            return payload, None
        AGENTIC_ACTIVE_RUN_LEASE = {
            "lease_id": activation.lease_id,
            "runner_id": activation.runner_id,
            "payload_sha256": activation.payload_sha256,
            "runner_artifact_sha256": context[
                "runner_artifact_sha256"
            ],
            "mode": mode,
            "activated_at": _utc_now_iso(),
        }
    return payload, config


def _authorize_agentic_action(
    action_class: str,
    *,
    scratch_write_bytes: int = 0,
    expected_lease_id: str | None = None,
    expected_mode: str | None = None,
) -> dict[str, Any]:
    with _AGENTIC_RUN_LEASE_LOCK:
        store = AGENTIC_RUN_LEASE_STORE
        active = AGENTIC_ACTIVE_RUN_LEASE
        if store is None or active is None:
            return {
                "allowed": False,
                "reason": "run_lease_not_active",
                "action_class": action_class,
            }
        if (
            expected_lease_id is not None
            and active.get("lease_id") != expected_lease_id
        ):
            return {
                "allowed": False,
                "reason": "run_lease_identity_mismatch",
                "action_class": action_class,
            }
        if (
            expected_mode is not None
            and active.get("mode") != expected_mode
        ):
            return {
                "allowed": False,
                "reason": "run_lease_execution_mode_mismatch",
                "action_class": action_class,
            }
        if (
            _agentic_runner_artifact_sha256()
            != active["runner_artifact_sha256"]
        ):
            return {
                "allowed": False,
                "reason": "run_lease_runner_artifact_changed",
                "action_class": action_class,
            }
        authorization = store.authorize(
            lease_id=active["lease_id"],
            runner_id=AGENTIC_POLICY_DAEMON_RUNNER_ID,
            action_class=action_class,
            costs={
                "cycles": 1 if action_class == "agentic.tick" else 0,
                "actions": 1,
                "external_requests": 0,
                "external_response_bytes": 0,
                "scratch_write_bytes": int(scratch_write_bytes),
                "child_tasks": 0,
                "concurrent_child_tasks": 0,
            },
        )
        return authorization.to_dict()


def _safe_finish_reason(reason: str) -> str:
    value = "".join(
        character
        if (
            character.isascii()
            and (character.isalnum() or character in "._:/@+-")
        )
        else "_"
        for character in str(reason)
    ).strip("_")
    return (value or "run_stopped")[:256]


def _finish_agentic_run_lease(
    reason: str,
    *,
    expected_lease_id: str | None = None,
    expected_mode: str | None = None,
) -> dict[str, Any]:
    global AGENTIC_ACTIVE_RUN_LEASE
    global AGENTIC_LAST_RUN_LEASE
    with _AGENTIC_RUN_LEASE_LOCK:
        store = AGENTIC_RUN_LEASE_STORE
        active = AGENTIC_ACTIVE_RUN_LEASE
        if store is None or active is None:
            return {
                "finished": False,
                "reason": "run_lease_not_active",
            }
        if (
            expected_lease_id is not None
            and active.get("lease_id") != expected_lease_id
        ):
            return {
                "finished": False,
                "reason": "run_lease_identity_mismatch",
                "lease_id": active.get("lease_id"),
            }
        if (
            expected_mode is not None
            and active.get("mode") != expected_mode
        ):
            return {
                "finished": False,
                "reason": "run_lease_execution_mode_mismatch",
                "lease_id": active.get("lease_id"),
            }
        finish_reason = _safe_finish_reason(reason)
        finished = store.finish(
            lease_id=active["lease_id"],
            runner_id=AGENTIC_POLICY_DAEMON_RUNNER_ID,
            reason=finish_reason,
        )
        AGENTIC_LAST_RUN_LEASE = {
            "lease_id": active["lease_id"],
            "mode": active["mode"],
            "payload_sha256": active["payload_sha256"],
            "activated_at": active["activated_at"],
            "finished_at": _utc_now_iso(),
            "finish_reason": finish_reason,
            "store_finish_reason": finished.reason,
            "store_finished": finished.finished,
        }
        if finished.finished:
            AGENTIC_ACTIVE_RUN_LEASE = None
        return finished.to_dict()


def _halt_agentic_run(
    reason: str,
    *,
    expected_lease_id: str | None = None,
    expected_mode: str | None = None,
) -> dict[str, Any]:
    # Validate the target before stopping shared scheduler state.  Otherwise a
    # stale daemon/manual caller could halt a newer run even though lease
    # finishing correctly rejects the stale identity.
    with _AGENTIC_RUN_LEASE_LOCK:
        active = AGENTIC_ACTIVE_RUN_LEASE
        if active is None:
            return {
                "finished": False,
                "reason": "run_lease_not_active",
            }
        if (
            expected_lease_id is not None
            and active.get("lease_id") != expected_lease_id
        ):
            return {
                "finished": False,
                "reason": "run_lease_identity_mismatch",
                "lease_id": active.get("lease_id"),
            }
        if (
            expected_mode is not None
            and active.get("mode") != expected_mode
        ):
            return {
                "finished": False,
                "reason": "run_lease_execution_mode_mismatch",
                "lease_id": active.get("lease_id"),
            }
        POLICY_SCHEDULER.stop(
            reason=_safe_finish_reason(reason),
            create_stop_file=False,
        )
        return _finish_agentic_run_lease(
            reason,
            expected_lease_id=expected_lease_id,
            expected_mode=expected_mode,
        )


def _cleanup_failed_agentic_start(
    *,
    lease_id: str,
    mode: str,
    reason: str,
) -> dict[str, Any]:
    """Reset partial scheduler state and finish only the failed start's lease."""

    safe_reason = _safe_finish_reason(reason)
    with _AGENTIC_RUN_LEASE_LOCK:
        active = AGENTIC_ACTIVE_RUN_LEASE
        if active is None:
            return {
                "scheduler_reset": False,
                "scheduler_stop_error": None,
                "lease_finish": {
                    "finished": False,
                    "reason": "run_lease_not_active",
                },
            }
        if active.get("lease_id") != lease_id:
            return {
                "scheduler_reset": False,
                "scheduler_stop_error": None,
                "lease_finish": {
                    "finished": False,
                    "reason": "run_lease_identity_mismatch",
                    "lease_id": active.get("lease_id"),
                },
            }
        if active.get("mode") != mode:
            return {
                "scheduler_reset": False,
                "scheduler_stop_error": None,
                "lease_finish": {
                    "finished": False,
                    "reason": "run_lease_execution_mode_mismatch",
                    "lease_id": active.get("lease_id"),
                },
            }
        scheduler_stop_error = ""
        try:
            POLICY_SCHEDULER.stop(
                reason=safe_reason,
                create_stop_file=False,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            scheduler_stop_error = type(exc).__name__
            POLICY_SCHEDULER.enabled = False
            POLICY_SCHEDULER.started_monotonic = None
            POLICY_SCHEDULER.stopped_at = _utc_now_iso()
            POLICY_SCHEDULER.stopped_reason = safe_reason
        finish = _finish_agentic_run_lease(
            reason,
            expected_lease_id=lease_id,
            expected_mode=mode,
        )
        return {
            "scheduler_reset": not POLICY_SCHEDULER.enabled,
            "scheduler_stop_error": scheduler_stop_error or None,
            "lease_finish": finish,
        }


def _review_queue_digest() -> str:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        return hashlib.sha256(_review_queue_snapshot_bytes()).hexdigest()


def _review_queue_write_bytes() -> int:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        return len(_review_queue_snapshot_bytes())


_CANDIDATE_INTENT_REVIEW_NOTE = (
    "autonomous candidate intent staged; not promoted"
)


def _candidate_review_queue_bytes(
    plan: CandidateIntentPlan,
) -> bytes:
    state = REVIEW_QUEUE.to_state()
    staged_ids = set(plan.newly_staged_ids)
    for raw in state.get("items", []):
        if (
            isinstance(raw, dict)
            and str(raw.get("item_id") or "") in staged_ids
        ):
            notes = raw.setdefault("review_notes", [])
            if _CANDIDATE_INTENT_REVIEW_NOTE not in notes:
                notes.append(_CANDIDATE_INTENT_REVIEW_NOTE)
    return _serialize_review_queue_state(state)


def _plan_candidate_intent_write() -> tuple[
    CandidateIntentPlan | None,
    bytes,
]:
    items = [item.to_dict() for item in REVIEW_QUEUE.list_items()]
    plan = CANDIDATE_PROMOTION_GATE.plan_candidate_intents(
        items,
        already_staged=set(AUTO_STAGED_INTENT_IDS),
    )
    if plan is None:
        return None, b""
    return plan, _candidate_review_queue_bytes(plan)


def _candidate_intent_write_reservation() -> int:
    """Diagnostic exact byte count; live application uses the same held plan."""

    with _AGENTIC_REVIEW_QUEUE_LOCK:
        plan, review_payload = _plan_candidate_intent_write()
        if plan is None:
            return 0
        return len(plan.manifest_bytes) + len(review_payload)


def _stage_candidate_intents_exact(
    *,
    expected_lease_id: str | None = None,
    expected_mode: str | None = None,
    require_lease: bool = False,
) -> dict[str, Any]:
    """Plan, authorize, and apply one byte-exact candidate write atomically."""

    with _AGENTIC_REVIEW_QUEUE_LOCK:
        plan, review_payload = _plan_candidate_intent_write()
        if plan is None:
            return {
                "allowed": False,
                "reason": "no_new_eligible",
                "auto_promoted": 0,
                "candidate_promotion": False,
                "candidate_intents_staged": 0,
                "candidate_staging_mutated": False,
                "review_queue_staging_mutated": False,
                "review_queue_persisted": False,
                "mutation_performed": False,
                "production_merge_attempted": False,
                "production_store_mutated": False,
                "reserved_scratch_write_bytes": 0,
            }
        exact_write_bytes = len(plan.manifest_bytes) + len(
            review_payload
        )
        authorization: dict[str, Any] = {
            "allowed": True,
            "reason": "local_compatibility_call",
            "action_class": "agentic.candidate_write",
        }
        if require_lease:
            authorization = _authorize_agentic_action(
                "agentic.candidate_write",
                scratch_write_bytes=exact_write_bytes,
                expected_lease_id=expected_lease_id,
                expected_mode=expected_mode,
            )
            if not authorization.get("allowed"):
                return {
                    **authorization,
                    "auto_promoted": 0,
                    "candidate_promotion": False,
                    "candidate_intents_staged": 0,
                    "candidate_staging_mutated": False,
                    "review_queue_staging_mutated": False,
                    "review_queue_persisted": False,
                    "mutation_performed": False,
                    "production_merge_attempted": False,
                    "production_store_mutated": False,
                    "reserved_scratch_write_bytes": exact_write_bytes,
                }

        result = CANDIDATE_PROMOTION_GATE.apply_candidate_intent_plan(
            plan
        )
        for item_id in plan.newly_staged_ids:
            AUTO_STAGED_INTENT_IDS.add(item_id)
            item = REVIEW_QUEUE.get(item_id)
            if (
                item is not None
                and _CANDIDATE_INTENT_REVIEW_NOTE
                not in item.review_notes
            ):
                item.review_notes.append(
                    _CANDIDATE_INTENT_REVIEW_NOTE
                )
        actual_review_payload = _review_queue_snapshot_bytes()
        if actual_review_payload != review_payload:
            return {
                **result,
                "allowed": False,
                "reason": "candidate_review_snapshot_mismatch",
                "review_queue_staging_mutated": True,
                "review_queue_persisted": False,
                "mutation_performed": True,
                "reserved_scratch_write_bytes": exact_write_bytes,
                "candidate_write_authorization": authorization,
            }
        review_persistence = _persist_review_queue_bytes(
            review_payload
        )
        persisted = bool(review_persistence.get("persisted"))
        return {
            **result,
            "allowed": bool(
                result.get("allowed") and persisted
            ),
            "auto_promoted": 0,
            "candidate_promotion": False,
            "review_queue_staging_mutated": True,
            "review_queue_persisted": persisted,
            "review_queue_persistence": review_persistence,
            "mutation_performed": bool(
                result.get("mutation_performed")
                or review_persistence.get("mutation_performed")
            ),
            "production_merge_attempted": False,
            "production_store_mutated": False,
            "reserved_scratch_write_bytes": exact_write_bytes,
            "candidate_write_authorization": authorization,
            "reason": (
                result.get("reason") or "candidate_intent_staged"
                if persisted
                else "review_queue_persistence_failed_after_candidate_write"
            ),
        }


def _persist_review_queue_under_lease(
    *,
    previous_digest: str,
    expected_lease_id: str,
    expected_mode: str,
) -> dict[str, Any]:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        payload = _review_queue_snapshot_bytes()
        if hashlib.sha256(payload).hexdigest() == previous_digest:
            return {
                "allowed": True,
                "reason": "review_queue_unchanged",
                "persisted": False,
                "reserved_scratch_write_bytes": 0,
            }
        write_bytes = len(payload)
        authorization = _authorize_agentic_action(
            "agentic.scratch_write",
            scratch_write_bytes=write_bytes,
            expected_lease_id=expected_lease_id,
            expected_mode=expected_mode,
        )
        if not authorization.get("allowed"):
            return {**authorization, "persisted": False}
        persistence = _persist_review_queue_bytes(payload)
        persisted = bool(persistence.get("persisted"))
        return {
            **authorization,
            **persistence,
            "persisted": persisted,
            "reserved_scratch_write_bytes": write_bytes,
            "reason": (
                authorization.get("reason")
                if persisted
                else "review_queue_persistence_failed"
            ),
        }


def _set_policy_scheduler(config: SchedulerConfig) -> None:
    global POLICY_SCHEDULER
    POLICY_SCHEDULER = PolicyDrivenAutonomousScheduler(
        config,
        event_bus=EVENT_BUS,
        review_queue=REVIEW_QUEUE,
        permission_gate=PERMISSION_GATE,
    )


@router.get("/policy-scheduler/status")
def policy_scheduler_status() -> dict[str, Any]:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        return {
            **SAFETY_FLAGS,
            **POLICY_SCHEDULER.state().to_dict(),
            "runs": len(POLICY_SCHEDULER_RUNS),
            "run_lease": _agentic_run_lease_status(),
        }


@router.post("/policy-scheduler/lease-context")
def policy_scheduler_lease_context(
    request: PolicySchedulerStartApiRequest,
) -> dict[str, Any]:
    """Return the exact unsigned context an external operator may sign."""

    try:
        context, _ = _build_agentic_run_lease_context(request)
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            **SAFETY_FLAGS,
            "available": False,
            "reason": str(exc) or type(exc).__name__,
            "signer_present_in_api": False,
        }
    return {
        **SAFETY_FLAGS,
        "available": True,
        "reason": "unsigned_live_context_reconstructed",
        "purpose": "atanor.autonomy-run-lease.v1",
        "live_context": context,
        "live_context_sha256": _canonical_sha256(context),
        "signer_present_in_api": False,
        "private_key_required_outside_api": True,
    }


@router.post("/policy-scheduler/start")
def policy_scheduler_start(request: PolicySchedulerStartApiRequest) -> dict[str, Any]:
    with _AGENTIC_RUN_EXECUTION_LOCK, _AGENTIC_REVIEW_QUEUE_LOCK:
        if AUTONOMOUS_DAEMON.is_running():
            return {
                **SAFETY_FLAGS,
                "allowed": False,
                "reason": "autonomous_daemon_already_running",
            }
        activation, config = _activate_agentic_run_lease(
            request,
            mode="manual",
        )
        if not activation.get("allowed") or config is None:
            return {**SAFETY_FLAGS, **activation}
        lease_id = str(activation.get("lease_id") or "")
        try:
            _set_policy_scheduler(config)
            stop_path = _resolved_runtime_path(config.stop_file)
            if stop_path.exists():
                stop_clear = _authorize_agentic_action(
                    "agentic.scratch_write",
                    scratch_write_bytes=1,
                    expected_lease_id=lease_id,
                    expected_mode="manual",
                )
                if not stop_clear.get("allowed"):
                    _halt_agentic_run(
                        str(stop_clear.get("reason")),
                        expected_lease_id=lease_id,
                        expected_mode="manual",
                    )
                    return {**SAFETY_FLAGS, **stop_clear}
            payload = POLICY_SCHEDULER.start(
                operator_confirmed=True
            )
        except Exception as exc:
            reason = (
                f"policy_scheduler_start_error:{type(exc).__name__}"
            )
            cleanup = _cleanup_failed_agentic_start(
                lease_id=lease_id,
                mode="manual",
                reason=reason,
            )
            return {
                **SAFETY_FLAGS,
                "allowed": False,
                "reason": reason,
                "run_lease_activation": activation,
                "start_cleanup": cleanup,
                "run_lease": _agentic_run_lease_status(),
            }
        if not payload.get("allowed"):
            _finish_agentic_run_lease(
                str(payload.get("reason") or "scheduler_start_failed"),
                expected_lease_id=lease_id,
                expected_mode="manual",
            )
        return {
            **SAFETY_FLAGS,
            **payload,
            "run_lease_activation": activation,
            "run_lease": _agentic_run_lease_status(),
        }


@router.post("/policy-scheduler/stop")
def policy_scheduler_stop(request: PolicySchedulerStopApiRequest) -> dict[str, Any]:
    with _AGENTIC_RUN_LEASE_LOCK:
        active = (
            dict(AGENTIC_ACTIVE_RUN_LEASE)
            if AGENTIC_ACTIVE_RUN_LEASE is not None
            else None
        )
    if (
        AUTONOMOUS_DAEMON.is_running()
        or (active is not None and active.get("mode") == "daemon")
    ):
        payload = AUTONOMOUS_DAEMON.stop(reason=request.reason)
    else:
        with _AGENTIC_RUN_EXECUTION_LOCK:
            payload = POLICY_SCHEDULER.stop(
                reason=request.reason,
                create_stop_file=False,
            )
            if active is not None:
                _finish_agentic_run_lease(
                    request.reason,
                    expected_lease_id=str(active["lease_id"]),
                    expected_mode="manual",
                )
    return {
        **SAFETY_FLAGS,
        **payload,
        "run_lease": _agentic_run_lease_status(),
    }


@router.post("/policy-scheduler/tick")
def policy_scheduler_tick() -> dict[str, Any]:
    with _AGENTIC_RUN_EXECUTION_LOCK:
        with _AGENTIC_RUN_LEASE_LOCK:
            active = (
                dict(AGENTIC_ACTIVE_RUN_LEASE)
                if AGENTIC_ACTIVE_RUN_LEASE is not None
                else None
            )
        if active is None:
            return {
                **SAFETY_FLAGS,
                "ran": False,
                "allowed": False,
                "reason": "signed_operator_run_lease_required",
                "run_lease": _agentic_run_lease_status(),
            }
        if (
            active.get("mode") != "manual"
            or AUTONOMOUS_DAEMON.is_running()
        ):
            return {
                **SAFETY_FLAGS,
                "ran": False,
                "allowed": False,
                "reason": "manual_tick_denied_while_daemon_active",
                "run_lease": _agentic_run_lease_status(),
            }
        lease_id = str(active["lease_id"])
        authorization = _authorize_agentic_action(
            "agentic.tick",
            expected_lease_id=lease_id,
            expected_mode="manual",
        )
        if not authorization.get("allowed"):
            _halt_agentic_run(
                str(authorization.get("reason")),
                expected_lease_id=lease_id,
                expected_mode="manual",
            )
            return {
                **SAFETY_FLAGS,
                "ran": False,
                **authorization,
                "run_lease": _agentic_run_lease_status(),
            }
        with _AGENTIC_REVIEW_QUEUE_LOCK:
            queue_digest_before = _review_queue_digest()
            try:
                payload = POLICY_SCHEDULER.tick()
            except Exception as exc:  # pragma: no cover - defensive
                terminal_reason = f"tick_error:{type(exc).__name__}"
                _halt_agentic_run(
                    terminal_reason,
                    expected_lease_id=lease_id,
                    expected_mode="manual",
                )
                return {
                    **SAFETY_FLAGS,
                    **POLICY_SCHEDULER.state().to_dict(),
                    "ran": False,
                    "allowed": False,
                    "reason": terminal_reason,
                    "run_lease_authorization": authorization,
                    "run_lease": _agentic_run_lease_status(),
                }
            last_result = payload.get("last_result")
            if isinstance(last_result, dict):
                POLICY_SCHEDULER_RUNS[
                    str(payload["scheduler_id"])
                ] = payload
            persistence = _persist_review_queue_under_lease(
                previous_digest=queue_digest_before,
                expected_lease_id=lease_id,
                expected_mode="manual",
            )

        terminal_reason = ""
        if not persistence.get("allowed") or (
            persistence.get("persisted") is False
            and persistence.get("reason")
            == "review_queue_persistence_failed"
        ):
            terminal_reason = str(
                persistence.get("reason")
                or "review_queue_persistence_denied"
            )
            _halt_agentic_run(
                terminal_reason,
                expected_lease_id=lease_id,
                expected_mode="manual",
            )
        elif not payload.get("enabled") or not payload.get("ran"):
            terminal_reason = str(
                payload.get("reason") or "scheduler_stopped"
            )
            _finish_agentic_run_lease(
                terminal_reason,
                expected_lease_id=lease_id,
                expected_mode="manual",
            )

        if terminal_reason:
            payload = {
                **payload,
                **POLICY_SCHEDULER.state().to_dict(),
                "ran": bool(payload.get("ran")),
                "reason": terminal_reason,
            }
        return {
            **SAFETY_FLAGS,
            **payload,
            "run_lease_authorization": authorization,
            "review_queue_persistence": persistence,
            "run_lease": _agentic_run_lease_status(),
            "mutation_performed": bool(
                persistence.get("mutation_performed")
            ),
            "production_store_mutated": False,
            "local_brain_write": False,
            "candidate_promotion": False,
            "auto_commit": False,
            "auto_push": False,
        }


@router.get("/policy-scheduler/runs/{scheduler_id}")
def policy_scheduler_run(scheduler_id: str) -> dict[str, Any]:
    return {**SAFETY_FLAGS, "run": POLICY_SCHEDULER_RUNS.get(scheduler_id)}


@router.get("/policy-scheduler/daemon/status")
def policy_scheduler_daemon_status() -> dict[str, Any]:
    return {
        **SAFETY_FLAGS,
        **AUTONOMOUS_DAEMON.status(),
        "run_lease": _agentic_run_lease_status(),
    }


@router.post("/policy-scheduler/daemon/start")
def policy_scheduler_daemon_start(request: PolicySchedulerDaemonStartApiRequest) -> dict[str, Any]:
    with _AGENTIC_RUN_EXECUTION_LOCK, _AGENTIC_REVIEW_QUEUE_LOCK:
        activation, config = _activate_agentic_run_lease(
            request,
            mode="daemon",
        )
        if not activation.get("allowed") or config is None:
            return {
                **SAFETY_FLAGS,
                "allowed": False,
                "daemon_running": False,
                **activation,
            }
        lease_id = str(activation.get("lease_id") or "")
        try:
            _set_policy_scheduler(config)
            stop_path = _resolved_runtime_path(config.stop_file)
            if stop_path.exists():
                stop_clear = _authorize_agentic_action(
                    "agentic.scratch_write",
                    scratch_write_bytes=1,
                    expected_lease_id=lease_id,
                    expected_mode="daemon",
                )
                if not stop_clear.get("allowed"):
                    _halt_agentic_run(
                        str(stop_clear.get("reason")),
                        expected_lease_id=lease_id,
                        expected_mode="daemon",
                    )
                    return {
                        **SAFETY_FLAGS,
                        "daemon_running": False,
                        **stop_clear,
                    }
            start_payload = POLICY_SCHEDULER.start(
                operator_confirmed=True
            )
            if not POLICY_SCHEDULER.enabled:
                _finish_agentic_run_lease(
                    str(
                        start_payload.get("reason")
                        or "scheduler_start_failed"
                    ),
                    expected_lease_id=lease_id,
                    expected_mode="daemon",
                )
                return {
                    **SAFETY_FLAGS,
                    "allowed": False,
                    "daemon_running": False,
                    **start_payload,
                }
            daemon_payload = AUTONOMOUS_DAEMON.start(
                POLICY_SCHEDULER
            )
        except Exception as exc:
            reason = (
                f"policy_scheduler_daemon_start_error:"
                f"{type(exc).__name__}"
            )
            daemon_reset = AUTONOMOUS_DAEMON.reset_failed_start(
                expected_lease_id=lease_id,
                reason=reason,
            )
            cleanup = _cleanup_failed_agentic_start(
                lease_id=lease_id,
                mode="daemon",
                reason=reason,
            )
            return {
                **SAFETY_FLAGS,
                "allowed": False,
                "daemon_running": False,
                "reason": reason,
                "daemon_reset": daemon_reset,
                "run_lease_activation": activation,
                "start_cleanup": cleanup,
                "run_lease": _agentic_run_lease_status(),
            }
        if not daemon_payload.get("daemon_running"):
            reason = str(
                daemon_payload.get("reason")
                or "daemon_start_failed"
            )
            daemon_reset = AUTONOMOUS_DAEMON.reset_failed_start(
                expected_lease_id=lease_id,
                reason=reason,
            )
            start_cleanup = _cleanup_failed_agentic_start(
                lease_id=lease_id,
                mode="daemon",
                reason=reason,
            )
        else:
            daemon_reset = False
            start_cleanup = None
        daemon_status = AUTONOMOUS_DAEMON.status()
        return {
            **SAFETY_FLAGS,
            "live_web": False,
            **start_payload,
            **daemon_payload,
            "daemon_running": bool(
                daemon_status.get("daemon_running")
            ),
            "allowed": bool(
                daemon_payload.get("daemon_running")
            ),
            "run_lease_activation": activation,
            "run_lease": _agentic_run_lease_status(),
            "daemon_reset": daemon_reset,
            "start_cleanup": start_cleanup,
            "candidate_staging_write_possible": True,
            "candidate_staging_mutated": daemon_status[
                "candidate_staging_mutated"
            ],
            "mutation_performed": daemon_status[
                "mutation_performed"
            ],
            "production_merge_attempted": False,
            "production_store_mutated": False,
            "local_brain_write": False,
            "candidate_promotion": False,
        }


@router.post("/policy-scheduler/daemon/stop")
def policy_scheduler_daemon_stop(request: PolicySchedulerStopApiRequest) -> dict[str, Any]:
    with _AGENTIC_RUN_LEASE_LOCK:
        active = (
            dict(AGENTIC_ACTIVE_RUN_LEASE)
            if AGENTIC_ACTIVE_RUN_LEASE is not None
            else None
        )
    if (
        active is not None
        and active.get("mode") != "daemon"
        and not AUTONOMOUS_DAEMON.is_running()
    ):
        return {
            **SAFETY_FLAGS,
            "allowed": False,
            "daemon_running": False,
            "reason": "daemon_stop_does_not_target_manual_run",
            "run_lease": _agentic_run_lease_status(),
        }
    payload = AUTONOMOUS_DAEMON.stop(reason=request.reason)
    return {
        **SAFETY_FLAGS,
        **payload,
        **AUTONOMOUS_DAEMON.status(),
        "run_lease": _agentic_run_lease_status(),
    }


@router.post("/wikipedia-grounded/ingest")
def wikipedia_grounded_ingest() -> dict[str, Any]:
    """Manually run one bounded Wikipedia-grounded learning batch.

    Same clean grounding path the autonomous loop uses each cycle. Candidate-only
    (no production write); unattended work may stage an intent, while promotion
    remains a separate operator action."""
    return {**SAFETY_FLAGS, **_run_wikipedia_grounded_learning(force=True)}


@router.get("/wikipedia-grounded/status")
def wikipedia_grounded_status() -> dict[str, Any]:
    return {
        **SAFETY_FLAGS,
        "min_interval_sec": WIKIPEDIA_GROUNDED_MIN_INTERVAL_SEC,
        "topics_per_tick": WIKIPEDIA_GROUNDED_TOPICS_PER_TICK,
        "last_result": _LAST_WIKIPEDIA_GROUNDED_RESULT,
    }


@router.get("/overnight-briefing")
def overnight_briefing() -> dict[str, Any]:
    """Lightweight 'while you were away' summary, shown when the user returns.

    The agent worked autonomously (AGORA + web) and may have something to mention
    or ask about. If nothing notable happened, ``has_briefing`` is False and the
    dashboard shows nothing. Nothing here requires action — it just informs.
    """
    log = AUTONOMOUS_DAEMON.status().get("activity_log") or []
    learned = 0
    web_reads = 0
    for rec in log:
        actions = rec.get("actions") or []
        learned += int(rec.get("candidate_drafts") or 0)
        if any(str(a).startswith("open_web") or str(a).startswith("web_explorer") for a in actions):
            web_reads += 1
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        review = REVIEW_QUEUE.status()
        candidate_intents_staged = len(AUTO_STAGED_INTENT_IDS)
        items = [
            item.to_dict() for item in REVIEW_QUEUE.list_items()
        ]
    candidate_staging_mutated = any(
        rec.get("candidate_staging_mutated") is True
        or rec.get("review_queue_staging_mutated") is True
        for rec in log
    )
    # Anything the agent held back (private/mutation hard floor) is worth a glance.
    held = [
        {"title": it.get("title"), "reason": "held: private/mutation signal"}
        for it in items
        if str(it.get("risk_level")) == "critical"
    ][:5]
    pending = int(review.get("pending") or 0)
    has_briefing = bool(
        log
        or learned > 0
        or candidate_intents_staged > 0
        or held
        or int(review.get("items_total") or 0) > 0
    )
    return {
        **SAFETY_FLAGS,
        "has_briefing": has_briefing,
        "cycles": len(log),
        "web_read_cycles": web_reads,
        "candidates_learned": int(review.get("items_total") or 0),
        "auto_promoted": 0,
        "candidate_intents_staged": candidate_intents_staged,
        "candidate_staging_mutated": candidate_staging_mutated,
        "mutation_performed": candidate_staging_mutated,
        "pending_review": pending,
        "needs_confirmation": held,
        "production_merge_attempted": False,
        "production_store_mutated": False,
    }


def _review_item_dicts() -> list[dict[str, Any]]:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        return [
            item.to_dict() for item in REVIEW_QUEUE.list_items()
        ]


@router.get("/promotion-gate/status")
def promotion_gate_status() -> dict[str, Any]:
    return {**SAFETY_FLAGS, **CANDIDATE_PROMOTION_GATE.status(_review_item_dicts())}


@router.post("/promotion-gate/draft")
def promotion_gate_draft(request: PromotionDraftApiRequest) -> dict[str, Any]:
    manifest = CANDIDATE_PROMOTION_GATE.draft_manifest(
        _review_item_dicts(),
        item_ids=request.item_ids or None,
        created_by=request.created_by,
    )
    return {**SAFETY_FLAGS, **manifest}


@router.post("/promotion-gate/confirm")
def promotion_gate_confirm(request: PromotionConfirmApiRequest) -> dict[str, Any]:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        result = CANDIDATE_PROMOTION_GATE.confirm_promotion(
            _review_item_dicts(),
            item_ids=request.item_ids or None,
            operator_confirmed=request.operator_confirmed,
            confirmation_phrase=request.confirmation_phrase,
            operator_id=request.operator_id,
        )
        if result.get("allowed"):
            # Record the human-approved staging on the review items themselves
            # so the queue reflects the operator's decision.
            for item_id in result.get("eligible_ids", []):
                item = REVIEW_QUEUE.get(str(item_id))
                if (
                    item is not None
                    and "promotion staged by operator"
                    not in item.review_notes
                ):
                    item.review_notes.append(
                        "promotion staged by operator"
                    )
            _persist_review_queue()
    if result.get("allowed"):
        emit_runtime_event(
            source="promotion_gate",
            event_type="review_item_approved",
            payload_summary=f"staged={len(result.get('eligible_ids', []))}",
            intensity=0.6,
        )
    return {
        **SAFETY_FLAGS,
        **result,
        "mutation_performed": False,
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
    }


@router.get("/host-executor/patch/status")
def scoped_patch_status() -> dict[str, Any]:
    return {**SAFETY_FLAGS, **SCOPED_PATCH_EXECUTOR.status()}


@router.post("/host-executor/execute")
def host_executor_execute(request: HostExecutorExecuteApiRequest) -> dict[str, Any]:
    result = HOST_EXECUTOR.execute(
        HostExecutionRequest(
            action_type=request.action_type,
            path=request.path,
            content=request.content,
            max_bytes=request.max_bytes,
            max_entries=request.max_entries,
            safe_test_token=request.safe_test_token,
            operator_id=request.operator_id,
        )
    )
    result_payload = result.to_dict()
    emit_runtime_event(
        source="host_executor",
        event_type="host_action_success" if result_payload.get("allowed") and result_payload.get("executed") else "host_action_denied",
        payload_summary=f"action={request.action_type}; allowed={result_payload.get('allowed')}; executed={result_payload.get('executed')}",
        intensity=0.75,
    )
    return {
        **SAFETY_FLAGS,
        **result_payload,
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "auto_commit": False,
        "auto_push": False,
    }


@router.post("/host-executor/patch/plan")
def scoped_patch_plan(request: ScopedPatchApiRequest) -> dict[str, Any]:
    result = SCOPED_PATCH_EXECUTOR.plan(
        ScopedPatchRequest(
            target_path=request.target_path,
            expected_old_text=request.expected_old_text,
            replacement_text=request.replacement_text,
            reason=request.reason,
            operator_confirmation=request.operator_confirmation,
            tier_session_id=request.tier_session_id,
            required_subswitches=request.required_subswitches,
            dry_run=request.dry_run,
            operator_id=request.operator_id,
        )
    )
    return {
        **SAFETY_FLAGS,
        **result.to_dict(),
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "auto_commit": False,
        "auto_push": False,
        "host_executor_v1_scoped_only": True,
    }


@router.post("/host-executor/patch/apply")
def scoped_patch_apply(request: ScopedPatchApiRequest) -> dict[str, Any]:
    result = SCOPED_PATCH_EXECUTOR.apply(
        ScopedPatchRequest(
            target_path=request.target_path,
            expected_old_text=request.expected_old_text,
            replacement_text=request.replacement_text,
            reason=request.reason,
            operator_confirmation=request.operator_confirmation,
            tier_session_id=request.tier_session_id,
            required_subswitches=request.required_subswitches,
            dry_run=False,
            operator_id=request.operator_id,
        )
    )
    return {
        **SAFETY_FLAGS,
        **result.to_dict(),
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "auto_commit": False,
        "auto_push": False,
        "host_executor_v1_scoped_only": True,
    }


@router.post("/host-executor/patch/rollback")
def scoped_patch_rollback(request: ScopedPatchRollbackApiRequest) -> dict[str, Any]:
    result = SCOPED_PATCH_EXECUTOR.rollback(
        ScopedPatchRollbackRequest(
            target_path=request.target_path,
            backup_path=request.backup_path,
            operator_confirmation=request.operator_confirmation,
            tier_session_id=request.tier_session_id,
            operator_id=request.operator_id,
        )
    )
    return {
        **SAFETY_FLAGS,
        **result.to_dict(),
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "auto_commit": False,
        "auto_push": False,
        "host_executor_v1_scoped_only": True,
    }


@router.get("/browser-read/status")
def browser_read_status() -> dict[str, Any]:
    return {**SAFETY_FLAGS, **BrowserReadConnector().status()}


@router.post("/browser-read")
def browser_read(request: BrowserReadApiRequest) -> dict[str, Any]:
    kernel = CapabilityKernel()
    token = kernel.issue("browser_read", reason="agentic-os browser-read proof")
    result = BrowserReadConnector(kernel=kernel).read(
        BrowserReadRequest(
            url=request.url,
            visible_text=request.visible_text,
            metadata=request.metadata,
            max_chars=request.max_chars,
        ),
        token,
    )
    return {**SAFETY_FLAGS, **result.to_dict()}


@router.get("/mcp/status")
def mcp_status() -> dict[str, Any]:
    return {**SAFETY_FLAGS, **MCPAllowlistGateway().status()}


@router.post("/mcp/validate")
def mcp_validate(request: MCPValidateApiRequest) -> dict[str, Any]:
    kernel = CapabilityKernel()
    token = kernel.issue("mcp_allowlist_validate", reason="agentic-os MCP allowlist proof")
    descriptors = default_descriptors()
    descriptor_hash = request.descriptor_hash or descriptors.get(request.descriptor, descriptors["render_preview"]).descriptor_hash
    result = MCPAllowlistGateway(descriptors=descriptors, kernel=kernel).validate(
        MCPValidationRequest(
            descriptor=request.descriptor,
            descriptor_hash=descriptor_hash,
            method=request.method,
            payload=request.payload,
        ),
        token,
    )
    return {**SAFETY_FLAGS, **result.to_dict()}


@router.post("/splatra/evaluate")
def splatra_evaluate(request: SplatraEvaluateApiRequest) -> dict[str, Any]:
    kernel = CapabilityKernel()
    token = kernel.issue("splatra_cosmos_evaluate", reason="agentic-os SPLATRA evaluator proof")
    result = SplatraCosmosEvaluator(kernel=kernel).evaluate(
        SplatraEvaluationRequest(
            candidate_id=request.candidate_id,
            particle_budget=request.particle_budget,
            target_fps=request.target_fps,
            include_city_proof=request.include_city_proof,
            emotion_probe=request.emotion_probe,
        ),
        token,
    )
    return {**SAFETY_FLAGS, **result.to_dict()}


def _splatra_visible_summary(frame_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    if frame_payload:
        objects = frame_payload.get("objects") or []
        if objects:
            item = objects[0]
            metadata = item.get("metadata") or {}
    turbovec = metadata.get("turbovec") or {}
    compressed_ref = item.get("compressed_ref") or turbovec.get("compressed_ref") or {}
    lod_summary = turbovec.get("lod_summary") or {}
    return {
        "active_archetype": metadata.get("active_archetype") or item.get("archetype") or "constellation",
        "visible_object": bool(metadata.get("visible_object", True)),
        "product_visible": bool(metadata.get("product_visible", True)),
        "particle_count": int(item.get("particle_count") or metadata.get("particle_count") or 1600),
        "compression_ratio": compressed_ref.get("compression_ratio"),
        "lod_levels": lod_summary.get("levels", [0, 1, 2]),
        "visual_intensity": metadata.get("visual_intensity", 0.72),
        "clear_radius": metadata.get("clear_radius", 0.34),
        "input_overlay_blocked": bool(metadata.get("input_overlay_blocked", False)),
    }


@router.get("/splatra/imagination/status")
def splatra_imagination_status() -> dict[str, Any]:
    visible_summary = _splatra_visible_summary()
    return {
        **SAFETY_FLAGS,
        **default_safety_flags(),
        "available": True,
        "proof_only": True,
        "label": "imagination",
        "source": "procedural",
        "is_verified_knowledge": False,
        "archetypes": list(ARCHETYPES),
        "product_budget": 1600,
        "lab_budget": 6500,
        **visible_summary,
    }


@router.post("/splatra/imagination/generate")
def splatra_imagination_generate(request: SplatraImaginationGenerateApiRequest) -> dict[str, Any]:
    if request.archetype not in ARCHETYPES:
        emit_runtime_event(
            source="splatra_imagination",
            event_type="splatra_generation_failure",
            payload_summary=f"unsupported archetype={request.archetype}",
            intensity=0.8,
        )
        return {
            **SAFETY_FLAGS,
            **default_safety_flags(),
            "allowed": False,
            "reason": "unsupported archetype",
            "archetypes": list(ARCHETYPES),
        }
    seed = ImaginationSeed(
        seed_id=request.seed_id,
        archetype=request.archetype,  # type: ignore[arg-type]
        randomness=max(0.0, min(1.0, request.randomness)),
        valence=max(-1.0, min(1.0, request.valence)),
        arousal=max(0.0, min(1.0, request.arousal)),
        curiosity=max(0.0, min(1.0, request.curiosity)),
        speaking_energy=max(0.0, min(1.0, request.speaking_energy)),
        state=request.state if request.state in {"imagining", "resting", "speaking", "thinking", "previewing", "blocked"} else "imagining",  # type: ignore[arg-type]
        particle_budget=max(16, min(request.particle_budget, 100_000)),
        lod_target=max(0, request.lod_target),
        created_at="api_procedural_seed",
    )
    frame = ImaginationGenerator(max_particle_budget=100_000).generate_frame(seed)
    frame_payload = frame.to_dict(include_particles=request.include_particles)
    visible_summary = _splatra_visible_summary(frame_payload)
    emit_runtime_event(
        source="splatra_imagination",
        event_type="splatra_generation_success",
        payload_summary=f"archetype={request.archetype}; particles={request.particle_budget}",
        intensity=0.45,
    )
    return {
        **SAFETY_FLAGS,
        **default_safety_flags(),
        "allowed": True,
        "frame": frame_payload,
        **visible_summary,
    }


@router.post("/splatra/imagination/evaluate")
def splatra_imagination_evaluate(request: SplatraImaginationEvaluateApiRequest) -> dict[str, Any]:
    proof = run_imagination_proof(particle_budget=max(16, min(request.particle_budget, 10_000)))
    return {**SAFETY_FLAGS, **default_safety_flags(), **proof, **_splatra_visible_summary()}


@router.post("/splatra/imagination/command")
def splatra_imagination_command(request: SplatraImaginationCommandApiRequest) -> dict[str, Any]:
    scene_command = request.scene_command if request.scene_command in {"spawn_object", "morph", "render_knowledge_hologram"} else "spawn_object"
    archetype = request.archetype if request.archetype in ARCHETYPES else None
    plan, frame = compile_splatra_command(
        request.command,
        particle_budget=max(64, min(request.particle_budget, 100_000)),
        mode=request.mode,
        scene_command=scene_command,  # type: ignore[arg-type]
        archetype=archetype,  # type: ignore[arg-type]
    )
    frame_payload = frame.to_dict(include_particles=request.include_particles)
    visible_summary = _splatra_visible_summary(frame_payload)
    emit_runtime_event(
        source="splatra_imagination",
        event_type="splatra_generation_success",
        payload_summary=f"command={plan.scene_command}; archetype={plan.archetype}",
        intensity=0.48,
    )
    return {
        **SAFETY_FLAGS,
        **default_safety_flags(),
        "allowed": True,
        "agent_can_use": True,
        "splatra_command_adapter": True,
        "external_splatra_called": False,
        "raw_buffer_in_agent_context": False,
        "command_plan": plan.to_dict(),
        "frame": frame_payload,
        **visible_summary,
    }


@router.post("/splatra/imagination/choreography")
def splatra_scene_choreography(request: SplatraSceneChoreographyApiRequest) -> dict[str, Any]:
    plan = compile_scene_choreography(request.model_dump())
    command_sequence = compile_scene_choreography_commands(plan)
    interactive_scene_analysis = analyze_scene_choreography(plan)
    cartridge_queue = build_candidate_cartridge_queue(command_sequence)
    sidecar_dispatch = (
        dispatch_candidate_queue_to_sidecar(cartridge_queue, poll_ticks=request.sidecar_poll_ticks)
        if request.dispatch_sidecar
        else SplatraSidecarDispatchResult(status="dispatch_not_requested", configured=False, sidecar_url=None, jobs=[])
    )
    emit_runtime_event(
        source="splatra_imagination",
        event_type="splatra_generation_success",
        payload_summary=f"choreography_beats={len(plan.beats)}; layout={plan.stage_layout}",
        intensity=0.42,
    )
    return {
        **SAFETY_FLAGS,
        **default_safety_flags(),
        "allowed": True,
        "agent_can_use": True,
        "splatra_choreography_adapter": True,
        "external_splatra_called": False,
        "raw_buffer_in_agent_context": False,
        "topic_scene_templates": False,
        "scene_choreography": plan.to_dict(),
        "splatra_command_sequence": command_sequence.to_dict(),
        "splatra_interactive_scene_analysis": interactive_scene_analysis.to_dict(),
        "splatra_cartridge_queue": cartridge_queue.to_dict(),
        "splatra_sidecar_dispatch": sidecar_dispatch.to_dict(),
    }


@router.post("/splatra/imagination/cartridge-queue")
def splatra_scene_cartridge_queue(request: SplatraSceneChoreographyApiRequest) -> dict[str, Any]:
    plan = compile_scene_choreography(request.model_dump())
    command_sequence = compile_scene_choreography_commands(plan)
    interactive_scene_analysis = analyze_scene_choreography(plan)
    cartridge_queue = build_candidate_cartridge_queue(command_sequence)
    sidecar_dispatch = (
        dispatch_candidate_queue_to_sidecar(cartridge_queue, poll_ticks=request.sidecar_poll_ticks)
        if request.dispatch_sidecar
        else SplatraSidecarDispatchResult(status="dispatch_not_requested", configured=False, sidecar_url=None, jobs=[])
    )
    queue_payload = cartridge_queue.to_dict()
    queue_payload["sidecar_dispatch"] = sidecar_dispatch.to_dict()
    queue_payload["sidecar_status"] = sidecar_dispatch.status
    queue_payload["sidecar_configured"] = sidecar_dispatch.configured
    queue_payload["external_splatra_called"] = sidecar_dispatch.external_splatra_called
    return {
        **SAFETY_FLAGS,
        **default_safety_flags(),
        "allowed": True,
        "agent_can_use": True,
        "splatra_cartridge_queue_adapter": True,
        "external_splatra_called": sidecar_dispatch.external_splatra_called,
        "raw_buffer_in_agent_context": False,
        "mutation_performed": False,
        "topic_scene_templates": False,
        "scene_choreography": plan.to_dict(),
        "splatra_command_sequence": command_sequence.to_dict(),
        "splatra_interactive_scene_analysis": interactive_scene_analysis.to_dict(),
        "splatra_cartridge_queue": queue_payload,
        "splatra_sidecar_dispatch": sidecar_dispatch.to_dict(),
    }


@router.get("/web-explorer/status")
def web_explorer_status() -> dict[str, Any]:
    return {
        **SAFETY_FLAGS,
        "available": True,
        "proof_only": True,
        "runs": len(WEB_EXPLORER_RUNS),
        "skill_drafts": len(WEB_EXPLORER_SKILL_DRAFTS),
        "default_limits": {
            "max_pages": 30,
            "max_depth": 2,
            "max_runtime_sec": 21600,
            "max_candidate_drafts": 100,
            "max_skill_drafts": 20,
        },
    }


@router.post("/web-explorer/run-once")
def web_explorer_run_once(request: WebExplorerRunOnceApiRequest) -> dict[str, Any]:
    config = WebExplorerConfig(
        goal=request.goal,
        allowed_domains=request.allowed_domains,
        pages=[
            WebPageInput(
                url=page.url,
                title=page.title,
                visible_text=page.visible_text,
                depth=page.depth,
            )
            for page in request.pages
        ],
        max_pages=max(1, min(request.max_pages, 30)),
        max_depth=max(0, min(request.max_depth, 4)),
        max_runtime_sec=max(1, min(request.max_runtime_sec, 21600)),
        max_candidate_drafts=max(0, min(request.max_candidate_drafts, 100)),
        max_skill_drafts=max(0, min(request.max_skill_drafts, 20)),
    )
    result = HermesWebExplorerLoop(config).run_once().to_dict()
    WEB_EXPLORER_RUNS[str(result["run_id"])] = result
    WEB_EXPLORER_SKILL_DRAFTS.extend(result["skill_drafts"])  # type: ignore[arg-type]
    emit_runtime_event(
        source="web_explorer",
        event_type="novelty_found" if result.get("candidate_drafts_count") or result.get("skill_drafts_count") else "conversation_success",
        payload_summary=f"run={result.get('run_id')}; pages={result.get('pages_read')}; drafts={result.get('candidate_drafts_count')}",
        intensity=0.8,
    )
    return {**SAFETY_FLAGS, **result}


@router.get("/web-explorer/runs/{run_id}")
def web_explorer_run(run_id: str) -> dict[str, Any]:
    return {**SAFETY_FLAGS, "run": WEB_EXPLORER_RUNS.get(run_id)}


@router.get("/skills/drafts")
def skill_drafts() -> dict[str, Any]:
    return {**SAFETY_FLAGS, "skill_drafts": WEB_EXPLORER_SKILL_DRAFTS}


@router.get("/web-explorer/open/status")
def open_web_explorer_status() -> dict[str, Any]:
    return {
        **SAFETY_FLAGS,
        "available": True,
        "proof_only": True,
        "fixed_allowlist_required": False,
        "live_web_default": False,
        "runs": len(OPEN_WEB_EXPLORER_RUNS),
        "default_limits": {
            "max_pages": 300,
            "max_depth": 3,
            "max_runtime_sec": 21600,
            "max_bytes_per_page": 250_000,
            "per_domain_delay_sec": 3,
            "max_pages_per_domain": 50,
            "max_candidate_drafts": 200,
            "max_skill_drafts": 50,
        },
        "denylist": ["localhost/internal IPs", "login/account/payment/upload patterns", "download-like URLs", "credentialed tokens/secrets"],
    }


@router.post("/web-explorer/open/run")
def open_web_explorer_run(request: OpenWebExplorerRunApiRequest) -> dict[str, Any]:
    config = OpenWebExplorerConfig(
        goal=request.goal,
        seed_urls=request.seed_urls,
        max_pages=max(1, min(request.max_pages, 300)),
        max_depth=max(0, min(request.max_depth, 3)),
        max_runtime_sec=max(1, min(request.max_runtime_sec, 21600)),
        max_bytes_per_page=max(1024, min(request.max_bytes_per_page, 250_000)),
        per_domain_delay_sec=max(0.0, min(request.per_domain_delay_sec, 30.0)),
        max_pages_per_domain=max(1, min(request.max_pages_per_domain, 50)),
        max_candidate_drafts=max(0, min(request.max_candidate_drafts, 200)),
        max_skill_drafts=max(0, min(request.max_skill_drafts, 50)),
        fetch_live_web=request.live_web,
    )
    fetcher = None if request.live_web else FixtureOpenWebFetcher({fixture.url: fixture.html for fixture in request.fixtures})
    result = OpenWebExplorerLoop(config, fetcher=fetcher).run().to_dict()
    OPEN_WEB_EXPLORER_RUNS[str(result["run_id"])] = result
    WEB_EXPLORER_SKILL_DRAFTS.extend(result["skill_drafts"])  # type: ignore[arg-type]
    emit_runtime_event(
        source="web_explorer",
        event_type="novelty_found" if result.get("candidate_drafts_count") or result.get("skill_drafts_count") else "conversation_success",
        payload_summary=f"open_run={result.get('run_id')}; pages={result.get('pages_read')}; drafts={result.get('candidate_drafts_count')}",
        intensity=0.8,
    )
    return {**SAFETY_FLAGS, **result}


@router.get("/web-explorer/open/runs/{run_id}")
def open_web_explorer_run_status(run_id: str) -> dict[str, Any]:
    return {**SAFETY_FLAGS, "run": OPEN_WEB_EXPLORER_RUNS.get(run_id)}


@router.get("/review/status")
def review_status() -> dict[str, Any]:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        return {**SAFETY_FLAGS, **REVIEW_QUEUE.status()}


@router.get("/review/items")
def review_items(item_type: str | None = None, risk_level: str | None = None, status: str | None = None) -> dict[str, Any]:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        return {
            **SAFETY_FLAGS,
            **REVIEW_QUEUE.status(),
            "items": [
                item.to_dict()
                for item in REVIEW_QUEUE.list_items(
                    item_type=item_type,
                    risk_level=risk_level,
                    status=status,
                )
            ],
        }


@router.get("/review/items/{item_id}")
def review_item(item_id: str) -> dict[str, Any]:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        item = REVIEW_QUEUE.get(item_id)
        return {
            **SAFETY_FLAGS,
            "item": item.to_dict() if item else None,
        }


@router.post("/review/decide")
def review_decide(
    request: ReviewDecideApiRequest,
    operator_id: str = Depends(_require_bound_review_operator),
) -> dict[str, Any]:
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        if request.item_id not in REVIEW_QUEUE.items:
            return {**SAFETY_FLAGS, "allowed": False, "reason": "review item not found", "mutation_performed": False}
        try:
            decision = REVIEW_QUEUE.decide(
                request.item_id,
                request.decision,
                operator_id,
                request.reason,
                "draft_only",
            )
        except ValueError as exc:
            return {**SAFETY_FLAGS, "allowed": False, "reason": str(exc), "mutation_performed": False}
        _persist_review_queue()
        item = REVIEW_QUEUE.get(request.item_id)
        item_payload = item.to_dict() if item else None
    decision_value = str(decision.decision)
    event_type = "review_item_approved" if decision_value == "approved" else "review_item_rejected" if decision_value == "rejected" else "review_queue_pressure"
    emit_runtime_event(
        source="review_queue",
        event_type=event_type,
        payload_summary=f"decision={decision_value}; item={request.item_id}",
        intensity=0.65,
    )
    return {
        **SAFETY_FLAGS,
        "allowed": True,
        "decision": decision.to_dict(),
        "item": item_payload,
        "review_authority_verified": True,
        "review_authority_boundary": "agentic_micro_os_permission_gate",
        "caller_reviewer_claim_authoritative": False,
        "caller_approved_for_claim_authoritative": False,
        "approved_for_policy": "draft_only",
        "mutation_performed": False,
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "skill_auto_promoted": False,
    }


@router.post("/review/import-web-run")
def review_import_web_run(request: ReviewImportWebRunApiRequest) -> dict[str, Any]:
    run_payload = request.run_payload
    if run_payload is None and request.run_id:
        run_payload = OPEN_WEB_EXPLORER_RUNS.get(request.run_id) or WEB_EXPLORER_RUNS.get(request.run_id)
    if not run_payload:
        return {**SAFETY_FLAGS, "allowed": False, "reason": "web run not found", "imported": 0}
    with _AGENTIC_REVIEW_QUEUE_LOCK:
        imported = REVIEW_QUEUE.import_web_run(run_payload)
        _persist_review_queue()
        status_payload = REVIEW_QUEUE.status()
    if int(status_payload.get("pending", 0) or 0) > 8 or int(status_payload.get("high_risk", 0) or 0) > 0:
        emit_runtime_event(
            source="review_queue",
            event_type="review_queue_pressure",
            payload_summary=f"pending={status_payload.get('pending')}; high_risk={status_payload.get('high_risk')}",
            intensity=0.75,
        )
    return {
        **SAFETY_FLAGS,
        **status_payload,
        "allowed": True,
        "imported": len(imported),
        "items": [item.to_dict() for item in imported],
        "mutation_performed": False,
        "production_store_mutated": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "skill_auto_promoted": False,
    }


@router.post("/action/validate")
def validate_action(request: DashboardActionRequest) -> dict[str, Any]:
    kernel = CapabilityKernel()
    token = kernel.issue("dashboard_action", reason="agentic-os status surface proof")
    result = DashboardActionBus(kernel).validate(request.action_type, request.payload, token)
    return {**SAFETY_FLAGS, **result}


@router.post("/brain-access/request")
def brain_access_request(request: BrainAccessApiRequest) -> dict[str, Any]:
    road = BrainAccessRoad()
    response = road.request(
        BrainAccessRequest(
            target=request.target,  # type: ignore[arg-type]
            operation=request.operation,
            query=request.query,
            scope=request.scope,
            redaction_level=request.redaction_level,
            purpose=request.purpose,
            requested_by_loop_id=request.requested_by_loop_id,
        )
    )
    return {**SAFETY_FLAGS, "request": request.model_dump(), "response": asdict(response)}


@router.post("/loop/propose")
def loop_propose(request: LoopProposeRequest) -> dict[str, Any]:
    loop = BoundedAgentLoop(goal=request.goal, max_cycles=max(1, min(request.max_cycles, 3)))
    state = loop.run()
    skill = draft_skill_from_loop(state)
    return {
        **SAFETY_FLAGS,
        "loop": state.to_dict(),
        "skill_draft": asdict(skill),
        "patch_proposals": [asdict(proposal) for proposal in state.patch_proposals],
        "approval_required": True,
    }


@router.get("/hermes-intake/status")
def hermes_intake_status() -> dict[str, Any]:
    if not HERMES_REPO.exists():
        return {
            **SAFETY_FLAGS,
            "repo_present": False,
            "status": "not_cloned",
            "architecture_extracted": False,
        }
    report = scan_repo(HERMES_REPO)
    return {
        **SAFETY_FLAGS,
        "repo_present": True,
        "status": "architecture_extracted",
        "architecture_extracted": True,
        "source_commit": report.source_commit,
        "license": report.license_detected,
        "mit_compatible": report.mit_compatible,
        "reusable_architecture_patterns": report.reusable_architecture_patterns,
        "rejected_patterns": report.forbidden_or_high_risk_components,
    }
