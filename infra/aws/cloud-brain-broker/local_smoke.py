from __future__ import annotations

import json
import os
import urllib.request


ENDPOINT = os.environ.get("ATANOR_CLOUD_ENDPOINT", "").rstrip("/")
API_KEY = os.environ.get("ATANOR_CLOUD_API_KEY", "")


def request(method: str, path: str, payload: dict | None = None) -> dict:
    if not ENDPOINT:
        raise SystemExit("Set ATANOR_CLOUD_ENDPOINT first.")
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if API_KEY:
        headers["X-ATANOR-API-Key"] = API_KEY
    req = urllib.request.Request(f"{ENDPOINT}{path}", data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    node_id = os.environ.get("ATANOR_NODE_ID", "atanor-smoke-node")
    print("status", request("GET", "/cloud/status"))
    print(
        "register",
        request(
            "POST",
            "/cloud/register-node",
            {
                "node_id": node_id,
                "device_label": "ATANOR Smoke Node",
                "app_version": "0.1.2",
                "contributor_state": "contributor_registered",
                "capabilities": {"supports_public_fragment_validation": True},
                "resource_limits": {"cpu_limit_percent": 10, "private_data_sharing_allowed": False},
            },
        ),
    )
    print("heartbeat", request("POST", "/cloud/heartbeat", {"node_id": node_id, "contributor_state": "task_polling"}))
    task = request("POST", "/cloud/tasks/poll", {"node_id": node_id})
    print("poll", task)
    if task.get("task"):
        task_id = task["task"]["task_id"]
        print(
            "submit",
            request(
                "POST",
                "/cloud/tasks/submit",
                {
                    "task_id": task_id,
                    "node_id": node_id,
                    "status": "completed",
                    "result_payload": {"accepted": True, "reason_codes": []},
                    "runtime_ms": 1,
                    "memory_peak_mb": 1,
                    "checksum": "smoke",
                },
            ),
        )
    print("query", request("GET", "/cloud/fragments/query?concept_id=GraphRAG&limit=5"))
    print("credits", request("GET", f"/cloud/credits?node_id={node_id}"))


if __name__ == "__main__":
    main()
