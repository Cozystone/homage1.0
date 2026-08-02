from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def _bootstrap_import_path() -> None:
    api_root = Path(__file__).resolve().parents[2]
    repo_root = api_root.parents[1]
    package_roots = [str(path) for path in (repo_root / "packages").iterdir() if path.is_dir()]
    for value in [str(api_root), *package_roots]:
        if value not in sys.path:
            sys.path.insert(0, value)


_bootstrap_import_path()

from app.services.cloud_broker_client import CloudBrokerClient, CloudBrokerConfig, CloudBrokerError  # noqa: E402
from app.services.contribution_service import ContributionService, RemoteCloudBroker  # noqa: E402


SAFE_SEED_TASK: dict[str, Any] = {
    "task_type": "public_fragment_validation",
    "privacy_classification": "public_only",
    "payload": {
        "topic": "atanor cloud brain broker",
        "source_url": "https://example.com/",
        "claim": "ATANOR Cloud Brain Broker coordinates public-only fragment validation tasks.",
        "fragment_edges": [
            {
                "source": "ATANOR Cloud Brain Broker",
                "predicate": "coordinates",
                "target": "public fragment validation",
            },
            {
                "source": "public fragment validation",
                "predicate": "produces",
                "target": "content addressed fragment",
            },
        ],
    },
    "max_runtime_ms": 2500,
    "max_memory_mb": 64,
    "max_output_bytes": 8192,
    "trust_requirement": 0,
    "credit_estimate": 1,
}


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _service() -> ContributionService:
    config = CloudBrokerConfig.from_env()
    broker = RemoteCloudBroker(CloudBrokerClient(config))
    return ContributionService(broker=broker)


def _maybe_seed_task(client: CloudBrokerClient) -> dict[str, Any] | None:
    seed_enabled = os.getenv("ATANOR_DEV_SEED_PUBLIC_TASKS", os.getenv("HOMAGE_DEV_SEED_PUBLIC_TASKS", "")).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not seed_enabled:
        return None
    try:
        return client.enqueue_task(SAFE_SEED_TASK)
    except CloudBrokerError as exc:
        # The queue may already contain tasks or remote may disallow seeding.
        return {"seed_state": "skipped", "reason": str(exc)}


def run_once(*, seed_if_empty: bool = True) -> dict[str, Any]:
    config = CloudBrokerConfig.from_env()
    if not config.remote_enabled:
        raise SystemExit("ATANOR_CLOUD_MODE=remote and ATANOR_CLOUD_ENDPOINT are required")
    client = CloudBrokerClient(config)
    service = _service()
    registered = service.register()
    heartbeat = service.heartbeat()
    polled = service.poll_public_task()
    seeded = None
    if seed_if_empty and not polled.get("current_task"):
        seeded = _maybe_seed_task(client)
        for _ in range(6):
            time.sleep(1.0)
            polled = service.poll_public_task()
            if polled.get("current_task"):
                break
    if not polled.get("current_task"):
        return {
            "state": "no_task",
            "registered": registered.get("broker_state"),
            "heartbeat": heartbeat.get("broker_state"),
            "seed": seeded,
            "broker": client.status(),
        }
    result = service.run_current_task()
    remote_tasks = result.get("tasks") or result.get("recent_tasks") or []
    remote_status = result.get("last_remote_submission") or {}
    current_remote = result.get("broker_state")
    return {
        "state": "submitted" if result.get("contributor_state") == "verification_pending" else result.get("contributor_state"),
        "broker_state": current_remote,
        "task_id": (remote_tasks[0] or {}).get("task_id") if remote_tasks else None,
        "fragment_id": (remote_status or {}).get("fragment_id") or result.get("fragment_id"),
        "content_hash": (remote_status or {}).get("content_hash") or result.get("content_hash"),
        "verification_state": (remote_status or {}).get("verification_state", "single_peer_pending"),
        "storage_backend": (remote_status or {}).get("storage_backend"),
        "seed": seeded,
        "status": result,
    }


def run_status() -> dict[str, Any]:
    config = CloudBrokerConfig.from_env()
    client = CloudBrokerClient(config)
    status = client.status()
    network = client.network()
    credits = client.credits(config.node_id)
    return {"config": config.public_status(), "status": status, "network": network, "credits": credits}


def run_dry_run() -> dict[str, Any]:
    config = CloudBrokerConfig.from_env()
    return {
        "state": "dry_run_ok",
        "remote_enabled": config.remote_enabled,
        "config": config.public_status(),
        "seed_task": SAFE_SEED_TASK,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ATANOR Cloud Brain contributor node runner")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="register, heartbeat, poll one task, execute, and submit")
    mode.add_argument("--loop", action="store_true", help="repeat contributor polling loop")
    mode.add_argument("--status", action="store_true", help="print broker and peer status")
    mode.add_argument("--dry-run", action="store_true", help="validate local configuration without remote writes")
    parser.add_argument("--interval", type=float, default=30.0, help="loop interval in seconds")
    args = parser.parse_args(argv)

    try:
        if args.dry_run:
            _print(run_dry_run())
            return 0
        if args.status:
            _print(run_status())
            return 0
        if args.once:
            _print(run_once())
            return 0
        while True:
            _print(run_once())
            time.sleep(max(5.0, args.interval))
    except KeyboardInterrupt:
        _print({"state": "stopped"})
        return 0
    except Exception as exc:
        _print({"state": "error", "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
