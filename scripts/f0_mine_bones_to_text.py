# -*- coding: utf-8 -*-
"""Track F / F0 — mine (BONES -> fluent SENTENCE) distant-supervision pairs (the neuro-symbolic core).

The realizer's job is form, not knowledge: given symbolic bones (graph triples) it must produce a
fluent natural sentence, and it must NOT itself store the fact. This miner builds that supervision by
aligning ATANOR's OWN graph to real wiki prose: each body paragraph's TITLE is the subject entity, so
we look up that subject's graph neighbourhood (bones) and keep the bones whose object is actually
present in a given sentence -> (those bones, that sentence). No-LLM, No fabrication (every bone is a
stored edge; every sentence is real prose), zero human labels.

  data/graph_scale/bones_to_text.jsonl   {"subject","bones":[[s,rel,o],...],"text": sentence}

This is the F1 realizer's training signal. Symbolic in, fluent out — the bridge the whole Track F
rests on. Coverage grows with graph_pairs (re-mine more subjects to raise it).

  python scripts/f0_mine_bones_to_text.py [max_pairs] [--body path]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.reasoning_vm.ace.match_features import tokenize, _stem   # noqa: E402

GRAPH_PAIRS = REPO / "data" / "graph_scale" / "graph_pairs.jsonl"
BODY = REPO / "data" / "graph_scale" / "wiki_passages_en_body" / "passages.tsv"
OUT = REPO / "data" / "graph_scale" / "bones_to_text.jsonl"
_SENT = re.compile(r"(?<=[.!?])\s+")
_STOP = {"the", "a", "an", "of", "to", "in", "is", "are", "was", "were", "and", "or", "for", "on",
         "at", "by", "with", "as", "it", "its", "this", "that", "from", "be"}


def _load_bones() -> dict[str, list[tuple[str, str]]]:
    """subject(lower) -> [(relation, object), ...] parsed from the mined graph neighbourhoods."""
    idx: dict[str, list[tuple[str, str]]] = {}
    if not GRAPH_PAIRS.exists():
        return idx
    with GRAPH_PAIRS.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            neigh = str(r.get("neighborhood") or "")
            if ":" not in neigh:
                continue
            subj, rest = neigh.split(":", 1)
            facts = []
            for chunk in rest.split(";"):
                parts = chunk.strip().split(" ", 1)
                if len(parts) == 2 and parts[1].strip():
                    facts.append((parts[0], parts[1].strip()))
            if facts:
                idx[subj.strip().lower()] = facts
    return idx


def _obj_present(obj: str, sent_stems: set[str]) -> bool:
    """The object's content stems must ALL be in the sentence (distinctive expression, not a stray word)."""
    ostems = {_stem(w) for w in tokenize(obj) if w.lower() not in _STOP and len(w) > 1}
    return bool(ostems) and ostems <= sent_stems


def main() -> int:
    max_pairs = int(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else 2_000_000
    body = Path(sys.argv[sys.argv.index("--body") + 1]) if "--body" in sys.argv else BODY
    if not body.exists():
        print(f"body corpus missing: {body} — run scripts/b2_build_fullarticle_corpus.py")
        return 1
    bones_idx = _load_bones()
    print(f"loaded bones for {len(bones_idx):,} subjects; streaming {body.parent.name}…", flush=True)

    written = seen_rows = hit_titles = 0
    fout = OUT.open("w", encoding="utf-8")
    with body.open(encoding="utf-8") as fh:
        for line in fh:
            seen_rows += 1
            tab = line.find("\t")
            if tab < 0:
                continue
            title, para = line[:tab], line[tab + 1:].strip()
            facts = bones_idx.get(title.strip().lower())
            if not facts:
                continue
            hit_titles += 1
            for sent in _SENT.split(para):
                if len(sent) < 30 or len(sent) > 400:
                    continue
                sent_stems = {_stem(w) for w in tokenize(sent)}
                bones = [[title, rel, obj] for rel, obj in facts if _obj_present(obj, sent_stems)]
                if bones:
                    fout.write(json.dumps({"subject": title, "bones": bones[:6], "text": sent},
                                          ensure_ascii=False) + "\n")
                    written += 1
                    if written >= max_pairs:
                        break
            if written >= max_pairs:
                break
            if seen_rows % 2_000_000 == 0:
                print(f'  rows {seen_rows:,} · title-hits {hit_titles:,} · pairs {written:,}', flush=True)
    fout.close()
    print(f"\nRESULT bones_to_text {{'pairs': {written}, 'title_hits': {hit_titles}, "
          f"'rows_scanned': {seen_rows}, 'out': '{OUT.name}'}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
