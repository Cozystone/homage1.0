from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.services.cloud_broker_client import CloudBrokerClient, CloudBrokerConfig, CloudBrokerError
from app.services.contribution_service import LocalBroker, TaskResult


class CloudBrainProvider(Protocol):
    provider: str

    def status(self) -> dict[str, Any]:
        ...

    def register_node(self, node: dict[str, Any]) -> dict[str, Any]:
        ...

    def heartbeat(self, node_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def poll_task(self, node_id: str, capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def submit_task_result(self, result: dict[str, Any]) -> dict[str, Any]:
        ...

    def query_fragment(self, query: str, *, limit: int = 8) -> dict[str, Any]:
        ...

    def put_fragment(self, fragment: dict[str, Any]) -> dict[str, Any]:
        ...

    def list_shards(self) -> dict[str, Any]:
        ...

    def list_credits(self, node_id: str) -> dict[str, Any]:
        ...

    def estimate_cost(self) -> dict[str, Any]:
        ...

    def provider_health(self) -> dict[str, Any]:
        ...


@dataclass
class LocalBrokerProvider:
    broker: LocalBroker | None = None
    provider: str = "local"

    def __post_init__(self) -> None:
        if self.broker is None:
            self.broker = LocalBroker()

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "cloud_mode": "local_broker",
            "broker_state": "local_broker_mode",
            "status": "ok",
            "remote": False,
            "raw_private_payload_storage": False,
        }

    def register_node(self, node: dict[str, Any]) -> dict[str, Any]:
        return {"accepted": True, "node_id": node.get("node_id"), "broker_state": "local_broker_mode"}

    def heartbeat(self, node_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"accepted": True, "node_id": node_id, "broker_state": "local_broker_mode"}

    def poll_task(self, node_id: str, capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self.broker is not None
        task = self.broker.poll_public_task()
        return {
            "state": "task_available" if task else "no_task",
            "task": task.to_dict() if task else None,
            "broker_state": "local_broker_mode",
        }

    def submit_task_result(self, result: dict[str, Any]) -> dict[str, Any]:
        assert self.broker is not None
        verified = self.broker.verify_result(TaskResult(**result))
        return {
            "accepted": verified,
            "state": "verification_pending" if verified else "rejected",
            "broker_state": "local_broker_mode",
        }

    def query_fragment(self, query: str, *, limit: int = 8) -> dict[str, Any]:
        return {"state": "local_only", "fragments": [], "raw_payload_exported": False, "broker_state": "local_broker_mode"}

    def put_fragment(self, fragment: dict[str, Any]) -> dict[str, Any]:
        return {"accepted": True, "state": "local_buffered", "raw_payload_exported": False, "broker_state": "local_broker_mode"}

    def list_shards(self) -> dict[str, Any]:
        return {"shards": [{"shard_id": "local-dev", "provider": "local"}], "broker_state": "local_broker_mode"}

    def list_credits(self, node_id: str) -> dict[str, Any]:
        return {"credits": [], "broker_state": "local_broker_mode"}

    def estimate_cost(self) -> dict[str, Any]:
        return {"provider": "local", "estimated_monthly_provider_cost_usd": 0.0, "notes": ["local machine bears runtime cost"]}

    def provider_health(self) -> dict[str, Any]:
        return self.status()


@dataclass
class HttpBrokerProvider:
    provider: str
    client: CloudBrokerClient

    def status(self) -> dict[str, Any]:
        return {**self.client.status(), "provider": self.provider, "broker_state": "remote_connected"}

    def register_node(self, node: dict[str, Any]) -> dict[str, Any]:
        return self.client.register_node(node)

    def heartbeat(self, node_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.heartbeat(node_id, payload)

    def poll_task(self, node_id: str, capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.poll_tasks(node_id, capabilities)

    def submit_task_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return self.client.submit_task(result)

    def query_fragment(self, query: str, *, limit: int = 8) -> dict[str, Any]:
        return self.client.query_fragments(query, limit=limit)

    def put_fragment(self, fragment: dict[str, Any]) -> dict[str, Any]:
        return self.client.put_fragment(fragment)

    def list_shards(self) -> dict[str, Any]:
        return self.client._request_json("GET", "/cloud/shards")

    def list_credits(self, node_id: str) -> dict[str, Any]:
        return self.client.credits(node_id)

    def estimate_cost(self) -> dict[str, Any]:
        profile = "edge-control-plane" if self.provider == "cloudflare" else "serverless-control-plane"
        return {
            "provider": self.provider,
            "profile": profile,
            "pricing_source": "configurable_estimate_only",
            "heavy_compute_location": "contributor_nodes",
        }

    def provider_health(self) -> dict[str, Any]:
        try:
            return self.status()
        except CloudBrokerError as exc:
            return {"provider": self.provider, "broker_state": "remote_error", "error": str(exc)}


class AwsBrokerProvider(HttpBrokerProvider):
    def __init__(self, client: CloudBrokerClient) -> None:
        super().__init__(provider="aws", client=client)


class CloudflareBrokerProvider(HttpBrokerProvider):
    def __init__(self, client: CloudBrokerClient) -> None:
        super().__init__(provider="cloudflare", client=client)


def provider_from_config(config: CloudBrokerConfig | None = None) -> CloudBrainProvider:
    config = config or CloudBrokerConfig.from_env()
    if config.cloud_mode in {"disabled", "local_broker"} or not config.remote_enabled:
        return LocalBrokerProvider()
    client = CloudBrokerClient(config)
    if config.cloud_provider == "cloudflare":
        return CloudflareBrokerProvider(client)
    if config.cloud_provider == "aws":
        return AwsBrokerProvider(client)
    return LocalBrokerProvider()
