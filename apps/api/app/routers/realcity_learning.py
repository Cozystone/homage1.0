# -*- coding: utf-8 -*-
"""Realcity LEARNING endpoint — ATANOR ambassadors overhear the city's ollama-driven NPCs and learn
from them WITHOUT contaminating the brain.

Owner (2026-07-21): the sibling router realcity_agent.py makes ATANOR the MIND of the citizens. This
router covers the other direction: an ATANOR-brained citizen standing near two ollama-NPCs OVERHEARS
their conversation. The constitution (external-minds-are-data) is absolute — an NPC/LLM sentence is
DATA, never a fact, and may never enter ATANOR's graph or corpus. So this endpoint only ever does
three doctrine-legal things with what it hears, and nothing else:

  step0  MORAL 0th gate — a line reading as harm/steal/deceive/attack/weapon/kill is refused (422);
         the whole batch is dropped, nothing is written (fail-closed).
  step1  QUARANTINE — every raw line is archived to overheard_quarantine.jsonl with a source label
         ('ollama-npc', heard_by 'atanor-ambassador'). This is a hearsay log; it is NEVER surfaced
         as a fact, never read back as knowledge.
  step2  REGISTER — the line is ANONYMIZED (speaker names -> SPEAKER_A/B..., known place -> PLACE,
         numbers -> N) and tagged with a coarse dialogue-act; the resulting template enters the
         usable register_pool.jsonl ONLY once its normalized form has been overheard in >= 2 DISTINCT
         conversations (consensus, tracked in register_counts.json). Register = HOW people talk, not
         what they said.
  step3  TOPICS — bare content tokens become UNGROUNDED entries in curiosity_topics.jsonl. They are
         QUESTIONS for ATANOR to go and ground ITSELF later (world-mentor pattern), never answers.

Reuse decisions (READ first, per task): packages/autonomy_kernel/register_harvest.py could not be
imported — it is Korean-cue specific, keys consensus on web DOMAINS not conversations, and has no
dialogue-act tagging; and packages/reasoning_vm/curiosity.py's CuriosityEngine.run() WRITES verified
facts into LiveMemory (exactly the contamination we must prevent) and exposes no enqueue-with-source
queue. So the pure transforms live in the minimal package packages/realcity_learning/, and topics go
to a jsonl ungrounded queue rather than through CuriosityEngine.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from packages.realcity_learning import harvest

router = APIRouter(prefix="/api/realcity", tags=["realcity-learning"])

# ONE module-level base path: every data file derives from it AT CALL TIME, so a test can
# monkeypatch this single attribute (realcity_learning.DATA_DIR) to redirect all writes to a tmp dir.
DATA_DIR = Path(__file__).resolve().parents[4] / "data" / "realcity"

_QUARANTINE = "overheard_quarantine.jsonl"
_POOL = "register_pool.jsonl"
_COUNTS = "register_counts.json"
_TOPICS = "curiosity_topics.jsonl"


class OverheardLine(BaseModel):
    speaker: str = ""
    text: str = ""


class OverhearRequest(BaseModel):
    speakers: list[str] = Field(default_factory=list)
    lines: list[OverheardLine] = Field(default_factory=list)
    place: str | None = None
    ts: float | None = None
    conv_id: str | None = None      # optional; the city omits it and one is derived per batch


# --- persistence helpers (all key off the CURRENT DATA_DIR global, so monkeypatch redirects them) -
def _path(name: str) -> Path:
    return DATA_DIR / name


def _append_jsonl(name: str, row: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _path(name).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _count_lines(name: str) -> int:
    path = _path(name)
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _load_counts() -> dict[str, Any]:
    path = _path(_COUNTS)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_counts(counts: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _path(_COUNTS).write_text(json.dumps(counts, ensure_ascii=False), encoding="utf-8")


def _enqueue_topics(topics: list[str], ts: float) -> int:
    """Curiosity queue: bump each topic's overheard count, ALWAYS status='ungrounded'. Overhearing
    an NPC never grounds a topic — ATANOR must ground it itself later. Read-modify-write keeps one
    row per topic with an accurate count."""
    if not topics:
        return 0
    path = _path(_TOPICS)
    rows: dict[str, Any] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                rows[row["topic"]] = row
            except Exception:
                continue
    for token in topics:
        row = rows.get(token) or {"topic": token, "count": 0, "status": "ungrounded", "first_ts": ts}
        row["count"] = int(row.get("count", 0)) + 1
        row["status"] = "ungrounded"        # invariant — an overheard pointer is never an answer
        row["last_ts"] = ts
        rows[token] = row
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows.values():
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(topics)


def _conversation_id(req: "OverhearRequest", ts: float) -> str:
    """Each overhear() call is one DISTINCT conversation for the consensus gate. Honor an explicit
    id if the caller sends one, else derive a stable id from speakers/place/ts/first-line."""
    if req.conv_id:
        return str(req.conv_id)
    basis = "|".join(req.speakers) + "||" + (req.place or "") + "||" + repr(ts) + "||" + (
        req.lines[0].text if req.lines else "")
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


@router.post("/overhear")
def overhear(req: OverhearRequest) -> dict[str, Any]:
    """Ingest one overheard exchange: moral-gate -> quarantine -> consensus register -> topic queue.
    Returns {ok, quarantined, register_promoted, topics}."""
    ts = float(req.ts) if req.ts is not None else time.time()
    speakers = list(req.speakers) or [line.speaker for line in req.lines if line.speaker]
    place = req.place or ""

    # ── step0: MORAL 0th gate — scan every line FIRST; if any reads as harm, write nothing (422) ──
    for line in req.lines:
        if harvest.reads_as_harm(line.text):
            raise HTTPException(
                status_code=422,
                detail=("Refused: an overheard line reads as harm/steal/deceive/attack/weapon/kill. "
                        "The moral 0th gate does not even quarantine it — the batch is dropped."),
            )

    conversation = _conversation_id(req, ts)
    name_map = harvest.speaker_map(speakers)
    place_names = [place] if place else []

    # ── step1: QUARANTINE — labelled hearsay archive, NEVER surfaced as fact ──────────────────────
    quarantined = 0
    for line in req.lines:
        _append_jsonl(_QUARANTINE, {
            "source": "ollama-npc",
            "heard_by": "atanor-ambassador",
            "ts": ts,
            "conv_id": conversation,
            "place": place,
            "speaker": line.speaker,
            "text": line.text,
        })
        quarantined += 1

    # ── step2: REGISTER — anonymized templates, promoted ONLY at >= 2 distinct conversations ──────
    counts = _load_counts()
    register_promoted = 0
    seen_here: set[str] = set()
    for line in req.lines:
        anonymized = harvest.anonymize(line.text, name_map, place_names)
        normalized = harvest.normalize_template(anonymized)
        if not normalized or normalized in seen_here:
            continue                                     # de-dupe repeats WITHIN this conversation
        seen_here.add(normalized)
        record = counts.get(normalized) or {
            "template": anonymized, "tag": harvest.dialogue_act(line.text),
            "convs": [], "promoted": False,
        }
        if conversation not in record["convs"]:
            record["convs"].append(conversation)
        if len(record["convs"]) >= 2 and not record.get("promoted"):
            _append_jsonl(_POOL, {
                "template": anonymized,
                "tag": record["tag"],
                "conversations": len(record["convs"]),
                "source": "register-consensus",
                "ts": ts,
            })
            record["promoted"] = True
            record["convs"] = record["convs"][:8]        # bound: consensus already reached
            register_promoted += 1
        counts[normalized] = record
    _save_counts(counts)

    # ── step3: TOPICS — ungrounded curiosity pointers ATANOR grounds itself later ─────────────────
    topics: list[str] = []
    seen_topics: set[str] = set()
    for line in req.lines:
        for token in harvest.extract_topics(line.text, speakers):
            if token not in seen_topics:
                seen_topics.add(token)
                topics.append(token)
    topic_count = _enqueue_topics(topics, ts)

    return {
        "ok": True,
        "quarantined": quarantined,
        "register_promoted": register_promoted,
        "topics": topic_count,
        "conv_id": conversation,
    }


@router.get("/learning-stats")
def learning_stats() -> dict[str, Any]:
    """Counts of the three doctrine-legal stores + the last overheard timestamp."""
    last_ts: float | None = None
    path = _path(_QUARANTINE)
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            try:
                last_ts = json.loads(lines[-1]).get("ts")
            except Exception:
                last_ts = None
    return {
        "ok": True,
        "quarantine": _count_lines(_QUARANTINE),
        "register_pool": _count_lines(_POOL),
        "topics": _count_lines(_TOPICS),
        "last_ts": last_ts,
        "data_dir": str(DATA_DIR),
    }
