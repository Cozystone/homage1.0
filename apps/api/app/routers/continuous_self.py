"""Persistent self-state API with signed, bounded background authority.

Importing or reading this router never starts the mechanism. An explicit start
can activate one externally signed run lease and then runs only the AUT-0 local
operational-self profile: local observation, homeostasis/digital hormones,
endogenous introspection, goals, pressure-paced cadence, and bounded state/audit
persistence. Network, production, code, training, and child-thread effects stay
outside this profile.

Two endpoints feed the "living-mind" UI:
 GET /api/selfhood/live → the current self snapshot
 GET /api/selfhood/stream → SSE, pushes the self as it changes (hash-diffed)
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import marshal
import os
import re
import shutil
import threading
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, AsyncIterator, Mapping

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from packages.autonomy_envelope.run_lease import (
    CONTINUOUS_SELF_RUNNER_ID,
    RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
    RUN_LEASE_PURPOSE,
    RunLeaseStore,
)
from packages.continuous_self.loop import (
    AUT0_LOCAL_CONTINUOUS_SELF_PROFILE,
    ContinuousSelf,
)
from packages.continuous_self.self_state import Observation

# English-only containment (owner directive 2026-07-17): the inner-voice web digests
# were still composed in Korean and fed the consciousness stream — an answer surface.
_SELF_LANG = "en" if os.environ.get("ATANOR_ENGLISH_ONLY", "1") != "0" else "ko"

router = APIRouter(prefix="/api/selfhood", tags=["continuous-self"])

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_STATE_PATH = _PROJECT_ROOT / "runtime" / "continuous_self" / "self_state.json"
_CONTINUOUS_SELF_SHADOW_LEDGER = (
    _PROJECT_ROOT
    / "reports"
    / "cognitive-shadow"
    / "continuous_self_cycles.jsonl"
)
_LIFECYCLE_SCHEMA = "atanor.continuous-self.lifecycle.v1"
_RUN_PROFILE_SCHEMA = "atanor.continuous-self.aut0-run-profile.v1"
_RUN_AUDIT_SCHEMA = "atanor.continuous-self.aut0-cycle-audit.v1"
_RUN_COMMIT_ATTEMPT_SCHEMA = (
    "atanor.continuous-self.aut0-commit-attempt.v1"
)
_RUNNER_ARTIFACT_SCHEMA = "atanor.continuous-self.runner-artifact.v1"
_RUN_INPUT_SCHEMA = "atanor.continuous-self.run-input.v1"
_RUNTIME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_STATE_WRITE_RESERVATION_BYTES = 512 * 1024
_AUDIT_RECORD_MAX_BYTES = 4 * 1024
_STOP_JOIN_TIMEOUT_SEC = 2.0
_IDENTITY_PACK_PATH = (
    _PROJECT_ROOT
    / "data"
    / "base_brain"
    / "packs"
    / "atanor_base_brain_v0.json"
)
_DEFAULT_RUN_LIMITS = {
    "max_runtime_sec": 600,
    "max_cycles": 24,
    "max_actions": 72,
    "max_external_requests": 0,
    "max_external_response_bytes": 0,
    "max_scratch_write_bytes": 13 * 1024 * 1024,
    "max_child_tasks": 0,
    "max_concurrent_child_tasks": 0,
}
_RUN_ACTION_CLASSES = [
    "self.audit_append",
    "self.observe_local",
    "self.state_write",
]
_AUT0_COMPUTE_PROFILE = replace(
    AUT0_LOCAL_CONTINUOUS_SELF_PROFILE,
    persist_state=False,
)

# delta tracking across observations (net-new growth is what the self "feels")
_prev = {"concepts": None, "relations": None}


def _disk_pressure() -> float:
    try:
        usage = shutil.disk_usage(str(Path(__file__).resolve().parents[4]))
        free_ratio = usage.free / max(1, usage.total)
        # pressure rises as free space falls below ~8%
        return max(0.0, min(1.0, (0.08 - free_ratio) / 0.08)) if free_ratio < 0.08 else 0.0
    except Exception:
        return 0.0


def _observe() -> Observation:
    """Gather the self's real signals THIS instant. Grounded, never fabricated."""
    learning_active = False
    c_delta = r_delta = 0
    uncertainty = 0.3
    deficits = 0
    try:
        from .cloud_brain import cloud_brain_continuous_metrics

        m = cloud_brain_continuous_metrics()
        learning_active = bool(m.get("running"))
        c = int(m.get("concepts_added") or 0)
        r = int(m.get("relations_added") or 0)
        if _prev["concepts"] is not None:
            c_delta = max(0, c - int(_prev["concepts"]))
            r_delta = max(0, r - int(_prev["relations"]))
        _prev["concepts"], _prev["relations"] = c, r
        # accept-rate below 1 means unresolved / rejected material → felt as uncertainty
        acc = float(m.get("accept_rate") or 1.0)
        uncertainty = max(0.0, min(1.0, 1.0 - acc))
    except Exception:
        pass
    try:
        hist = _STATE_PATH.parent.parent.parent / "data" / "self_improve_history.jsonl"
        if hist.exists():
            last = hist.read_text(encoding="utf-8").strip().splitlines()[-1]
            deficits = int(json.loads(last).get("hard_remaining") or 0)
    except Exception:
        pass
    # Phase 4-5 x 3-6: the camera's person-sighting IS the user's presence —
    # perception reaching the selfhood loop (arrival fires noradrenaline there)
    user_present = False
    person_unfamiliar = False
    try:
        from .perception import person_recently_seen, present_person_unfamiliar

        user_present = person_recently_seen()
        person_unfamiliar = present_person_unfamiliar()   # face cortex saw someone it didn't know
    except Exception:
        pass
    return Observation(
        learning_active=learning_active,
        concepts_delta=c_delta,
        relations_delta=r_delta,
        uncertainty_signal=uncertainty,
        resource_pressure=_disk_pressure(),
        deficit_count=deficits,
        user_present=user_present,
        person_unfamiliar=person_unfamiliar,
    )


def _self_probe(kind: str) -> dict[str, Any]:
    """A READ-ONLY probe the mind runs on ITSELF to serve a goal. OBSERVE-tier only —
    it never writes to the graph, a store, or code. It measures; it does not change."""
    if kind == "measure_coverage_gaps":
        try:
            hist = _STATE_PATH.parent.parent.parent / "data" / "self_improve_history.jsonl"
            last = json.loads(hist.read_text(encoding="utf-8").strip().splitlines()[-1])
            return {"open_gaps": int(last.get("hard_remaining") or 0),
                    "answered": int(last.get("answered_after") or 0)}
        except Exception:
            return {}
    if kind == "probe_uncertainty":
        try:
            from .cloud_brain import cloud_brain_continuous_metrics

            m = cloud_brain_continuous_metrics()
            return {"accept_rate": m.get("accept_rate"), "last_error": m.get("last_error")}
        except Exception:
            return {}
    if kind == "scan_frontier":
        # a read-only peek at what the learner is reaching toward next (no side effects).
        try:
            from .cloud_brain import cloud_brain_continuous_metrics

            titles = cloud_brain_continuous_metrics().get("last_titles") or []
            return {"frontier": titles[0]} if titles else {}
        except Exception:
            return {}
    return {"observed": True}


def _identity_answer(question: str, topic: str) -> str | None:
    """Read grounded identity without invoking instrumented answer surfaces."""
    _ = question, topic
    try:
        payload = json.loads(_IDENTITY_PACK_PATH.read_text(encoding="utf-8"))
        concepts = (
            (payload.get("semantic_graph") or {}).get("concepts") or []
        )
        concept = next(
            (
                row
                for row in concepts
                if type(row) is dict
                and row.get("concept_id") == "atanor"
            ),
            None,
        )
        if (
            type(concept) is not dict
            or concept.get("source_type") != "curated_base_pack"
            or type(concept.get("confidence")) not in {int, float}
            or float(concept["confidence"]) < 0.5
        ):
            return None
        answer = str(concept.get("short_description") or "").strip()
        if answer:
            return answer
    except Exception:
        pass
    return None


