# -*- coding: utf-8 -*-
"""Standalone, out-of-process oracle for B5-2-E2E. Reads {events, queries} as JSON on stdin, writes
the expected answers as JSON on stdout. It DOES NOT import SessionMemory -- it is an independent
forward-simulation of the declared bitemporal semantics, run in a SEPARATE PROCESS, so it cannot
share any in-memory state or code path with the store under test (GPT audit requirement).

Declared semantics (must match the charter, re-implemented here from scratch):
  current(s,p)  = latest non-retracted assert; None if the entity was deleted.
  as_of(s,p,t)  = belief at t: latest assert with valid-time <= t, applying only retractions whose
                  correction event-time <= t (a future correction is invisible to a past query).
  rumours never count; private edges are viewer-scoped; pure-revert (empty value) contributes nothing.
"""
from __future__ import annotations

import json
import sys


def _snapshot(events: list[dict], upto_t, viewer: str) -> dict:
    # INTERVAL model: replay prefix in time order; retract/pure-revert/delete END a value (gap).
    prefix = sorted((e for e in events if upto_t is None or e["t"] <= upto_t),
                    key=lambda e: (e["t"], e["fid"]))
    state: dict[tuple, str] = {}
    for e in prefix:
        op = e["op"]
        if op == "delete":
            for k in [k for k in state if k[0] == e["s"] and (e.get("p", "") == "" or k[1] == e["p"])]:
                del state[k]
            continue
        if op == "rumour":
            continue
        if op == "retract" or (op == "correct" and e.get("o", "") == ""):
            state.pop((e["s"], e["p"]), None)
            continue
        if op == "private" and e.get("owner") and e["owner"] != viewer:
            continue
        if op in ("assert", "correct", "private"):
            state[(e["s"], e["p"])] = e["o"]
    return {f"{k[0]}\t{k[1]}": v for k, v in state.items()}


def answer(events: list[dict], queries: list[dict]) -> list:
    out = []
    for q in queries:
        s, p, kind = q["s"], q.get("p", ""), q["kind"]
        if kind == "private":
            snap = _snapshot(events, None, "public")            # public viewer must not see private
            out.append(snap.get(f"{s}\t{p}"))
        elif kind == "asof":
            out.append(_snapshot(events, q["t"], "public").get(f"{s}\t{p}"))
        else:                                                   # current / missing
            out.append(_snapshot(events, None, "public").get(f"{s}\t{p}"))
    return out


if __name__ == "__main__":
    payload = json.loads(sys.stdin.read())
    print(json.dumps(answer(payload["events"], payload["queries"])))
