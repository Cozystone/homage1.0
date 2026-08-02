from __future__ import annotations

import hashlib
import json
import platform
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.services.cloud_broker_client import CloudBrokerClient, CloudBrokerConfig, CloudBrokerError, peer_id_hash_for_node


ContributorState = Literal[
    "local_only",
    "contributor_disabled",
    "contributor_preview",
    "contributor_active",
    "contributor_registered",
    "task_polling",
    "task_running",
    "task_submitted",
    "verification_pending",
    "credit_confirmed",
    "paused",
    "disabled",
    "error",
]

TaskStatus = Literal["completed", "rejected", "failed", "timed_out"]
CreditStatus = Literal["pending", "confirmed", "rejected", "expired"]


ALLOWED_TASK_TYPES = {
    "public_fragment_validation",
    "source_noise_check",
    "duplicate_relation_check",
    "graph_delta_compression",
    "public_alias_review",
    "freshness_check",
    "public_source_fetch",
}

SUSPICIOUS_PAYLOAD_MARKERS = (
    "__import__",
    "subprocess",
    "os.",
    "eval(",
    "exec(",
    "open(",
    "file://",
    "../",
    "..\\",
    "cmd.exe",
    "powershell",
    "bash -c",
    "python -c",
    "<script",
    "/etc/",
    "C:\\",
)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_node_id() -> str:
    label = f"{platform.node() or 'atanor-local'}:atanor-0.1.2"
    return f"atanor-node-{uuid.uuid5(uuid.NAMESPACE_DNS, label).hex[:16]}"


