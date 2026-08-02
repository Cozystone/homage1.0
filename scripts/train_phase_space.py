# -*- coding: utf-8 -*-
"""Train the phase space over the live store's entity edges and report the
honest held-out link-prediction eval."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.graph_scale.phase_space import neighbors, resonance, train_phase_space  # noqa: E402
from packages.graph_scale.triple_store import TripleStore  # noqa: E402


def main() -> None:
    store = TripleStore(REPO / "data" / "graph_scale" / "kg_triples")
    result = train_phase_space(store)
    print("RESULT:", result)
    for probe in ("서울", "커피", "참새", "김치"):
        ns = neighbors(probe, k=6)
        if ns:
            print(f"  {probe} ->", ", ".join(f"{t}({s:.2f})" for t, s in ns))
    r1, r2 = resonance("서울", "도시"), resonance("서울", "커피")
    if r1 is not None and r2 is not None:
        print(f"  resonance(서울,도시)={r1:.3f}  vs  resonance(서울,커피)={r2:.3f}")


if __name__ == "__main__":
    main()
