# -*- coding: utf-8 -*-
"""English-only enforcement RATCHET — the mechanism that breaks the Korean-remnant error chain.

Owner directive (2026-07-18): "excise every Korean remnant, cleanly overlay the English era —
in the most certain way to break the continuous chain of errors." A one-time mass edit cannot
be the answer (it was tried, it regressed). The certain fix is an INVARIANT that source cannot
silently violate: this gate makes Korean in code a hard failure.

Design — a monotonic ratchet, not a cliff:
 * `korean_debt.json` records the baseline Hangul-count PER FILE (whole repo: packages/, scripts/,
 apps/api/).
 * The gate FAILS (exit 1) if ANY file's Hangul count rises above its baseline (no new Korean),
 or if a file in the CLEARED set contains ANY Hangul (cleared stays clean).
 * As files are excised, drop their baseline (or move them to CLEARED); the total can only fall.
This lets the excision proceed incrementally while GUARANTEEING no regression — the chain is broken
because Korean can never silently re-enter, and every commit ratchets the number down.

Allowlist (documented, not silent): only two things may legitimately hold Hangul —
 1. the English-only INPUT DETECTOR — it must recognise the Hangul unicode block to REFUSE it.
 Expressed as unicode escapes (- ...), so it carries zero literal Hangul characters
 and is not exempted here at all — it simply won't match.
 2. owner Korean deliverables (business-plan / pitch-deck generators) — Korean OUTPUT documents for
 the owner, not engine remnants. Listed in ALLOWLIST; flagged in the report for an explicit call.

Usage:
 python scripts/enforce_english_only.py --baseline # (re)write korean_debt.json from current state
 python scripts/enforce_english_only.py # gate: exit 1 on any regression / cleared-file dirt
 python scripts/enforce_english_only.py --report # show top offenders + burn-down, exit 0
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HAN = re.compile(r"[가-힣㄰-㆏ᄀ-ᇿ]")   # syllables + jamo, no literal Hangul here
ROOTS = ["packages", "scripts", "apps/api"]
DEBT = REPO / "korean_debt.json"

# Files that may legitimately contain Korean OUTPUT (owner deliverables) — excluded from the count.
# Everything else must reach zero. This list is the ONLY sanctioned Korean; keep it minimal.
ALLOWLIST = re.compile(r"build_business_plan|build_pitch_deck|business_plan|pitch_deck|bizplan",
                       re.IGNORECASE)


def hangul_count(path: Path) -> int:
    try:
        return len(HAN.findall(path.read_text(encoding="utf-8", errors="ignore")))
    except Exception:
        return 0


def scan() -> dict[str, int]:
    out: dict[str, int] = {}
    for root in ROOTS:
        for p in (REPO / root).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            rel = str(p.relative_to(REPO)).replace("\\", "/")
            if ALLOWLIST.search(rel):
                continue
            c = hangul_count(p)
            if c:
                out[rel] = c
    return out


def main() -> int:
    cur = scan()
    total = sum(cur.values())
    if "--baseline" in sys.argv:
        DEBT.write_text(json.dumps({"total": total, "files": dict(sorted(cur.items())),
                                    "cleared": []}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"baseline written: {total} Hangul chars across {len(cur)} files -> {DEBT.name}")
        return 0
    base = json.loads(DEBT.read_text(encoding="utf-8")) if DEBT.exists() else {"files": {}, "cleared": []}
    base_files, cleared = base.get("files", {}), set(base.get("cleared", []))

    regressions, dirty_cleared = [], []
    for f, c in cur.items():
        if f in cleared:
            dirty_cleared.append((f, c))
        elif c > base_files.get(f, 0):
            regressions.append((f, base_files.get(f, 0), c))
    # a brand-new file with Korean not in baseline is also a regression
    for f, c in cur.items():
        if f not in base_files and f not in cleared and (f, base_files.get(f, 0), c) not in regressions:
            regressions.append((f, 0, c))

    base_total = base.get("total", sum(base_files.values()))
    if "--report" in sys.argv:
        print(f"burn-down: {total} / {base_total} Hangul chars  ({base_total - total} removed)")
        print(f"files remaining: {len(cur)} / {len(base_files)}   cleared: {len(cleared)}")
        for f, c in sorted(cur.items(), key=lambda kv: -kv[1])[:20]:
            print(f"  {c:5d}  {f}")
        return 0

    ok = not regressions and not dirty_cleared
    if dirty_cleared:
        print("FAIL: cleared files regained Korean (must stay clean):")
        for f, c in dirty_cleared:
            print(f"  +{c}  {f}")
    if regressions:
        print("FAIL: Korean rose above baseline (no NEW Korean allowed):")
        for f, b, c in regressions[:30]:
            print(f"  {b}->{c}  {f}")
    if ok:
        print(f"PASS: no regression. burn-down {total}/{base_total} "
              f"({base_total - total} removed, {len(cleared)} files sealed clean).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
