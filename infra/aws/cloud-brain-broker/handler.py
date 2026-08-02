from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr


SERVICE = "atanor-cloud-brain-broker"
MODE = os.getenv("ATANOR_CLOUD_MODE", "dev")
NODES_TABLE = os.environ["NODES_TABLE"]
TASKS_TABLE = os.environ["TASKS_TABLE"]
FRAGMENTS_TABLE = os.environ["FRAGMENTS_TABLE"]
CREDITS_TABLE = os.environ["CREDITS_TABLE"]
FRAGMENTS_BUCKET = os.getenv("FRAGMENTS_BUCKET", "")
BROKER_API_KEY = os.getenv("BROKER_API_KEY", "")
ALLOWED_ORIGINS = [item.strip() for item in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:3022,http://localhost:3022").split(",") if item.strip()]

dynamodb = boto3.resource("dynamodb")
nodes_table = dynamodb.Table(NODES_TABLE)
tasks_table = dynamodb.Table(TASKS_TABLE)
fragments_table = dynamodb.Table(FRAGMENTS_TABLE)
credits_table = dynamodb.Table(CREDITS_TABLE)


ALLOWED_TASK_TYPES = {
    "public_fragment_validation",
    "source_noise_check",
    "duplicate_relation_check",
    "graph_delta_compression",
    "public_alias_review",
    "freshness_check",
}

FORBIDDEN_KEYS = {
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

FORBIDDEN_MARKERS = (
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


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _epoch_ttl(days: int = 30) -> int:
    return int(time.time()) + days * 86400


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _decimalize(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _decimalize(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_decimalize(item) for item in value]
    return value


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raise ValueError("base64 request bodies are not accepted")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _origin(event: dict[str, Any]) -> str:
    headers = event.get("headers") or {}
    return headers.get("origin") or headers.get("Origin") or ""


def _headers(event: dict[str, Any]) -> dict[str, str]:
    origin = _origin(event)
    allow_origin = origin if origin in ALLOWED_ORIGINS else (ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*")
    return {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-ATANOR-API-Key",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }


def _response(event: dict[str, Any], status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": _headers(event),
        "body": json.dumps(payload, ensure_ascii=False, default=_json_default),
    }


def _request_info(event: dict[str, Any]) -> tuple[str, str]:
    http = (event.get("requestContext") or {}).get("http") or {}
    method = str(http.get("method") or event.get("httpMethod") or "GET").upper()
    path = str(http.get("path") or event.get("rawPath") or event.get("path") or "/")
    stage_prefix = f"/{MODE}"
    if path.startswith(stage_prefix + "/"):
        path = path[len(stage_prefix) :]
    return method, path


def _authorized(event: dict[str, Any]) -> bool:
    if not BROKER_API_KEY:
        return True
    method, path = _request_info(event)
    if method == "GET" and path == "/cloud/status":
        return True
    headers = event.get("headers") or {}
    supplied = headers.get("x-atanor-api-key") or headers.get("X-ATANOR-API-Key")
    auth = headers.get("authorization") or headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        supplied = auth.split(" ", 1)[1].strip()
    return supplied == BROKER_API_KEY


def _contains_forbidden_public_data(value: Any) -> bool:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    lowered = encoded.lower()
    if any(marker.lower() in lowered for marker in FORBIDDEN_MARKERS):
        return True
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                return True
            if _contains_forbidden_public_data(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_public_data(item) for item in value)
    return False


def _validate_public_task(task: dict[str, Any]) -> None:
    if task.get("task_type") not in ALLOWED_TASK_TYPES:
        raise ValueError("unknown task_type")
    if task.get("privacy_classification") != "public_only":
        raise ValueError("privacy_classification must be public_only")
    payload = task.get("payload") or {}
    if _contains_forbidden_public_data(payload):
        raise ValueError("task payload contains forbidden private or executable markers")


def _validate_public_fragment(fragment: dict[str, Any]) -> None:
    if fragment.get("raw_payload_exported") is not False:
        raise ValueError("raw_payload_exported must be false")
    for node in fragment.get("nodes") or []:
        if "raw_text" in node:
            raise ValueError("fragment nodes must not contain raw_text")
    if _contains_forbidden_public_data(fragment):
        raise ValueError("fragment contains forbidden private/local markers")


def _status() -> dict[str, Any]:
    return {
        "service": SERVICE,
        "mode": MODE,
        "status": "ok",
        "schema": "atanor.cloud-broker.v1",
        "raw_private_payload_storage": False,
        "tables": {
            "nodes": NODES_TABLE,
            "tasks": TASKS_TABLE,
            "fragments": FRAGMENTS_TABLE,
            "credits": CREDITS_TABLE,
        },
        "s3_bucket_configured": bool(FRAGMENTS_BUCKET),
        "created_at": _now_iso(),
    }


def _register_node(payload: dict[str, Any]) -> dict[str, Any]:
    if _contains_forbidden_public_data(payload):
        raise ValueError("register-node payload contains private/local markers")
    node_id = str(payload.get("node_id") or f"atanor-node-{uuid.uuid4().hex[:12]}")
    item = {
        "node_id": node_id,
        "device_label": str(payload.get("device_label") or "ATANOR Contributor"),
        "app_version": str(payload.get("app_version") or "unknown"),
        "contributor_state": str(payload.get("contributor_state") or "contributor_registered"),
        "registered_at": payload.get("registered_at") or _now_iso(),
        "last_seen_at": _now_iso(),
        "capabilities": payload.get("capabilities") or {},
        "resource_limits": payload.get("resource_limits") or {},
        "trust_score": Decimal(str(payload.get("trust_score") or 0.5)),
    }
    nodes_table.put_item(Item=_decimalize(item))
    return {"accepted": True, "node_id": node_id, "broker_state": "remote_connected", "node": item}


def _heartbeat(payload: dict[str, Any]) -> dict[str, Any]:
    node_id = str(payload.get("node_id") or "")
    if not node_id:
        raise ValueError("node_id is required")
    if _contains_forbidden_public_data(payload):
        raise ValueError("heartbeat payload contains private/local markers")
    now = _now_iso()
    nodes_table.update_item(
        Key={"node_id": node_id},
        UpdateExpression="SET last_seen_at=:now, contributor_state=:state, capabilities=:capabilities, resource_limits=:limits",
        ExpressionAttributeValues=_decimalize(
            {
                ":now": now,
                ":state": str(payload.get("contributor_state") or "heartbeat"),
                ":capabilities": payload.get("capabilities") or {},
                ":limits": payload.get("resource_limits") or {},
            }
        ),
    )
    return {"accepted": True, "node_id": node_id, "last_seen_at": now, "broker_state": "remote_connected"}


def _sample_task(node_id: str) -> dict[str, Any]:
    now = _now_iso()
    return {
        "task_id": f"dev-public-fragment-validation-{hashlib.sha256(node_id.encode()).hexdigest()[:10]}",
        "task_type": "public_fragment_validation",
        "schema_version": "atanor.contribution-task.v1",
        "payload": {
            "fragment_edges": [
                {
                    "source": "GraphRAG",
                    "predicate": "uses",
                    "target": "public-evidence",
                }
            ],
            "privacy_classification": "public_only",
        },
        "max_runtime_ms": 1500,
        "max_memory_mb": 64,
        "max_output_bytes": 4096,
        "created_at": now,
        "expires_at": now,
        "trust_requirement": 0.0,
        "credit_estimate": 1.0,
        "privacy_classification": "public_only",
    }


def _poll_task(payload: dict[str, Any]) -> dict[str, Any]:
    node_id = str(payload.get("node_id") or "")
    if not node_id:
        raise ValueError("node_id is required")
    response = tasks_table.scan(
        FilterExpression=Attr("status").eq("open") & Attr("privacy_classification").eq("public_only"),
        Limit=1,
    )
    items = response.get("Items") or []
    if not items:
        task = _sample_task(node_id)
        _validate_public_task(task)
        return {"state": "task_available", "task": task, "broker_state": "remote_connected"}
    task = items[0]
    _validate_public_task(task)
    tasks_table.update_item(
        Key={"task_id": task["task_id"]},
        UpdateExpression="SET #s=:assigned, assigned_node_id=:node",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":assigned": "assigned", ":node": node_id},
    )
    return {"state": "task_available", "task": task, "broker_state": "remote_connected"}


def _submit_task(payload: dict[str, Any]) -> dict[str, Any]:
    if _contains_forbidden_public_data(payload):
        raise ValueError("task result contains private/local markers")
    task_id = str(payload.get("task_id") or "")
    node_id = str(payload.get("node_id") or "")
    if not task_id or not node_id:
        raise ValueError("task_id and node_id are required")
    credit_id = f"credit-{uuid.uuid4().hex[:16]}"
    now = _now_iso()
    credit = {
        "credit_id": credit_id,
        "node_id": node_id,
        "task_id": task_id,
        "amount_estimated": Decimal(str(payload.get("credit_estimate") or 1.0)),
        "amount_confirmed": Decimal("0"),
        "status": "pending",
        "reason": "verification_pending",
        "created_at": now,
        "confirmed_at": None,
    }
    credits_table.put_item(Item=credit)
    tasks_table.put_item(
        Item=_decimalize(
            {
                "task_id": task_id,
                "task_type": payload.get("task_type") or "submitted_result",
                "status": "verification_pending",
                "payload": {"result_checksum": payload.get("checksum"), "runtime_ms": payload.get("runtime_ms")},
                "assigned_node_id": node_id,
                "created_at": now,
                "expires_at": _epoch_ttl(7),
                "credit_estimate": credit["amount_estimated"],
                "privacy_classification": "public_only",
            }
        )
    )
    return {
        "accepted": True,
        "state": "verification_pending",
        "credit": credit,
        "broker_state": "remote_connected",
    }


def _put_fragment(payload: dict[str, Any]) -> dict[str, Any]:
    _validate_public_fragment(payload)
    fragment_id = str(payload.get("fragment_id") or f"fragment-{uuid.uuid4().hex[:16]}")
    checksum = str(payload.get("checksum") or hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest())
    item = {
        "fragment_id": fragment_id,
        "shard_id": str(payload.get("shard_id") or "dev-public"),
        "concept_ids": payload.get("concept_ids") or [],
        "nodes": payload.get("nodes") or [],
        "edges": payload.get("edges") or [],
        "evidence_summaries": payload.get("evidence_summaries") or [],
        "source_metadata": payload.get("source_metadata") or {},
        "provenance": payload.get("provenance") or {},
        "trust_score": Decimal(str(payload.get("trust_score") or 0.5)),
        "freshness_score": Decimal(str(payload.get("freshness_score") or 0.5)),
        "conflict_markers": payload.get("conflict_markers") or [],
        "schema_version": str(payload.get("schema_version") or "atanor.cloud-fragment.v1"),
        "checksum": checksum,
        "created_at": payload.get("created_at") or _now_iso(),
        "expires_at": int(payload.get("expires_at") or _epoch_ttl(30)),
        "raw_payload_exported": False,
    }
    fragments_table.put_item(Item=_decimalize(item))
    return {"accepted": True, "fragment_id": fragment_id, "checksum": checksum, "broker_state": "remote_connected"}


def _query_fragments(params: dict[str, str]) -> dict[str, Any]:
    concept_id = params.get("concept_id") or params.get("query") or ""
    limit = max(1, min(25, int(params.get("limit") or 8)))
    if concept_id:
        response = fragments_table.scan(FilterExpression=Attr("concept_ids").contains(concept_id), Limit=limit)
    else:
        response = fragments_table.scan(Limit=limit)
    fragments = response.get("Items") or []
    return {
        "state": "completed",
        "raw_payload_exported": False,
        "fragments": fragments,
        "count": len(fragments),
        "broker_state": "remote_connected",
    }


def _credits(params: dict[str, str]) -> dict[str, Any]:
    node_id = params.get("node_id") or ""
    if not node_id:
        return {"credits": [], "broker_state": "remote_connected"}
    response = credits_table.scan(FilterExpression=Attr("node_id").eq(node_id), Limit=25)
    return {"credits": response.get("Items") or [], "broker_state": "remote_connected"}


def _shards() -> dict[str, Any]:
    return {
        "shards": [
            {
                "shard_id": "dev-public",
                "mode": "tiny_public_fragment_store",
                "raw_private_payload_storage": False,
            }
        ],
        "broker_state": "remote_connected",
    }


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    method, path = _request_info(event)
    if method == "OPTIONS":
        return _response(event, 204, {})
    if not _authorized(event):
        return _response(event, 401, {"error": "unauthorized"})
    try:
        query = event.get("queryStringParameters") or {}
        if method == "GET" and path == "/cloud/status":
            return _response(event, 200, _status())
        if method == "POST" and path == "/cloud/register-node":
            return _response(event, 200, _register_node(_body(event)))
        if method == "POST" and path == "/cloud/heartbeat":
            return _response(event, 200, _heartbeat(_body(event)))
        if method == "POST" and path == "/cloud/tasks/poll":
            return _response(event, 200, _poll_task(_body(event)))
        if method == "POST" and path == "/cloud/tasks/submit":
            return _response(event, 200, _submit_task(_body(event)))
        if method == "GET" and path == "/cloud/fragments/query":
            return _response(event, 200, _query_fragments(query))
        if method == "POST" and path == "/cloud/fragments/put":
            return _response(event, 200, _put_fragment(_body(event)))
        if method == "GET" and path == "/cloud/shards":
            return _response(event, 200, _shards())
        if method == "GET" and path == "/cloud/credits":
            return _response(event, 200, _credits(query))
        return _response(event, 404, {"error": "not_found", "path": path, "method": method})
    except ValueError as exc:
        return _response(event, 422, {"error": str(exc)})
    except Exception as exc:
        return _response(event, 500, {"error": "internal_error", "detail": str(exc)})