def _research(question: str) -> dict[str, Any] | None:
    """READ-ONLY web research for the self's own open question (OBSERVE tier — it
    reads public pages, writes nothing but the self-state). Uses the same relevance-
    gated pipeline as chat answers (referent resonance inside compose_web_answer), so
    an off-topic page is rejected rather than absorbed — the self only comes to
    'know' what actually answers its question. Returns {answer, sources, follow_ups}
    or None (an honest miss)."""
    try:
        from app.services.web_search import compose_web_answer, general_web_search

        q = str(question or "").strip()
        if not q:
            return None
        rows = general_web_search(q, count=6)
        composed = compose_web_answer(q, rows, language=_SELF_LANG) if rows else None
        if not composed or not str(composed.get("answer") or "").strip():

            # retry on the question's own content terms (morphology-level extraction).
            from packages.continuous_self.voice import harvest_terms

            terms = harvest_terms(q, set(), limit=2)
            if terms:
                rows = general_web_search(" ".join(terms), count=6)
                composed = compose_web_answer(terms[0], rows, language=_SELF_LANG) if rows else None
        if composed and str(composed.get("answer") or "").strip():
            ans = str(composed["answer"]).strip()
            # junk gate: navigation/link-list text is not knowledge. A real prose
            # answer doesn't carry pipe-separated menus or long middot chains, and

            # absorbed as "self-understanding").
            if ans.count("|") >= 2 or ans.count("·") >= 6 or len(ans) < 40:
                return None
            # ANTIFRAGILE SHIELD (owner 2026-07-10): observed web content is DATA, not a
            # command — screen it for injection/brainwash before the self folds it. An
            # attack is recorded as a social observation + immunized, never absorbed.
            try:
                from packages.graph_scale.epistemic_shield import shield
                _st = getattr(globals().get("_SELF"), "state", None)
                v = shield(ans, source="web:self_research", harden_state=_st)
                if v.get("attack"):
                    return None
            except Exception:
                pass
            return {
                "answer": ans,
                "sources": list(composed.get("sources") or []),
                "follow_ups": list(composed.get("follow_ups") or []),
            }
    except Exception:
        return None
    return None


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return hashlib.sha256(b"missing").hexdigest()


class _PhysicalWriteError(OSError):
    """I/O failure carrying bytes physically submitted before the error."""

    def __init__(self, message: str, *, bytes_written: int = 0) -> None:
        super().__init__(message)
        self.bytes_written = max(0, int(bytes_written))


def _write_all_unbuffered(handle: Any, payload: bytes) -> int:
    total = 0
    view = memoryview(payload)
    while total < len(payload):
        try:
            written = handle.write(view[total:])
        except OSError as exc:
            raise _PhysicalWriteError(
                str(exc),
                bytes_written=total,
            ) from exc
        if type(written) is not int or written <= 0:
            raise _PhysicalWriteError(
                "zero-length physical write",
                bytes_written=total,
            )
        total += written
    return total


def _atomic_replace_bytes(path: Path, payload: bytes) -> int:
    """Write one exact payload to the approved temp path, then replace."""

    temporary = path.with_suffix(".tmp")
    written = 0
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("wb", buffering=0) as handle:
            written = _write_all_unbuffered(handle, payload)
            os.fsync(handle.fileno())
        temporary.replace(path)
        return written
    except _PhysicalWriteError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except OSError as exc:
        cleanup_error: OSError | None = None
        try:
            temporary.unlink(missing_ok=True)
        except OSError as unlink_error:
            cleanup_error = unlink_error
        message = str(exc)
        if cleanup_error is not None:
            message = (
                f"{message}; temporary cleanup failed: "
                f"{type(cleanup_error).__name__}"
            )
        raise _PhysicalWriteError(
            message,
            bytes_written=written,
        ) from exc


def _append_fsync_bytes(path: Path, payload: bytes) -> int:
    """Append one exact audit payload and report submitted physical bytes."""

    written = 0
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab", buffering=0) as handle:
            written = _write_all_unbuffered(handle, payload)
            os.fsync(handle.fileno())
        return written
    except _PhysicalWriteError:
        raise
    except OSError as exc:
        raise _PhysicalWriteError(
            str(exc),
            bytes_written=written,
        ) from exc


def _action_costs(
    *,
    cycles: int = 0,
    scratch_write_bytes: int = 0,
) -> dict[str, int]:
    return {
        "cycles": cycles,
        "actions": 1,
        "external_requests": 0,
        "external_response_bytes": 0,
        "scratch_write_bytes": scratch_write_bytes,
        "child_tasks": 0,
        "concurrent_child_tasks": 0,
    }


def _validate_boot_limits(value: Mapping[str, Any]) -> dict[str, int]:
    expected = frozenset(_DEFAULT_RUN_LIMITS)
    if (
        type(value) is not dict
        or frozenset(value) != expected
        or any(type(value[key]) is not int for key in expected)
    ):
        raise ValueError("continuous_self_run_limits_invalid")
    limits = {key: value[key] for key in _DEFAULT_RUN_LIMITS}
    if (
        not 1 <= limits["max_runtime_sec"] <= 3_600
        or not 1 <= limits["max_cycles"] <= 1_800
        or not 3 * limits["max_cycles"]
        <= limits["max_actions"]
        <= 20_000
        or limits["max_external_requests"] != 0
        or limits["max_external_response_bytes"] != 0
        or limits["max_child_tasks"] != 0
        or limits["max_concurrent_child_tasks"] != 0
        or not (
            limits["max_cycles"]
            * (
                _STATE_WRITE_RESERVATION_BYTES
                + _AUDIT_RECORD_MAX_BYTES
            )
            <= limits["max_scratch_write_bytes"]
            <= 16 * 1024 * 1024
        )
    ):
        raise ValueError("continuous_self_run_limits_invalid")
    return limits


@dataclass(frozen=True)
class _ContinuousSelfRunLeaseBinding:
    store: RunLeaseStore
    runtime_instance_id: str
    limits: dict[str, int]


_RUN_LEASE_BINDING: _ContinuousSelfRunLeaseBinding | None = None
_RUN_LEASE_BINDING_LOCK = threading.RLock()
_CONTROL_LOCK = threading.RLock()


