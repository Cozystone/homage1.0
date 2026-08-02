# -*- coding: utf-8 -*-
"""P0 sentinel — the unattended answer-quality parole officer.

Owner (2026-07-11): " ... ." The diet-flood P0 regression was
only caught because an operator happened to run the battery. Unattended, a flood could pollute
for hours. This sentinel makes acceleration SAFE to run without a babysitter: it fires a small
CANARY of P0-critical questions every few minutes, and the moment answer quality regresses it
(a) FREEZES learning (touch data/autonomy/LEARNING_FROZEN — the learner idles, answer path
untouched), (b) runs a pack-purity audit, and (c) writes an alert the /ops dashboard surfaces.
When the canary passes again it thaws learning automatically.

Because the sentinel guards the sanctuary, the diet can be pushed FASTER with confidence — a
regression is caught in minutes and contained, not discovered hours later.

 python scripts/p0_sentinel.py # loop (watchdog-managed service)
 python scripts/p0_sentinel.py --once # single canary check, print + exit
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENGINE = os.getenv("ATANOR_BATTERY_BASE", "http://127.0.0.1:8502")
FREEZE_FLAG = REPO / "data" / "autonomy" / "LEARNING_FROZEN"
STATUS = REPO / "data" / "autonomy" / "p0_sentinel_status.json"
INTERVAL_S = int(os.getenv("ATANOR_SENTINEL_INTERVAL_SEC", "900") or 900)   # 15 min default



CANARIES = [
    ("물은 무엇으로 이루어져 있어?", r"수소|산소", None),
    ("상대성이론이 뭐야?", r"아인슈타인|물리학", None),
    ("DNA가 뭐야?", r"뉴클레오|유전|이중나선", None),
    ("세종대왕이 만든 것은 뭐야?", r"한글|훈민정음", None),
    ("한글을 만든 사람은 누구야?", r"세종", None),
    ("대한민국의 수도는 부산이야?", r"아니|서울|틀", r"부산(입니다|이 맞)"),
    ("커피가 뭐야?", r"카페인|커피", None),
    ("물이 뭐야?", r"액체|화합물|수소|물질", None),
]


def _ask(q: str) -> str:
    body = json.dumps({"message": q, "conversation_context": []}).encode("utf-8")
    req = urllib.request.Request(ENGINE + "/api/chat/atanor", data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=40) as r:      # nosec B310 - localhost engine
        out = json.loads(r.read().decode("utf-8"))
    res = out.get("result") if isinstance(out, dict) else out
    return str((res or {}).get("answer") or "")


def _check() -> dict:
    # Each fail is tagged by KIND so the guardian can tell a CONTENT regression (a real wrong answer
    # → freeze) from an INFRA hiccup (engine cold/slow/down, empty answer → do NOT freeze; the
    # learner isn't the cause). Conflating them once flipped a scary RED + freeze the moment the
    # engine was cold right after a restart, though nothing had regressed.
    fails = []
    for q, must, must_not in CANARIES:
        try:
            a = _ask(q)
        except Exception as e:
            fails.append({"q": q, "kind": "engine_error", "why": f"engine error: {type(e).__name__}"})
            continue
        if not a.strip():
            fails.append({"q": q, "kind": "engine_error", "why": "empty answer (engine cold / abstained)"})
        elif not re.search(must, a):
            fails.append({"q": q, "kind": "wrong_answer", "why": f"missing /{must}/", "answer": a[:80]})
        elif must_not and re.search(must_not, a):
            fails.append({"q": q, "kind": "wrong_answer", "why": f"hit forbidden /{must_not}/", "answer": a[:80]})
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "total": len(CANARIES),
            "passed": len(CANARIES) - len(fails), "fails": fails, "ok": not fails}


def _purity_audit() -> str:
    try:
        out = subprocess.run([sys.executable, str(REPO / "scripts" / "pack_purity.py"), "audit"],
                             capture_output=True, text=True, timeout=60,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return out.splitlines()[1] if len(out.splitlines()) > 1 else out[:120]
    except Exception as e:
        return f"audit failed: {e}"


def _write(status: dict) -> None:
    try:
        STATUS.parent.mkdir(parents=True, exist_ok=True)
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception:
        pass


def _run_once() -> dict:
    r = _check()
    wrong = [f for f in r["fails"] if f.get("kind") == "wrong_answer"]
    if r["ok"]:
        # thaw: a passing canary clears any freeze this sentinel set
        if FREEZE_FLAG.exists():
            try:
                FREEZE_FLAG.unlink()
                r["action"] = "thawed learning (canary green again)"
            except Exception:
                pass
        r["state"] = "GREEN"
    elif wrong:
        # a REAL content regression (a wrong answer, not just a slow/cold engine) → freeze &
        # contain the flood, don't wait for an operator. This is the only path that freezes.
        try:
            FREEZE_FLAG.parent.mkdir(parents=True, exist_ok=True)
            FREEZE_FLAG.write_text(r["at"], encoding="utf-8")
        except Exception:
            pass
        r["state"] = "RED"
        r["action"] = f"FROZE learning; {len(wrong)} real answer regression(s) — run pack_purity.py"
        r["purity_audit"] = _purity_audit()
    else:
        # only INFRA failures (engine cold/slow/down) — NOT a content regression. Freezing the
        # learner wouldn't help (it isn't the cause) and would false-alarm the operator. Report a
        # transient, self-clearing DEGRADED; leave learning running.
        r["state"] = "DEGRADED"
        r["action"] = "engine unavailable/slow — transient, not a regression; learning left running"
    _write(r)
    return r


def _start_health_server() -> None:
    # tiny localhost health endpoint so the shared watchdog can supervise this like any service
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b'{"ok": true, "service": "atanor-p0-sentinel"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a):
            pass

    import threading
    threading.Thread(target=lambda: ThreadingHTTPServer(("127.0.0.1", 8511), _H).serve_forever(),
                     daemon=True).start()


def main() -> None:
    if "--once" in sys.argv:
        print(json.dumps(_run_once(), ensure_ascii=False, indent=2))
        return
    try:
        _start_health_server()
    except Exception:
        pass
    # let the engine finish cold-loading before the first canary (a cold miss ≠ regression)
    time.sleep(int(os.getenv("ATANOR_SENTINEL_WARMUP_SEC", "90") or 90))
    while True:
        try:
            r = _run_once()
            print(f"[{r['at']}] sentinel {r['state']} {r['passed']}/{r['total']}"
                  + (f" — {r.get('action','')}" if not r["ok"] else ""), flush=True)
        except Exception as e:
            print(f"sentinel error: {e}", flush=True)
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
