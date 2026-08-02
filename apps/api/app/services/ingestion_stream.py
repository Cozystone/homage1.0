from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge_bakery import build_memory, daemon_status, export_graph, memory_status


STREAM_STARTED_MONOTONIC = time.monotonic()
STREAM_STARTED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cumulative_learning_seconds() -> int:
    try:
        daemon = daemon_status()
    except Exception:
        return 0
    return int(
        daemon.get("display_learning_seconds")
        or daemon.get("active_learning_seconds")
        or daemon.get("cumulative_learning_seconds")
        or 0
    )


def _event_id() -> str:
    return f"{int(time.time() * 1000)}"


def _edge_key(edge: dict[str, Any]) -> str:
    source = str(edge.get("source") or edge.get("source_hash") or "")
    target = str(edge.get("target") or edge.get("target_hash") or "")
    return f"{source}:{target}"


def _file_fingerprint(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _scan_files(root: Path) -> dict[str, tuple[int, int]]:
    root.mkdir(parents=True, exist_ok=True)
    result: dict[str, tuple[int, int]] = {}
    for path in sorted([*root.rglob("*.txt"), *root.rglob("*.md")]):
        fingerprint = _file_fingerprint(path)
        if fingerprint is not None:
            result[str(path.resolve())] = fingerprint
    return result


def format_sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {data.get('event_id', _event_id())}\nevent: {event}\ndata: {payload}\n\n"


@dataclass
class GraphEventSubscriber:
    queue: asyncio.Queue[dict[str, Any]]
    limit: int


@dataclass
class GraphEventHub:
    subscribers: set[int] = field(default_factory=set)
    _queues: dict[int, GraphEventSubscriber] = field(default_factory=dict)
    _last_node_ids: set[str] = field(default_factory=set)
    _last_edge_keys: set[str] = field(default_factory=set)
    _baseline_ready: bool = False
    _next_id: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def subscribe(self, *, limit: int = 5000) -> tuple[int, asyncio.Queue[dict[str, Any]]]:
        async with self._lock:
            self._next_id += 1
            subscriber_id = self._next_id
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=32)
            self.subscribers.add(subscriber_id)
            self._queues[subscriber_id] = GraphEventSubscriber(queue=queue, limit=max(1, int(limit)))
        await queue.put(await self.snapshot_event(event_type="graph_snapshot", trigger="subscriber_connected", limit=limit, mark_known=False))
        return subscriber_id, queue

    async def unsubscribe(self, subscriber_id: int) -> None:
        async with self._lock:
            self.subscribers.discard(subscriber_id)
            self._queues.pop(subscriber_id, None)

    async def publish(self, event: dict[str, Any]) -> None:
        async with self._lock:
            subscribers = list(self._queues.values())
        for subscriber in subscribers:
            item = dict(event)
            if len(item.get("nodes") or []) > subscriber.limit:
                item["nodes"] = list(item.get("nodes") or [])[: subscriber.limit]
            if subscriber.queue.full():
                try:
                    subscriber.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                subscriber.queue.put_nowait(item)
            except asyncio.QueueFull:
                pass

    async def publish_snapshot(self, *, event_type: str, trigger: str, limit: int = 5000, changed_paths: list[str] | None = None) -> dict[str, Any]:
        event = await self.snapshot_event(event_type=event_type, trigger=trigger, limit=limit, changed_paths=changed_paths)
        await self.publish(event)
        return event

    async def snapshot_event(
        self,
        *,
        event_type: str,
        trigger: str,
        limit: int = 5000,
        changed_paths: list[str] | None = None,
        mark_known: bool = True,
    ) -> dict[str, Any]:
        graph = await asyncio.to_thread(export_graph, limit=limit)
        status = await asyncio.to_thread(memory_status)
        nodes = list(graph.get("nodes") or [])
        edges = list(graph.get("edges") or [])
        current_node_ids = {str(node.get("id") or node.get("node_hash") or "") for node in nodes if node.get("id") or node.get("node_hash")}
        current_edge_keys = {_edge_key(edge) for edge in edges if _edge_key(edge) != ":"}

        if self._baseline_ready:
            new_node_ids = sorted(current_node_ids - self._last_node_ids)
            new_edge_keys = sorted(current_edge_keys - self._last_edge_keys)
        elif event_type == "graph_delta":
            new_node_ids = sorted(current_node_ids)
            new_edge_keys = sorted(current_edge_keys)
        else:
            new_node_ids = []
            new_edge_keys = []
        if mark_known:
            self._last_node_ids = current_node_ids
            self._last_edge_keys = current_edge_keys
            self._baseline_ready = True

        ghost_shell = status.get("ghost_shell") or {
            "system_state": "GHOST SHELL EMPTY",
            "control_plane_hashes": len(nodes),
            "control_plane_edges": len(edges),
            "payload_vault_records": 0,
        }
        logs = [
            "SYSTEM STATE: GHOST SHELL ACTIVE" if ghost_shell.get("system_state") == "GHOST SHELL ACTIVE" else "SYSTEM STATE: GHOST SHELL EMPTY",
            f"CONTROL PLANE: Loaded {ghost_shell.get('control_plane_hashes', len(nodes))} Schematic Hashes (Memory: Minimal)",
            "DATA PLANE: Vaulting Payloads to Edge Storage",
            f"[STREAM] {event_type} via {trigger}",
            f"[STREAM] new ghost hashes: {len(new_node_ids)} / new edges: {len(new_edge_keys)}",
        ]
        return {
            **graph,
            "event_id": _event_id(),
            "event_type": event_type,
            "generated_at": utc_now_iso(),
            "learning_started_at": STREAM_STARTED_AT,
            "cumulative_learning_seconds": cumulative_learning_seconds(),
            "source": "sse_live_memory_graph",
            "state": graph.get("state", "completed"),
            "stream": "sse_v1",
            "trigger": trigger,
            "changed_paths": changed_paths or [],
            "new_node_ids": new_node_ids[:512],
            "new_edge_keys": new_edge_keys[:2048],
            "ghost_shell": {
                **ghost_shell,
                "logs": logs,
            },
            "graph_counts": {
                "nodes": len(nodes),
                "edges": len(edges),
                "new_nodes": len(new_node_ids),
                "new_edges": len(new_edge_keys),
            },
        }

    async def heartbeat(self) -> dict[str, Any]:
        status = await asyncio.to_thread(memory_status)
        node_count = int(status.get("ghost_hash_count") or status.get("node_count") or 0)
        edge_count = int(status.get("ghost_edge_count") or status.get("edge_count") or 0)
        ghost_shell = status.get("ghost_shell") or {
            "system_state": "GHOST SHELL EMPTY",
            "control_plane_hashes": node_count,
            "control_plane_edges": edge_count,
            "payload_vault_records": 0,
        }
        return {
            "event_id": _event_id(),
            "event_type": "heartbeat",
            "generated_at": utc_now_iso(),
            "learning_started_at": STREAM_STARTED_AT,
            "cumulative_learning_seconds": cumulative_learning_seconds(),
            "state": "ready",
            "stream": "sse_v1",
            "source": "graph_event_hub",
            "ghost_shell": {
                **ghost_shell,
                "logs": [
                    "[SSE] heartbeat pulsing; listener stream alive",
                    f"CONTROL PLANE: {node_count} hashes / {edge_count} edges",
                ],
            },
            "graph_counts": {
                "nodes": node_count,
                "edges": edge_count,
                "new_nodes": 0,
                "new_edges": 0,
            },
        }


