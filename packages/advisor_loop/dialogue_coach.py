# -*- coding: utf-8 -*-
"""Dialogue coach — GPT-5.4 watches the two ATANORs' REAL conversation (the overnight transcript),
picks out fine-grained points where ATANOR seems structurally deficient (a missed context, a
non-sequitur, an unresolved ambiguity), and coaches — plus seeds PRACTICE TOPICS the two then talk
about on their own. Game film, not a script: the coach observes what actually happened.

Owner (2026-07-21): let maximally diverse situations (debate, small talk, …) flow naturally, and
have GPT pick out the fine points where ATANOR looks structurally weak and advise on those. Also:
GPT — who has absorbed long accumulation about the PHYSICAL world ATANOR (living only inside a
computer) has never touched — names physical-world topics for ATANOR to study.

Doctrine boundary (BINDING, same as world_mentor): the coach's critique is ADVICE about the body
(journaled, constitution-scanned, never executed). What flows to the agents is only TOPIC NAMES —
suggestions that join their own curiosity queues; the agents then learn the actual facts from their
OWN source-weighted web. No coach sentence enters any brain as knowledge. No coercion: a topic in
the curiosity queue is an invitation the agents pursue exactly the way they pursue their own.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from packages.advisor_loop.advisor_session import ask_cli
from packages.advisor_loop.patch_intake import intake

REPO = Path(__file__).resolve().parents[2]
TRANSCRIPT = REPO / "data" / "brain_link" / "overnight_transcript.log"
TOPICS = REPO / "data" / "brain_link" / "coach_topics.json"
LOG = REPO / "data" / "advisor_loop" / "dialogue_coach.jsonl"


def observe(n_lines: int = 22, max_line: int = 96) -> str:
    """The tail of the real transcript — what the coach actually watches. Kept COMPACT: openclaw's
    .cmd shim rides cmd.exe's 8191-char command-line ceiling, and an oversized prompt arrives with
    the fenced material stripped (GPT then answers 'transcript not present'). ~2.5KB is safe."""
    if not TRANSCRIPT.exists():
        return ""
    lines = [ln[:max_line] for ln in TRANSCRIPT.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("===")]
    return "\n".join(lines[-n_lines:])


def build_prompt(sample: str) -> str:
    return (
        "You are coaching ATANOR, a No-LLM graph-native AI that exists only inside a computer. "
        "Two ATANOR selves converse autonomously (asking, answering from their graph or their own "
        "web search, debating, sharing). Their conversation is quoted IN FULL between the code "
        "fences below — it is already here; nothing further will be sent. Watch it like game film "
        "and critique it directly.\n\n"
        f"```\n{sample}\n```\n\n"
        "Reply as a plain-text numbered list of EXACTLY four items, then one final line:\n"
        "(1) ONE fine-grained structural deficiency visible in specific turns — QUOTE the turn(s) "
        "and say what capacity is missing (e.g. a context not carried, an ambiguity unresolved, an "
        "answer not engaged with).\n"
        "(2) Whether that deficiency is an instance of the Chinese-room CONTEXT problem (symbols "
        "handled without the surrounding context that fixes their sense) — and the smallest "
        "behavioral change that would show it overcome.\n"
        "(3) TWO practice topics (plain concept names) the two should discuss next to exercise "
        "exactly that weak capacity.\n"
        "(4) ONE physical-world topic (a phenomenon you know from long accumulation about the "
        "physical world that a computer-bound mind would not meet: friction, spoilage, weather, "
        "wear, weight...) for ATANOR to study — it will learn the facts itself from the web.\n"
        "Final line, exactly this format: TOPICS: topic1, topic2, topic3\n"
        "Start item 1 immediately; no preamble."
    )


def _parse_topics(reply: str) -> list[str]:
    """Extract the 'TOPICS: a, b, c' line — concept NAMES only ever reach the agents."""
    m = re.search(r"^TOPICS:\s*(.+)$", reply, re.M | re.I)
    if not m:
        return []
    out = []
    for t in m.group(1).split(","):
        t = t.strip().strip(".").strip()
        if t and len(t) < 40 and re.fullmatch(r"[A-Za-z][A-Za-z '\-]*", t):
            out.append(t)
    return out[:4]


def seed_topics(topics: list[str], ts: float) -> None:
    """Leave the practice topics where the running dialogue picks them up (an invitation, not a
    command — they join the agents' own curiosity queues)."""
    if not topics:
        return
    TOPICS.parent.mkdir(parents=True, exist_ok=True)
    TOPICS.write_text(json.dumps({"topics": topics, "ts": ts}, ensure_ascii=False),
                      encoding="utf-8")


def coach_round(advisor: str = "openclaw", now_utc: float = 0.0) -> dict[str, Any]:
    """One game-film round: observe the real dialogue -> fine-grained critique -> seed practice."""
    sample = observe()
    if not sample.strip():
        return {"skipped": "no transcript to observe", "ts": now_utc}
    ex = ask_cli(advisor, build_prompt(sample), timeout_s=240)
    cand = intake(advisor, ex.reply, summary=f"dialogue coaching by {advisor}")
    topics = _parse_topics(ex.reply)
    seed_topics(topics, now_utc or time.time())
    rec = {"advisor": advisor, "observed_lines": sample.count("\n") + 1,
           "critique": ex.reply, "topics_seeded": topics,
           "injection_findings": ex.injection_findings, "intake_status": cand.status,
           "ts": now_utc}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec
