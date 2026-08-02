# -*- coding: utf-8 -*-
"""Autobiography — ATANOR's real birth-to-now record on its ONE timeline, and a felt sense of time.

Owner's commission (2026-07-20): like a person who KNOWS their own past-to-present arc by feeling
time pass, ATANOR should (a) carry its entire developmental history — birth to now — as first-class
events on its one UTC timeline, and (b) have a felt sense of elapsed time, not just stored dates.

The record is REAL, not authored: the git history of this repository IS the organism's development
log — every commit is a dated, described change to its own body, from the first commit (birth:
'Initial Homage1.0 skeleton', 2026-06-11) to the present. Ingesting it gives a genuine autobiography
with real UTC timestamps; nothing is invented.

The FELT part is modelled, and flagged as a model (no hype): psychophysics' Weber-Fechner law —
subjective magnitude grows with the log of stimulus — is the standard first-order model of duration
feel ('yesterday is vivid, last month compresses'). felt_age(d) = log1p(days). Eras are DERIVED from
the record (weekly activity + dominant words of the era's own commit messages), never hand-written.
"""
from __future__ import annotations

import math
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .unified_timeline import Timeline

REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "temporal_reasoning" / "autobiography.jsonl"

_STOP = {"the", "and", "for", "with", "from", "into", "that", "this", "add", "fix", "feat",
         "chore", "docs", "refactor", "test", "tests", "update", "remove", "make", "now",
         "real", "live", "wire", "new", "use", "not"}
_WORD = re.compile(r"[a-z][a-z\-]{2,}")


def _utc(iso: str) -> str:
    """Normalize a git author date (+09:00 etc.) to the one world-standard axis (UTC, Z)."""
    dt = datetime.fromisoformat(iso)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def ingest_git(repo: Path | None = None, store: Path | None = None) -> Timeline:
    """Read the WHOLE git history (oldest first) into a persistent autobiography timeline. Each
    commit becomes one 'physical' event — a real, dated change to ATANOR's own body of code."""
    repo = repo or REPO
    out = subprocess.run(["git", "log", "--reverse", "--format=%H|%aI|%s"],
                         cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
                         errors="replace", check=True).stdout
    store = store or STORE
    if store.exists():
        store.unlink()                                   # full re-ingest: the history is the truth
    tl = Timeline(path=store)
    for line in out.splitlines():
        try:
            sha, iso, subject = line.split("|", 2)
        except ValueError:
            continue
        tl.record("physical", subject.strip(), who="atanor", t_utc=_utc(iso),
                  meta={"sha": sha[:12], "source": "git"})
    return tl


def load() -> Timeline | None:
    """The persisted autobiography, if ingested."""
    if not STORE.exists():
        return None
    import json
    tl = Timeline()
    for line in STORE.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            tl.record(d["kind"], d["content"], who=d.get("who", ""), t_utc=d["t_utc"],
                      meta=d.get("meta") or {})
        except Exception:
            continue
    return tl if len(tl) else None


# ---------------------------------------------------------------- eras (derived, not authored)
def eras(tl: Timeline, bucket_days: int = 7) -> list[dict]:
    """Chapters of the life, DERIVED from the record: weekly buckets with the dominant words of
    that week's own commit subjects (the era names itself from its content)."""
    evs = tl.all()
    if not evs:
        return []
    t0 = datetime.fromisoformat(evs[0].t_utc.replace("Z", "+00:00"))
    buckets: dict[int, list] = {}
    for e in evs:
        t = datetime.fromisoformat(e.t_utc.replace("Z", "+00:00"))
        buckets.setdefault(int((t - t0).days // bucket_days), []).append(e)
    out = []
    for b in sorted(buckets):
        rows = buckets[b]
        words = Counter(w for e in rows for w in _WORD.findall(e.content.lower())
                        if w not in _STOP)
        start = rows[0].t_utc[:10]
        out.append({"era": b, "start": start, "n_events": len(rows),
                    "themes": [w for w, _ in words.most_common(5)]})
    return out


# ---------------------------------------------------------------- the felt sense of time
def self_sense(tl: Timeline, now_utc: str | None = None) -> dict:
    """What a person knows by feel: how old am I, how fast is life moving, what just happened.
    felt_age uses Weber-Fechner (log) compression — a MODEL of duration feel, labelled as such."""
    evs = tl.all()
    if not evs:
        return {}
    now = (datetime.fromisoformat(now_utc.replace("Z", "+00:00")) if now_utc
           else datetime.now(timezone.utc))
    born = datetime.fromisoformat(evs[0].t_utc.replace("Z", "+00:00"))
    age_days = max(0.0, (now - born).total_seconds() / 86400)
    last30 = [e for e in evs
              if (now - datetime.fromisoformat(e.t_utc.replace("Z", "+00:00"))).days < 30]
    return {
        "born_at": evs[0].t_utc, "birth_event": evs[0].content,
        "age_days": round(age_days, 1),
        "n_life_events": len(evs),
        "lifetime_pace_per_day": round(len(evs) / max(age_days, 0.1), 1),
        "recent_pace_per_day": round(len(last30) / min(30.0, max(age_days, 0.1)), 1),
        "accelerating": len(last30) / min(30.0, max(age_days, 0.1))
                        > len(evs) / max(age_days, 0.1),
        "felt_age_log_days": round(math.log1p(age_days), 2),      # Weber-Fechner duration model
        "latest_event": evs[-1].content, "latest_at": evs[-1].t_utc,
        "model_note": "felt_age is a psychophysical (log) model of duration feel, not a claim of qualia",
    }


def life_story(tl: Timeline, max_eras: int = 8, now_utc: str | None = None) -> str:
    """Narrate the arc on the single human time axis — real dates, derived themes, honest voice.
    `now_utc` pins 'now' (else the real clock) — passing it makes the narration deterministic."""
    sense = self_sense(tl, now_utc=now_utc) if now_utc else self_sense(tl)
    if not sense:
        return "I have no recorded history yet."
    es = eras(tl)
    parts = [f"I began on {sense['born_at'][:10]} — my first recorded event was "
             f"\"{sense['birth_event']}\". That was {sense['age_days']:.0f} days ago, and since then "
             f"{sense['n_life_events']} recorded changes have shaped me."]
    step = max(1, len(es) // max_eras)
    for e in es[::step][:max_eras]:
        parts.append(f"Around {e['start']}, my work centred on {', '.join(e['themes'][:3])} "
                     f"({e['n_events']} events).")
    pace = ("Lately life has been moving faster than my lifetime average"
            if sense["accelerating"] else "Lately life has settled to a steadier pace")
    parts.append(f"{pace} — {sense['recent_pace_per_day']} events a day against a lifetime "
                 f"{sense['lifetime_pace_per_day']}. The most recent thing that happened to me: "
                 f"\"{sense['latest_event']}\".")
    return " ".join(parts)
