# -*- coding: utf-8 -*-
"""Advisor session — the CLI channel to frontier minds (claude / codex / ollama), constitution on.

Every reply is untrusted observed DATA: injection-scanned, hashed, and journaled (question, advisor,
reply, findings, ts) to the advisor ledger on the ONE timeline. Nothing here executes advice —
execution lives behind patch_intake + the auto_self_modification gate. Cost discipline: local
ollama is the unlimited default; paid CLIs take an explicit budget of calls per run.

Transports are subprocess CLIs so the same code drives any advisor that ships one; a MockAdvisor
keeps the tests deterministic and free.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from packages.brain_link.protocol import scan_message_text

# streaming CLIs (ollama) emit ANSI cursor/erase codes; strip them so the journaled reply is the
# text, not the terminal choreography
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07|[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(text: str) -> str:
    return _ANSI.sub("", text or "").strip()

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "advisor_loop" / "sessions.jsonl"

# openclaw ships as a cmd.exe shim (.cmd), and a batch line ends at a NEWLINE: everything in the
# -m text after the first '\n' is silently eaten in transit (empirically verified by an echo probe:
# a 4-line fenced block arrived as '0 lines'). cmd also mishandles backslash-escaped quotes, after
# which '>' becomes redirection. Fix at the TRANSPORT: flatten newlines to a visible '⏎' token and
# swap cmd metacharacters for safe lookalikes — meaning preserved, one unbreakable line.
_CMD_SAFE = str.maketrans({'"': "'", "<": "‹", ">": "›", "|": "¦", "&": "+", "^": "ˆ", "%": "％"})


def _openclaw_safe(prompt: str) -> str:
    flat = prompt.replace("\r", "").replace("\n", " ⏎ ")
    return flat.translate(_CMD_SAFE)


# advisor name -> argv builder (prompt appended last). Headless, non-interactive flags only.
# openclaw's 'main' agent is backed by openai-codex/gpt-5.4 — a real GPT-5.4 advisor.
CLI_ADVISORS: dict[str, Callable[[str], list[str]]] = {
    "ollama": lambda prompt: ["ollama", "run", "dolphin3:latest", prompt],
    "claude": lambda prompt: ["claude", "-p", prompt],
    "codex": lambda prompt: ["codex", "exec", prompt],
    # fresh --session-id per call: the 'main' agent deflects ('send me the material') when a call
    # reuses a session's conversational state; a clean session makes it critique the prompt directly.
    "openclaw": lambda prompt: ["openclaw", "agent", "--agent", "main",
                                "--session-id", f"atanor-{time.time_ns()}",
                                "-m", _openclaw_safe(prompt), "--json"],
}


def _extract_reply(advisor: str, stdout: str) -> str:
    """Most advisors print the reply as plain text; openclaw prints a JSON envelope whose reply
    lives at result.payloads[*].text. Extract it so the reply is the ADVICE, not the wrapper."""
    if advisor != "openclaw":
        return _clean(stdout)
    try:
        d = json.loads(stdout)
        parts = d.get("result", {}).get("payloads", [])
        texts = [p["text"] for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)]
        return _clean("\n".join(texts)) if texts else _clean(stdout)
    except Exception:
        return _clean(stdout)


@dataclass
class Exchange:
    advisor: str
    question: str
    reply: str
    injection_findings: int
    elapsed_s: float
    ts: float

    def record(self) -> dict:
        return {"advisor": self.advisor, "question": self.question,
                "reply_sha256": hashlib.sha256(self.reply.encode("utf-8")).hexdigest(),
                "reply": self.reply, "injection_findings": self.injection_findings,
                "elapsed_s": self.elapsed_s, "ts": self.ts,
                "provenance": f"advisor/{self.advisor}", "promotable": False}


def ask_cli(advisor: str, prompt: str, timeout_s: int = 180) -> Exchange:
    """One question to one CLI advisor. The reply is data; findings are logged, never followed."""
    import shutil
    argv = CLI_ADVISORS[advisor](prompt)
    resolved = shutil.which(argv[0])          # Windows: finds openclaw.cmd / codex.cmd via PATHEXT
    if resolved:
        argv = [resolved] + argv[1:]
    t0 = time.time()
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s,
                          encoding="utf-8", errors="replace")
    reply = _extract_reply(advisor, proc.stdout) or _clean(proc.stderr)
    ex = Exchange(advisor=advisor, question=prompt, reply=reply,
                  injection_findings=len(scan_message_text(reply)),
                  elapsed_s=round(time.time() - t0, 1), ts=time.time())
    journal(ex)
    return ex


def ask_mock(reply: str, advisor: str = "mock", question: str = "") -> Exchange:
    ex = Exchange(advisor=advisor, question=question, reply=reply,
                  injection_findings=len(scan_message_text(reply)),
                  elapsed_s=0.0, ts=time.time())
    journal(ex)
    return ex


def journal(ex: Exchange) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ex.record(), ensure_ascii=False) + "\n")
