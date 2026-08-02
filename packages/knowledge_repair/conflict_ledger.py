# -*- coding: utf-8 -*-
"""What ATANOR notices about its OWN knowledge while using it — not what an audit finds later.

The moment of noticing already existed and was being thrown away. In
`base_brain/relational_lookup.py::_predicate_targets`, a single-valued relation whose top targets
TIE means the store contradicts itself, and the code says:

    return "", []                      # ambiguous single-valued fact -> abstain

That line IS the system knowing its knowledge is merged. It abstained honestly and remembered
nothing, so the same wall was hit again on the next ask, forever. (The identical pattern as the
scene composer computing why a question was unreadable and discarding it.)

WHY THIS IS NOT A SCANNER. An offline sweep over the graph ranks by severity and surfaces
`'Untitled'.creator = 2861 values` at the top -- 2,861 different artworks called "Untitled" merged
into one node. Real, but nobody asks. Recording conflicts AS THEY BLOCK A REAL ANSWER ranks by
what actually gets in the way, which is the ordering repair should follow. Metacognition is
noticing during use, not being audited afterwards.

The ledger only records. It never decides which value is right -- that evidence is not in the
graph, which is exactly why the acquisition step has to go and look for it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "knowledge_repair" / "conflicts.jsonl"


@dataclass(frozen=True)
class Conflict:
    """One subject holding several values on a relation the graph says is single-valued."""
    subject: str
    predicate: str
    values: tuple[str, ...]
    hits: int = 1                      # how many separate asks walked into this

    def as_question(self) -> str:
        """What the acquisition step must find out. An open question, never an assumed answer:
        pre-committing to 'these are different things' would be the fabrication this avoids."""
        return (f"Does '{self.subject}' refer to more than one distinct thing? "
                f"My graph gives {len(self.values)} different values for '{self.predicate}': "
                f"{', '.join(self.values[:5])}.")


def record_conflict(subject: str, predicate: str, values: Any, *, source: str = "") -> None:
    """Append one sighting. Best-effort: a ledger fault must never touch the answer path."""
    try:
        vals = tuple(sorted({str(v).strip() for v in values if str(v).strip()}))
        if len(vals) < 2 or not str(subject).strip():
            return
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        # UTC, offset-bearing. It used to be naive local time, and `repair_verification` compares
        # timestamps to split the ledger at a repair claim -- so a claim written in UTC sorted
        # BEFORE conflicts that had actually happened nine hours earlier, and every repair was
        # graded `recurred` no matter what it did. One clock, stated.
        row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "subject": str(subject)[:200],
               "predicate": str(predicate)[:80], "values": [v[:120] for v in vals[:12]],
               "source": source}
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def standing_conflicts(limit: int = 50) -> list[Conflict]:
    """Conflicts ranked by how often they actually blocked an answer.

    Repetition is the signal, the same principle `self_repair.defect_ledger` uses for code: one
    sighting may be an odd query, the same wall hit again and again is a defect the system keeps
    walking into. Here the sightings are its own, not an advisor's."""
    seen: dict[tuple[str, str], list] = {}
    try:
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            key = (str(r.get("subject", "")), str(r.get("predicate", "")))
            if not key[0]:
                continue
            entry = seen.setdefault(key, [0, set()])
            entry[0] += 1
            entry[1].update(str(v) for v in (r.get("values") or []))
    except OSError:
        return []
    out = [Conflict(subject=k[0], predicate=k[1], values=tuple(sorted(v[1])), hits=v[0])
           for k, v in seen.items()]
    out.sort(key=lambda c: (-c.hits, -len(c.values)))
    return out[:limit]
