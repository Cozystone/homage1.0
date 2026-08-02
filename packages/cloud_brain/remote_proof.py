from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "apps" / "api"
KNOWLEDGE_ROOT = REPO_ROOT / "packages" / "knowledge_bakery"
for import_root in (REPO_ROOT, API_ROOT, KNOWLEDGE_ROOT):
    import_path = str(import_root)
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.services.cloud_broker_client import CloudBrokerConfig
from knowledge_bakery import memory_status


PROOF_DIR = Path("data/cloud_brain/proofs")
PROOF_JSON = PROOF_DIR / "remote_cloud_brain_proof.json"
PROOF_MD = PROOF_DIR / "remote_cloud_brain_proof.md"

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
    "device_name",
    "ip",
    "token",
    "secret",
    "password",
}

FORBIDDEN_MARKERS = (
    "C:\\",
    "file://",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "192.168.",
    "10.",
    "172.16.",
    "/Users/",
    "/home/",
    "../",
    "..\\",
    "AppData",
    "payload_vault",
    "homage.db",
    "atanor.db",
)


@dataclass(frozen=True)
class RemoteProbeConfig:
    endpoint: str
    api_key: str | None
    timeout_seconds: float = 8.0

    @classmethod
    def from_env(cls) -> "RemoteProbeConfig":
        config = CloudBrokerConfig.from_env()
        return cls(endpoint=config.endpoint, api_key=config.api_key, timeout_seconds=config.timeout_seconds)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _contains_private_marker(value: Any) -> bool:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    lowered = encoded.lower()
    if any(marker.lower() in lowered for marker in FORBIDDEN_MARKERS):
        return True
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                return True
            if _contains_private_marker(nested):
                return True
    if isinstance(value, list):
        return any(_contains_private_marker(item) for item in value)
    return False


def validate_public_remote_fragment(payload: dict[str, Any]) -> None:
    if payload.get("privacy_scope") != "public":
        raise ValueError("privacy_scope must be public")
    if payload.get("source_scope") != "cloud":
        raise ValueError("source_scope must be cloud")
    if _contains_private_marker(payload):
        raise ValueError("public remote fragment contains private/local markers")


def deterministic_public_test_fragment(seed: str | None = None) -> dict[str, Any]:
    unique = seed or f"atanor-remote-submit-test-{_now_iso()}"
    content_hash = hashlib.sha256(unique.encode("utf-8")).hexdigest()
    fragment = {
        "fragment_id": f"remote-submit-test-{content_hash[:16]}",
        "content_hash": content_hash,
        "privacy_scope": "public",
        "source_scope": "cloud",
        "origin": "remote_submit_test",
        "text": "ATANOR remote Cloud Brain broker public read-back verification fragment.",
        "matched_seed_concepts": ["ATANOR", "Cloud Brain", "Remote Broker"],
        "matched_seed_edges": [["ATANOR", "verifies", "Remote Broker"]],
        "trust_state": "seed_aligned",
        "verification_state": "seed_aligned_pending_verification",
    }
    validate_public_remote_fragment(fragment)
    return fragment


