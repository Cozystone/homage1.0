# -*- coding: utf-8 -*-
"""Context Ledger — the local, bounded, append-only store of distilled activity.

The : what you have been engaging with, as CONCEPTS not content.
It never holds raw titles or screenshots (capture.py already discarded them). It is the
prior the answer engine can consult — 'what has the user been reading lately?' — without
any of it ever leaving the machine.

Bounded: keeps the latest N events + a rolling concept-frequency map (recency-weighted),
so the ledger cannot grow without limit and a stale interest fades.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .capture import ActivityEvent


class ContextLedger:
    def __init__(self, path: str | Path, max_events: int = 2000) -> None:
        self.path = Path(path)
        self.max_events = max_events

    def record(self, event: ActivityEvent) -> None:
        """Append a distilled event. Redacted events are logged as a redaction MARKER
        (so the audit shows the sensor stayed on) but carry no concepts."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        self._truncate()

    def _truncate(self) -> None:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            if len(lines) > self.max_events:
                self.path.write_text("\n".join(lines[-self.max_events:]) + "\n", encoding="utf-8")
        except FileNotFoundError:
            pass

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def interests(self, top: int = 12, half_life_events: int = 300) -> list[tuple[str, float]]:
        """Recency-weighted concept interests — the user's current context, decayed so old
        activity fades. Weight = 0.5 ** (age_in_events / half_life)."""
        events = self.recent(limit=self.max_events)
        n = len(events)
        weights: Counter[str] = Counter()
        for i, ev in enumerate(events):
            age = n - 1 - i
            w = 0.5 ** (age / max(1, half_life_events))
            for c in ev.get("concepts", []) or []:
                weights[c] += w
        return sorted(((c, round(v, 3)) for c, v in weights.items()), key=lambda x: -x[1])[:top]

    def stats(self) -> dict[str, Any]:
        events = self.recent(limit=self.max_events)
        redacted = sum(1 for e in events if e.get("redacted"))
        apps = Counter(e.get("app", "unknown") for e in events)
        return {
            "events": len(events),
            "redacted": redacted,
            "distinct_apps": len(apps),
            "top_apps": apps.most_common(5),
            "interests": self.interests(),
            "guarantees": {"raw_content_stored": False, "screenshots_stored": False,
                           "left_device": False, "concepts_only": True},
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
