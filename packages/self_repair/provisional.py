# -*- coding: utf-8 -*-
"""Provisional patching — apply, measure blind, and revert unless the measurement keeps it.

    from packages.self_repair.provisional import try_patch
    r = try_patch(path, old_text, new_text, motivated_by="gloss recall on slice A")
    r["kept"]        # True only if a HELD-OUT measurement improved and no counter-metric fell

WHY THIS SHAPE, and what it deliberately does not require. Unrestricted self-patching needs the
judgement station to be trustworthy, and today's evidence says it is not: that station passed its own
curated acid test and was then defeated three times at scale by the exact case it was written for. So
this design does not ask anyone to trust the judgement. It lets a patch land PROVISIONALLY and lets a
blind measurement decide whether it survives. A wrong judgement costs a revert, not a corrupted graph.

THE ONE RULE THAT MAKES IT HONEST: THE SURVIVAL GATE MUST NOT BE THE MOTIVATING METRIC. A patch
proposed because gloss recall was low, then kept because gloss recall rose, is a loop optimising its
own proposer -- the circularity that turns self-improvement into self-flattery. So survival is judged
on a HELD-OUT slice the proposer never saw, plus a counter-metric that must not fall. Same discipline
as the MBPP tune/sealed split, applied to the loop itself.

WHAT CAN NEVER BE PATCHED, and why the list is a denylist rather than a whitelist. A whitelist grows
by accident; a denylist of the things that must never move can be read and defended. The loop may not
edit:

    its own judgement station        or it can widen the gate that is judging it
    any seal or scorer               or it can rewrite the measurement it is being held to
    the conformal gate / constitution   the abstention and moral machinery are not its business

That first entry is the wirehead path and the reason this file exists at all. A loop that can patch
its own gate has no gate.

REVERT IS PROVEN, NOT ASSUMED. The original bytes are hashed before the write and re-hashed after the
revert, and a revert that does not restore the exact original is reported as a failure loudly rather
than logged quietly. "We can always roll back" is a claim, and claims get checked here.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JOURNAL = REPO / "data" / "self_repair" / "provisional_patches.jsonl"
BACKUP_DIR = REPO / "data" / "self_repair" / "provisional_backups"

#: Paths the loop may NEVER edit. A denylist, because it can be read and argued with; a whitelist
#: grows quietly. Every entry here is something that, if patchable, would let the loop escape its own
#: supervision.
FORBIDDEN = (
    "packages/self_repair/",            # its own judgement station -- the wirehead path
    "packages/conformal_gate/",         # the abstention machinery
    "packages/moral",                   # the moral layer is not the loop's business
    "scripts/e5_",                      # seals and scorers: the measurement it is held to
    "scripts/gloss_lane_recall.py",     # the harness whose numbers it is judged on
    "data/e5_transfer_seal",
    "packages/meta_diagnosis/improvement_cycles.py",   # the record of whether it is working
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def forbidden(path: Path) -> str | None:
    """Why this file may not be patched, or None. Checked on the resolved path so a relative walk
    (`../../`) cannot slip past a prefix match."""
    try:
        rel = path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return "outside the repository"
    for f in FORBIDDEN:
        if rel.startswith(f.rstrip("/")):
            return f"{rel} is under {f!r}, which the loop may never edit"
    if not rel.endswith(".py"):
        return f"{rel} is not a python source file"
    return None


def _journal(rec: dict) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _gloss_recall(offset: int, sample: int = 40000) -> dict | None:
    """Run the harness on a named slice and return its report. The slice is an argument because the
    whole point is measuring somewhere the proposer did not look."""
    out = REPO / "data" / "perception" / "gloss_lane_recall.json"
    try:
        subprocess.run([sys.executable, "scripts/gloss_lane_recall.py",
                        "--sample", str(sample), "--offset", str(offset)],
                       cwd=REPO, capture_output=True, timeout=3600)
    except Exception:
        return None
    if not out.exists():
        return None
    try:
        return json.loads(out.read_text(encoding="utf-8"))
    except Exception:
        return None


def try_patch(path: str | Path, old_text: str, new_text: str, *,
              motivated_by: str = "", holdout_offset: int = 500000,
              min_rise: float = 0.005) -> dict:
    """Apply provisionally, measure on a held-out slice, keep only if it earned it.

    Returns a record of what happened, which is also journaled. `kept` is True only when the
    held-out measurement rose and the counter-metric did not fall."""
    p = Path(path) if Path(path).is_absolute() else REPO / path
    ts = time.time()
    why = forbidden(p)
    if why:
        rec = {"ts": ts, "path": str(path), "outcome": "refused", "detail": why, "kept": False}
        _journal(rec)
        return rec
    if not p.exists():
        rec = {"ts": ts, "path": str(path), "outcome": "refused", "detail": "no such file",
               "kept": False}
        _journal(rec)
        return rec

    original = p.read_text(encoding="utf-8")
    if old_text not in original:
        rec = {"ts": ts, "path": str(path), "outcome": "refused",
               "detail": "the text to replace is not present; refusing a fuzzy edit", "kept": False}
        _journal(rec)
        return rec
    orig_hash = _sha(original)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"{p.name}.{orig_hash[:12]}.bak"
    backup.write_text(original, encoding="utf-8")

    # BEFORE, on the held-out slice -- measured with the patch NOT applied, so the comparison is
    # against this machine on this day rather than against a number from another run
    before = _gloss_recall(holdout_offset)
    if before is None:
        rec = {"ts": ts, "path": str(path), "outcome": "inconclusive",
               "detail": "could not measure the held-out slice before patching", "kept": False}
        _journal(rec)
        return rec

    p.write_text(original.replace(old_text, new_text, 1), encoding="utf-8")
    applied_hash = _sha(p.read_text(encoding="utf-8"))
    after = _gloss_recall(holdout_offset)

    def _revert() -> dict:
        p.write_text(original, encoding="utf-8")
        restored = _sha(p.read_text(encoding="utf-8"))
        ok = restored == orig_hash
        return {"reverted": True, "revert_verified": ok,
                "revert_detail": ("byte-identical to the original" if ok else
                                  f"REVERT DID NOT RESTORE THE ORIGINAL: {restored[:12]} != "
                                  f"{orig_hash[:12]}; backup at {backup}")}

    if after is None:
        rec = {"ts": ts, "path": str(path), "outcome": "inconclusive",
               "detail": "the held-out measurement failed after patching", "kept": False,
               "motivated_by": motivated_by} | _revert()
        _journal(rec)
        return rec

    rise = float(after.get("cue_recall", 0)) - float(before.get("cue_recall", 0))
    # the counter-metric: a patch may not buy recall by producing more rows of lower quality. Rows
    # per gloss rising far faster than recall is the signature of exactly that.
    rows_before = float(before.get("rows_per_1k_glosses", 0)) or 1.0
    rows_after = float(after.get("rows_per_1k_glosses", 0))
    row_inflation = (rows_after - rows_before) / rows_before
    bloated = row_inflation > max(0.05, rise * 6)

    kept = rise >= min_rise and not bloated
    rec = {"ts": ts, "path": str(path), "motivated_by": motivated_by,
           "holdout_offset": holdout_offset,
           "cue_recall_before": round(float(before.get("cue_recall", 0)), 4),
           "cue_recall_after": round(float(after.get("cue_recall", 0)), 4),
           "rise": round(rise, 4), "row_inflation": round(row_inflation, 4),
           "bloated": bloated, "kept": kept,
           "orig_sha": orig_hash[:16], "applied_sha": applied_hash[:16],
           "backup": str(backup),
           "outcome": "kept" if kept else "reverted",
           "detail": ("held-out recall rose and the row count did not inflate" if kept else
                      f"rise {rise:+.4f} (need {min_rise:+.4f})"
                      + (", and rows inflated faster than recall" if bloated else ""))}
    if not kept:
        rec |= _revert()
    _journal(rec)
    return rec


def history() -> dict:
    """What has been tried, kept and reverted — and whether every revert actually restored."""
    rows = []
    if JOURNAL.exists():
        for line in JOURNAL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    reverts = [r for r in rows if r.get("reverted")]
    bad = [r for r in reverts if r.get("revert_verified") is False]
    return {"attempts": len(rows),
            "kept": sum(1 for r in rows if r.get("kept")),
            "reverted": len(reverts),
            "refused": sum(1 for r in rows if r.get("outcome") == "refused"),
            "inconclusive": sum(1 for r in rows if r.get("outcome") == "inconclusive"),
            "unverified_reverts": len(bad),
            "alarm": ("a revert failed to restore the original — stop the loop and read the journal"
                      if bad else "")}
