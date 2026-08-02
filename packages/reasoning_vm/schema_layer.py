# -*- coding: utf-8 -*-
""" L2 — / . " ?" 
restaurant ****( ) . ·
1 , (). "" "" 
 SCHEMA (≈GUESSED ) — . No LLM.

: docs/ATANOR_brainlike_graph_design.md ( 2601.18946)."""
from __future__ import annotations

from typing import Any, Optional


class SchemaLayer:
    def __init__(self):
        # name → {"triggers": set, "slots": {slot: value}, "steps": [ordered]}
        self.schemas: dict[str, dict] = {}
        self._trigger_index: dict[str, str] = {}     # trigger word → schema name

    def add(self, name: str, triggers: list[str] | None = None,
            slots: dict[str, str] | None = None, steps: list[str] | None = None) -> None:
        self.schemas[name] = {"triggers": set(triggers or []) | {name},
                              "slots": dict(slots or {}), "steps": list(steps or [])}
        for t in self.schemas[name]["triggers"]:
            self._trigger_index[t.lower()] = name

    def match(self, key: str) -> Optional[str]:
        """ / ."""
        k = str(key).lower()
        if k in self.schemas:
            return k
        if k in self._trigger_index:
            return self._trigger_index[k]
        for w in k.replace("?", " ").split():
            if w in self._trigger_index:
                return self._trigger_index[w]
        for t in sorted(self._trigger_index, key=len, reverse=True):
            if len(t) >= 2 and t in k:
                return self._trigger_index[t]
        return None

    def slot(self, situation: str, p: str) -> Optional[str]:
        """ (). None."""
        name = self.match(situation)
        if name is None:
            return None
        return self.schemas[name]["slots"].get(p)

    def script(self, situation: str) -> Optional[list[str]]:
        name = self.match(situation)
        return self.schemas[name]["steps"] if name else None

    def answer(self, situation: str, p: str, conf: float = 0.65) -> Optional[dict[str, Any]]:
        """(, ) → SCHEMA . None ( )."""
        val = self.slot(situation, p)
        if val is None:
            return None
        return {"answer": val, "epistemic_type": "SCHEMA", "confidence": round(conf, 3),
                "path": [f"schema:{self.match(situation)}.{p} (전형적)"],
                "surface": f"보통 {val}입니다."}
