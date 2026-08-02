# -*- coding: utf-8 -*-
"""Korean-era remnant audit — triage by RISK, not by raw count.

Owner directive (2026-07-18): "find and excise every Korean-era remnant, cleanly overlay the
English era." A blind translate-everything pass is dangerous: ~16k Korean string literals exist,
and MANY must stay Korean — the [-] input detector, the Korean refusal message, intentional
Korean deliverables (business plan / pitch deck for the owner), and tests OF retired Korean
features. The real breach is not "Korean text in code"; it is Korean reaching a USER, or a Korean
lane still WIRED into the live answer path. So this classifies each Korean literal by context.

Risk tiers (highest first):
 R1 user_output Korean in a value that becomes answer/text the user reads (return dicts with
 answer/text/message keys, f-strings assigned to `answer`/`text`). THE breach.
 R2 live_routing Korean dict KEYS or regex used for routing/matching on the answer path (a
 Korean key can silently never match English input).
 R3 dead_feature files whose whole purpose is a retired Korean feature (kiwi/josa/korean_*),
 candidates for DELETION not translation.
 R4 legitimate the [-] detector, the refusal string, Korean deliverable generators — KEEP.
 R5 cosmetic comments / docstrings — harmless, lowest priority.

Read-only. Writes reports/korean_remnants.json. Usage: python scripts/audit_korean_remnants.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HAN = re.compile(r"[가-힣]")
ROOTS = ["packages", "scripts", "apps/api"]
OUT = REPO / "reports" / "korean_remnants.json"

# files that are INTENTIONALLY Korean (owner deliverables / the guard itself) — keep, never flag R1
LEGIT_FILES = re.compile(
    r"business_plan|pitch_deck|bizplan|_ko\.py$|korean_|_hangul", re.IGNORECASE)
# whole-purpose retired-Korean feature files (deletion candidates)
DEAD_FEATURE = re.compile(r"kiwi|josa|korean_discourse|korean_realizer|hangul|어문|조사", re.IGNORECASE)
# answer-bearing assignment targets / dict keys
ANSWER_KEYS = re.compile(r'^\s*["\'](answer|text|message|summary|reply|response|body)["\']\s*:', )
ANSWER_ASSIGN = re.compile(r'\b(answer|text|reply|response|msg|message)\s*(?:=|\+=)\s*$')


def classify(path: str, tok: tokenize.TokenInfo, src_lines: list[str]) -> str:
    line = src_lines[tok.start[0] - 1] if tok.start[0] <= len(src_lines) else ""
    if tok.type == tokenize.COMMENT:
        return "R5_cosmetic"
    if tok.type != tokenize.STRING:
        return "R5_cosmetic"
    # docstring: a bare string statement
    stripped = line.strip()
    if stripped.startswith(('"""', "'''")) and tok.string.startswith(('"""', "'''")):
        return "R5_cosmetic"
    if LEGIT_FILES.search(path):
        return "R4_legitimate"
    # the input detector / refusal: a literal containing the han-range regex or the refusal text
    if "가-힣" in tok.string or "I can only speak English" in tok.string:
        return "R4_legitimate"
    if DEAD_FEATURE.search(path):
        return "R3_dead_feature"
    # user output: string is a value of an answer-ish key, OR assigned to an answer var
    before = line[:tok.start[1]]
    # THE `return "..."` RULE NEVER FIRED. It searched `before` for a trailing quote -- and `before` is
    # everything to the LEFT of the token, so it stops immediately before that quote and can never contain
    # it. Every user-facing Korean string that a function simply RETURNS was therefore filed as
    # R2_live_routing, a 14,000-item bucket nobody can act on.
    #
    # Found 2026-07-31 while chasing packages/perception/open_vocab.py, which emits Korean region words
    # ("왼쪽" / "오른쪽" / "가운데") from `return` statements on a live_default path -- user-facing scene
    # descriptions -- and showed up in this audit as 36 R2 hits and zero R1. The English-only record was
    # being kept by a classifier that could not see returned strings.
    if ANSWER_KEYS.match(line) or re.search(r'["\'](answer|text|message|summary|reply)["\']\s*:\s*$', before) \
            or ANSWER_ASSIGN.search(before) or re.search(r'\breturn\s+f?$', before) \
            or re.search(r'\belse\s+f?$', before):
        return "R1_user_output"
    # routing: Korean used as a dict key or in a regex/compile
    if re.search(r'\bre\.(compile|search|match|sub|findall)\b', line) or before.rstrip().endswith("["):
        return "R2_live_routing"
    if re.search(r':\s*$', before) and "{" in "".join(src_lines[max(0, tok.start[0] - 3):tok.start[0]]):
        return "R2_live_routing"
    return "R2_live_routing"          # default: assume it can matter until proven cosmetic


