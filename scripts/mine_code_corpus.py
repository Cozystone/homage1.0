# -*- coding: utf-8 -*-
"""Mine (intent -> diff) pairs from our OWN git history — 1599 commits of real, license-clean,
human-authored code changes. This is to code authorship what bones->text was to language: the
commit message is the INTENT (the spec), the diff is the REALIZATION (the change). Self-supervised,
zero external data, zero LLM-generated content.

Bounded to small, single-file, single-hunk changes — the learnable atomic units. Writes JSONL:
{intent, path, hunk_header, added:[...], removed:[...], lang}.

  python scripts/mine_code_corpus.py [--max 800]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "code_reason" / "intent_diff_corpus.jsonl"
MAX_HUNK_LINES = 40                 # only atomic changes; giant refactors are not learnable units


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def mine(max_pairs: int) -> int:
    shas = _git("log", "--format=%H", "-n", "4000").split()
    pairs = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as g:
        for sha in shas:
            if pairs >= max_pairs:
                break
            subject = _git("log", "-1", "--format=%s", sha).strip()
            if not subject or subject.startswith("Merge"):
                continue
            # single-file commits only (one clear intent -> one file's change)
            files = [l for l in _git("show", "--name-only", "--format=", sha).splitlines() if l.strip()]
            if len(files) != 1 or not files[0].endswith((".py", ".ts", ".tsx", ".rs")):
                continue
            diff = _git("show", "--format=", "--unified=0", sha)
            added, removed, header = [], [], ""
            for line in diff.splitlines():
                if line.startswith("@@"):
                    header = line
                elif line.startswith("+") and not line.startswith("+++"):
                    added.append(line[1:])
                elif line.startswith("-") and not line.startswith("---"):
                    removed.append(line[1:])
            if not added and not removed:
                continue
            if len(added) + len(removed) > MAX_HUNK_LINES:
                continue
            g.write(json.dumps({
                "intent": subject, "path": files[0], "hunk_header": header,
                "added": added, "removed": removed,
                "lang": files[0].rsplit(".", 1)[-1],
            }, ensure_ascii=False) + "\n")
            pairs += 1
    return pairs


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 800
    n = mine(mx)
    langs: dict[str, int] = {}
    for line in OUT.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        langs[rec["lang"]] = langs.get(rec["lang"], 0) + 1
    print(f"mined {n} (intent -> diff) atomic pairs -> {OUT}")
    print(f"by language: {langs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