class CleanedDirectoryWatcher:
    def __init__(
        self,
        *,
        hub: GraphEventHub,
        cleaned_dir: str = "data/cleaned",
        ontology_dir: str = "data/ontology",
        memory_dir: str = "data/memory",
        scan_interval_seconds: float = 0.25,
    ) -> None:
        self.hub = hub
        self.cleaned_dir = Path(cleaned_dir)
        self.ontology_dir = ontology_dir
        self.memory_dir = memory_dir
        self.scan_interval_seconds = max(0.05, float(scan_interval_seconds))
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._build_lock = asyncio.Lock()
        self._pending_paths: set[str] = set()
        self._last_snapshot: dict[str, tuple[int, int]] = {}

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop = asyncio.Event()
        self._last_snapshot = _scan_files(self.cleaned_dir)
        self._task = asyncio.create_task(self._watch_loop(), name="homage-cleaned-directory-watcher")

    async def stop(self) -> None:
        self._stop.set()
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def trigger_build(self, *, reason: str, changed_paths: list[str] | None = None) -> None:
        self._pending_paths.update(changed_paths or [])
        if self._build_lock.locked():
            return
        while self._pending_paths:
            paths = sorted(self._pending_paths)
            self._pending_paths.clear()
            async with self._build_lock:
                await self.hub.publish(
                    {
                        "event_id": _event_id(),
                        "event_type": "graph_build_started",
                        "generated_at": utc_now_iso(),
                        "learning_started_at": STREAM_STARTED_AT,
                        "cumulative_learning_seconds": cumulative_learning_seconds(),
                        "state": "running",
                        "stream": "sse_v1",
                        "trigger": reason,
                        "changed_paths": paths,
                        "nodes": [],
                        "edges": [],
                        "new_node_ids": [],
                        "new_edge_keys": [],
                        "ghost_shell": {
                            "system_state": "GHOST SHELL BUILDING",
                            "logs": [
                                f"[WATCHER] detected {len(paths)} cleaned file change(s)",
                                "[WATCHER] build_memory() started immediately",
                            ],
                        },
                    }
                )
                await asyncio.to_thread(
                    build_memory,
                    cleaned_dir=str(self.cleaned_dir),
                    ontology_dir=self.ontology_dir,
                    memory_dir=self.memory_dir,
                )
                await self.hub.publish_snapshot(event_type="graph_delta", trigger=reason, changed_paths=paths)

    async def _watch_loop(self) -> None:
        await self.hub.publish(
            {
                "event_id": _event_id(),
                "event_type": "watcher_ready",
                "generated_at": utc_now_iso(),
                "learning_started_at": STREAM_STARTED_AT,
                "cumulative_learning_seconds": cumulative_learning_seconds(),
                "state": "ready",
                "stream": "sse_v1",
                "trigger": "lifespan_start",
                "nodes": [],
                "edges": [],
                "new_node_ids": [],
                "new_edge_keys": [],
                "ghost_shell": {
                    "system_state": "GHOST SHELL WATCHING",
                    "logs": [f"[WATCHER] monitoring {self.cleaned_dir.as_posix()}"],
                },
            }
        )
        while not self._stop.is_set():
            # EVENT-LOOP YIELD (2026-07-13): _scan_files (a synchronous directory stat-walk) and
            # trigger_build (SSE snapshot serialization) block the event loop — during a chat
            # request that stalls the request's awaits (measured ~0.87s live-vs-inprocess). Defer
            # the scan while a request is in flight so the loop stays free for the answer; the
            # file watcher is not latency-critical, a sub-second delay is invisible.
            try:
                from packages.graph_scale.load_signal import busy as _req_busy
                if _req_busy():
                    await asyncio.sleep(0.15)
                    continue
            except Exception:
                pass
            snapshot = _scan_files(self.cleaned_dir)
            changed = [
                path
                for path, fingerprint in snapshot.items()
                if path not in self._last_snapshot or self._last_snapshot[path] != fingerprint
            ]
            self._last_snapshot = snapshot
            if changed:
                await self.trigger_build(reason="cleaned_directory_change", changed_paths=changed)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.scan_interval_seconds)
            except asyncio.TimeoutError:
                continue


graph_event_hub = GraphEventHub()
cleaned_directory_watcher = CleanedDirectoryWatcher(hub=graph_event_hub)
