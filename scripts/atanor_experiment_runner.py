from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_BASE = "http://127.0.0.1:8500"
DOC_URL = "https://docs.google.com/document/d/1m9phn1au8DpfBP1X2S-teNYSh_AA5gc2UQulgebeLGs/edit?usp=drivesdk"
LOCAL_LOG = ROOT / "docs" / "experiment_log_0613.md"
RAW_DIR = ROOT / "data" / "raw"
DEFAULT_PYTHONPATH = os.pathsep.join(
    [
        "apps/api",
        "packages/rag_engine",
        "packages/guard",
        "packages/ontology_forge",
        "packages/datagate",
        "packages/knowledge_bakery",
        "packages/neuro_efficiency",
        "packages/trainer",
        "packages/model",
    ]
)


@dataclass
class HttpResult:
    ok: bool
    status: int | None
    body: Any
    error: str | None = None


def now_kst() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 12) -> HttpResult:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                body: Any = json.loads(raw)
            except json.JSONDecodeError:
                body = raw
            return HttpResult(ok=200 <= response.status < 300, status=response.status, body=body)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        return HttpResult(ok=False, status=exc.code, body=body, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - CLI diagnostics should not hide transport errors.
        return HttpResult(ok=False, status=None, body=None, error=str(exc))


def read_first_sse_event(url: str, timeout: int = 12) -> HttpResult:
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            lines: list[str] = []
            started = time.monotonic()
            while time.monotonic() - started < timeout:
                line = response.readline().decode("utf-8", errors="replace")
                if line == "":
                    break
                lines.append(line.rstrip("\r\n"))
                if line.strip() == "" and lines:
                    break
            event_text = "\n".join(lines)
            return HttpResult(
                ok=200 <= response.status < 300 and "event:" in event_text,
                status=response.status,
                body={
                    "content_type": response.headers.get("content-type"),
                    "first_event": event_text[:2000],
                },
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return HttpResult(ok=False, status=exc.code, body=raw, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        return HttpResult(ok=False, status=None, body=None, error=str(exc))


def powershell_json(command: str) -> Any:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    output = completed.stdout.strip()
    if completed.returncode != 0 or not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output


def find_port_pids(port: int) -> list[int]:
    if platform.system() == "Windows":
        command = (
            f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty OwningProcess -Unique | ConvertTo-Json -Compress"
        )
        data = powershell_json(command)
        if data is None:
            return []
        values = data if isinstance(data, list) else [data]
        return sorted({int(value) for value in values if str(value).isdigit()})
    completed = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=10)
    return sorted({int(line) for line in completed.stdout.splitlines() if line.strip().isdigit()})


def stop_process(pid: int) -> None:
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True, timeout=15)
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def restart_fastapi() -> subprocess.Popen[str]:
    for pid in find_port_pids(8500):
        stop_process(pid)
    time.sleep(1.5)
    env = os.environ.copy()
    env["PYTHONPATH"] = DEFAULT_PYTHONPATH
    creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8500"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        creationflags=creationflags,
    )
    wait_for_api()
    return process


def wait_for_api(timeout: int = 30) -> None:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        result = request_json("GET", f"{API_BASE}/api/pipeline/status", timeout=4)
        if result.ok:
            return
        time.sleep(1)
    raise RuntimeError("FastAPI companion did not become ready on 127.0.0.1:8500")


def launch_desktop_artifact() -> subprocess.Popen[str] | None:
    candidates = [
        ROOT / "src-tauri" / "target" / "release" / "atanor-desktop.exe",
        ROOT / "src-tauri" / "target" / "release" / "bundle" / "nsis" / "ATANOR_0.1.0_x64-setup.exe",
        ROOT / "src-tauri" / "target" / "release" / "bundle" / "msi" / "ATANOR_0.1.0_x64_en-US.msi",
        ROOT / "src-tauri" / "target" / "release" / "homage-desktop.exe",
    ]
    artifact = next((path for path in candidates if path.exists()), None)
    if artifact is None:
        return None
    if artifact.suffix.lower() == ".msi":
        return subprocess.Popen(["msiexec", "/i", str(artifact), "/passive"], cwd=ROOT)
    return subprocess.Popen([str(artifact)], cwd=ROOT)


def sample_process(pid: int | None) -> dict[str, Any]:
    if not pid:
        return {"pid": None, "state": "not_launched"}
    if platform.system() == "Windows":
        command = (
            f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
            "if ($p) { $p | Select-Object Id,ProcessName,CPU,WorkingSet64,PrivateMemorySize64,StartTime | ConvertTo-Json -Compress }"
        )
        return powershell_json(command) or {"pid": pid, "state": "not_found"}
    return {"pid": pid, "state": "sampling_not_implemented_for_platform"}


