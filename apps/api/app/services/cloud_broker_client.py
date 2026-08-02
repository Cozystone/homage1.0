from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal


CloudMode = Literal["disabled", "local_broker", "remote"]
CloudProviderName = Literal["local", "aws", "cloudflare"]

FORBIDDEN_PUBLIC_KEYS = {
    "raw_text",
    "raw_document",
    "private_payload",
    "payload_vault",
    "chat_log",
    "local_path",
    "file_path",
    "absolute_path",
    "private_graph",
}

FORBIDDEN_PUBLIC_MARKERS = (
    "C:\\",
    "file://",
    "/Users/",
    "/home/",
    "../",
    "..\\",
    "AppData",
    "payload_vault",
    "homage.db",
    "atanor.db",
)


def _env_alias(primary: str, legacy: str, default: str | None = None) -> str | None:
    return os.getenv(primary, os.getenv(legacy, default))


def _env_bool(primary: str, legacy: str, default: bool = False) -> bool:
    value = _env_alias(primary, legacy)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_endpoint(endpoint: str | None) -> str:
    value = (endpoint or "").strip().rstrip("/")
    if value and not value.startswith("https://") and not value.startswith("http://127.0.0.1"):
        raise ValueError("ATANOR_CLOUD_ENDPOINT must be HTTPS unless it is localhost")
    return value


def peer_id_hash_for_node(node_id: str) -> str:
    return hashlib.sha256(f"peer:{node_id}".encode("utf-8")).hexdigest()


def _contains_forbidden_public_data(value: Any) -> bool:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    lowered = encoded.lower()
    if any(marker.lower() in lowered for marker in FORBIDDEN_PUBLIC_MARKERS):
        return True
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in FORBIDDEN_PUBLIC_KEYS:
                return True
            if _contains_forbidden_public_data(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_public_data(item) for item in value)
    return False


def _strip_private_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip_private_fields(nested)
            for key, nested in value.items()
            if str(key).lower() not in FORBIDDEN_PUBLIC_KEYS
        }
    if isinstance(value, list):
        return [_strip_private_fields(item) for item in value]
    return value


def public_fragment_from_text(
    *,
    text: str,
    source_url: str | None,
    source_peer_id: str,
    max_concepts: int = 12,
) -> dict[str, Any]:
    """Create a public, summary-only fragment payload for the remote broker.

    This intentionally does not export raw Payload Vault records. The remote
    broker receives tiny public concept hashes and bounded evidence summaries.
    """

    cleaned = re.sub(r"\s+", " ", text.strip())
    tokens = re.findall(r"[A-Za-z0-9가-힣][A-Za-z0-9가-힣_\-]{1,48}", cleaned)
    seen: set[str] = set()
    concepts: list[str] = []
    for token in tokens:
        normalized = token.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        concepts.append(token)
        if len(concepts) >= max_concepts:
            break
    if not concepts:
        concepts = ["public-fragment"]
    nodes = []
    for concept in concepts:
        node_hash = hashlib.sha256(f"public:{concept.lower()}".encode("utf-8")).hexdigest()
        nodes.append(
            {
                "id": node_hash,
                "node_hash": node_hash,
                "label": concept[:64],
                "type": "public_concept_hash",
            }
        )
    edges = []
    for left, right in zip(nodes, nodes[1:]):
        edges.append(
            {
                "source_hash": left["node_hash"],
                "target_hash": right["node_hash"],
                "source": left["node_hash"],
                "target": right["node_hash"],
                "weight": 0.5,
            }
        )
    digest = hashlib.sha256(json.dumps({"source_url": source_url or "", "nodes": nodes, "edges": edges}, sort_keys=True).encode("utf-8")).hexdigest()
    summary = cleaned[:360]
    return {
        "fragment_id": f"public-fragment-{digest[:16]}",
        "shard_id": "dev-public",
        "concept_ids": concepts,
        "nodes": nodes,
        "edges": edges,
        "evidence_summaries": [summary] if summary else [],
        "source_metadata": {
            "source_url": source_url or "inline-public-fragment",
            "raw_payload_exported": False,
        },
        "provenance": {
            "source_peer_id": source_peer_id,
            "submitted_at": _now_iso(),
            "privacy_classification": "public_fragment",
        },
        "trust_score": 0.5,
        "freshness_score": 0.5,
        "conflict_markers": [],
        "schema_version": "atanor.cloud-fragment.v1",
        "checksum": digest,
        "created_at": _now_iso(),
        "raw_payload_exported": False,
    }