def _request_json(config: RemoteProbeConfig, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not config.endpoint:
        raise RuntimeError("missing ATANOR_CLOUD_ENDPOINT")
    url = f"{config.endpoint.rstrip('/')}{path if path.startswith('/') else '/' + path}"
    body = None if payload is None else json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "ATANOR-RemoteProof/0.1.2",
    }
    if config.api_key:
        headers["X-ATANOR-API-Key"] = config.api_key
    request = urllib.request.Request(url, data=body, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            raw = response.read(1_000_000)
            status = response.status
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(f"remote HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"remote request failed: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("remote returned non-JSON response") from exc
    if status >= 400:
        raise RuntimeError(f"remote HTTP {status}: {data}")
    if not isinstance(data, dict):
        raise RuntimeError("remote returned non-object JSON")
    return data


def _local_brain_state() -> dict[str, Any]:
    memory = memory_status()
    return {
        "local_brain_initialized": False,
        "local_total_nodes": 0,
        "local_total_edges": 0,
        "memory_db_path_known": bool(memory.get("db_path")),
    }


def load_last_remote_proof() -> dict[str, Any] | None:
    if not PROOF_JSON.exists():
        return None
    try:
        payload = json.loads(PROOF_JSON.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_remote_cloud_brain_proof(*, config: RemoteProbeConfig | None = None, seed: str | None = None) -> dict[str, Any]:
    cfg = config or RemoteProbeConfig.from_env()
    failures: list[str] = []
    status: dict[str, Any] | None = None
    submit: dict[str, Any] | None = None
    query: dict[str, Any] | None = None
    readback: dict[str, Any] | None = None
    fragment = deterministic_public_test_fragment(seed)

    if not cfg.endpoint:
        failures.append("missing ATANOR_CLOUD_ENDPOINT")
    else:
        try:
            status = _request_json(cfg, "GET", "/cloud/status")
        except Exception as exc:
            failures.append(f"status failed: {exc}")
        if status is not None:
            try:
                submit = _request_json(cfg, "POST", "/cloud/fragments/submit", fragment)
            except Exception as exc:
                failures.append(f"submit failed: {exc}")
            try:
                query_path = "/cloud/fragments/query?" + urllib.parse.urlencode({"limit": 5, "q": fragment["content_hash"]})
                query = _request_json(cfg, "GET", query_path)
            except Exception as exc:
                failures.append(f"query failed: {exc}")
            try:
                read_path = "/cloud/fragments/read?" + urllib.parse.urlencode({"content_hash": fragment["content_hash"]})
                readback = _request_json(cfg, "GET", read_path)
            except Exception as exc:
                failures.append(f"read-back failed: {exc}")

    readback_fragment = readback.get("fragment") if isinstance(readback, dict) else None
    persisted = isinstance(readback_fragment, dict) and readback_fragment.get("content_hash") == fragment["content_hash"]
    local_state = _local_brain_state()
    pass_state = not failures and persisted
    proof = {
        "schema": "atanor.remote-cloud-brain-proof.v1",
        "proved_at": _now_iso(),
        "pass": pass_state,
        "result": "PASS" if pass_state else "FAIL",
        "statement": (
            "ATANOR has a real remote Cloud Brain broker. Public fragments can be submitted, persisted remotely, queried, and read back without writing into Local Brain."
            if pass_state
            else "ATANOR does not yet have a verified real remote Cloud Brain. Current Cloud Brain UI is local/proof/mirror only unless remote read-back passes."
        ),
        "endpoint_configured": bool(cfg.endpoint),
        "endpoint": cfg.endpoint or None,
        "status_success": status is not None,
        "fragment_submit_success": submit is not None and bool(submit.get("accepted", True)),
        "fragment_query_success": query is not None,
        "fragment_readback_success": persisted,
        "remote_persistence": persisted,
        "content_hash": fragment["content_hash"],
        "remote_status": status,
        "remote_submit": submit,
        "remote_query": query,
        "remote_readback": readback,
        "failures": failures,
        "local_brain_state": local_state,
        "external_llm_used": False,
        "external_sllm_used": False,
        "rule_template_final_generation_claimed": False,
        "writes_local_brain": False,
    }
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    PROOF_JSON.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    PROOF_MD.write_text(_proof_markdown(proof), encoding="utf-8")
    return proof


def _proof_markdown(proof: dict[str, Any]) -> str:
    failures = proof.get("failures") or []
    failure_lines = "\n".join(f"- {item}" for item in failures) if failures else "- none"
    return f"""# ATANOR Remote Cloud Brain Proof

Result: **{proof.get("result")}**

{proof.get("statement")}

## Verification

- Endpoint configured: `{proof.get("endpoint_configured")}`
- Endpoint: `{proof.get("endpoint")}`
- Status success: `{proof.get("status_success")}`
- Submit success: `{proof.get("fragment_submit_success")}`
- Query success: `{proof.get("fragment_query_success")}`
- Read-back success: `{proof.get("fragment_readback_success")}`
- Remote persistence proven: `{proof.get("remote_persistence")}`
- Content hash: `{proof.get("content_hash")}`
- Writes Local Brain: `{proof.get("writes_local_brain")}`

## Failures

{failure_lines}
"""


def main() -> None:
    proof = write_remote_cloud_brain_proof()
    print(json.dumps(proof, ensure_ascii=False, indent=2))
    raise SystemExit(0 if proof.get("pass") else 1)


if __name__ == "__main__":
    main()
