#!/usr/bin/env python3
"""Feed an external dataset into ATANOR's cumulative graph learner.

ATANOR is NOT an LLM and does NOT train on a corpus by gradient descent. Its only
form of "learning" is sentence ingestion: each DECLARATIVE sentence goes through the
verification gate -> decomposer -> verified graph store (concepts + relations + IS_A).
So the datasets that actually help are the ones with clean declarative knowledge or
QA answers. This script turns such a dataset into sentences and POSTs them, in
batches, to the SAME endpoint the continuous web-learner uses:

    POST /api/cloud-brain/learning/tick   (payloads -> gate -> decompose -> graph)

It does NOT touch any rule table and does NOT invent facts — it only forwards source
sentences. Honest about scope (see --kind code below).

Supported input shapes (auto-detected per row), JSONL or a .txt (one item per line):
  - {"text": "..."}                          plain declarative text
  - {"output": "..."}                        Alpaca-style (uses the output/answer)
  - {"answer": "..."} / {"a": "..."}         QA answer
  - {"question": "...", "answer": "..."}     QA pair -> "Q? A." declarative-ish
  - {"instruction": "...", "output": "..."}  uses output; if --kind code, uses the
                                              instruction (the NL "what it does")

--kind code: for CODE datasets (e.g. Code-Instructions, StarCoder), this feeds the
  NATURAL-LANGUAGE description fields ONLY (instruction / docstring / problem), never
  raw source code — the NL decomposer would produce garbage from raw code, and a real
  code-reasoning capability needs an AST->graph ingester, which is a separate engine.

LICENSE: you are responsible for the dataset's license. Pass --license so it is
recorded as provenance on every accepted sentence. For a COMMERCIAL demo, avoid
non-commercial sets (e.g. Alpaca / anything OpenAI-output-derived).

Usage:
  python scripts/feed_dataset.py data.jsonl --license "apache-2.0" --max 500
  python scripts/feed_dataset.py code.jsonl --kind code --license "bigcode-openrail-m"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request

# Windows consoles default to cp949 and choke on Korean / em-dashes when printing.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

_WS = re.compile(r"\s+")
# A declarative sentence has an end mark or a Korean predicate ending; questions and
# bare fragments are skipped (they don't decompose into clean SUBJ-REL-OBJ facts).
_KO_PRED = re.compile(r"(다|이다|입니다|한다|된다|났다|있다|없다)\.?$")
_HANGUL = re.compile(r"[가-힣]")
_QUESTION = re.compile(r"[?？]\s*$")
_CODEY = re.compile(r"[{};=<>]|def |class |import |function |const |println|System\.|</?\w+>")


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "").replace(" ", " ")).strip()


def _row_to_texts(row: dict, kind: str) -> list[str]:
    """Pull the declarative NL text out of one dataset row, honoring --kind."""
    if kind == "code":
        # NL description fields only — never raw code. Fall back to text/content
        # (datasets pulled via fetch_hf_rows.py land their chosen field in "text").
        for key in ("instruction", "prompt", "problem", "docstring", "description", "question", "text", "content"):
            v = _norm(str(row.get(key) or ""))
            if v and not _CODEY.search(v):
                return [v]
        return []
    parts: list[str] = []
    q = _norm(str(row.get("question") or row.get("q") or ""))
    a = _norm(str(row.get("answer") or row.get("a") or row.get("output") or row.get("response") or ""))
    if a:
        parts.append(a)
    elif q:
        parts.append(q)
    plain = _norm(str(row.get("text") or row.get("content") or ""))
    if plain and plain not in parts:
        parts.append(plain)
    return parts


def _sentences(text: str) -> list[str]:
    """Split into sentence-ish units and keep only clean declaratives."""
    out: list[str] = []
    for raw in re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s+|\n+", text):
        seg = _norm(raw)
        if not (18 <= len(seg) <= 1000):
            continue
        if _QUESTION.search(seg):
            continue
        if _CODEY.search(seg):  # skip stray code lines even in NL datasets
            continue
        is_ko = bool(_HANGUL.search(seg))
        # English: must look like a statement (has a verb-ish token); Korean: predicate ending.
        if is_ko and not _KO_PRED.search(seg):
            continue
        if not is_ko and not re.search(
            r"\b(is|are|was|were|has|have|had|refers|means|describes|consists|became|becomes|"
            r"provides|includes|represents|defines|specifies|denotes|returns|computes|converts|"
            r"creates|generates|performs|implements|contains|supports|enables|produces|stores)\b",
            seg, re.I):
            continue
        out.append(seg)
    return out


def _post(backend: str, payloads: list[dict], timeout: float = 120.0) -> dict:
    body = json.dumps({
        "payloads": payloads,
        "max_payloads_per_tick": len(payloads),
        "max_accepted_per_run": len(payloads),
        "promote_to_verified": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        backend.rstrip("/") + "/api/cloud-brain/learning/tick",
        data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Feed a dataset into ATANOR's graph learner.")
    ap.add_argument("path", help="JSONL / JSON-array / .txt dataset file")
    ap.add_argument("--license", default="unknown", help="dataset license, recorded as provenance")
    ap.add_argument("--kind", choices=["knowledge", "code"], default="knowledge")
    ap.add_argument("--source-type", default="approved_public_corpus",
                    help="verification-gate allowed source_type (default approved_public_corpus)")
    ap.add_argument("--source-name", default="external_dataset", help="provenance label")
    ap.add_argument("--max", type=int, default=400, help="max sentences to feed")
    ap.add_argument("--batch", type=int, default=25, help="sentences per POST (<=100)")
    ap.add_argument("--backend", default="http://127.0.0.1:8502")
    ap.add_argument("--dry-run", action="store_true", help="parse + print, do not POST")
    args = ap.parse_args()

    # Load rows (JSONL preferred; fall back to a JSON array; else one text per line).
    rows: list[dict] = []
    with open(args.path, "r", encoding="utf-8") as fh:
        head = fh.read()
    head_strip = head.lstrip()
    if head_strip.startswith("["):
        rows = [r for r in json.loads(head) if isinstance(r, dict)]
    else:
        for line in head.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                rows.append(obj if isinstance(obj, dict) else {"text": str(obj)})
            except Exception:
                rows.append({"text": line})

    # Rows -> clean declarative sentences.
    seen: set[str] = set()
    sentences: list[str] = []
    for row in rows:
        for txt in _row_to_texts(row, args.kind):
            for seg in _sentences(txt):
                if seg not in seen:
                    seen.add(seg)
                    sentences.append(seg)
                    if len(sentences) >= args.max:
                        break
            if len(sentences) >= args.max:
                break
        if len(sentences) >= args.max:
            break

    print(f"parsed {len(rows)} rows -> {len(sentences)} clean declarative sentences "
          f"(kind={args.kind}, license={args.license})")
    if not sentences:
        print("nothing to feed (no clean declarative sentences found).")
        return 1
    if args.dry_run:
        for s in sentences[:10]:
            print("  ·", s)
        print("(dry run — not POSTed)")
        return 0

    fed = accepted = concepts = relations = 0
    ts = int(time.time() * 1000)
    for i in range(0, len(sentences), max(1, min(100, args.batch))):
        chunk = sentences[i:i + args.batch]
        payloads = [{
            "source_type": args.source_type,
            "source_id": f"{args.source_name}:{ts}:{i+j}",
            "text": seg,
            "language": "ko" if _HANGUL.search(seg) else "en",
            "license_hint": args.license[:120],
            "source_url_or_path": args.source_name[:800],
        } for j, seg in enumerate(chunk)]
        try:
            d = _post(args.backend, payloads)
        except Exception as exc:
            print(f"  batch {i//args.batch} POST failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        sem = (d.get("semantic") or {})
        fed += len(payloads)
        accepted += int(sem.get("payloads_accepted") or 0)
        concepts += int(sem.get("concepts_added") or 0)
        relations += int(sem.get("relations_added") or 0)
        print(f"  batch {i//args.batch}: fed {len(payloads)} | "
              f"accepted {sem.get('payloads_accepted')} | +{sem.get('concepts_added')} concepts | "
              f"+{sem.get('relations_added')} relations")

    print(f"\nDONE  fed={fed}  accepted={accepted}  concepts+={concepts}  relations+={relations}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
