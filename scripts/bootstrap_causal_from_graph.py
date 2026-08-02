# -*- coding: utf-8 -*-
"""Bootstrap the causal graph from the rich prose ATANOR already holds — no web, no download.

The causal relation extractor was measured data-starved: search snippets are terse and
dictionary-polluted, so live harvest yielded almost nothing. But a rich causal-prose source is
already local — data/graph_scale/bones_to_text.jsonl carries an English text field per subject
(mined encyclopedic sentences), and ~3.9% of them state causation ("trial court decisions result
in appeals", "visual impairment prevents use"). This reads those, extracts stated causation, and
records it under the SAME consensus store the live harvest uses.

Consensus = independent SUBJECTS agreeing. Each subject's article is one source, so a causal edge
becomes eligible for the graph only when two DIFFERENT articles state it — which is exactly what
filters the extractor's boundary noise ("ueshiba's involvement causes partly" appears once and never
reaches consensus; "friction causes heat" recurs and does). Nothing is asserted here: consensus
edges land in the quarantined store with source counts, offered to the promotion gate via to_bones,
never a silent production write. Doctrine intact — extraction not generation, consensus not
assertion, quarantine not injection.

  python scripts/bootstrap_causal_from_graph.py [max_subjects]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.temporal_reasoning.causal_relation_extractor import (consensus_edges, extract,
                                                                   observe, stats)

GRAPH = REPO / "data" / "graph_scale" / "bones_to_text.jsonl"


def main() -> int:
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else 200000
    t0 = time.time()
    n = with_text = with_causal = obs = 0
    with GRAPH.open(encoding="utf-8") as f:
        for line in f:
            if n >= cap:
                break
            n += 1
            try:
                r = json.loads(line)
            except Exception:
                continue
            text = r.get("text") or ""
            if not text:
                continue
            with_text += 1
            edges = extract(text)
            if not edges:
                continue
            with_causal += 1
            # the SUBJECT is the source key: two different articles stating the same edge = consensus
            obs += observe(edges, domain=f"graph:{r.get('subject','')[:40]}")
            if n % 20000 == 0:
                print(f"  {n} scanned, {with_causal} causal, {obs} observations, "
                      f"{stats()['consensus_edges']} consensus so far ({time.time()-t0:.0f}s)")

    st = stats()
    cons = consensus_edges(min_sources=2)
    print(f"\nscanned {n} subjects ({with_text} had text), {with_causal} stated causation")
    print(f"candidate edges {st['candidate_edges']}, CONSENSUS edges (>=2 articles) {st['consensus_edges']}")
    print(f"consensus by relation: {st['by_relation']}")
    print(f"top consensus causal edges (graph-bone candidates):")
    for e in cons[:15]:
        print(f"  {e['cause']} --{e['relation']}--> {e['effect']}  ({e['sources']} articles)")
    print(f"\nelapsed {time.time()-t0:.0f}s — quarantined store, offered to the promotion gate, "
          f"never written to production here")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