@dataclass(frozen=True)
class CloudBrokerConfig:
    cloud_provider: CloudProviderName = "local"
    cloud_mode: CloudMode = "local_broker"
    endpoint: str = ""
    api_key: str | None = None
    node_id: str = "atanor-local-peer"
    contribution_enabled: bool = False
    timeout_seconds: float = 3.0

    @classmethod
    def from_env(cls) -> "CloudBrokerConfig":
        raw_mode = (_env_alias("ATANOR_CLOUD_MODE", "HOMAGE_CLOUD_MODE", "local_broker") or "local_broker").strip().lower()
        mode: CloudMode = raw_mode if raw_mode in {"disabled", "local_broker", "remote"} else "local_broker"  # type: ignore[assignment]
        endpoint = _safe_endpoint(_env_alias("ATANOR_CLOUD_ENDPOINT", "HOMAGE_CLOUD_ENDPOINT", ""))
        provider_default = "aws" if mode == "remote" and endpoint else "local"
        raw_provider = (_env_alias("ATANOR_CLOUD_PROVIDER", "HOMAGE_CLOUD_PROVIDER", provider_default) or provider_default).strip().lower()
        provider: CloudProviderName = raw_provider if raw_provider in {"local", "aws", "cloudflare"} else "local"  # type: ignore[assignment]
        if mode == "remote" and not endpoint:
            mode = "local_broker"
            provider = "local"
        if mode != "remote":
            provider = "local"
        try:
            timeout = float(_env_alias("ATANOR_CLOUD_TIMEOUT_SECONDS", "HOMAGE_CLOUD_TIMEOUT_SECONDS", "8.0") or "8.0")
        except ValueError:
            timeout = 8.0
        return cls(
            cloud_provider=provider,
            cloud_mode=mode,
            endpoint=endpoint,
            api_key=_env_alias("ATANOR_CLOUD_API_KEY", "HOMAGE_CLOUD_API_KEY"),
            node_id=_env_alias("ATANOR_NODE_ID", "HOMAGE_NODE_ID", "atanor-local-peer") or "atanor-local-peer",
            contribution_enabled=_env_bool("ATANOR_CONTRIBUTION_ENABLED", "HOMAGE_CONTRIBUTION_ENABLED", False),
            timeout_seconds=max(0.5, min(10.0, timeout)),
        )

    @property
    def remote_enabled(self) -> bool:
        return self.cloud_mode == "remote" and bool(self.endpoint)

    def public_status(self) -> dict[str, Any]:
        return {
            "cloud_provider": self.cloud_provider,
            "cloud_mode": self.cloud_mode,
            "endpoint_configured": bool(self.endpoint),
            "endpoint": self.endpoint if self.endpoint else None,
            "api_key_configured": bool(self.api_key),
            "node_id": self.node_id,
            "contribution_enabled": self.contribution_enabled,
        }


class CloudBrokerError(RuntimeError):
    pass