def main() -> int:
    buckets: dict[str, list[dict]] = {k: [] for k in
                                      ["R1_user_output", "R2_live_routing", "R3_dead_feature",
                                       "R4_legitimate", "R5_cosmetic"]}
    per_file: dict[str, dict[str, int]] = {}
    for root in ROOTS:
        for p in Path(root).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            try:
                src = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if not HAN.search(src):
                continue
            rel = str(p).replace("\\", "/")
            lines = src.splitlines()
            try:
                toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
            except Exception:
                continue
            fc = per_file.setdefault(rel, {})
            for t in toks:
                if not HAN.search(t.string):
                    continue
                tier = classify(rel, t, lines)
                fc[tier] = fc.get(tier, 0) + 1
                if tier in ("R1_user_output", "R3_dead_feature") and len(buckets[tier]) < 120:
                    buckets[tier].append({"file": rel, "line": t.start[0],
                                          "text": t.string[:90]})
    totals = {k: sum(f.get(k, 0) for f in per_file.values()) for k in buckets}
    # files ranked by R1 then R2
    ranked = sorted(per_file.items(),
                    key=lambda kv: (-kv[1].get("R1_user_output", 0), -kv[1].get("R2_live_routing", 0)))
    # EVERY R1 FILE, NOT THE TOP FORTY. Ranking by VOLUME buried the thing that mattered: on 2026-07-31
    # packages/perception/open_vocab.py was found emitting Korean region words on a live_default path --
    # user-facing scene descriptions -- and it never appeared in this report, because a test file with 90
    # cosmetic Korean comments outranks a live file with three. Reach is what makes a remnant serious, not
    # how much of it there is. 127 R1 hits is small enough to list exhaustively, so it is listed.
    r1_files = sorted((f for f, c in per_file.items() if c.get("R1_user_output", 0)),
                      key=lambda f: -per_file[f].get("R1_user_output", 0))
    rep = {"totals": totals, "files_with_hangul": len(per_file),
           "R1_files_ALL": [{"file": f, "R1": per_file[f].get("R1_user_output", 0),
                             "R2": per_file[f].get("R2_live_routing", 0)} for f in r1_files],
           "top_files": [{"file": f, **c} for f, c in ranked[:40]],
           "R1_samples": buckets["R1_user_output"][:60],
           "R3_dead_feature_files": sorted({s["file"] for s in buckets["R3_dead_feature"]})}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== Korean remnant triage (by risk) ===")
    for k in ["R1_user_output", "R2_live_routing", "R3_dead_feature", "R4_legitimate", "R5_cosmetic"]:
        print(f"  {k:18s} {totals[k]:6d}")
    print(f"\n  files with Hangul: {len(per_file)}")
    print(f"\n  top files by user-output risk (R1|R2|R3):")
    for f, c in ranked[:20]:
        print(f"    R1={c.get('R1_user_output',0):4d} R2={c.get('R2_live_routing',0):4d} "
              f"R3={c.get('R3_dead_feature',0):4d}  {f}")
    # AND THEN EVERY ONE OF THEM. The list above is ranked by volume, which is what hid
    # packages/perception/open_vocab.py: it emits Korean region words on a live_default path -- user-facing
    # scene descriptions -- from only three sites, so a test file with ninety cosmetic comments outranked
    # it and it never appeared. Reach is what makes a remnant serious, not how much of it there is.
    print(f"\n  EVERY file with user-output Korean ({len(r1_files)}), volume no longer hides reach:")
    for f in r1_files:
        print(f"    R1={per_file[f].get('R1_user_output', 0):4d}  {f}")
    print(f"\n  wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
