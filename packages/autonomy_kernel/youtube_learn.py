# -*- coding: utf-8 -*-
"""YouTube comprehensive-context learning — one video is a whole slice of the human world.

Owner (2026-07-14): as a single medium YouTube is the richest teacher — every topic exists,
there is a video and a thumbnail, and under it real people react to the SAME thing: comments,
replies to comments, kind ones and toxic ones. Facts, everyday discourse, and the full range of
human communication, all in one comprehensible CONTEXT.

What one session learns from one video (No-LLM, gated, nothing to production directly):
 FACTS — title + description go through web_expedition.ingest_page (shield → candidates →
 the same cross-source consensus every fact waits for).
 REGISTER — comments run through register_harvest (anonymized, safety-floored, chrome-cut),
 each fragment tagged with the video TOPIC as its context (a reaction understood
 as a reaction TO something — ). Consensus unit = the video id, so the
 same phrase under different videos is different strangers agreeing.
 DIALOGUE — (comment → reply) pairs, the turn-taking skeleton of everyday talk, stored to
 data/register_bank/discourse_pairs.jsonl with both sides anonymized and length-
 capped. This is what "how people answer each other" literally looks like.
 IMMUNITY — toxic comments are never stored as speakable; they are counted and a short
 fingerprint goes to the immunity journal (learn to RECOGNIZE, never to speak).

Thumbnails/video frames are the perception track's food — declared, not faked here (text first).

 python -m packages.autonomy_kernel.youtube_learn "ytsearch3: "
 python -m packages.autonomy_kernel.youtube_learn "https://www.youtube.com/watch?v=..."
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_PAIRS = _ROOT / "data" / "register_bank" / "discourse_pairs.jsonl"
_IMMUNITY = _ROOT / "data" / "autonomy" / "register_immunity.jsonl"

# toxicity — reject-as-speakable cues (intake filter, never a routing rule). Learn to recognize,
# never to speak: matched comments are counted + fingerprinted to the immunity journal.
_TOXIC = re.compile(r"(꺼져|닥쳐|병신|씨발|시발|좆|지랄|멍청|한심|틀딱|급식|벌레|기레기|"
                    r"죽어라|뒤져|혐오|극혐|쓰레기\s*같|역겹|미개|저능|무뇌|찐따|꼴값|나가\s*죽)")
_MAX_COMMENTS = 60


def _yt_info(target: str) -> list[dict[str, Any]]:
    """Fetch metadata + comments for a video URL or a ytsearchN: query (no API key; yt_dlp's
    public web client). Returns a list of video info dicts."""
    import yt_dlp
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "getcomments": True, "extract_flat": False,
        "extractor_args": {"youtube": {"max_comments": [str(_MAX_COMMENTS), "all", "20", "5"]}},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(target, download=False)
    entries = info.get("entries") if isinstance(info, dict) and info.get("entries") else [info]
    return [e for e in entries if isinstance(e, dict)]


def _topic_of(info: dict[str, Any]) -> str:
    t = str(info.get("title") or "").strip()
    return re.sub(r"[\[\](){}|#@]", " ", t)[:60].strip()


def learn_video(info: dict[str, Any]) -> dict[str, Any]:
    """Run the four lanes over one fetched video."""
    from packages.autonomy_kernel.register_harvest import harvest_register, _scrub, _SAFETY_REJECT
    from packages.autonomy_kernel.web_expedition import ingest_page

    vid = str(info.get("id") or "")
    url = str(info.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}")
    topic = _topic_of(info)
    comments = [c for c in (info.get("comments") or []) if isinstance(c, dict)]

    # FACTS: title + description through the standard page gate (shield + candidates)
    fact_text = f"{info.get('title') or ''}. {info.get('description') or ''}"
    fact_rep = {}
    try:
        fact_rep = ingest_page(url, fact_text[:8000])
    except Exception:
        pass

    # REGISTER: comment texts as one flattened page, tagged with the video topic as context
    reg = {"harvested": 0, "rejected": 0}
    toxic = 0
    clean_comments: dict[str, dict[str, Any]] = {}
    for c in comments:
        txt = str(c.get("text") or "").strip()
        if not txt:
            continue
        if _TOXIC.search(txt):
            toxic += 1
            _journal_immunity(txt, url)
            continue
        clean_comments[str(c.get("id") or "")] = c
    try:
        blob = "\n".join(str(c.get("text") or "")[:200] for c in clean_comments.values())
        reg = harvest_register(blob, url, context=topic)   # L1: all registers, not just comfort
    except Exception:
        pass

    # DIALOGUE: (parent comment -> reply) pairs — the turn-taking skeleton. Both sides scrubbed;
    # a pair survives only if both sides are clean, short, Korean-bearing.
    pairs = 0
    rows: list[str] = []
    for cid, c in clean_comments.items():
        parent = str(c.get("parent") or "root")
        if parent == "root" or parent not in clean_comments:
            continue
        a = _scrub(str(clean_comments[parent].get("text") or "")[:200])
        b = _scrub(str(c.get("text") or "")[:200])
        if not (6 <= len(a) <= 90 and 6 <= len(b) <= 90):
            continue
        if not (re.search(r"[가-힣]", a) and re.search(r"[가-힣]", b)):
            continue
        if _SAFETY_REJECT.search(a) or _SAFETY_REJECT.search(b):
            continue
        rows.append(json.dumps({"q": a, "r": b, "context": topic, "src": f"youtube:{vid}",
                                "ts": int(time.time())}, ensure_ascii=False))
        pairs += 1
    if rows:
        _PAIRS.parent.mkdir(parents=True, exist_ok=True)
        with _PAIRS.open("a", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")

    return {"video": vid, "topic": topic, "comments": len(comments), "toxic_blocked": toxic,
            "register": reg, "dialogue_pairs": pairs,
            "fact_candidates": int(fact_rep.get("candidates") or 0)}


def _journal_immunity(text: str, url: str) -> None:
    try:
        _IMMUNITY.parent.mkdir(parents=True, exist_ok=True)
        with _IMMUNITY.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "toxic_comment",
                                "fingerprint": text[:40], "src": url}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def learn(target: str) -> list[dict[str, Any]]:
    """One learning session: a video URL or 'ytsearchN:<query>'."""
    reports = []
    for info in _yt_info(target):
        try:
            reports.append(learn_video(info))
        except Exception as exc:
            reports.append({"video": str(info.get("id") or "?"), "error": str(exc)[:120]})
    return reports


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    tgt = sys.argv[1] if len(sys.argv) > 1 else "ytsearch2:오늘 하루 힘들었던 사람들에게"
    for r in learn(tgt):
        print(json.dumps(r, ensure_ascii=False, indent=2))