class CloudBrokerClient:
    def __init__(self, config: CloudBrokerConfig | None = None) -> None:
        self.config = config or CloudBrokerConfig.from_env()

    def status(self) -> dict[str, Any]:
        return self._request_json("GET", "/cloud/status")

    def register_node(self, node_payload: dict[str, Any]) -> dict[str, Any]:
        payload = _strip_private_fields(node_payload)
        payload["node_id"] = payload.get("node_id") or self.config.node_id
        payload["node_public_id"] = payload.get("node_public_id") or payload["node_id"]
        payload["peer_id_hash"] = payload.get("peer_id_hash") or peer_id_hash_for_node(str(payload["node_id"]))
        if _contains_forbidden_public_data(payload):
            raise CloudBrokerError("register-node payload contains private/local data markers")
        return self._request_json("POST", "/cloud/register-node", payload)

    def heartbeat(self, node_id: str, status_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = _strip_private_fields(status_payload or {})
        payload["node_id"] = node_id or self.config.node_id
        payload["peer_id_hash"] = peer_id_hash_for_node(payload["node_id"])
        if _contains_forbidden_public_data(payload):
            raise CloudBrokerError("heartbeat payload contains private/local data markers")
        return self._request_json("POST", "/cloud/heartbeat", payload)

    def poll_tasks(self, node_id: str, capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "node_id": node_id or self.config.node_id,
            "peer_id_hash": peer_id_hash_for_node(node_id or self.config.node_id),
            "capabilities": _strip_private_fields(capabilities or {}),
        }
        if _contains_forbidden_public_data(payload):
            raise CloudBrokerError("task poll payload contains private/local data markers")
        return self._request_json("POST", "/cloud/tasks/poll", payload)

    def enqueue_task(self, task_payload: dict[str, Any]) -> dict[str, Any]:
        payload = _strip_private_fields(task_payload)
        payload["privacy_classification"] = "public_only"
        if _contains_forbidden_public_data(payload):
            raise CloudBrokerError("task enqueue payload contains private/local data markers")
        return self._request_json("POST", "/cloud/tasks/enqueue", payload)

    def submit_task(self, result_payload: dict[str, Any]) -> dict[str, Any]:
        payload = _strip_private_fields(result_payload)
        if payload.get("node_id") and not payload.get("peer_id_hash"):
            payload["peer_id_hash"] = peer_id_hash_for_node(str(payload["node_id"]))
        if _contains_forbidden_public_data(payload):
            raise CloudBrokerError("task result contains private/local data markers")
        return self._request_json("POST", "/cloud/tasks/submit", payload)

    def query_fragments(
        self,
        concept_id: str = "",
        *,
        content_hash: str = "",
        topic: str = "",
        limit: int = 8,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": max(1, min(25, int(limit)))}
        if content_hash:
            params["content_hash"] = content_hash
        elif topic:
            params["topic"] = topic
        else:
            params["concept_id"] = concept_id
        query = urllib.parse.urlencode(params)
        return self._request_json("GET", f"/cloud/fragments/query?{query}")

    def peers(self) -> dict[str, Any]:
        return self._request_json("GET", "/cloud/peers")

    def network(self) -> dict[str, Any]:
        return self._request_json("GET", "/cloud/network")

    def put_fragment(self, fragment: dict[str, Any]) -> dict[str, Any]:
        payload = _strip_private_fields(fragment)
        if payload.get("raw_payload_exported") is not False:
            raise CloudBrokerError("cloud fragments must declare raw_payload_exported=false")
        if _contains_forbidden_public_data(payload):
            raise CloudBrokerError("fragment contains private/local data markers")
        return self._request_json("POST", "/cloud/fragments/put", payload)

    def credits(self, node_id: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"node_id": node_id or self.config.node_id})
        return self._request_json("GET", f"/cloud/credits?{query}")

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.config.remote_enabled:
            raise CloudBrokerError("remote Cloud Brain broker is not configured")
        base = self.config.endpoint.rstrip("/")
        url = f"{base}{path if path.startswith('/') else '/' + path}"
        body = None if payload is None else json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ATANOR-LocalCompanion/0.1.2",
        }
        if self.config.api_key:
            headers["X-ATANOR-API-Key"] = self.config.api_key
        request = urllib.request.Request(url, data=body, method=method.upper(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read(1_000_000)
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", errors="replace")
            raise CloudBrokerError(f"remote broker HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CloudBrokerError(f"remote broker request failed: {exc}") from exc
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise CloudBrokerError("remote broker returned non-JSON response") from exc
        if status >= 400:
            raise CloudBrokerError(f"remote broker HTTP {status}: {data}")
        if not isinstance(data, dict):
            raise CloudBrokerError("remote broker returned non-object JSON")
        return data
