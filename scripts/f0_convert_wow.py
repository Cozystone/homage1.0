# -*- coding: utf-8 -*-
"""Track F / F0 — convert the acquired WoW dump (post/knowledge/labels/response) into grounded
realizer pairs: {"bones":[[topic, grounded_in, sentence]], "history":[...], "text": wizard_reply}.
Each pair is a HUMAN-written fluent reply grounded in a wiki sentence = the realizer task in
dialogue form (P3b history conditioning). CC-BY-SA lineage, No-LLM.
  python scripts/f0_convert_wow.py"""
from __future__ import annotations
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
SRC = Path("D:/atanor_corpus/dialogue/wow_raw.jsonl")
OUT = REPO / "data" / "graph_scale" / "dialogue_grounded.jsonl"

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    n = skipped = 0
    with SRC.open(encoding="utf-8") as fin, OUT.open("w", encoding="utf-8") as fout:
        for line in fin:
            try:
                r = json.loads(line)
            except Exception:
                continue
            post, know, labels, resp = r.get("post") or [], r.get("knowledge") or [], \
                r.get("labels") or [], r.get("response") or []
            topics = r.get("topics") or []
            for i, reply in enumerate(resp):
                if i >= len(know) or i >= len(labels):
                    break
                cands = know[i]
                li = labels[i]
                if not isinstance(cands, list) or not (0 <= li < len(cands)):
                    continue
                sel = cands[li]
                if "__knowledge__" not in sel or "no_passages_used" in sel:
                    skipped += 1
                    continue
                topic, sent = sel.split("__knowledge__", 1)
                reply = (reply or "").strip()
                sent = sent.strip()
                if len(reply) < 10 or len(sent) < 20:
                    skipped += 1
                    continue
                hist = [t.strip() for t in post[: i + 1] if t and t.strip()][-3:]
                fout.write(json.dumps({"bones": [[topic.strip() or (topics[i] if i < len(topics) else ""),
                                                  "grounded_in", sent]],
                                       "history": hist, "text": reply}, ensure_ascii=False) + "\n")
                n += 1
    print(f"RESULT wow_convert {{'pairs': {n}, 'skipped_nopassage': {skipped}, 'out': '{OUT.name}'}}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
