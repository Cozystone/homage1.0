# -*- coding: utf-8 -*-
"""Loader for the MemAware dataset — parse sessions into episodes, questions with resolved gold.

The shipped dataset (data/memaware_eval/dataset/) contains:
  - questions.json : 900 implicit-context questions. Each carries `difficulty` (easy|medium|hard),
    the `question` (the new user request), `should_recall` (the target past fact in prose),
    `answer` (the key fact), and `answer_session_ids` (the GOLD session id(s) that hold it).
  - sessions/*.md  : one markdown file per day; each file holds many `## Session <id>` blocks
    (one coherent multi-turn conversation = one episode).

A question's `answer_session_ids` is a PREFIX of the concrete episode id: gold `answer_280352e9`
resolves to episode `answer_280352e9`, and gold `answer_1a2b` resolves to `answer_1a2b_1`,
`answer_1a2b_2`, `answer_1a2b_abs_1`, ... (the answer split across turns). We resolve by exact or
`gold + "_"` prefix — gold ids are full hashes so over-matching is not possible.

No LLM, no network.
"""
from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_ROOT.parents[1]
DATASET_DIR = _REPO_ROOT / "data" / "memaware_eval" / "dataset"

_SESSION_HEADER = re.compile(r"(?m)^##\s+Session\s+(\S+)\s*$")


@dataclass
class Session:
    """One episode — a single `## Session <id>` block from a day file."""
    sid: str
    day: str            # source day-file stem, e.g. "2023-04-01" (the official BM25 retrieval unit)
    text: str

    @property
    def n_chars(self) -> int:
        return len(self.text)


@dataclass
class Question:
    qid: str
    difficulty: str          # easy | medium | hard
    question: str            # the new user request (implicit context)
    should_recall: str       # target past fact, in prose
    answer: str              # the key fact string
    gold_prefixes: list[str] # answer_session_ids as shipped (prefixes)
    gold_sids: list[str] = field(default_factory=list)   # resolved concrete episode ids
    gold_days: list[str] = field(default_factory=list)   # day-files that contain any gold episode


def parse_sessions(sessions_dir: Path | str = None) -> dict[str, Session]:
    """Parse every day file into individual episodes keyed by session id."""
    sessions_dir = Path(sessions_dir) if sessions_dir is not None else DATASET_DIR / "sessions"
    out: dict[str, Session] = {}
    for md in sorted(sessions_dir.glob("*.md")):
        day = md.stem
        txt = md.read_text(encoding="utf-8")
        parts = _SESSION_HEADER.split(txt)
        # parts = [preamble, sid1, body1, sid2, body2, ...]
        for i in range(1, len(parts), 2):
            sid = parts[i].strip()
            body = parts[i + 1] if i + 1 < len(parts) else ""
            out[sid] = Session(sid=sid, day=day, text=body.strip())
    return out


def _resolve(prefixes: list[str], all_sids: list[str]) -> list[str]:
    hits: list[str] = []
    for g in prefixes:
        for sid in all_sids:
            if sid == g or sid.startswith(g + "_"):
                hits.append(sid)
    return sorted(set(hits))


def load_questions(sessions: dict[str, Session] | None = None,
                   questions_path: Path | str = None) -> list[Question]:
    """Load questions and resolve each one's gold episode ids (and their day-files) against the
    parsed sessions, so the grader can check provenance overlap deterministically."""
    questions_path = Path(questions_path) if questions_path is not None else DATASET_DIR / "questions.json"
    if sessions is None:
        sessions = parse_sessions()
    all_sids = list(sessions.keys())
    sid_to_day = {s.sid: s.day for s in sessions.values()}

    raw = json.loads(Path(questions_path).read_text(encoding="utf-8"))
    out: list[Question] = []
    for r in raw:
        prefixes = list(r.get("answer_session_ids") or [])
        gold_sids = _resolve(prefixes, all_sids)
        gold_days = sorted({sid_to_day[s] for s in gold_sids if s in sid_to_day})
        out.append(Question(
            qid=r["question_id"],
            difficulty=r["difficulty"],
            question=r["question"],
            should_recall=r.get("should_recall", ""),
            answer=r.get("answer", ""),
            gold_prefixes=prefixes,
            gold_sids=gold_sids,
            gold_days=gold_days,
        ))
    return out


def deterministic_sample(questions: list[Question], n_per_tier: int | None) -> list[Question]:
    """Bounded, reproducible sample: sort by qid within each tier and take the first n. n=None -> all."""
    if n_per_tier is None:
        return list(questions)
    by_tier: dict[str, list[Question]] = {"easy": [], "medium": [], "hard": []}
    for q in questions:
        by_tier.setdefault(q.difficulty, []).append(q)
    out: list[Question] = []
    for tier in ("easy", "medium", "hard"):
        picked = sorted(by_tier.get(tier, []), key=lambda q: q.qid)[:n_per_tier]
        out.extend(picked)
    return out


# ── token accounting (tiktoken if present, honest whitespace fallback otherwise) ────────────────
@functools.lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def count_tokens(text: str) -> int:
    """Token count for the surfaced context (token-efficiency metric). Uses tiktoken cl100k_base
    when available; otherwise a whitespace*1.3 estimate (flagged in the report)."""
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text))
    return int(len(str(text).split()) * 1.3)


def tokenizer_name() -> str:
    return "tiktoken/cl100k_base" if _encoder() is not None else "whitespace*1.3 (tiktoken absent)"