def write_high_density_payload(cycle: int) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"experiment_cycle_{cycle:03d}_neuro_symbolic_load.md"
    body = f"""# ATANOR Experiment Cycle {cycle} High Density Payload

ATANOR is a local-first neuro-symbolic hybrid AI engine. Hardware Adapter routes graph limits by RAM and VRAM tier.
SQLite WAL Mode protects the PayloadVault and GhostTopology during sudden reboot or blue-screen failure.
Generative Replay consolidates high-confidence working memory into long-term synaptic edges during idle windows.
Crash Safety Daemon checkpoints daemon_state.json, graph events, payload vault records, and memory snapshots.
GraphRAG activation should transform raw surface words into concept hashes, relations, and local synthesis context.
The intended abstraction layer separates lexical tokens, predicates, compound concepts, source quality, and edge confidence.
If the parser only stores repeated nouns, the cycle must be marked as a concept abstraction failure.
If graph_delta events append without canvas reset, the WebGL persistent buffer strategy is considered stable.
If the response generator copies fragments without concept-level synthesis, local generation quality is considered weak.

Relations:
- Hardware Adapter governs max graph nodes and batch size.
- SQLite WAL Mode protects PayloadVault persistence.
- Generative Replay strengthens useful synaptic edges.
- Crash Safety Daemon prevents data loss after restart.
- GhostTopology signals hashes before PayloadVault resolves raw text.
- LocalSynthesizer assembles Korean responses without external LLM APIs.
"""
    path.write_text(body, encoding="utf-8")
    return path


def summarize_json(value: Any, max_chars: int = 900) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2) if not isinstance(value, str) else value
    return text if len(text) <= max_chars else text[:max_chars] + "...(truncated)"


def append_local_log(markdown: str) -> None:
    LOCAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    if not LOCAL_LOG.exists():
        LOCAL_LOG.write_text(
            "# ATANOR Experiment Log 2026-06-13\n\n"
            f"Google Docs target: {DOC_URL}\n\n"
            "This file is the local fallback when Google Docs connector append is unavailable.\n\n",
            encoding="utf-8",
        )
    with LOCAL_LOG.open("a", encoding="utf-8") as handle:
        handle.write(markdown.rstrip() + "\n")


def cycle_log(
    cycle: int,
    started_at: str,
    ended_at: str,
    hypothesis: str,
    metrics: dict[str, Any],
    failure_reasons: list[str],
) -> str:
    status = "??쎈솭" if failure_reasons else "?源껊궗"
    return f"""
### [??쎈퓮 ?????#{cycle}] - 揶쎛????쇱젟 獄?野꺜筌?嚥≪뮄??* **??뽰삂 ??볦퍢:** {started_at}
* **?ル굝利???볦퍢:** {ended_at}

#### 1. 揶쎛????쇱젟 (Hypothesis)
* {hypothesis}

#### 2. 野꺜筌??⑥눘??獄?筌β돦???怨쀬뵠??(Verification & Metrics)
* ??쎈뻬 ?袁㏓럡/??띻펾: FastAPI 127.0.0.1:8500 / Tauri desktop artifact / Python automation runner
* ??뺤쒔/API ?怨밴묶:
```json
{summarize_json(metrics.get("api"))}
```
* 域밸챶?????쎈뱜??
```json
{summarize_json(metrics.get("graph_stream"))}
```
* ?귐딅꺖??
```json
{summarize_json(metrics.get("resources"))}
```
* ???뼓/??밴쉐 ??됱춳:
```json
{summarize_json(metrics.get("quality"))}
```
* ??살첒: {", ".join(failure_reasons) if failure_reasons else "??곸벉"}

#### 3. ?됰슢???獄???쇱벉 鈺곌퀣??(Briefing & Next Step)
* 野껉퀗???遺용튋: 揶쎛??{status}. ?紐껊굡/?節? ??쎈뱜?? daemon ?怨밴묶, 嚥≪뮇類???밴쉐 ?臾먮뼗??疫꿸퀣???곗쨮 ?癒?젟??덈뼄.
* 癰귣쵎?? {", ".join(failure_reasons) if failure_reasons else "?袁⑹삺 ?????곷퓠??筌앸맩??餓λ쵎???癰귣쵎??? 揶쏅Ŋ???? ??놁벉."}
* 筌ㅼ뮇?????뽯툧: ??쎈솭 ???????됱몵筌?????API/???쐭筌????뼓 野껋럥以덄몴???쇱벉 ?????곸벥 ??μ뵬 揶쎛??살쨮 野꺿뫖???뺣뼄.
--------------------------------------------------

"""