def configure_continuous_self_run_lease(
    store: RunLeaseStore,
    *,
    runtime_instance_id: str,
    limits: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Install a boot-provisioned verifier; HTTP requests cannot configure it."""
    global _RUN_LEASE_BINDING
    if type(store) is not RunLeaseStore:
        raise TypeError("provisioned RunLeaseStore required")
    if (
        type(runtime_instance_id) is not str
        or _RUNTIME_ID_RE.fullmatch(runtime_instance_id) is None
    ):
        raise ValueError("continuous_self_runtime_instance_id_invalid")
    configured_limits = _validate_boot_limits(
        dict(limits) if limits is not None else dict(_DEFAULT_RUN_LIMITS)
    )
    with _RUN_LEASE_BINDING_LOCK:
        if globals().get("_SELF") is not None:
            telemetry = _SELF.lease_telemetry()
            if _SELF.running or not telemetry["lease_finalized"]:
                raise RuntimeError(
                    "continuous_self_must_be_dormant_to_reconfigure"
                )
        _RUN_LEASE_BINDING = _ContinuousSelfRunLeaseBinding(
            store=store,
            runtime_instance_id=runtime_instance_id,
            limits=configured_limits,
        )
    context = continuous_self_run_lease_context()
    assert context is not None
    return context


def _clear_continuous_self_run_lease_for_tests() -> None:
    """Test-only reset; production bootstrap has no HTTP unbind surface."""
    global _RUN_LEASE_BINDING
    if globals().get("_SELF") is not None:
        _SELF.stop(reason="test_reset")
    with _RUN_LEASE_BINDING_LOCK:
        _RUN_LEASE_BINDING = None


def _callable_identity(value: Any) -> str:
    module = str(getattr(value, "__module__", "") or "")
    name = str(
        getattr(value, "__qualname__", "")
        or getattr(value, "__name__", "")
        or type(value).__qualname__
    )
    return f"{module}:{name}"[:256]


def _callable_manifest(value: Any) -> dict[str, Any]:
    identity = _callable_identity(value)
    code = getattr(value, "__code__", None)
    code_sha256 = hashlib.sha256(b"no-python-code").hexdigest()
    if code is not None:
        try:
            code_sha256 = hashlib.sha256(marshal.dumps(code)).hexdigest()
        except (TypeError, ValueError):
            pass
    source_path: Path | None = None
    try:
        raw_source = inspect.getsourcefile(value)
        if raw_source:
            source_path = Path(raw_source).resolve(strict=False)
    except (OSError, TypeError):
        pass
    source_label = None
    source_sha256 = hashlib.sha256(b"no-source-file").hexdigest()
    if source_path is not None:
        try:
            source_label = source_path.relative_to(_PROJECT_ROOT).as_posix()
        except ValueError:
            source_label = str(source_path)
        source_sha256 = _file_sha256(source_path)
    return {
        "identity": identity,
        "code_sha256": code_sha256,
        "source_path": source_label,
        "source_sha256": source_sha256,
    }


def _continuous_self_artifact_files() -> list[Path]:
    package_root = _PROJECT_ROOT / "packages" / "continuous_self"
    router_root = _PROJECT_ROOT / "apps" / "api" / "app" / "routers"
    paths = {
        Path(__file__).resolve(),
        router_root / "cloud_brain.py",
        router_root / "perception.py",
        *(
            path
            for path in package_root.rglob("*.py")
            if "tests" not in path.parts and "__pycache__" not in path.parts
        ),
    }
    return sorted(path.resolve(strict=False) for path in paths)


def _continuous_self_write_policy(state_path: Path) -> dict[str, Any]:
    audit_path = state_path.parent / "aut0_cycle_audit.jsonl"
    return {
        "schema_version": "atanor.continuous-self.local-write-policy.v1",
        "allowed_write_paths": sorted(
            {
                str(state_path.resolve(strict=False)),
                str(state_path.with_suffix(".tmp").resolve(strict=False)),
                str(audit_path.resolve(strict=False)),
            }
        ),
        "allowed_directory_create_paths": [
            str(state_path.parent.resolve(strict=False))
        ],
        "all_other_filesystem_writes": "denied_by_execution_profile",
    }


def _continuous_self_input_manifest() -> dict[str, Any]:
    state_path = _SELF.state_path
    with _SELF._lock:
        state_bytes = _canonical_bytes(asdict(_SELF.state))
    state_exists = state_path.is_file()
    identity_pack_exists = _IDENTITY_PACK_PATH.is_file()
    return {
        "schema_version": _RUN_INPUT_SCHEMA,
        "state_path": str(state_path.resolve(strict=False)),
        "state_exists": state_exists,
        "state_sha256": (
            _file_sha256(state_path)
            if state_exists
            else hashlib.sha256(b"missing").hexdigest()
        ),
        "state_memory_sha256": hashlib.sha256(state_bytes).hexdigest(),
        "state_memory_bytes": len(state_bytes),
        "identity_pack_path": str(
            _IDENTITY_PACK_PATH.resolve(strict=False)
        ),
        "identity_pack_exists": identity_pack_exists,
        "identity_pack_sha256": (
            _file_sha256(_IDENTITY_PACK_PATH)
            if identity_pack_exists
            else hashlib.sha256(b"missing").hexdigest()
        ),
        "observation_provider": _callable_manifest(_SELF.obs_provider),
        "local_probe_provider": _callable_manifest(_SELF.observe_fn),
        "identity_provider": _callable_manifest(_SELF.identity_fn),
    }


def _continuous_self_live_context(
    binding: _ContinuousSelfRunLeaseBinding,
    *,
    input_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state_path = _SELF.state_path
    write_policy = _continuous_self_write_policy(state_path)
    artifact_files = _continuous_self_artifact_files()
    artifact_manifest = {
        "schema_version": _RUNNER_ARTIFACT_SCHEMA,
        "files": [
            {
                "path": path.relative_to(_PROJECT_ROOT).as_posix(),
                "sha256": _file_sha256(path),
            }
            for path in artifact_files
        ],
        "providers": {
            "observation": _callable_manifest(_SELF.obs_provider),
            "local_probe": _callable_manifest(_SELF.observe_fn),
            "identity": _callable_manifest(_SELF.identity_fn),
        },
    }
    bound_input = (
        dict(input_manifest)
        if input_manifest is not None
        else _continuous_self_input_manifest()
    )
    profile_config = {
        "schema_version": _RUN_PROFILE_SCHEMA,
        "execution_profile": asdict(AUT0_LOCAL_CONTINUOUS_SELF_PROFILE),
        "compute_profile": asdict(_AUT0_COMPUTE_PROFILE),
        "commit_protocol": (
            "preauthorize_new_plus_worst_case_rollback_then_write_v2"
        ),
        "commit_failure_scope": "in_process_io_failures_only",
        "process_crash_atomicity_claim": False,
        "base_interval": _SELF.base_interval,
        "initiative_every": _SELF.initiative_every,
        "state_write_reservation_bytes": _STATE_WRITE_RESERVATION_BYTES,
        "audit_record_max_bytes": _AUDIT_RECORD_MAX_BYTES,
        "stop_join_timeout_sec": _STOP_JOIN_TIMEOUT_SEC,
    }
    filesystem_policy_sha256 = _canonical_sha256(write_policy)
    network_policy_sha256 = _canonical_sha256(
        {
            "schema_version": "atanor.network-policy.v1",
            "policy": "deny_all",
        }
    )
    child_task_policy_sha256 = _canonical_sha256(
        {
            "schema_version": "atanor.child-task-policy.v1",
            "policy": "deny_all",
        }
    )
    root = _PROJECT_ROOT.resolve(strict=True)
    return {
        "runner_id": CONTINUOUS_SELF_RUNNER_ID,
        "deployment_id": binding.store.boundary.deployment_id,
        "runtime_instance_id": binding.runtime_instance_id,
        "runner_artifact_sha256": _canonical_sha256(artifact_manifest),
        "config_sha256": _canonical_sha256(profile_config),
        "input_manifest_sha256": _canonical_sha256(bound_input),
        "capability_manifest": {
            "schema_version": RUN_LEASE_CAPABILITY_SCHEMA_VERSION,
            "action_classes": list(_RUN_ACTION_CLASSES),
            "filesystem_policy_sha256": filesystem_policy_sha256,
            "network_policy_sha256": network_policy_sha256,
            "child_task_policy_sha256": child_task_policy_sha256,
        },
        "limits": dict(binding.limits),
        "scratch_boundary": {
            "boundary_id": "atanor-continuous-self-local-state-v1",
            "resolved_root_sha256": hashlib.sha256(
                str(root).encode("utf-8")
            ).hexdigest(),
            "identity_manifest_sha256": filesystem_policy_sha256,
        },
        "operator_boundary_id": binding.store.boundary.operator_boundary_id,
        "operator_boundary_config_sha256": (
            binding.store.boundary.operator_boundary_config_sha256
        ),
        "nonce_replay_domain": binding.store.boundary.replay_domain,
    }


def continuous_self_run_lease_context() -> dict[str, Any] | None:
    """Return the exact public context an external operator may sign."""
    with _RUN_LEASE_BINDING_LOCK:
        binding = _RUN_LEASE_BINDING
    if binding is None:
        return None
    return json.loads(
        json.dumps(
            _continuous_self_live_context(binding),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


class _LeaseBoundContinuousSelf(ContinuousSelf):
    """ContinuousSelf runner whose live loop spends a signed lease per effect."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._run_lock = threading.RLock()
        self._effect_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._lease_store: RunLeaseStore | None = None
        self._lease_id: str | None = None
        self._lease_finalized = True
        self._requested_stop_reason = "operator_stop"
        self._termination_reason = "never_started"
        self._last_authorization_reason = "not_authorized"
        self._last_finish: dict[str, Any] | None = None
        self._last_cycle: dict[str, Any] | None = None
        self._last_commit_attempt: dict[str, Any] | None = None
        self._pending_finish_reason: str | None = None
        self._bound_input_manifest: dict[str, Any] | None = None
        self._expected_disk_exists = False
        self._expected_disk_sha256 = hashlib.sha256(b"missing").hexdigest()
        self._last_persisted_sha256: str | None = None

    def arm(
        self,
        store: RunLeaseStore,
        lease_id: str,
        *,
        input_manifest: Mapping[str, Any],
    ) -> None:
        bound_input_manifest = json.loads(
            json.dumps(
                dict(input_manifest),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        with self._run_lock:
            if self._running or not self._lease_finalized:
                raise RuntimeError("continuous_self_runner_already_armed")
            self._lease_store = store
            self._lease_id = lease_id
            self._lease_finalized = False
            self._requested_stop_reason = "operator_stop"
            self._termination_reason = "starting"
            self._last_authorization_reason = "run_lease_activated"
            self._last_finish = None
            self._last_cycle = None
            self._last_commit_attempt = None
            self._pending_finish_reason = None
            self._bound_input_manifest = bound_input_manifest
            self._expected_disk_exists = bool(
                input_manifest.get("state_exists")
            )
            self._expected_disk_sha256 = str(
                input_manifest.get("state_sha256") or ""
            )
            self._last_persisted_sha256 = None
            self._stop_event.clear()

    def _authorize(
        self,
        action_class: str,
        *,
        cycles: int = 0,
        scratch_write_bytes: int = 0,
    ) -> Any:
        with self._run_lock:
            store = self._lease_store
            lease_id = self._lease_id
        if store is None or lease_id is None:
            return None
        result = store.authorize(
            lease_id=lease_id,
            runner_id=CONTINUOUS_SELF_RUNNER_ID,
            action_class=action_class,
            costs=_action_costs(
                cycles=cycles,
                scratch_write_bytes=scratch_write_bytes,
            ),
        )
        self._last_authorization_reason = result.reason
        return result

    def _finish_lease(self, reason: str) -> bool:
        with self._run_lock:
            if self._lease_finalized:
                return True
            store = self._lease_store
            lease_id = self._lease_id
            if store is None or lease_id is None:
                return False
            self._pending_finish_reason = reason
            try:
                result = store.finish(
                    lease_id=lease_id,
                    runner_id=CONTINUOUS_SELF_RUNNER_ID,
                    reason=reason,
                )
            except Exception as finish_error:
                self._last_finish = {
                    "finished": False,
                    "reason": "run_lease_finish_exception",
                    "lease_id": lease_id,
                    "runner_id": CONTINUOUS_SELF_RUNNER_ID,
                    "exception_type": type(finish_error).__name__,
                    "durable_finished": False,
                    "reconciled_after_ambiguous_result": False,
                }
                self._lease_finalized = False
                self._termination_reason = (
                    "lease_finish_failed:run_lease_finish_exception"
                )
                return False
            durable_finished = bool(result.finished)
            if not durable_finished:
                try:
                    durable = store.status().get("runners", {}).get(
                        CONTINUOUS_SELF_RUNNER_ID,
                        {},
                    )
                    durable_finished = bool(
                        durable.get("state_ok") is True
                        and durable.get("status") == "finished"
                        and durable.get("lease_id") == lease_id
                        and durable.get("finish_reason") == reason
                    )
                except Exception:
                    durable_finished = False
            self._last_finish = {
                **result.to_dict(),
                "durable_finished": durable_finished,
                "reconciled_after_ambiguous_result": bool(
                    durable_finished and not result.finished
                ),
            }
            self._lease_finalized = durable_finished
            self._termination_reason = (
                reason
                if durable_finished
                else f"lease_finish_failed:{result.reason}"
            )
            if durable_finished:
                self._pending_finish_reason = None
            return durable_finished

    def _retry_pending_finish(self) -> bool:
        """Retry exact durable finish only after the worker is confirmed dead."""

        with self._run_lock:
            thread_alive = bool(
                self._thread is not None and self._thread.is_alive()
            )
            if self._running or thread_alive:
                return False
            if self._lease_finalized:
                return True
            reason = self._pending_finish_reason
        if not reason:
            return False
        finished = self._finish_lease(reason)
        if finished and reason == "runner_start_failed":
            with self._run_lock:
                self._lease_store = None
                self._lease_id = None
                self._bound_input_manifest = None
                self._expected_disk_exists = False
                self._expected_disk_sha256 = hashlib.sha256(
                    b"missing"
                ).hexdigest()
                self._last_persisted_sha256 = None
                self._thread = None
                self._stop_event.clear()
        return finished

    def _finish_failed_start(
        self,
        store: RunLeaseStore,
        lease_id: str,
    ) -> bool:
        """Close an activated lease when no worker was successfully started."""

        with self._run_lock:
            thread_alive = bool(
                self._thread is not None and self._thread.is_alive()
            )
            if thread_alive:
                self._termination_reason = "runner_start_failure_stop_pending"
                self._stop_event.set()
                return False
            if (
                self._lease_id is not None
                and self._lease_id != lease_id
                and not self._lease_finalized
            ):
                self._termination_reason = (
                    "runner_start_failure_lease_identity_mismatch"
                )
                return False
            self._running = False
            self._lease_store = store
            self._lease_id = lease_id
            self._lease_finalized = False
            self._pending_finish_reason = "runner_start_failed"
            self._termination_reason = "runner_start_failed"
        finished = self._finish_lease("runner_start_failed")
        if not finished:
            return False
        with self._run_lock:
            self._lease_store = None
            self._lease_id = None
            self._bound_input_manifest = None
            self._expected_disk_exists = False
            self._expected_disk_sha256 = hashlib.sha256(
                b"missing"
            ).hexdigest()
            self._last_persisted_sha256 = None
            self._thread = None
            self._stop_event.clear()
        return True

    def _input_binding_matches(self) -> bool:
        with self._run_lock:
            expected = (
                dict(self._bound_input_manifest)
                if self._bound_input_manifest is not None
                else None
            )
        if expected is None:
            self._last_authorization_reason = (
                "continuous_self_input_binding_missing"
            )
            return False
        current = _continuous_self_input_manifest()
        if _canonical_sha256(current) != _canonical_sha256(expected):
            self._last_authorization_reason = (
                "continuous_self_input_binding_drift"
            )
            return False
        return True

    def _commit_cycle(
        self,
        *,
        before_state: Any,
        before_tick: int,
    ) -> dict[str, Any] | None:
        state_path = self.state_path
        state_payload = json.dumps(
            asdict(self.state),
            ensure_ascii=False,
        ).encode("utf-8")
        if len(state_payload) > _STATE_WRITE_RESERVATION_BYTES:
            self._last_authorization_reason = (
                "continuous_self_state_exceeds_write_reservation"
            )
            self._last_commit_attempt = {
                "schema_version": _RUN_COMMIT_ATTEMPT_SCHEMA,
                "status": "state_too_large",
                "attempted_state_bytes": len(state_payload),
                "authorized_scratch_write_bytes": 0,
                "physical_write_bytes": 0,
            }
            self.state = before_state
            return None
        state_sha256 = hashlib.sha256(state_payload).hexdigest()
        audit = {
            "schema_version": _RUN_AUDIT_SCHEMA,
            "at": time.time(),
            "lease_id": self._lease_id,
            "profile_id": AUT0_LOCAL_CONTINUOUS_SELF_PROFILE.profile_id,
            "ticks_before": before_tick,
            "ticks_after": int(self.state.ticks),
            "state_path": str(state_path.resolve(strict=False)),
            "state_sha256": state_sha256,
            "state_persisted": True,
            "external_requests": 0,
            "child_tasks": 0,
            "production_writes": 0,
            "code_writes": 0,
        }
        audit_payload = _canonical_bytes(audit) + b"\n"
        if len(audit_payload) > _AUDIT_RECORD_MAX_BYTES:
            self._last_authorization_reason = (
                "continuous_self_audit_record_too_large"
            )
            self._last_commit_attempt = {
                "schema_version": _RUN_COMMIT_ATTEMPT_SCHEMA,
                "status": "audit_too_large",
                "attempted_state_bytes": len(state_payload),
                "attempted_audit_bytes": len(audit_payload),
                "authorized_scratch_write_bytes": 0,
                "physical_write_bytes": 0,
            }
            self.state = before_state
            return None
        with self._effect_lock:
            if self._stop_event.is_set():
                self._last_authorization_reason = (
                    "continuous_self_stop_requested"
                )
                self._last_commit_attempt = {
                    "schema_version": _RUN_COMMIT_ATTEMPT_SCHEMA,
                    "status": "stop_requested",
                    "attempted_state_bytes": len(state_payload),
                    "attempted_audit_bytes": len(audit_payload),
                    "authorized_scratch_write_bytes": 0,
                    "physical_write_bytes": 0,
                }
                self.state = before_state
                return None
            current_exists = state_path.is_file()
            current_sha256 = (
                _file_sha256(state_path)
                if current_exists
                else hashlib.sha256(b"missing").hexdigest()
            )
            if (
                current_exists != self._expected_disk_exists
                or current_sha256 != self._expected_disk_sha256
            ):
                self._last_authorization_reason = (
                    "continuous_self_disk_state_drift"
                )
                self._last_commit_attempt = {
                    "schema_version": _RUN_COMMIT_ATTEMPT_SCHEMA,
                    "status": "disk_state_drift",
                    "attempted_state_bytes": len(state_payload),
                    "attempted_audit_bytes": len(audit_payload),
                    "authorized_scratch_write_bytes": 0,
                    "physical_write_bytes": 0,
                    "actual_state_exists": current_exists,
                    "actual_state_sha256": current_sha256,
                }
                self.state = before_state
                return None
            audit_path = state_path.parent / "aut0_cycle_audit.jsonl"
            state_temp_path = state_path.with_suffix(".tmp")
            try:
                if state_temp_path.exists():
                    raise OSError("stale state temporary file")
                prior_state_payload = (
                    state_path.read_bytes() if current_exists else None
                )
                if (
                    prior_state_payload is not None
                    and hashlib.sha256(prior_state_payload).hexdigest()
                    != current_sha256
                ):
                    raise OSError("state changed during commit preflight")
                audit_existed = audit_path.is_file()
                audit_size = (
                    audit_path.stat().st_size if audit_existed else None
                )
            except OSError:
                self._last_authorization_reason = (
                    "continuous_self_cycle_persistence_preflight_failed"
                )
                self._last_commit_attempt = {
                    "schema_version": _RUN_COMMIT_ATTEMPT_SCHEMA,
                    "status": "persistence_preflight_failed",
                    "attempted_state_bytes": len(state_payload),
                    "attempted_audit_bytes": len(audit_payload),
                    "authorized_scratch_write_bytes": 0,
                    "physical_write_bytes": 0,
                }
                self.state = before_state
                return None
            rollback_state_bytes = len(prior_state_payload or b"")
            state_write_budget = len(state_payload) + rollback_state_bytes
            attempt = {
                "schema_version": _RUN_COMMIT_ATTEMPT_SCHEMA,
                "status": "authorizing",
                "attempted_state_bytes": len(state_payload),
                "attempted_state_sha256": state_sha256,
                "attempted_audit_bytes": len(audit_payload),
                "rollback_state_bytes": rollback_state_bytes,
                "authorized_state_write_bytes": 0,
                "authorized_audit_write_bytes": 0,
                "authorized_scratch_write_bytes": 0,
                "physical_state_write_bytes": 0,
                "physical_audit_write_bytes": 0,
                "physical_rollback_write_bytes": 0,
                "physical_write_bytes": 0,
                "rollback_attempted": False,
                "rollback_succeeded": None,
                "state_changed": False,
                "state_temp_changed": False,
                "audit_changed": False,
            }
            self._last_commit_attempt = dict(attempt)
            state_authorized = self._authorize(
                "self.state_write",
                scratch_write_bytes=state_write_budget,
            )
            if state_authorized is None or not state_authorized.allowed:
                attempt["status"] = "state_authorization_denied"
                self._last_commit_attempt = dict(attempt)
                self.state = before_state
                return None
            attempt["authorized_state_write_bytes"] = state_write_budget
            attempt["authorized_scratch_write_bytes"] = state_write_budget
            audit_authorized = self._authorize(
                "self.audit_append",
                scratch_write_bytes=len(audit_payload),
            )
            if audit_authorized is None or not audit_authorized.allowed:
                attempt["status"] = "audit_authorization_denied"
                self._last_commit_attempt = dict(attempt)
                self.state = before_state
                return None
            attempt["authorized_audit_write_bytes"] = len(audit_payload)
            attempt["authorized_scratch_write_bytes"] = (
                state_write_budget + len(audit_payload)
            )
            stage = "state_write"
            try:
                written = _atomic_replace_bytes(state_path, state_payload)
                attempt["physical_state_write_bytes"] = written
                attempt["physical_write_bytes"] += written
                stage = "state_verify"
                if _file_sha256(state_path) != state_sha256:
                    raise _PhysicalWriteError(
                        "continuous self state digest mismatch"
                    )
                stage = "audit_write"
                written = _append_fsync_bytes(audit_path, audit_payload)
                attempt["physical_audit_write_bytes"] = written
                attempt["physical_write_bytes"] += written
            except OSError as write_error:
                failed_bytes = max(
                    0,
                    int(getattr(write_error, "bytes_written", 0)),
                )
                if stage == "state_write":
                    attempt["physical_state_write_bytes"] += failed_bytes
                elif stage == "audit_write":
                    attempt["physical_audit_write_bytes"] += failed_bytes
                attempt["physical_write_bytes"] += failed_bytes
                attempt["failure_stage"] = stage
                attempt["write_error"] = type(write_error).__name__
                attempt["rollback_attempted"] = True
                rollback_errors: list[str] = []
                rollback_physical = 0
                try:
                    state_matches_before = bool(
                        state_path.is_file() == current_exists
                        and _file_sha256(state_path) == current_sha256
                    )
                    if not state_matches_before:
                        if prior_state_payload is None:
                            state_path.unlink()
                        else:
                            rollback_physical += _atomic_replace_bytes(
                                state_path,
                                prior_state_payload,
                            )
                except OSError as rollback_error:
                    rollback_physical += max(
                        0,
                        int(
                            getattr(
                                rollback_error,
                                "bytes_written",
                                0,
                            )
                        ),
                    )
                    rollback_errors.append(
                        f"state:{type(rollback_error).__name__}"
                    )
                try:
                    current_audit_exists = audit_path.is_file()
                    current_audit_size = (
                        audit_path.stat().st_size
                        if current_audit_exists
                        else None
                    )
                    audit_matches_before = bool(
                        current_audit_exists == audit_existed
                        and (
                            not audit_existed
                            or current_audit_size == audit_size
                        )
                    )
                    if not audit_matches_before:
                        if not audit_existed:
                            audit_path.unlink()
                        elif audit_path.is_file():
                            with audit_path.open("r+b") as handle:
                                handle.truncate(audit_size)
                        else:
                            raise OSError(
                                "audit disappeared during rollback"
                            )
                except OSError as rollback_error:
                    rollback_errors.append(
                        f"audit:{type(rollback_error).__name__}"
                    )
                try:
                    if state_temp_path.exists():
                        state_temp_path.unlink()
                except OSError as rollback_error:
                    rollback_errors.append(
                        f"state_temp:{type(rollback_error).__name__}"
                    )
                attempt["physical_rollback_write_bytes"] = (
                    rollback_physical
                )
                attempt["physical_write_bytes"] += rollback_physical
                actual_state_exists = state_path.is_file()
                actual_state_sha256 = (
                    _file_sha256(state_path)
                    if actual_state_exists
                    else hashlib.sha256(b"missing").hexdigest()
                )
                actual_audit_exists = audit_path.is_file()
                actual_state_temp_exists = state_temp_path.exists()
                try:
                    actual_audit_size = (
                        audit_path.stat().st_size
                        if actual_audit_exists
                        else None
                    )
                except OSError:
                    actual_audit_size = -1
                state_restored = bool(
                    actual_state_exists == current_exists
                    and actual_state_sha256 == current_sha256
                )
                audit_restored = bool(
                    actual_audit_exists == audit_existed
                    and (
                        not audit_existed
                        or actual_audit_size == audit_size
                    )
                )
                state_temp_restored = not actual_state_temp_exists
                rollback_succeeded = bool(
                    state_restored
                    and audit_restored
                    and state_temp_restored
                )
                attempt.update(
                    {
                        "status": (
                            "rolled_back"
                            if rollback_succeeded
                            else "rollback_failed"
                        ),
                        "rollback_succeeded": rollback_succeeded,
                        "rollback_errors": rollback_errors,
                        "actual_state_exists": actual_state_exists,
                        "actual_state_sha256": actual_state_sha256,
                        "actual_state_temp_exists": (
                            actual_state_temp_exists
                        ),
                        "actual_audit_exists": actual_audit_exists,
                        "actual_audit_size": actual_audit_size,
                        "state_changed": not state_restored,
                        "state_temp_changed": not state_temp_restored,
                        "audit_changed": not audit_restored,
                        "state_persisted_without_complete_audit": bool(
                            actual_state_exists
                            and actual_state_sha256 == state_sha256
                        ),
                    }
                )
                self._last_commit_attempt = dict(attempt)
                self._expected_disk_exists = actual_state_exists
                self._expected_disk_sha256 = actual_state_sha256
                if state_restored:
                    self.state = before_state
                    self._last_persisted_sha256 = None
                elif actual_state_sha256 == state_sha256:
                    self._last_persisted_sha256 = state_sha256
                else:
                    self._last_persisted_sha256 = None
                self._last_authorization_reason = (
                    "continuous_self_cycle_persistence_failed_rolled_back"
                    if rollback_succeeded
                    else "continuous_self_cycle_rollback_failed"
                )
                return None
            self._expected_disk_exists = True
            self._expected_disk_sha256 = state_sha256
            self._last_persisted_sha256 = state_sha256
            self._last_cycle = dict(audit)
            attempt.update(
                {
                    "status": "committed",
                    "rollback_succeeded": None,
                    "actual_state_exists": True,
                    "actual_state_sha256": state_sha256,
                    "actual_state_temp_exists": False,
                    "actual_audit_exists": True,
                    "actual_audit_size": (
                        (audit_size or 0) + len(audit_payload)
                    ),
                    "state_changed": True,
                    "state_temp_changed": False,
                    "audit_changed": True,
                    "state_persisted_without_complete_audit": False,
                }
            )
            self._last_commit_attempt = dict(attempt)
            return audit

    def _run(self) -> None:
        finish_reason = "operator_stop"
        try:
            if not self._input_binding_matches():
                finish_reason = "input_binding_drift"
                return
            while self._running and not self._stop_event.is_set():
                observed = self._authorize(
                    "self.observe_local",
                    cycles=1,
                )
                if observed is None or not observed.allowed:
                    finish_reason = "authority_denied"
                    break
                if self._stop_event.is_set():
                    finish_reason = self._requested_stop_reason
                    break
                before_state = None
                try:
                    with self._lock:
                        before_state = copy.deepcopy(self.state)
                        before_tick = int(self.state.ticks)
                        self.step(
                            profile=_AUT0_COMPUTE_PROFILE,
                            _lock_already_held=True,
                        )
                        audit = self._commit_cycle(
                            before_state=before_state,
                            before_tick=before_tick,
                        )
                except BaseException as cycle_error:
                    if before_state is not None:
                        with self._lock:
                            self.state = before_state
                    self._last_authorization_reason = (
                        "continuous_self_runner_exception:"
                        f"{type(cycle_error).__name__}"
                    )
                    finish_reason = "runner_error"
                    break
                if audit is None:
                    if self._stop_event.is_set():
                        finish_reason = self._requested_stop_reason
                    elif self._last_authorization_reason == (
                        "continuous_self_cycle_rollback_failed"
                    ):
                        finish_reason = "persistence_rollback_failed"
                    elif self._last_authorization_reason.startswith(
                        "continuous_self_cycle_persistence"
                    ):
                        finish_reason = "persistence_failed"
                    else:
                        finish_reason = "authority_denied"
                    break
                from packages.continuous_self.pressure_clock import (
                    next_wake_delay,
                )

                with self._lock:
                    energy = self.state.energy
                    delay = next_wake_delay(
                        self.state,
                        energy,
                        base=self.base_interval,
                    )
                if self._stop_event.wait(delay):
                    finish_reason = self._requested_stop_reason
                    break
            else:
                finish_reason = self._requested_stop_reason
        except BaseException as run_error:
            self._last_authorization_reason = (
                "continuous_self_runner_exception:"
                f"{type(run_error).__name__}"
            )
            finish_reason = "runner_error"
        finally:
            try:
                self._finish_lease(finish_reason)
            finally:
                with self._run_lock:
                    self._running = False

    def start(self) -> bool:
        with self._run_lock:
            if self._lease_store is None or self._lease_finalized:
                self._termination_reason = "signed_run_lease_required"
                return False
            self._stop_event.clear()
            return super().start()

    def stop(self, *, reason: str = "operator_stop") -> bool:
        with self._effect_lock:
            with self._run_lock:
                self._requested_stop_reason = reason
                if self._running:
                    self._termination_reason = "stop_pending"
                self._stop_event.set()
        thread = self._thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=_STOP_JOIN_TIMEOUT_SEC)
        thread_stopped = bool(thread is None or not thread.is_alive())
        if thread_stopped:
            self._retry_pending_finish()
        return thread_stopped

    def lease_telemetry(self) -> dict[str, Any]:
        with self._run_lock:
            return {
                "lease_id": self._lease_id,
                "lease_finalized": self._lease_finalized,
                "termination_reason": self._termination_reason,
                "pending_finish_reason": self._pending_finish_reason,
                "last_authorization_reason": (
                    self._last_authorization_reason
                ),
                "last_finish": (
                    dict(self._last_finish)
                    if self._last_finish is not None
                    else None
                ),
                "last_cycle": (
                    dict(self._last_cycle)
                    if self._last_cycle is not None
                    else None
                ),
                "last_commit_attempt": (
                    dict(self._last_commit_attempt)
                    if self._last_commit_attempt is not None
                    else None
                ),
                "thread_alive": bool(
                    self._thread is not None
                    and self._thread.is_alive()
                ),
            }


_SELF = _LeaseBoundContinuousSelf(
    _STATE_PATH, _observe, base_interval=2.0, observe_fn=_self_probe,
    identity_fn=_identity_answer, research_fn=_research, initiative_every=15,
    research_every=30, shadow_ledger_path=_CONTINUOUS_SELF_SHADOW_LEDGER,
)


def _lifecycle_status(
    *,
    read_lease_store: bool = True,
) -> dict[str, Any]:
    """Report actual loop, lease, budget, and execution-profile state."""
    running = bool(_SELF.running)
    with _RUN_LEASE_BINDING_LOCK:
        binding = _RUN_LEASE_BINDING
    telemetry = _SELF.lease_telemetry()
    lease_store_status: dict[str, Any] | None = None
    if binding is not None and read_lease_store:
        lease_store_status = binding.store.status()
    stopping = bool(
        running
        and telemetry["termination_reason"] == "stop_pending"
    )
    termination_pending = bool(
        not running
        and telemetry["lease_id"] is not None
        and not telemetry["lease_finalized"]
    )
    reason = (
        "stop_pending"
        if stopping
        else (
            "signed_run_lease_active"
            if running
            else (
                telemetry["termination_reason"]
                if telemetry["termination_reason"]
                not in {"never_started", "starting"}
                else (
                    "signed_run_lease_required"
                    if binding is not None
                    else "run_lease_store_not_provisioned"
                )
            )
        )
    )
    lifecycle_state = (
        "stopping"
        if stopping
        else (
            "running"
            if running
            else (
                "termination_pending"
                if termination_pending
                else "dormant"
            )
        )
    )
    runner_status = None
    if lease_store_status is not None:
        runner_status = lease_store_status.get("runners", {}).get(
            CONTINUOUS_SELF_RUNNER_ID
        )
    return {
        "schema": _LIFECYCLE_SCHEMA,
        "state": lifecycle_state,
        "running": running,
        "default_dormant": True,
        "router_start_authorized": binding is not None,
        "reason": reason,
        "required_boundary": "externally_signed_bounded_run_lease",
        "execution_profile": {
            "profile_id": AUT0_LOCAL_CONTINUOUS_SELF_PROFILE.profile_id,
            "action_classes": list(_RUN_ACTION_CLASSES),
            "network": False,
            "production": False,
            "code": False,
            "training": False,
            "child_tasks": False,
            "functional_consciousness_only": True,
        },
        "lease": telemetry,
        "lease_store_runner": runner_status,
        "capability_claim": False,
        "e4_claim": False,
        "e5_claim": False,
    }


def _start_refusal(reason: str | None = None) -> dict[str, Any]:
    lifecycle = _lifecycle_status()
    if reason:
        lifecycle["reason"] = reason
    return {
        "ok": False,
        "started": False,
        **lifecycle,
    }


def _ensure_alive() -> dict[str, Any]:
    """Legacy callers cannot mint or reuse run authority."""
    return _start_refusal("signed_run_lease_required")


def _public_snapshot() -> dict[str, Any]:
    """Return persisted state while making the actual lifecycle unambiguous."""
    snapshot = dict(_SELF.snapshot())
    lifecycle = _lifecycle_status()
    snapshot["continuous"] = lifecycle["running"]
    snapshot["offline"] = not lifecycle["running"]
    snapshot["lifecycle"] = lifecycle
    return snapshot


@router.get("/lifecycle")
def selfhood_lifecycle() -> dict[str, Any]:
    return _lifecycle_status()


@router.get("/lease-context")
def selfhood_lease_context() -> dict[str, Any]:
    """Read-only exact context preview for the external lease signer."""
    context = continuous_self_run_lease_context()
    with _RUN_LEASE_BINDING_LOCK:
        binding = _RUN_LEASE_BINDING
    available = context is not None and binding is not None
    return {
        "available": available,
        "configured": available,
        "reason": (
            "unsigned_live_context_reconstructed"
            if available
            else "run_lease_store_not_provisioned"
        ),
        "purpose": RUN_LEASE_PURPOSE,
        "live_context": context,
        "live_context_sha256": (
            _canonical_sha256(context)
            if context is not None
            else None
        ),
        "signer_present_in_api": False,
        "private_key_required_outside_api": True,
        "expected_key_id": (
            binding.store.boundary.expected_key_id
            if binding is not None
            else None
        ),
        # Compatibility for existing local callers.
        "context": context,
    }


@router.post("/start")
def selfhood_start(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    with _CONTROL_LOCK:
        return _selfhood_start_locked(payload)


def _selfhood_start_locked(
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Activate one exact signed lease, then start the local AUT-0 profile."""
    with _RUN_LEASE_BINDING_LOCK:
        binding = _RUN_LEASE_BINDING
    if binding is None:
        return _start_refusal("run_lease_store_not_provisioned")
    if _SELF.running:
        return _start_refusal("continuous_self_already_running")
    if not _SELF.lease_telemetry()["lease_finalized"]:
        return _start_refusal(
            "continuous_self_lease_termination_pending"
        )
    if type(payload) is not dict or type(payload.get("run_lease")) is not dict:
        return _start_refusal("signed_run_lease_required")
    input_manifest = _continuous_self_input_manifest()
    current_state_bytes = int(input_manifest["state_memory_bytes"])
    if current_state_bytes > _STATE_WRITE_RESERVATION_BYTES // 2:
        return _start_refusal(
            "continuous_self_state_exceeds_write_reservation"
        )
    live_context = _continuous_self_live_context(
        binding,
        input_manifest=input_manifest,
    )
    activated = binding.store.activate(
        document=payload["run_lease"],
        live_context=live_context,
    )
    if not activated.allowed or activated.lease_id is None:
        return _start_refusal(activated.reason)
    try:
        _SELF.arm(
            binding.store,
            activated.lease_id,
            input_manifest=input_manifest,
        )
        started = _SELF.start()
    except Exception:
        _SELF._finish_failed_start(
            binding.store,
            activated.lease_id,
        )
        return _start_refusal("continuous_self_runner_start_failed")
    if not started:
        _SELF._finish_failed_start(
            binding.store,
            activated.lease_id,
        )
        return _start_refusal("continuous_self_runner_start_failed")
    return {
        "ok": True,
        "started": True,
        # Avoid contending with the newly started worker for the Windows
        # process-wide replay-ledger file lock. GET /lifecycle remains the
        # durable status surface after the worker has entered its loop.
        **_lifecycle_status(read_lease_store=False),
    }


@router.post("/stop")
def selfhood_stop() -> dict[str, Any]:
    with _CONTROL_LOCK:
        return _selfhood_stop_locked()


def _selfhood_stop_locked() -> dict[str, Any]:
    """Request stop; report success only after the worker has really exited."""
    was_running = _SELF.running
    joined = _SELF.stop(reason="operator_stop")
    return {
        "ok": True,
        "stopped": bool(was_running and joined),
        "stop_pending": bool(was_running and not joined),
        **_lifecycle_status(),
    }


@router.get("/live")
def selfhood_live() -> dict[str, Any]:
    return _public_snapshot()


@router.post("/arena-event")
def selfhood_arena_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Fail closed until arena improvement is bound to external evaluation evidence.

    Caller-supplied ``fitness`` and ``prev_fitness`` are not evidence.  Accepting
    them as dopamine would let any local HTTP caller manufacture reward and steer
    the operational self.  The existing external evaluation schema additionally
    requires an operator-pinned signature and independently reconstructed live
    context; the arena does not yet emit that complete bundle.  Therefore this
    endpoint intentionally has no success path and, critically, does not call
    ``_ensure_alive`` or mutate hormones/narrative state.
    """
    _ = payload
    return {
        "ok": False,
        "felt": False,
        "reward_signal_accepted": False,
        "reason": "externally_signed_live_bound_evaluation_receipt_required",
        "required_boundary": "packages.autonomy_envelope.evaluation_trust",
    }


@router.get("/narrative")
def selfhood_narrative(limit: int = 8) -> dict[str, Any]:
    """The autobiographical self — the Identity Genesis Ledger read as a story: the
    knowledge that actually SHOOK the self (crossed the Self_Relevance gate) and how its
    worldview expanded. 'What I adopted as my story', not 'what I know'."""
    try:
        from packages.continuous_self.self_relevance import narrative
        return narrative(limit=limit)
    except Exception as exc:  # pragma: no cover
        return {"entries": [], "count": 0, "error": str(exc)}


_DEEPEN_STORE: Any = None


def _deepen_store() -> Any:
    global _DEEPEN_STORE
    if _DEEPEN_STORE is None:
        from packages.graph_scale.graph_paths import SHIPPED_GRAPH_ROOT
        from packages.graph_scale.triple_store import TripleStore

        _DEEPEN_STORE = TripleStore(SHIPPED_GRAPH_ROOT)
    return _DEEPEN_STORE


@router.post("/deepen")
def selfhood_deepen(payload: dict[str, Any]) -> dict[str, Any]:
    """Self-awareness -> answer-depth fusion, demonstrated end-to-end on LIVE
    self-state: if the query is about what the self is currently pondering, weave
    MORE of that subject's GROUNDED relations into the answer. Additive only —
    the extra clauses are literal graph facts, so hallucination-0 is preserved.
    `set_self_question` lets you steer the self's focus to see engaged-vs-not."""
    query = str(payload.get("query") or "").strip()
    if not query:
        return {"error": "query_required"}
    st = _SELF.state
    state = {
        "self_question": getattr(st, "self_question", "") or "",
        "self_question_open": bool(getattr(st, "self_question_open", False)),
        "last_inquiry_topic": getattr(st, "_last_inquiry_topic", "") or "",
        "curiosity": float(getattr(st, "curiosity", 0.5) or 0.5),
        "recent_insights": [],
    }
    if payload.get("set_self_question"):  # demo: steer the self's focus
        state["self_question"] = str(payload["set_self_question"])
        state["self_question_open"] = True

    from packages.continuous_self.inquiry_fusion import (
        depth_bias, engagement_note, extra_relation_budget,
    )
    from packages.graph_scale.query_frame import parse

    subject = parse(query).subject or query
    bias = depth_bias(subject, state)

    from packages.base_brain.zero_user_answer import answer_with_base_brain

    base = answer_with_base_brain(query)
    base_answer = str(base.get("answer") or "")
    deepened, added = base_answer, []
    if bias >= 0.5:
        try:
            budget = extra_relation_budget(bias) - 3  # only the EXTRA relations
            facts = _deepen_store().facts_about(subject, limit=budget + 4)
            for (s, p, o) in facts:
                if o and str(o) not in base_answer and str(o) not in query:
                    added.append(f"{s}의 {p}: {o}")
                if len(added) >= max(1, budget):
                    break
        except Exception:
            added = []
        if added:
            deepened = f"{base_answer.rstrip()} — {'; '.join(added)}. ({engagement_note(subject, bias)})"

    return {
        "query": query, "subject": subject,
        "self_question": state["self_question"],
        "self_question_open": state["self_question_open"],
        "depth_bias": bias, "self_engaged": bias >= 0.5,
        "base_answer": base_answer,
        "deepened_answer": deepened,
        "added_grounded_relations": added,
        "note": engagement_note(subject, bias),
        "hallucination_safe": True,
    }


# ---- gated self-modification: operator approval API -------------------------------
# The mind proposes; ONLY a human decides here. Nothing auto-applies anywhere.
@router.get("/self-modification/proposals")
def selfmod_proposals() -> dict[str, Any]:
    from packages.continuous_self.self_modification import list_proposals

    rows = list_proposals(_SELF.selfmod_ledger)
    return {"proposals": rows[-20:], "pending": [r for r in rows if r["status"] == "pending"],
            "current_params": dict(_SELF.params)}


@router.post("/self-modification/decide")
def selfmod_decide(payload: dict[str, Any]) -> dict[str, Any]:
    """Operator decision. Body: {proposal_id, approve: bool, confirm: "SELF_MOD",
    note?}. The confirm phrase is a deliberate friction — a human must mean it."""
    from packages.continuous_self.self_modification import apply_approved, decide

    if str(payload.get("confirm") or "") != "SELF_MOD":
        return {"ok": False, "reason": "confirm phrase 'SELF_MOD' required — operator only"}
    hit = decide(_SELF.selfmod_ledger, str(payload.get("proposal_id") or ""),
                 bool(payload.get("approve")), str(payload.get("note") or ""))
    if hit is None:
        return {"ok": False, "reason": "proposal not found or not pending"}
    applied = apply_approved(_SELF.selfmod_ledger, _SELF.params) if hit["status"] == "approved" else []
    # clear the bid once decided
    if _SELF.state.attention_bid.get("proposal_id") == hit["id"]:
        _SELF.state.attention_bid = {}
    return {"ok": True, "decision": hit["status"], "applied": [a["id"] for a in applied],
            "current_params": dict(_SELF.params)}


_CODE_LEDGER = _STATE_PATH.parent / "code_selfmod_ledger.jsonl"
_STAGED_DIR = _STATE_PATH.parent / "staged_code_patches"


@router.get("/code-modification/proposals")
def code_mod_proposals() -> dict[str, Any]:
    """Code-patch proposals the mind raised about its OWN source. Read-only view; the
    patches are additive-only and whitelisted, and NONE is applied to the live tree."""
    from packages.continuous_self.code_self_modification import _load as _load_cm

    rows = _load_cm(_CODE_LEDGER)
    return {"proposals": rows[-20:], "pending": [r for r in rows if r["status"] == "pending"],
            "note": "코드 패치는 추가(additive)만, 화이트리스트 파일만, 승인해도 라이브 코드가 아니라 스테이징에만 기록됩니다."}


@router.post("/code-modification/decide")
def code_mod_decide(payload: dict[str, Any]) -> dict[str, Any]:
    """Operator decision on a CODE patch. Body: {proposal_id, approve, confirm:
    "SELF_MOD_CODE", note?}. A DISTINCT, stronger confirm phrase than parameter changes.
    On approval the patch is STAGED to a directory only — the live source is never touched
    by the machine; a human reviews the staged .patch and applies it by hand."""
    from packages.continuous_self.code_self_modification import stage_approved
    from packages.continuous_self.self_modification import decide

    if str(payload.get("confirm") or "") != "SELF_MOD_CODE":
        return {"ok": False, "reason": "confirm phrase 'SELF_MOD_CODE' required — operator only, code changes"}
    hit = decide(_CODE_LEDGER, str(payload.get("proposal_id") or ""),
                 bool(payload.get("approve")), str(payload.get("note") or ""))
    if hit is None:
        return {"ok": False, "reason": "proposal not found or not pending"}
    staged = stage_approved(_CODE_LEDGER, _STAGED_DIR) if hit["status"] == "approved" else []
    return {"ok": True, "decision": hit["status"],
            "staged": [{"id": s["id"], "staged_path": s.get("staged_path")} for s in staged],
            "live_tree_touched": False,
            "note": "승인된 패치는 스테이징 폴더에 기록만 되었습니다. 라이브 적용은 사람이 직접 검토 후 git apply로 합니다."}


@router.get("/consciousness")
def selfhood_consciousness() -> dict[str, Any]:
    """The honest consciousness-CORRELATES report (AST / HOT / IIT Φ-proxy / GWT) for the
    current self-state — functional measures only, never a claim of phenomenal experience."""
    from packages.continuous_self.consciousness_correlates import consciousness_report

    report = dict(consciousness_report(_SELF.state))
    report["lifecycle"] = _lifecycle_status()
    return report


@router.get("/stream")
async def selfhood_stream() -> StreamingResponse:
    async def _events() -> AsyncIterator[str]:
        last = ""
        last_sent = 0.0
        while True:
            snap = _public_snapshot()
            body = json.dumps(snap, ensure_ascii=False)
            now = time.time()
            # the clock-ish fields change every step; hash the felt content instead so
            # a quiet mind streams quietly.
            felt = json.dumps(
                {"vitals": snap["vitals"], "mode": snap["mode"], "focus": snap["focus"],
                 "current_thought": snap["current_thought"]},
                ensure_ascii=False, sort_keys=True,
            )
            if felt != last:
                last = felt
                last_sent = now
                yield f"data: {body}\n\n"
            elif now - last_sent >= 20.0:
                last_sent = now
                yield ": heartbeat\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(
        _events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
