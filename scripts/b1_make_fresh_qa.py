# -*- coding: utf-8 -*-
"""Tier B / B1 — generate a FRESH, sealed short-passage extractive-QA test (the "시험지").

SQuAD cannot be the exam — the B1 span head trains on it, so testing on it measures memorisation.
This builds fresh passage-QA from ATANOR's OWN graph (data/graph_scale/graph_pairs.jsonl): a handful
of a subject's real relations are verbalised into a short passage, and one relation is asked so the
answer is a contiguous SPAN in that passage. No-LLM (every fact is a stored edge), fresh (generated
now, SHA-sealed), machine-checkable (exact span match). The distractor facts make it real extraction:
the model must locate the RIGHT span, not just any noun.

  python scripts/b1_make_fresh_qa.py [n] [seed]
Output: data/benchmarks/b1_fresh/qa_{seed}.jsonl  (+ a sha manifest). Held out until the L1/L2/L3
span ladder is measured against it; the file is the sealed instrument, never trained on.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAIRS = REPO / "data" / "graph_scale" / "graph_pairs.jsonl"
OUTDIR = REPO / "data" / "benchmarks" / "b1_fresh"

# relation -> (passage verbalisation, question). Polysemy-prone / gloss relations (is_a, defined_as)
# are excluded so every item is well-posed; the object must read as a clean noun-phrase span.
_TEMPLATES = {
    "located_in":  ("The {s} is found in the {o}.",       "Where is the {s} found?"),
    "capable_of":  ("A {s} can {o}.",                     "What can a {s} do?"),
    "has_property": ("The {s} is {o}.",                   "What is the {s} like?"),
    "used_for":    ("A {s} is used for {o}.",             "What is a {s} used for?"),
    "part_of":     ("A {s} is part of a {o}.",            "What is a {s} part of?"),
    "made_of":     ("A {s} is made of {o}.",              "What is a {s} made of?"),
    "has_a":       ("A {s} has a {o}.",                   "What does a {s} have?"),
    "manner_of":   ("A {s} is a manner of {o}.",          "What is a {s} a manner of?"),
}


def _parse(neigh: str) -> tuple[str, list[tuple[str, str]]]:
    if ":" not in neigh:
        return "", []
    subj, rest = neigh.split(":", 1)
    facts = []
    for chunk in rest.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(" ", 1)
        if len(parts) == 2 and parts[0] in _TEMPLATES:
            rel, obj = parts[0], parts[1].strip()
            if obj and len(obj) <= 40:
                facts.append((rel, obj))
    return subj.strip(), facts


def _make_item(subj: str, facts: list[tuple[str, str]], rng: random.Random):
    # dedupe relations (one fact per relation) and require >=2 so there is a real distractor
    seen, uniq = set(), []
    for rel, obj in facts:
        if rel not in seen:
            seen.add(rel)
            uniq.append((rel, obj))
    if len(uniq) < 2:
        return None
    rng.shuffle(uniq)
    chosen = uniq[:3]
    target_rel, target_obj = chosen[0]
    sentences = [_TEMPLATES[r][0].format(s=subj, o=o) for r, o in chosen]
    rng.shuffle(sentences)
    passage = " ".join(sentences)
    question = _TEMPLATES[target_rel][1].format(s=subj)
    # answer span = the target object, located verbatim in the assembled passage
    start = passage.find(target_obj)
    if start < 0:
        return None
    # reject if the object string occurs more than once (ambiguous span) or is trivially the subject
    if passage.count(target_obj) != 1 or target_obj.lower() == subj.lower():
        return None
    return {"subject": subj, "question": question, "passage": passage,
            "answer": target_obj, "answer_start": start, "relation": target_rel}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20260719
    if not PAIRS.exists():
        print(f"no graph_pairs at {PAIRS} — run scripts/ace2_mine_graph_pairs.py first")
        return 1

    rng = random.Random(seed)
    rows = []
    with PAIRS.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    rng.shuffle(rows)

    items, seen_sha = [], set()
    for r in rows:
        subj, facts = _parse(str(r.get("neighborhood") or ""))
        if not subj or not facts:
            continue
        it = _make_item(subj, facts, rng)
        if not it:
            continue
        sha = hashlib.sha256(json.dumps({"q": it["question"], "p": it["passage"]},
                                        sort_keys=True).encode()).hexdigest()[:16]
        if sha in seen_sha:
            continue
        seen_sha.add(sha)
        it["sha"] = sha
        items.append(it)
        if len(items) >= n:
            break

    # sanity: every answer must align as a verbatim span (the machine-checkable guarantee)
    aligned = sum(1 for it in items if it["passage"][it["answer_start"]:
                                                    it["answer_start"] + len(it["answer"])] == it["answer"])
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / f"qa_{seed}.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    manifest_sha = hashlib.sha256("".join(sorted(it["sha"] for it in items)).encode()).hexdigest()[:16]
    (OUTDIR / f"qa_{seed}.manifest.json").write_text(
        json.dumps({"n": len(items), "seed": seed, "aligned": aligned,
                    "manifest_sha": manifest_sha, "source": "graph_pairs.jsonl"}, indent=2),
        encoding="utf-8")

    by_rel: dict[str, int] = {}
    for it in items:
        by_rel[it["relation"]] = by_rel.get(it["relation"], 0) + 1
    print(f"=== B1 fresh sealed passage-QA generated ===")
    print(f"items {len(items)} · span-aligned {aligned}/{len(items)} · manifest {manifest_sha}")
    print(f"by relation: {by_rel}")
    print(f"wrote {out.relative_to(REPO)}")
    if items:
        ex = items[0]
        print(f"\nexample:\n  passage: {ex['passage']}\n  question: {ex['question']}\n  answer: {ex['answer']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