def run_cycle(cycle: int, launch_desktop: bool) -> tuple[str, bool]:
    started_at = now_kst()
    hypothesis = (
        "limit=50,000 ?怨밴묶?癒?퐣 FastAPI SSE, daemon status, GraphRAG query, "
        "WebGL persistent buffer ??낆젾 野껋럥以덂첎? 1,232+ ?紐껊굡/7,132+ ?癒? 域뱀뮆?덃틦?? wipe ??곸뵠 ?醫???뺣뼄."
    )
    metrics: dict[str, Any] = {"api": {}, "graph_stream": {}, "resources": {}, "quality": {}}
    failures: list[str] = []

    restart_fastapi()
    pipeline = request_json("GET", f"{API_BASE}/api/pipeline/status")
    daemon = request_json("GET", f"{API_BASE}/api/learning/daemon/status")
    sse = read_first_sse_event(f"{API_BASE}/api/graph/events?limit=50000")
    metrics["api"] = {
        "pipeline_status": pipeline.status,
        "pipeline_state": pipeline.body.get("system_state") if isinstance(pipeline.body, dict) else None,
        "daemon_status": daemon.status,
        "daemon_state": daemon.body.get("state") if isinstance(daemon.body, dict) else None,
    }
    metrics["graph_stream"] = sse.body if isinstance(sse.body, dict) else {"error": sse.error, "body": sse.body}
    if not pipeline.ok or metrics["api"]["pipeline_state"] != "alpha_active":
        failures.append("pipeline_status_not_alpha_active")
    if not sse.ok:
        failures.append(f"sse_limit_50000_failed:{sse.status}:{sse.error}")

    desktop_process = launch_desktop_artifact() if launch_desktop else None
    time.sleep(3 if desktop_process else 0)
    metrics["resources"]["desktop_process"] = sample_process(desktop_process.pid if desktop_process else None)

    payload_path = write_high_density_payload(cycle)
    tick = request_json("POST", f"{API_BASE}/api/learning/daemon/tick", {"force": True, "run_decay": True}, timeout=30)
    graph = request_json("GET", f"{API_BASE}/api/graph/subgraph?limit=50000", timeout=20)
    metrics["graph_stream"]["payload_file"] = str(payload_path.relative_to(ROOT))
    metrics["graph_stream"]["tick_status"] = tick.status
    if isinstance(graph.body, dict):
        metrics["graph_stream"]["node_count"] = len(graph.body.get("nodes", []))
        metrics["graph_stream"]["edge_count"] = len(graph.body.get("edges", []))
    if graph.status == 422:
        failures.append("graph_subgraph_limit_50000_returned_422")
    questions = ["안녕", "GraphRAG가 뭐야", "ATANOR 구조 설명해줘", "유재석이 누구야"]
    answers: list[dict[str, Any]] = []
    for question in questions:
        result = request_json("POST", f"{API_BASE}/api/graphrag/query", {"query": question, "web_search": False}, timeout=30)
        answers.append({"query": question, "status": result.status, "body": result.body})
        if not result.ok:
            failures.append(f"graphrag_query_failed:{question}:{result.status}")
    metrics["quality"]["fixed_question_set"] = answers
    metrics["quality"]["surface_copy_warning"] = "manual_review_required"

    if desktop_process and desktop_process.poll() is not None:
        failures.append(f"desktop_process_exited:{desktop_process.returncode}")
    ended_at = now_kst()
    return cycle_log(cycle, started_at, ended_at, hypothesis, metrics, failures), not failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ATANOR long-run stability and graph quality experiment cycles.")
    parser.add_argument("--cycles", type=int, default=1, help="Maximum experiment cycles to run.")
    parser.add_argument("--launch-desktop", action="store_true", help="Launch the Tauri desktop artifact during each cycle.")
    parser.add_argument("--continue-on-failure", action="store_true", help="Continue running cycles after a failed cycle.")
    args = parser.parse_args()

    LOCAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    print(f"Google Docs target: {DOC_URL}")
    print(f"Local fallback log: {LOCAL_LOG}")
    for cycle in range(1, args.cycles + 1):
        markdown, ok = run_cycle(cycle, launch_desktop=args.launch_desktop)
        append_local_log(markdown)
        print(markdown)
        if not ok and not args.continue_on_failure:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
