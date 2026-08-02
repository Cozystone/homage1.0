# -*- coding: utf-8 -*-
"""D1 — Sleep Consolidation Daemon: the artificial-CLS "sleep" phase. Awake, the live buffer (hippocampus)
takes one-shot episodic facts and the miss log records what the system could not answer. Asleep, this
daemon REPLAYS the day: it promotes VERIFIED live facts into a durable cortex store (hippocampus→cortex
systems consolidation) and MINES the misses into a training curriculum (the deficits to target). "You wake
up smarter" — engineered.

Hallucination-0 preserved: only verified items consolidate; provenance carries; the cortex is a durable
LiveMemory so consolidated facts stay recallable after the volatile buffer is cleared. The heavy TCT
training that the mined curriculum feeds runs separately, behind the A/B win-gate. No LLM.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from packages.reasoning_vm.live_memory import LiveMemory, _toks

REPO = Path(__file__).resolve().parents[2]
_BASE = REPO / "data" / "graph_scale" / "live_memory"
HIPPO = _BASE / "store.jsonl"          # volatile episodic buffer (the day)
CORTEX = _BASE / "cortex.jsonl"        # durable consolidated semantic store
MISSLOG = _BASE / "misses.jsonl"       # what the system could not ground (the deficit signal)


class MissLog:
    """Episodic record of misses — ungrounded / low-confidence answers. The deficit signal that drives
    both curiosity (D3) and the training curriculum (D1 deep sleep)."""
    def __init__(self, path: Path = MISSLOG):
        self.path = path

    def record(self, question: str, answer: str = "", confidence: float = 0.0,
               grounded: bool = False, kind: str = "low_confidence") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"q": str(question), "a": str(answer),
                                 "confidence": round(float(confidence), 4), "grounded": bool(grounded),
                                 "kind": kind, "at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                ensure_ascii=False) + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for ln in self.path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue
        return out

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class SleepConsolidator:
    def __init__(self, hippocampus: LiveMemory | None = None, cortex: LiveMemory | None = None,
                 misslog: MissLog | None = None):
        self.hippo = hippocampus or LiveMemory(path=HIPPO)
        self.cortex = cortex or LiveMemory(path=CORTEX)
        self.misslog = misslog or MissLog()

    def consolidate(self, prune: bool = False) -> dict[str, int]:
        """Systems consolidation: move VERIFIED episodic facts hippocampus→cortex (dedup by normalized
        text). prune=True clears consolidated items from the volatile buffer (hippocampal clearance)."""
        have = {" ".join(_toks(it["text"])) for it in self.cortex.items}
        promoted = 0
        kept = []
        for it in self.hippo.items:
            key = " ".join(_toks(it["text"]))
            if it.get("verified") and key and key not in have:
                self.cortex.remember(it["text"], source=f"consolidated:{it.get('source','')}", verified=True)
                have.add(key)
                promoted += 1
            elif not (it.get("verified") and key in have):
                kept.append(it)                          # unverified or novel → stays in the buffer
        if prune and promoted:
            self.hippo.items = [it for it in self.hippo.items
                                if " ".join(_toks(it["text"])) not in have or not it.get("verified")]
            self.hippo._rewrite()
        return {"promoted": promoted, "cortex_size": len(self.cortex.items),
                "hippo_size": len(self.hippo.items)}

    def mine_curriculum(self, top_k: int = 20) -> list[dict[str, Any]]:
        """Replay the misses → rank deficits. Frequent ungrounded content tokens are the topics the system
        keeps failing on — the targets for a curiosity expedition (D3) and the next training curriculum."""
        misses = self.misslog.read()
        tok_freq: Counter = Counter()
        for m in misses:
            if not m.get("grounded"):
                tok_freq.update(set(_toks(m.get("q", ""))))
        deficits = []
        for tok, cnt in tok_freq.most_common(top_k):
            sample = [m["q"] for m in misses if tok in _toks(m.get("q", ""))][:3]
            deficits.append({"topic": tok, "miss_count": cnt, "sample_questions": sample})
        return deficits

    def sleep_cycle(self, prune: bool = False) -> dict[str, Any]:
        """One night: consolidate + mine + report. The TCT training the curriculum feeds runs behind the
        A/B win-gate separately (deep sleep)."""
        t0 = time.time()
        con = self.consolidate(prune=prune)
        curriculum = self.mine_curriculum()
        report = {"consolidated": con, "curriculum_deficits": len(curriculum),
                  "top_deficits": curriculum[:5], "misses_replayed": len(self.misslog.read()),
                  "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "elapsed_s": round(time.time() - t0, 2)}
        rep_dir = _BASE / "sleep_reports"
        rep_dir.mkdir(parents=True, exist_ok=True)
        (rep_dir / f"sleep_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
            json.dumps({**report, "curriculum": curriculum}, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
