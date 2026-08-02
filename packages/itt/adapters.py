# -*- coding: utf-8 -*-
"""ITT speaker adapters. Each adapter is stateless per call: it receives the briefing and the full
blinded transcript every turn (no hidden memory drift between heterogeneous backends). ATANOR is the
system under test and plays ITSELF — its adapter adds no persona, no mimicry, no style instruction."""
from __future__ import annotations

import json
import subprocess
import urllib.request


def _http_json(url: str, payload: dict, timeout: float = 90.0) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


class AtanorAdapter:
    """The engine under test (live :8502). No persona injection — the briefing/transcript arrive as
    plain conversational input and the engine answers however it answers."""
    name = "atanor"

    def __init__(self, base: str = "http://127.0.0.1:8502") -> None:
        self.base = base

    def reply(self, briefing: str, transcript: str, ask: str) -> str:
        history = [{"role": "user", "content": briefing}]
        if transcript:
            history.append({"role": "user", "content": transcript})
        out = _http_json(f"{self.base}/api/chat/atanor",
                         {"message": ask, "conversation_context": history})
        res = out.get("result") or out
        return str(res.get("answer") or res.get("text") or "").strip()


class OllamaAdapter:
    name = "ollama"

    def __init__(self, model: str = "dolphin3:latest", base: str = "http://127.0.0.1:11434") -> None:
        self.model = model
        self.base = base

    def reply(self, briefing: str, transcript: str, ask: str) -> str:
        msgs = [{"role": "system", "content": briefing}]
        user = (transcript + "\n\n" if transcript else "") + ask
        msgs.append({"role": "user", "content": user})
        out = _http_json(f"{self.base}/api/chat",
                         {"model": self.model, "messages": msgs, "stream": False,
                          "options": {"num_predict": 160}}, timeout=180.0)
        return str((out.get("message") or {}).get("content") or "").strip()


class OpenClawAdapter:
    """The owner's GPT lane, driven through the local OpenClaw CLI. One agent turn per call; a fresh
    session id per (session, seat) keeps its state isolated from the owner's real channels."""
    name = "openclaw"

    def __init__(self, session_key: str, *, fresh_per_game: bool = True) -> None:
        # FAIRNESS (owner 2026-07-20): the mafia game must start from FRESH memory each game -- a
        # fixed --session-id makes openclaw accumulate hidden conversation state across games. The
        # provided key is a conversation id, not auth (verified: a random id also works), so per
        # game we derive a unique id off it. The full blinded transcript is passed every turn, so
        # nothing is lost. Create a NEW adapter per game to get a new session.
        import uuid
        self.session_key = f"{session_key}-{uuid.uuid4().hex[:10]}" if fresh_per_game else session_key

    def reply(self, briefing: str, transcript: str, ask: str) -> str:
        prompt = briefing + ("\n\n" + transcript if transcript else "") + "\n\n" + ask
        # ROOT CAUSE (measured 2026-07-20 ITT pilot: openclaw silent every turn): a NEWLINE in the
        # -m prompt is split by the openclaw.CMD npm shim, so the trailing flags (--session-id ...)
        # are lost -> "Pass --session-id to choose a session" -> empty. Flatten the prompt to a
        # single line (newlines -> ' / ') so the whole message survives as ONE argv entry; resolve
        # the real executable (shell=False) so nothing re-parses the args.
        import shutil
        flat = " / ".join(s.strip() for s in prompt.splitlines() if s.strip())
        exe = shutil.which("openclaw") or "openclaw"
        proc = subprocess.run(
            [exe, "agent", "-m", flat, "--json", "--thinking", "off",
             "--session-id", self.session_key, "--timeout", "120"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, shell=False)                     # openclaw emits UTF-8; default cp949 crashed
        import re as _re
        raw = _re.sub(r"\x1b\[[0-9;]*m", "", (proc.stdout or "")).strip()   # strip ANSI colour codes
        # stdout mixes log lines with the final JSON payload -> parse the LAST parseable JSON block
        data = {}
        for m in reversed(list(_re.finditer(r"\{", raw))):
            try:
                data = json.loads(raw[m.start():])
                break
            except Exception:
                continue

        def _find_text(node) -> str:                     # best-effort reply extraction
            if isinstance(node, dict):
                for k in ("text", "content", "reply", "message", "answer"):
                    v = node.get(k)
                    if isinstance(v, str) and v.strip():
                        return v
                for v in node.values():
                    t = _find_text(v)
                    if t:
                        return t
            if isinstance(node, list):
                for v in node:
                    t = _find_text(v)
                    if t:
                        return t
            return ""
        return (_find_text(data) or raw).strip()