def _json_size(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _contains_suspicious_content(payload: Any) -> bool:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()
    return any(marker.lower() in encoded for marker in SUSPICIOUS_PAYLOAD_MARKERS)


def _public_fragment_result(
    *,
    text: str,
    source_url: str,
    topic: str,
    input_edges: list[Any] | None = None,
) -> dict[str, Any]:
    cleaned = " ".join(str(text).split())[:900]
    topic = topic.strip() or "public_fragment"
    words = []
    seen: set[str] = set()
    for token in json.dumps({"topic": topic, "text": cleaned}, ensure_ascii=False).replace('"', " ").split():
        normalized = token.strip(".,:;()[]{}").lower()
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        words.append(normalized)
        if len(words) >= 12:
            break
    if not words:
        words = ["public", "fragment"]
    nodes = [
        {
            "node_hash": hashlib.sha256(f"public:{word}".encode("utf-8")).hexdigest(),
            "label": word[:64],
            "type": "public_concept_hash",
        }
        for word in words
    ]
    edges = []
    for left, right in zip(nodes, nodes[1:]):
        edges.append(
            {
                "source_hash": left["node_hash"],
                "target_hash": right["node_hash"],
                "predicate": "co_occurs_public",
                "weight": 0.35,
            }
        )
    for item in input_edges or []:
        if isinstance(item, dict):
            source = str(item.get("source") or item.get("source_hash") or "")
            target = str(item.get("target") or item.get("target_hash") or "")
            if source and target:
                edges.append(
                    {
                        "source": source[:120],
                        "target": target[:120],
                        "predicate": str(item.get("predicate") or "public_relation")[:80],
                        "weight": 0.5,
                    }
                )
    return {
        "shard_id": hashlib.sha256(topic.lower().encode("utf-8")).hexdigest()[:16],
        "topic": topic[:160],
        "source_url": source_url,
        "source_hash": hashlib.sha256(f"{source_url}\n{topic}".encode("utf-8")).hexdigest(),
        "nodes": nodes,
        "edges": edges[:48],
        "evidence": [cleaned[:360]] if cleaned else [],
        "raw_payload_exported": False,
        "privacy_classification": "public_only",
        "verification_state": "single_peer_pending",
        "requires_cross_check": True,
    }


@dataclass
class ContributorCapabilities:
    cpu_available: bool = True
    gpu_available: bool = False
    ram_limit_gb: float = 2.0
    disk_cache_limit_gb: float = 1.0
    network_mode: str = "broker_metadata_only"
    supports_public_fragment_validation: bool = True
    supports_source_noise_check: bool = True
    supports_graph_delta_compression: bool = True
    supports_duplicate_relation_check: bool = True
    supports_public_alias_review: bool = True


@dataclass
class ResourceLimits:
    cpu_limit_percent: int = 20
    gpu_enabled: bool = False
    gpu_limit_percent: int = 0
    ram_limit_gb: float = 2.0
    network_limit: str = "broker_only"
    battery_pause: bool = True
    thermal_pause: bool = True
    night_only: bool = False
    private_data_sharing_allowed: bool = False


@dataclass
class ContributorNode:
    node_id: str = field(default_factory=_stable_node_id)
    device_label: str = "ATANOR Local Contributor"
    app_version: str = "0.1.2"
    contributor_state: ContributorState = "local_only"
    registered_at: str | None = None
    last_seen_at: str | None = None
    capabilities: ContributorCapabilities = field(default_factory=ContributorCapabilities)
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    privacy_policy: dict[str, Any] = field(default_factory=lambda: {
        "private_local_brain_shared": False,
        "payload_vault_shared": False,
        "chat_logs_shared": False,
        "local_file_paths_shared": False,
        "public_tasks_only": True,
    })
    trust_score: float = 0.5
    total_tasks_completed: int = 0
    total_tasks_rejected: int = 0
    total_credits_confirmed: float = 0.0
    total_credits_pending: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PublicTask:
    task_id: str
    task_type: str
    schema_version: str
    payload: dict[str, Any]
    max_runtime_ms: int
    max_memory_mb: int
    max_output_bytes: int
    created_at: str
    expires_at: str
    trust_requirement: float
    credit_estimate: float
    privacy_classification: str = "public_only"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskResult:
    task_id: str
    node_id: str
    status: TaskStatus
    result_payload: dict[str, Any]
    runtime_ms: int
    memory_peak_mb: int
    checksum: str
    submitted_at: str
    error_message: str | None = None
    local_trace_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContributionCredit:
    credit_id: str
    node_id: str
    task_id: str
    amount_estimated: float
    amount_confirmed: float
    status: CreditStatus
    reason: str
    created_at: str
    confirmed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["disclaimer"] = (
            "Contribution Credit is an internal contribution accounting score in this build. "
            "It is not cryptocurrency or a financial asset unless a separate production settlement layer is enabled."
        )
        return data


class ContributionValidationError(ValueError):
    pass


def validate_contribution_task(task: PublicTask | dict[str, Any]) -> PublicTask:
    if isinstance(task, dict):
        allowed = {
            "task_id",
            "task_type",
            "schema_version",
            "payload",
            "max_runtime_ms",
            "max_memory_mb",
            "max_output_bytes",
            "created_at",
            "expires_at",
            "trust_requirement",
            "credit_estimate",
            "privacy_classification",
        }
        task = PublicTask(**{key: value for key, value in task.items() if key in allowed})
    if task.schema_version != "atanor.contribution-task.v1":
        raise ContributionValidationError("invalid schema_version")
    if task.task_type not in ALLOWED_TASK_TYPES:
        raise ContributionValidationError("unknown task_type")
    if task.privacy_classification != "public_only":
        raise ContributionValidationError("privacy_classification must be public_only")
    if task.max_runtime_ms <= 0 or task.max_runtime_ms > 30_000:
        raise ContributionValidationError("max_runtime_ms out of bounds")
    if task.max_memory_mb <= 0 or task.max_memory_mb > 1024:
        raise ContributionValidationError("max_memory_mb out of bounds")
    if task.max_output_bytes <= 0 or task.max_output_bytes > 64_000:
        raise ContributionValidationError("max_output_bytes out of bounds")
    if _json_size(task.payload) > 64_000:
        raise ContributionValidationError("payload too large")
    if _contains_suspicious_content(task.payload):
        raise ContributionValidationError("payload contains executable or local-file markers")
    if task.payload.get("requires_local_file_access") or task.payload.get("requires_private_graph_access"):
        raise ContributionValidationError("task requests private local access")
    if task.payload.get("requires_network_access"):
        raise ContributionValidationError("task requests non-broker network access")
    return task


class LocalBroker:
    broker_state = "local_broker_mode"

    def __init__(self) -> None:
        self._tasks = [
            PublicTask(
                task_id="local-source-noise-001",
                task_type="source_noise_check",
                schema_version="atanor.contribution-task.v1",
                payload={
                    "query_concept": "GraphRAG",
                    "source_title": "Graph retrieval augmented generation notes",
                    "source_snippet": "GraphRAG expands graph paths before evidence synthesis.",
                    "expected_concept_aliases": ["GraphRAG", "graph retrieval", "knowledge graph retrieval"],
                },
                max_runtime_ms=1500,
                max_memory_mb=64,
                max_output_bytes=4096,
                created_at=_now(),
                expires_at=_now(),
                trust_requirement=0.0,
                credit_estimate=1.2,
            ),
            PublicTask(
                task_id="local-duplicate-relation-001",
                task_type="duplicate_relation_check",
                schema_version="atanor.contribution-task.v1",
                payload={
                    "relation_a": {"source": "GraphRAG", "predicate": "uses", "target": "Evidence"},
                    "relation_b": {"source": "GraphRAG", "predicate": "uses", "target": "Evidence Bundle"},
                },
                max_runtime_ms=1500,
                max_memory_mb=64,
                max_output_bytes=4096,
                created_at=_now(),
                expires_at=_now(),
                trust_requirement=0.0,
                credit_estimate=1.0,
            ),
        ]
        self._cursor = 0

    def poll_public_task(self) -> PublicTask | None:
        task = self._tasks[self._cursor % len(self._tasks)]
        self._cursor += 1
        return task

    def verify_result(self, result: TaskResult) -> bool:
        return result.status == "completed" and not _contains_suspicious_content(result.result_payload)


class RemoteCloudBroker:
    """Minimal AWS-backed broker adapter.

    The adapter only sends public node/task metadata to the remote broker. It
    never uploads local Payload Vault text, private documents, chat logs, or
    local file paths.
    """

    def __init__(self, client: CloudBrokerClient | None = None) -> None:
        self.client = client or CloudBrokerClient()
        self.broker_state = "remote_error"
        self.last_error: str | None = None
        self.last_status: dict[str, Any] | None = None

    def _mark_connected(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.broker_state = "remote_connected"
        self.last_error = None
        self.last_status = payload
        return payload

    def _mark_error(self, exc: Exception) -> None:
        self.broker_state = "remote_error"
        self.last_error = str(exc)

    def check_status(self) -> dict[str, Any]:
        try:
            return self._mark_connected(self.client.status())
        except Exception as exc:
            self._mark_error(exc)
            return {"status": "remote_error", "error": str(exc)}

    def register_node(self, node: ContributorNode) -> dict[str, Any]:
        try:
            return self._mark_connected(self.client.register_node(self._public_node_profile(node)))
        except Exception as exc:
            self._mark_error(exc)
            raise

    def heartbeat(self, node: ContributorNode) -> dict[str, Any]:
        try:
            return self._mark_connected(
                self.client.heartbeat(
                    node.node_id,
                    {
                        "contributor_state": node.contributor_state,
                        "app_version": node.app_version,
                        "capabilities": asdict(node.capabilities),
                        "resource_limits": asdict(node.resource_limits),
                    },
                )
            )
        except Exception as exc:
            self._mark_error(exc)
            raise

    @staticmethod
    def _public_node_profile(node: ContributorNode) -> dict[str, Any]:
        """Return broker-safe node metadata without local/private marker keys."""

        return {
            "node_id": node.node_id,
            "device_label": node.device_label,
            "app_version": node.app_version,
            "contributor_state": node.contributor_state,
            "capabilities": asdict(node.capabilities),
            "resource_limits": {
                "cpu_limit_percent": node.resource_limits.cpu_limit_percent,
                "gpu_enabled": node.resource_limits.gpu_enabled,
                "ram_limit_gb": node.resource_limits.ram_limit_gb,
                "network_limit": node.resource_limits.network_limit,
                "battery_pause": node.resource_limits.battery_pause,
                "thermal_pause": node.resource_limits.thermal_pause,
                "night_only": node.resource_limits.night_only,
                "sharing_private_data": False,
            },
            "privacy_boundary": {
                "raw_payload_exported": False,
                "chat_exported": False,
                "public_tasks_only": True,
            },
            "trust_score": node.trust_score,
        }

    def poll_public_task(self, node: ContributorNode | None = None) -> PublicTask | None:
        node_id = node.node_id if node else ""
        capabilities = asdict(node.capabilities) if node else {}
        try:
            payload = self._mark_connected(self.client.poll_tasks(node_id, capabilities))
        except Exception as exc:
            self._mark_error(exc)
            raise
        if payload.get("state") == "no_task" or payload.get("task") is None:
            return None
        task_payload = payload.get("task")
        if not isinstance(task_payload, dict):
            raise ContributionValidationError("remote broker returned invalid task payload")
        return validate_contribution_task(task_payload)

    def submit_result(self, result: TaskResult) -> dict[str, Any]:
        try:
            payload = result.to_dict()
            payload["peer_id_hash"] = peer_id_hash_for_node(result.node_id)
            return self._mark_connected(self.client.submit_task(payload))
        except Exception as exc:
            self._mark_error(exc)
            raise

    def verify_result(self, result: TaskResult) -> bool:
        return result.status == "completed" and not _contains_suspicious_content(result.result_payload)

    def credits(self, node_id: str) -> dict[str, Any]:
        try:
            return self._mark_connected(self.client.credits(node_id))
        except Exception as exc:
            self._mark_error(exc)
            return {"status": "remote_error", "error": str(exc), "credits": []}


def build_default_broker() -> LocalBroker | RemoteCloudBroker:
    config = CloudBrokerConfig.from_env()
    if config.cloud_mode == "remote" and config.endpoint:
        return RemoteCloudBroker(CloudBrokerClient(config))
    return LocalBroker()


class ContributionService:
    def __init__(self, broker: LocalBroker | RemoteCloudBroker | None = None) -> None:
        self.broker = broker or build_default_broker()
        self.node = ContributorNode()
        self.current_task: PublicTask | None = None
        self.recent_tasks: list[dict[str, Any]] = []
        self.credits: list[ContributionCredit] = []
        self.last_error: str | None = None
        self.last_remote_submission: dict[str, Any] | None = None

    def get_status(self) -> dict[str, Any]:
        remote_status = None
        if isinstance(self.broker, RemoteCloudBroker):
            remote_status = self.broker.check_status()
            if self.broker.last_error:
                self.last_error = self.broker.last_error
        return {
            "schema": "atanor.contributor-node.v1",
            "contributor_state": self.node.contributor_state,
            "broker_state": self.broker.broker_state if self.node.contributor_state != "disabled" else "disabled",
            "cloud_mode": "remote" if isinstance(self.broker, RemoteCloudBroker) else "local_broker",
            "remote_broker": remote_status,
            "preview_disclaimer": (
                "Contributor Node is connected to the remote Cloud Brain Broker."
                if isinstance(self.broker, RemoteCloudBroker) and self.broker.broker_state == "remote_connected"
                else "Contributor Node is production-oriented. This localhost runtime is using Local Broker Mode "
                "until the remote Cloud Brain broker endpoint is configured."
            ),
            "current_task": self.current_task.to_dict() if self.current_task else None,
            "pending_credits": round(self.node.total_credits_pending, 3),
            "confirmed_credits": round(self.node.total_credits_confirmed, 3),
            "total_tasks_completed": self.node.total_tasks_completed,
            "total_tasks_rejected": self.node.total_tasks_rejected,
            "recent_tasks": self.recent_tasks,
            "resource_limits": asdict(self.node.resource_limits),
            "privacy_guarantees": self.node.privacy_policy,
            "last_error": self.last_error,
            "last_remote_submission": self.last_remote_submission,
            "node": self.node.to_dict(),
        }

    def update_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        cpu = settings.get("cpu_limit_percent")
        if isinstance(cpu, int):
            self.node.resource_limits.cpu_limit_percent = max(5, min(80, cpu))
        self.node.resource_limits.gpu_enabled = bool(settings.get("gpu_enabled", self.node.resource_limits.gpu_enabled))
        gpu_limit = settings.get("gpu_limit_percent")
        if isinstance(gpu_limit, int):
            self.node.resource_limits.gpu_limit_percent = max(0, min(95, gpu_limit))
            self.node.resource_limits.gpu_enabled = self.node.resource_limits.gpu_limit_percent > 0
        ram = settings.get("ram_limit_gb")
        if isinstance(ram, (int, float)):
            self.node.resource_limits.ram_limit_gb = max(0.25, min(16.0, float(ram)))
        self.node.resource_limits.battery_pause = bool(settings.get("battery_pause", self.node.resource_limits.battery_pause))
        self.node.resource_limits.thermal_pause = bool(settings.get("thermal_pause", self.node.resource_limits.thermal_pause))
        self.node.resource_limits.night_only = bool(settings.get("night_only", self.node.resource_limits.night_only))
        self.node.resource_limits.private_data_sharing_allowed = False
        return self.get_status()

    def _credit_multiplier(self) -> float:
        cpu_bonus = min(0.35, max(0.0, self.node.resource_limits.cpu_limit_percent - 20) / 60 * 0.35)
        gpu_bonus = 0.0
        if self.node.resource_limits.gpu_enabled:
            gpu_bonus = max(0.0, self.node.resource_limits.gpu_limit_percent) / 95 * 1.65
        return round(1.0 + cpu_bonus + gpu_bonus, 3)

    def register(self) -> dict[str, Any]:
        now = _now()
        try:
            if isinstance(self.broker, RemoteCloudBroker):
                self.broker.register_node(self.node)
            self.node.registered_at = self.node.registered_at or now
            self.node.last_seen_at = now
            self.node.contributor_state = "contributor_registered"
            self.last_error = None
        except Exception as exc:
            self.node.contributor_state = "error"
            self.last_error = str(exc)
        return self.get_status()

    def heartbeat(self) -> dict[str, Any]:
        if self.node.contributor_state in {"disabled", "local_only"}:
            return self.get_status()
        try:
            if isinstance(self.broker, RemoteCloudBroker):
                self.broker.heartbeat(self.node)
            self.node.last_seen_at = _now()
            if self.node.contributor_state == "contributor_registered":
                self.node.contributor_state = "task_polling"
            self.last_error = None
        except Exception as exc:
            self.node.contributor_state = "error"
            self.last_error = str(exc)
        return self.get_status()

    def poll_public_task(self) -> dict[str, Any]:
        if self.node.contributor_state in {"disabled", "paused"}:
            return self.get_status()
        if self.node.contributor_state == "local_only":
            self.register()
        self.node.contributor_state = "task_polling"
        try:
            task = self.broker.poll_public_task(self.node) if isinstance(self.broker, RemoteCloudBroker) else self.broker.poll_public_task()
        except Exception as exc:
            self.current_task = None
            self.node.total_tasks_rejected += 1
            self.node.contributor_state = "error"
            self.last_error = str(exc)
            return self.get_status()
        if task is None:
            self.current_task = None
            return self.get_status()
        try:
            self.current_task = validate_contribution_task(task)
            self.node.contributor_state = "contributor_active"
            self.last_error = None
        except ContributionValidationError as exc:
            self.current_task = None
            self.node.total_tasks_rejected += 1
            self.node.contributor_state = "error"
            self.last_error = str(exc)
        return self.get_status()

    def run_current_task(self) -> dict[str, Any]:
        if not self.current_task:
            self.poll_public_task()
        if not self.current_task:
            return self.get_status()
        self.node.contributor_state = "task_running"
        started = time.perf_counter()
        try:
            task = validate_contribution_task(self.current_task)
            result_payload = self._execute_task(task)
            runtime_ms = max(1, int((time.perf_counter() - started) * 1000))
            encoded = json.dumps(result_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            if len(encoded) > task.max_output_bytes:
                raise ContributionValidationError("result exceeds max_output_bytes")
            checksum = hashlib.sha256(encoded).hexdigest()
            result = TaskResult(
                task_id=task.task_id,
                node_id=self.node.node_id,
                status="completed",
                result_payload=result_payload,
                runtime_ms=runtime_ms,
                memory_peak_mb=min(task.max_memory_mb, 24),
                checksum=checksum,
                submitted_at=_now(),
                local_trace_id=f"local-broker-{checksum[:10]}",
            )
        except Exception as exc:
            runtime_ms = max(1, int((time.perf_counter() - started) * 1000))
            result = TaskResult(
                task_id=self.current_task.task_id,
                node_id=self.node.node_id,
                status="failed",
                result_payload={},
                runtime_ms=runtime_ms,
                memory_peak_mb=0,
                checksum=hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),
                submitted_at=_now(),
                error_message=str(exc),
            )
        return self.submit_task_result(result)

    def submit_task_result(self, result: TaskResult) -> dict[str, Any]:
        safe_payload = self._sanitize_result_payload(result.result_payload)
        result.result_payload = safe_payload
        remote_payload: dict[str, Any] | None = None
        if isinstance(self.broker, RemoteCloudBroker):
            try:
                remote_payload = self.broker.submit_result(result)
                self.last_remote_submission = remote_payload
                # Remote omission or a merely truthy value is not acceptance.
                verified = remote_payload.get("accepted") is True
            except Exception as exc:
                self.node.total_tasks_rejected += 1
                self.node.contributor_state = "error"
                self.last_error = str(exc)
                return self.get_status()
        else:
            verified = self.broker.verify_result(result)
        task = self.current_task
        self.recent_tasks.insert(0, result.to_dict())
        self.recent_tasks = self.recent_tasks[:20]
        if verified and task:
            credited_amount = round(task.credit_estimate * self._credit_multiplier(), 3)
            credit = ContributionCredit(
                credit_id=f"credit-{uuid.uuid4().hex[:12]}",
                node_id=self.node.node_id,
                task_id=task.task_id,
                amount_estimated=credited_amount,
                amount_confirmed=0.0,
                status="pending",
                reason="remote broker verification pending" if remote_payload else "local broker verification pending",
                created_at=_now(),
            )
            self.credits.insert(0, credit)
            self.node.total_tasks_completed += 1
            self.node.total_credits_pending += credited_amount
            self.node.contributor_state = "verification_pending"
        else:
            self.node.total_tasks_rejected += 1
            self.node.contributor_state = "error" if result.status == "failed" else "task_submitted"
            self.last_error = result.error_message
        self.current_task = None
        return self.get_status()

    def pause(self) -> dict[str, Any]:
        self.node.contributor_state = "paused"
        return self.get_status()

    def resume(self) -> dict[str, Any]:
        self.node.contributor_state = "task_polling"
        return self.get_status()

    def disable(self) -> dict[str, Any]:
        self.current_task = None
        self.node.contributor_state = "disabled"
        return self.get_status()

    def list_credits(self) -> dict[str, Any]:
        remote = self.broker.credits(self.node.node_id) if isinstance(self.broker, RemoteCloudBroker) else None
        return {"credits": [credit.to_dict() for credit in self.credits], "remote_credits": remote, **self.get_status()}

    def list_recent_tasks(self) -> dict[str, Any]:
        return {"tasks": self.recent_tasks, **self.get_status()}

    @staticmethod
    def _execute_task(task: PublicTask) -> dict[str, Any]:
        payload = task.payload
        if task.task_type == "source_noise_check":
            aliases = [str(item).lower() for item in payload.get("expected_concept_aliases", [])]
            snippet = f"{payload.get('source_title', '')} {payload.get('source_snippet', '')}".lower()
            overlap = sum(1 for alias in aliases if alias and alias in snippet)
            confidence = min(0.98, 0.42 + overlap * 0.22)
            return {
                "is_noise": overlap == 0,
                "confidence": round(confidence, 3),
                "reason_codes": [] if overlap else ["concept_overlap_low", "surface_word_only"],
            }
        if task.task_type == "duplicate_relation_check":
            a = payload.get("relation_a", {})
            b = payload.get("relation_b", {})
            same_source = str(a.get("source", "")).lower() == str(b.get("source", "")).lower()
            same_predicate = str(a.get("predicate", "")).lower() == str(b.get("predicate", "")).lower()
            target_a = str(a.get("target", "")).lower()
            target_b = str(b.get("target", "")).lower()
            target_overlap = target_a in target_b or target_b in target_a
            likelihood = 0.2 + 0.3 * same_source + 0.3 * same_predicate + 0.2 * target_overlap
            return {
                "duplicate_likelihood": round(likelihood, 3),
                "merge_recommended": likelihood >= 0.75,
                "confidence": round(min(0.95, likelihood), 3),
                "reason_codes": ["same_source", "same_predicate"] if same_source and same_predicate else ["partial_overlap"],
            }
        if task.task_type == "graph_delta_compression":
            nodes = payload.get("nodes", [])
            edges = payload.get("edges", [])
            retained_nodes = min(len(nodes), 64)
            retained_edges = min(len(edges), 128)
            total = max(1, len(nodes) + len(edges))
            retained = retained_nodes + retained_edges
            return {
                "compressed_delta": {"nodes": nodes[:retained_nodes], "edges": edges[:retained_edges]},
                "compression_ratio": round(retained / total, 3),
                "retained_nodes": retained_nodes,
                "retained_edges": retained_edges,
            }
        if task.task_type == "public_alias_review":
            concept = str(payload.get("canonical_concept", "")).lower()
            alias = str(payload.get("alias_candidate", "")).lower()
            evidence = str(payload.get("evidence", "")).lower()
            alias_valid = bool(alias and (alias in evidence or concept in evidence))
            return {
                "alias_valid": alias_valid,
                "confidence": 0.82 if alias_valid else 0.35,
                "reason_codes": ["evidence_mentions_alias"] if alias_valid else ["evidence_gap"],
            }
        if task.task_type == "freshness_check":
            return {"freshness": "local_broker_unknown", "confidence": 0.5, "reason_codes": ["no_global_clock_source"]}
        if task.task_type == "public_source_fetch":
            source_url = str(payload.get("source_url") or "")
            parsed = urllib.parse.urlparse(source_url)
            if parsed.scheme not in {"https", "http"}:
                raise ContributionValidationError("public_source_fetch requires http(s) source_url")
            hostname = (parsed.hostname or "").lower()
            if (
                hostname in {"localhost", "127.0.0.1", "::1"}
                or hostname.startswith("10.")
                or hostname.startswith("192.168.")
                or hostname.endswith(".local")
                or hostname.endswith(".internal")
            ):
                raise ContributionValidationError("public_source_fetch rejects local/private source_url")
            snippet = ""
            try:
                request = urllib.request.Request(source_url, headers={"User-Agent": "ATANOR-Contributor/0.1 public-fragment-fetch"})
                with urllib.request.urlopen(request, timeout=3.0) as response:
                    snippet = response.read(4096).decode("utf-8", errors="replace")
            except (urllib.error.URLError, TimeoutError, OSError):
                snippet = str(payload.get("claim") or payload.get("topic") or source_url)
            return {
                **_public_fragment_result(
                    text=snippet or str(payload.get("claim") or source_url),
                    source_url=source_url,
                    topic=str(payload.get("topic") or "public_source_fetch"),
                ),
                "source_url": source_url,
                "raw_payload_uploaded": False,
                "result_policy": "hash_and_summary_only",
                "confidence": 0.38,
                "reason_codes": ["bounded_public_fetch", "single_peer_pending"],
            }
        if task.task_type == "public_fragment_validation":
            edges = payload.get("fragment_edges", payload.get("edges", []))
            edge_list = edges if isinstance(edges, list) else []
            topic = str(payload.get("topic") or payload.get("claim") or "public_fragment_validation")
            return {
                **_public_fragment_result(
                    text=f"{topic} {json.dumps(edges, ensure_ascii=False)}",
                    source_url=str(payload.get("source_url") or ""),
                    topic=topic,
                    input_edges=edge_list,
                ),
                "accepted_edges": edge_list[:32],
                "rejected_edges": [],
                "conflict_markers": [],
                "trust_delta": 0.01 * min(len(edge_list), 32),
                "verification_state": "single_peer_pending",
                "requires_cross_check": True,
            }
        raise ContributionValidationError("unsupported task_type")

    @staticmethod
    def _sanitize_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if _contains_suspicious_content(payload):
            return {"rejected": True, "reason": "result contained forbidden local or executable marker"}
        forbidden_keys = {"local_path", "file_path", "payload_vault", "chat_log", "private_graph", "raw_document"}
        return {key: value for key, value in payload.items() if key not in forbidden_keys and key.lower() not in forbidden_keys}


default_contribution_service = ContributionService()
