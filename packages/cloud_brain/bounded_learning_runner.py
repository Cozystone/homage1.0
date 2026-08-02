from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
from typing import Any, Iterable

try:  # psutil is optional; the runner must still enforce non-psutil caps.
    import psutil  # type: ignore
except Exception:  # pragma: no cover - exercised when psutil is absent.
    psutil = None  # type: ignore

from .continuous_learning import CloudSurfaceLearningLoop
from .source_capacity_planner import plan_source_capacity
from .verified_payload_feeder import LearningPayload, PayloadSourcePolicy, VerifiedPayloadFeeder, payload_from_mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT_DIR = PROJECT_ROOT / "data" / "audits" / "bounded_learning_runner"
DEFAULT_TARGET_STORE = Path(tempfile.gettempdir()) / "atanor_bounded_cloud_surface_candidate"


def utc_now() -> str:
    """Return a compact UTC timestamp."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _folder_stats(path: Path) -> tuple[float, int]:
    """Return folder size in MiB and number of files."""

    if not path.exists():
        return 0.0, 0
    total = 0
    count = 0
    for item in path.rglob("*"):
        if item.is_file():
            count += 1
            total += item.stat().st_size
    return total / 1024 / 1024, count


def _disk_free_gb(path: Path) -> float:
    """Return free disk space for the filesystem containing ``path``."""

    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    if psutil is not None:
        usage = psutil.disk_usage(str(probe))
        return float(usage.free / 1024 / 1024 / 1024)
    drive = Path(probe.anchor or ".")
    try:
        import shutil

        usage = shutil.disk_usage(drive)
        return float(usage.free / 1024 / 1024 / 1024)
    except Exception:
        return float("inf")


@dataclass(frozen=True)
class BoundedLearningRunConfig:
    """Resource and safety caps for one candidate-only bounded run."""

    profile: str = "interactive_safe"
    max_payloads: int | None = None
    max_seconds: int | None = None
    max_store_mb: float | None = None
    min_ram_free_gb: float = 8.0
    min_disk_free_gb: float = 40.0
    max_cpu_percent: float | None = None
    max_candidate_files: int | None = None
    target_candidate_store: str = str(DEFAULT_TARGET_STORE)
    promote_to_verified: bool = False
    update_surface_graph: bool = True
    update_cgsr: bool = True
    update_rhfc_candidate: bool = True
    require_review_before_production: bool = True
    dry_run: bool = True
    execute: bool = False
    batch_size: int | None = None
    target_payloads_per_second: float | None = None
    target_duration_seconds: int | None = None
    min_source_rows_for_target_duration: int | None = None
    pacing_mode: str = "none"
    checkpoint_interval_seconds: int | None = None
    status_interval_seconds: int | None = None

    def normalized(self) -> "BoundedLearningRunConfig":
        """Return this config with conservative profile defaults filled in."""

        defaults = {
            "interactive_safe": {
                "max_payloads": 1000,
                "max_seconds": 300,
                "max_store_mb": 256.0,
                "max_cpu_percent": 70.0,
                "max_candidate_files": 64,
                "batch_size": 100,
                "min_disk_free_gb": 40.0,
                "min_ram_free_gb": 8.0,
            },
            "24h_balanced": {
                "max_payloads": 50_000,
                "max_seconds": 3600,
                "max_store_mb": 1024.0,
                "max_cpu_percent": 80.0,
                "max_candidate_files": 96,
                "batch_size": 250,
                "min_disk_free_gb": 80.0,
                "min_ram_free_gb": 8.0,
            },
            "night_max": {
                "max_payloads": 200_000,
                "max_seconds": 7200,
                "max_store_mb": 4096.0,
                "max_cpu_percent": 92.0,
                "max_candidate_files": 128,
                "batch_size": 500,
                "min_disk_free_gb": 80.0,
                "min_ram_free_gb": 6.0,
            },
        }
        values = defaults.get(self.profile, defaults["interactive_safe"])
        payload = asdict(self)
        for key, value in values.items():
            if payload.get(key) is None:
                payload[key] = value
        if self.profile not in defaults:
            payload["profile"] = "interactive_safe"
        if payload.get("pacing_mode") not in {"none", "sleep_between_batches", "token_bucket"}:
            payload["pacing_mode"] = "none"
        return BoundedLearningRunConfig(**payload)


@dataclass(frozen=True)
class ResourceSnapshot:
    """One lightweight resource pressure sample."""

    timestamp: str
    ram_free_gb: float | None
    disk_free_gb: float
    process_memory_mb: float | None
    candidate_store_mb: float
    candidate_file_count: int
    cpu_percent: float | None
    queue_depth: int = 0
    writer_backlog: int = 0
    pressure_state: str = "ok"
    throttle_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BoundedLearningRunResult:
    """Summary of one bounded candidate-only run."""

    state: str
    stop_reason: str
    elapsed_seconds: float
    payloads_seen: int = 0
    payloads_accepted: int = 0
    payloads_rejected: int = 0
    accepted_per_second: float = 0.0
    concepts_added_candidate: int = 0
    relations_added_candidate: int = 0
    evidence_added_candidate: int = 0
    case_frames_added_candidate: int = 0
    surface_candidates: int = 0
    cgsr_frames: int = 0
    rhfc_candidates: int = 0
    candidate_store_mb: float = 0.0
    resource_samples: list[ResourceSnapshot] = field(default_factory=list)
    invariants: dict[str, Any] = field(default_factory=dict)
    production_store_mutated: bool = False
    local_brain_write: bool = False
    false_confident: int = 0
    forgetting_count: int = 0
    unsupported_claims: int = 0
    target_payloads_per_second: float | None = None
    target_duration_seconds: int | None = None
    source_capacity_plan: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["resource_samples"] = [sample.to_dict() for sample in self.resource_samples]
        return payload


class ResourcePressureMonitor:
    """Measure and classify resource pressure for a candidate-only run."""

    def __init__(self, config: BoundedLearningRunConfig, *, started_at: float | None = None) -> None:
        self.config = config.normalized()
        self.started_at = started_at if started_at is not None else time.perf_counter()
        self.process = psutil.Process() if psutil is not None else None

    def sample(self, *, payloads_seen: int = 0, candidate_store: str | Path | None = None) -> ResourceSnapshot:
        """Return current resource pressure, degrading gracefully without psutil."""

        target = Path(candidate_store or self.config.target_candidate_store)
        store_mb, file_count = _folder_stats(target)
        ram_free_gb: float | None = None
        process_mb: float | None = None
        cpu_percent: float | None = None
        if psutil is not None:
            ram_free_gb = float(psutil.virtual_memory().available / 1024 / 1024 / 1024)
            if self.process is not None:
                process_mb = float(self.process.memory_info().rss / 1024 / 1024)
            cpu_percent = float(psutil.cpu_percent(interval=None))
        disk_free_gb = _disk_free_gb(target)
        reason = ""
        state = "ok"
        if ram_free_gb is not None and ram_free_gb < self.config.min_ram_free_gb:
            state = "paused"
            reason = "ram_pressure"
        elif disk_free_gb < self.config.min_disk_free_gb:
            state = "paused"
            reason = "disk_pressure"
        elif self.config.max_store_mb is not None and store_mb > self.config.max_store_mb:
            state = "paused"
            reason = "store_cap_reached"
        elif self.config.max_candidate_files is not None and file_count > self.config.max_candidate_files:
            state = "paused"
            reason = "candidate_file_cap_reached"
        elif self.config.max_cpu_percent is not None and cpu_percent is not None and cpu_percent > self.config.max_cpu_percent:
            state = "throttled"
            reason = "cpu_pressure"
        return ResourceSnapshot(
            timestamp=utc_now(),
            ram_free_gb=ram_free_gb,
            disk_free_gb=disk_free_gb,
            process_memory_mb=process_mb,
            candidate_store_mb=store_mb,
            candidate_file_count=file_count,
            cpu_percent=cpu_percent,
            queue_depth=0,
            writer_backlog=0,
            pressure_state=state,
            throttle_reason=reason,
        )

    def terminal_reason(self, *, payloads_seen: int, accepted: int, sample: ResourceSnapshot) -> str | None:
        """Return a terminal stop reason if a configured cap has fired."""

        elapsed = time.perf_counter() - self.started_at
        if sample.pressure_state == "paused":
            return sample.throttle_reason or "resource_pressure"
        if self.config.max_seconds is not None and elapsed >= self.config.max_seconds:
            return "time_cap_reached"
        if self.config.max_payloads is not None and payloads_seen >= self.config.max_payloads:
            return "payload_cap_reached"
        return None


def _empty_invariants() -> dict[str, Any]:
    return {
        "production_store_mutated": False,
        "local_brain_write": False,
        "false_confident": 0,
        "forgetting_count": 0,
        "eval_rows_used_for_learning": False,
        "external_llm_used": False,
        "mock_growth": False,
        "pair_edges_sent": 0,
        "private_data_used_for_cloud_learning": False,
        "unsupported_claims": 0,
    }


def _source_capacity_plan_for_config(cfg: BoundedLearningRunConfig, source_rows: int) -> dict[str, Any]:
    """Return a source-capacity plan when long-duration pacing is requested."""

    if cfg.target_payloads_per_second is None or cfg.target_duration_seconds is None:
        return {}
    return plan_source_capacity(
        source_rows=source_rows,
        accepted_estimate=source_rows,
        target_duration_seconds=int(cfg.target_duration_seconds),
        target_payloads_per_second=float(cfg.target_payloads_per_second),
        min_payloads_required=cfg.min_source_rows_for_target_duration,
        candidate_store_cap_mb=cfg.max_store_mb,
    ).to_dict()


def _pace_after_batch(
    cfg: BoundedLearningRunConfig,
    *,
    started: float,
    payloads_seen: int,
    batch_payloads: int,
) -> None:
    """Spend real wall-clock time so ingestion does not exceed the target rate.

    Pacing never fabricates accepted rows; it only sleeps. Two honest modes are
    supported:

    * ``sleep_between_batches`` reserves each batch's full time budget
      (``batch_payloads / target_rate``) as a deterministic gap after the batch.
      This yields the machine between batches and keeps the observed rate at or
      below target even when real ingestion is *slower* than the target rate, so
      the gap is applied regardless of how long ``run_once`` took.
    * ``token_bucket`` is an adaptive throttle that only sleeps when the run is
      running *ahead* of the cumulative target schedule; it never slows a run
      that is already at or below the target rate.
    """

    if cfg.pacing_mode == "none" or cfg.target_payloads_per_second is None:
        return
    target_rate = float(cfg.target_payloads_per_second)
    if target_rate <= 0 or payloads_seen <= 0 or batch_payloads <= 0:
        return
    if cfg.pacing_mode == "sleep_between_batches":
        delay = batch_payloads / target_rate
    else:  # token_bucket: catch-up only, never slow a run that is already on pace.
        target_elapsed = payloads_seen / target_rate
        actual_elapsed = time.perf_counter() - started
        delay = target_elapsed - actual_elapsed
    if delay > 0:
        time.sleep(delay)


def _invariant_failure(result: dict[str, Any]) -> str | None:
    invariants = result.get("invariants") or {}
    checks = {
        "production_store_mutated": result.get("production_store_mutated") is False,
        "local_brain_write": invariants.get("local_brain_write") is False,
        "false_confident": int(result.get("false_confident") or 0) == 0,
        "forgetting_count": int(result.get("forgetting_count") or 0) == 0,
        "eval_rows_used_for_learning": invariants.get("eval_rows_used_for_learning") is False,
        "external_llm_used": invariants.get("external_llm_used_for_reasoning") is False,
        "mock_growth": invariants.get("mock_growth") is False,
        "pair_edges_sent": int(result.get("pair_edges_sent") or 0) == 0,
        "private_data_used_for_cloud_learning": result.get("private_data_used_for_cloud_learning") is False,
        "unsupported_claims": int((result.get("surface") or {}).get("unsupported_claims") or 0) == 0,
    }
    for key, ok in checks.items():
        if not ok:
            return f"invariant_failure:{key}"
    return None


def run_bounded_candidate_learning(
    config: BoundedLearningRunConfig,
    *,
    payloads: Iterable[LearningPayload] | None = None,
    feeder: VerifiedPayloadFeeder | None = None,
) -> BoundedLearningRunResult:
    """Run candidate-only learning with hard resource and safety caps."""

    cfg = config.normalized()
    started = time.perf_counter()
    monitor = ResourcePressureMonitor(cfg, started_at=started)
    first_sample = monitor.sample(candidate_store=cfg.target_candidate_store)
    if cfg.promote_to_verified:
        return BoundedLearningRunResult(
            state="failed",
            stop_reason="production_promotion_rejected",
            elapsed_seconds=0.0,
            resource_samples=[first_sample],
            invariants=_empty_invariants(),
        )
    if not cfg.execute or cfg.dry_run:
        reason = "execute_required" if not cfg.execute else "dry_run"
        if first_sample.pressure_state == "paused":
            reason = first_sample.throttle_reason or reason
        return BoundedLearningRunResult(
            state="paused" if first_sample.pressure_state == "paused" else "dry_run",
            stop_reason=reason,
            elapsed_seconds=round(time.perf_counter() - started, 6),
            candidate_store_mb=first_sample.candidate_store_mb,
            resource_samples=[first_sample],
            invariants=_empty_invariants(),
        )
    if first_sample.pressure_state == "paused":
        return BoundedLearningRunResult(
            state="paused",
            stop_reason=first_sample.throttle_reason or "resource_pressure",
            elapsed_seconds=round(time.perf_counter() - started, 6),
            candidate_store_mb=first_sample.candidate_store_mb,
            resource_samples=[first_sample],
            invariants=_empty_invariants(),
        )

    if payloads is None:
        payload_rows = (feeder or VerifiedPayloadFeeder(policy=PayloadSourcePolicy())).run_once().payloads
    else:
        payload_rows = list(payloads)
    original_payload_count = len(payload_rows)
    source_capacity_plan = _source_capacity_plan_for_config(cfg, original_payload_count)
    if source_capacity_plan and not bool(source_capacity_plan.get("can_run_full_duration")):
        return BoundedLearningRunResult(
            state="paused",
            stop_reason="insufficient_source_rows_for_target_duration",
            elapsed_seconds=round(time.perf_counter() - started, 6),
            candidate_store_mb=first_sample.candidate_store_mb,
            resource_samples=[first_sample],
            invariants=_empty_invariants(),
            source_capacity_plan=source_capacity_plan,
            target_payloads_per_second=cfg.target_payloads_per_second,
            target_duration_seconds=cfg.target_duration_seconds,
        )
    if cfg.max_payloads is not None:
        payload_rows = payload_rows[: cfg.max_payloads]

    batch_size = max(1, int(cfg.batch_size or 100))
    loop = CloudSurfaceLearningLoop(
        candidate_store_root=cfg.target_candidate_store,
        promote_to_verified=False,
        update_surface_graph=cfg.update_surface_graph,
        update_rhfc_candidate=cfg.update_rhfc_candidate,
        require_review_before_production=cfg.require_review_before_production,
    )
    samples = [first_sample]
    totals = {
        "seen": 0,
        "accepted": 0,
        "rejected": 0,
        "concepts": 0,
        "relations": 0,
        "evidence": 0,
        "case_frames": 0,
        "surface": 0,
        "cgsr": 0,
        "rhfc": 0,
    }
    final_invariants = _empty_invariants()
    stop_reason = "no_payloads"
    state = "completed"
    index = 0
    while index < len(payload_rows):
        sample = monitor.sample(payloads_seen=totals["seen"], candidate_store=cfg.target_candidate_store)
        samples.append(sample)
        terminal = monitor.terminal_reason(payloads_seen=totals["seen"], accepted=totals["accepted"], sample=sample)
        if terminal:
            stop_reason = terminal
            state = "completed" if terminal in {"payload_cap_reached", "time_cap_reached"} else "paused"
            break
        batch = payload_rows[index : index + batch_size]
        result = loop.run_once(payloads=batch, max_accepted_per_run=len(batch), dry_run=False).to_dict()
        failure = _invariant_failure(result)
        if failure:
            final_invariants = result.get("invariants") or final_invariants
            stop_reason = failure
            state = "failed"
            break
        semantic = result.get("semantic") or {}
        surface = result.get("surface") or {}
        cgsr = result.get("cgsr_rhfc") or {}
        totals["seen"] += int(semantic.get("payloads_seen") or len(batch))
        totals["accepted"] += int(semantic.get("payloads_accepted") or 0)
        totals["rejected"] += int(semantic.get("payloads_rejected") or 0)
        totals["concepts"] += int(semantic.get("concepts_added") or 0)
        totals["relations"] += int(semantic.get("relations_added") or 0)
        totals["evidence"] += int(semantic.get("evidence_added") or 0)
        totals["case_frames"] += int(semantic.get("case_frames_added") or 0)
        totals["surface"] += int(surface.get("accepted_surface_candidates") or 0)
        totals["cgsr"] += int(cgsr.get("frames_added") or 0)
        totals["rhfc"] += int(cgsr.get("rhfc_candidates_added") or 0)
        final_invariants = result.get("invariants") or final_invariants
        index += len(batch)
        _pace_after_batch(cfg, started=started, payloads_seen=totals["seen"], batch_payloads=len(batch))
        post_batch_sample = monitor.sample(payloads_seen=totals["seen"], candidate_store=cfg.target_candidate_store)
        samples.append(post_batch_sample)
        post_batch_terminal = monitor.terminal_reason(
            payloads_seen=totals["seen"],
            accepted=totals["accepted"],
            sample=post_batch_sample,
        )
        if post_batch_terminal:
            stop_reason = post_batch_terminal
            state = "completed" if post_batch_terminal in {"payload_cap_reached", "time_cap_reached"} else "paused"
            break
    else:
        if cfg.max_payloads is not None and original_payload_count >= cfg.max_payloads and totals["seen"] >= cfg.max_payloads:
            stop_reason = "payload_cap_reached"
        else:
            stop_reason = "payloads_exhausted" if payload_rows else "no_payloads"
        state = "completed"

    final_sample = monitor.sample(payloads_seen=totals["seen"], candidate_store=cfg.target_candidate_store)
    samples.append(final_sample)
    elapsed = time.perf_counter() - started
    accepted_per_second = totals["accepted"] / elapsed if elapsed > 0 else 0.0
    return BoundedLearningRunResult(
        state=state,
        stop_reason=stop_reason,
        elapsed_seconds=round(elapsed, 6),
        payloads_seen=totals["seen"],
        payloads_accepted=totals["accepted"],
        payloads_rejected=totals["rejected"],
        accepted_per_second=accepted_per_second,
        concepts_added_candidate=totals["concepts"],
        relations_added_candidate=totals["relations"],
        evidence_added_candidate=totals["evidence"],
        case_frames_added_candidate=totals["case_frames"],
        surface_candidates=totals["surface"],
        cgsr_frames=totals["cgsr"],
        rhfc_candidates=totals["rhfc"],
        candidate_store_mb=final_sample.candidate_store_mb,
        resource_samples=samples,
        invariants=final_invariants,
        production_store_mutated=False,
        local_brain_write=False,
        false_confident=int(final_invariants.get("false_confident") or 0),
        forgetting_count=int(final_invariants.get("forgetting_count") or 0),
        unsupported_claims=0,
        target_payloads_per_second=cfg.target_payloads_per_second,
        target_duration_seconds=cfg.target_duration_seconds,
        source_capacity_plan=source_capacity_plan,
    )


def assess_24h_readiness(
    *,
    profile: str = "24h_balanced",
    target_candidate_store: str | Path = DEFAULT_TARGET_STORE,
    measured_accepted_per_second: float = 196.97,
    measured_store_mb_per_payload: float = 22.62 / 5000,
) -> dict[str, Any]:
    """Return a conservative 24h readiness recommendation."""

    cfg = BoundedLearningRunConfig(profile=profile, target_candidate_store=str(target_candidate_store)).normalized()
    sample = ResourcePressureMonitor(cfg).sample(candidate_store=cfg.target_candidate_store)
    enough_ram = sample.ram_free_gb is None or sample.ram_free_gb >= cfg.min_ram_free_gb
    enough_disk = sample.disk_free_gb >= cfg.min_disk_free_gb
    projected_payloads = int(measured_accepted_per_second * 86400)
    projected_store_mb = projected_payloads * measured_store_mb_per_payload
    store_cap_ok = cfg.max_store_mb is not None and cfg.max_store_mb <= max(0.0, (sample.disk_free_gb - cfg.min_disk_free_gb) * 1024)
    safe = bool(enough_ram and enough_disk and store_cap_ok)
    reason = "ready" if safe else "resource_caps_not_met"
    if not enough_ram:
        reason = "ram_below_profile_minimum"
    elif not enough_disk:
        reason = "disk_below_profile_minimum"
    elif not store_cap_ok:
        reason = "store_cap_exceeds_safe_disk_budget"
    return {
        "timestamp": utc_now(),
        "profile": cfg.profile,
        "current_ram_free_gb": sample.ram_free_gb,
        "current_disk_free_gb": sample.disk_free_gb,
        "measured_accepted_per_second": measured_accepted_per_second,
        "safe_accepted_per_second_target": min(measured_accepted_per_second, 25.0 if cfg.profile == "interactive_safe" else 75.0),
        "recommended_profile": cfg.profile if safe else "interactive_safe",
        "recommended_max_payloads": cfg.max_payloads,
        "recommended_max_store_mb": cfg.max_store_mb,
        "recommended_min_ram_free_gb": cfg.min_ram_free_gb,
        "recommended_min_disk_free_gb": cfg.min_disk_free_gb,
        "projected_full_speed_payloads_24h": projected_payloads,
        "projected_full_speed_store_mb_24h": round(projected_store_mb, 3),
        "safe_to_start_24h_candidate_run": safe,
        "reason": reason,
        "resource_snapshot": sample.to_dict(),
    }


def write_runner_report(name: str, payload: dict[str, Any], *, audit_dir: str | Path = DEFAULT_AUDIT_DIR) -> Path:
    """Write a bounded runner JSON/MD report and return the JSON path."""

    root = Path(audit_dir)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = root / f"{name}_{stamp}.json"
    md_path = root / f"{name}_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                f"# {name}",
                f"- State: `{payload.get('state') or payload.get('verdict') or 'n/a'}`",
                f"- Stop reason: `{payload.get('stop_reason') or payload.get('reason') or 'n/a'}`",
                f"- Safe to start 24h: `{payload.get('safe_to_start_24h_candidate_run', False)}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return json_path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded candidate-only Cloud Surface learning.")
    parser.add_argument("--profile", default="interactive_safe", choices=["interactive_safe", "24h_balanced", "night_max"])
    parser.add_argument("--max-payloads", type=int, default=None)
    parser.add_argument("--max-seconds", type=int, default=None)
    parser.add_argument("--max-store-mb", type=float, default=None)
    parser.add_argument("--min-ram-free-gb", type=float, default=8.0)
    parser.add_argument("--min-disk-free-gb", type=float, default=40.0)
    parser.add_argument("--max-cpu-percent", type=float, default=None)
    parser.add_argument("--target-candidate-store", default=str(DEFAULT_TARGET_STORE))
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--execute", action="store_true", default=False)
    parser.add_argument("--payload-file", default=None)
    parser.add_argument("--target-payloads-per-second", type=float, default=None)
    parser.add_argument("--target-duration-seconds", type=int, default=None)
    parser.add_argument("--min-source-rows-for-target-duration", type=int, default=None)
    parser.add_argument("--pacing-mode", default="none", choices=["none", "sleep_between_batches", "token_bucket"])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for the bounded runner."""

    args = _parse_args(argv)
    dry_run = True if not args.execute else bool(args.dry_run)
    config = BoundedLearningRunConfig(
        profile=args.profile,
        max_payloads=args.max_payloads,
        max_seconds=args.max_seconds,
        max_store_mb=args.max_store_mb,
        min_ram_free_gb=args.min_ram_free_gb,
        min_disk_free_gb=args.min_disk_free_gb,
        max_cpu_percent=args.max_cpu_percent,
        target_candidate_store=args.target_candidate_store,
        dry_run=dry_run,
        execute=bool(args.execute),
        target_payloads_per_second=args.target_payloads_per_second,
        target_duration_seconds=args.target_duration_seconds,
        min_source_rows_for_target_duration=args.min_source_rows_for_target_duration,
        pacing_mode=args.pacing_mode,
    )
    payloads: list[LearningPayload] | None = None
    if args.payload_file:
        rows = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
        payloads = [payload_from_mapping(row) for row in rows]
    if args.execute:
        print("WARNING: executing bounded candidate-only learning. Production promotion remains disabled.")
    result = run_bounded_candidate_learning(config, payloads=payloads)
    report = result.to_dict()
    report_path = write_runner_report("bounded_learning_run", report)
    print(json.dumps({"report": str(report_path), **report}, ensure_ascii=False, indent=2))
    return 0 if result.state in {"completed", "dry_run", "paused"} else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
