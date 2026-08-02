# -*- coding: utf-8 -*-
"""RealTimeThinker — the real-time thinking loop, one callable. It fuses the three organs measured this
session into hear → think → doubt:

  • HEAR   — Layer A live buffer (LiveMemory): a fact stated this turn is written in <0.1 ms, no retrain.
  • FUSE   — live recalls are ALWAYS injected into the reader's candidate set (priority over the static
             disk corpus): a just-heard fact is never dropped by a retrieval cap; among candidates the
             LEARNED relevance head ranks (honest — live is guaranteed considered, not blindly forced).
  • THINK  — the multi-hop reader answers over the fused evidence (parallel top-k, the measured-best
             default; the internal-monologue path stays available for open-corpus multi-hop).
  • DOUBT  — the DoubtGate scores confidence; below threshold → ABSTAIN ("need more evidence"), never a
             fabricated answer. Every answer carries evidence provenance + live/static origin + verified
             flag (hallucination-0). No LLM.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.reasoning_vm.live_memory import STORE, LiveMemory, _toks

REPO = Path(__file__).resolve().parents[3]


def _overlap(question: str, text: str) -> int:
    """Shared content tokens — the calibrated relevance signal (the neural relevance head is saturated at
    ~1.0 for everything: good for RANKING, useless as an absolute threshold)."""
    return len(set(_toks(question)) & set(_toks(text)))


class RealTimeThinker:
    def __init__(self, ckpt: str = "ace_hotpot.pt", store: Path | None = None,
                 threshold: float = 0.35, k: int = 3, min_overlap: int = 2,
                 cortex_path: Path | None = None, misslog=None, record_misses: bool = True,
                 support_ckpt: str = "ace_support.pt",
                 answerability_threshold: float = 0.90,
                 support_net_threshold: float = 0.90):
        from packages.reasoning_vm.consolidation import CORTEX, MissLog
        from packages.reasoning_vm.deliberator.doubt_gate import DoubtGate
        from packages.reasoning_vm.deliberator.planner import MultiHopReader
        self.mem = LiveMemory(path=store or STORE)                # hippocampus (volatile, the day)
        self.cortex = LiveMemory(path=cortex_path or CORTEX)      # cortex (durable, consolidated knowledge)
        self.misslog = misslog if misslog is not None else MissLog()
        self.record_misses = record_misses
        self.reader = MultiHopReader(ckpt=ckpt)
        support_path = REPO / "data" / "graph_scale" / support_ckpt
        support_reader = MultiHopReader(ckpt=support_ckpt) if support_path.is_file() else None
        self.gate = DoubtGate(
            self.reader,
            threshold=threshold,
            support_reader=support_reader,
            answerability_threshold=answerability_threshold,
            support_net_threshold=support_net_threshold,
        )
        self.k = k
        self.min_overlap = min_overlap        # a fact must cover ≥N of the question's content tokens to
        #                                        count as relevant — one shared GENERIC word ("city",
        #                                        "planet") is not a match, so unknowns abstain not leak.

    def learn(self, fact: str, source: str = "") -> dict[str, Any]:
        """HEAR an untrusted fact for immediate recall, never verification.

        This service method is also an ingress boundary: verification metadata
        is intentionally not accepted here, so another adapter cannot recreate
        the former HTTP ``verified=True`` bypass.
        """
        return self.mem.remember(fact, source=source, verified=False)

    def promote_verified(self, item_id: int) -> bool:
        """Promote one stored item from a server-owned verifier or operator gate.

        This operation has no public HTTP route.  It preserves the existing
        ``LiveMemory.verify`` path while keeping verification authority separate
        from caller-controlled learning metadata.
        """
        return self.mem.verify(item_id)

    def think(self, question: str, static_paragraphs: list[tuple[str, str]] | None = None,
              k_live: int = 4, include_unverified: bool = True) -> dict[str, Any]:
        """HEAR→FUSE→THINK, coverage 1.0 — ALWAYS engage, NEVER abstain (doctrine: answering ≠ fabricating).

        FUSE = fresh-facts-answer-first: live recalls get PRIORITY; static is the fallback. Then FIND HARDER
        rather than bail — if nothing clears the overlap floor, still engage over whatever evidence exists.
        ``grounded=True`` requires both server-verified evidence authority and
        an independent answerability + SUPPORTS-minus-REFUTES judgment over the
        proposed answer and that exact evidence. Retrieval overlap can propose
        evidence but cannot certify it. A rejected answer remains engaged but
        is labelled ``grounded=False`` and becomes a learning deficit."""
        live = self.mem.recall(question, k=k_live, include_unverified=include_unverified)
        live = [h for h in live if _overlap(question, h["text"]) >= self.min_overlap]
        live_candidates = [
            (f"live:{h['source'] or 'mem'}", h["text"], bool(h["verified"]), "live")
            for h in live
        ]
        cortex = self.cortex.recall(question, k=k_live, include_unverified=False)   # durable, verified only
        cortex = [h for h in cortex if _overlap(question, h["text"]) >= self.min_overlap]
        cortex_candidates = [
            (f"cortex:{h['source'] or 'mem'}", h["text"], bool(h["verified"]), "cortex")
            for h in cortex
        ]
        static_candidates = [
            (str(title), text, False, "static")
            for title, text in (static_paragraphs or [])
        ]
        static_rel = sorted(
            (item for item in static_candidates if _overlap(question, item[1]) >= self.min_overlap),
            key=lambda item: -_overlap(question, item[1]),
        )
        # PRIORITY fresh(live) → durable(cortex) → static → FIND HARDER (never abstain to empty)
        candidates = live_candidates or cortex_candidates or static_rel or static_candidates
        if not candidates:                                    # only when literally no evidence was supplied
            if self.record_misses:
                self.misslog.record(question, kind="no_evidence")
            return {"answer": "", "confidence": 0.0, "grounded": False, "used_live": False,
                    "support": [], "evidence": [], "engaged": True, "type": "span",
                    "note": "no evidence available to ground an answer"}
        pool = [(title, text) for title, text, _verified, _origin in candidates]
        out = self.reader.answer(question, pool, k=min(self.k, len(pool)), chain=False, rank="ans")
        answer = out.get("answer", "")
        titles = out.get("support", [])
        support_indices = out.get("support_indices")
        answer_index = out.get("answer_index")
        answer_type = out.get("type", "span")
        identity_valid = (
            isinstance(titles, list)
            and isinstance(support_indices, list)
            and bool(support_indices)
            and all(type(index) is int for index in support_indices)
            and len(support_indices) == len(set(support_indices))
            and all(0 <= index < len(candidates) for index in support_indices)
            and titles == [candidates[index][0] for index in support_indices]
            and answer_type in {"span", "yesno"}
        )
        if answer_type == "span":
            identity_valid = (
                identity_valid
                and type(answer_index) is int
                and answer_index in support_indices
            )
            gate_indices = [answer_index] if identity_valid else []
        else:
            identity_valid = identity_valid and answer_index is None
            gate_indices = list(support_indices) if identity_valid else []
        selected = [candidates[index] for index in gate_indices]
        used_live = any(origin == "live" for _title, _text, _verified, origin in selected)
        if not identity_valid:
            verdict = {
                "accepted": False,
                "confidence": 0.0,
                "reason": "evidence_selection_unbound",
                "signals": {
                    "candidate_count": len(candidates),
                    "reported_support_count": (
                        len(support_indices) if isinstance(support_indices, list) else 0
                    ),
                },
            }
        elif not all(verified for _title, _text, verified, _origin in selected):
            verdict = {
                "accepted": False,
                "confidence": 0.0,
                "reason": "evidence_authority_unverified",
                "signals": {
                    "evidence_count": len(selected),
                    "verified_count": sum(
                        int(verified) for _title, _text, verified, _origin in selected
                    ),
                },
            }
        else:
            try:
                verdict = self.gate.judge_answer(
                    question,
                    str(answer),
                    [text for _title, text, _verified, _origin in selected],
                )
            except Exception as exc:
                # Verifier failure is fail-closed. The response remains engaged,
                # while only the exception type is exposed for diagnostics.
                verdict = {
                    "accepted": False,
                    "confidence": 0.0,
                    "reason": "evidence_answer_discriminator_error",
                    "signals": {"error_type": type(exc).__name__},
                }
        conf = float(verdict.get("confidence") or 0.0)
        grounded = bool(verdict.get("accepted"))
        if self.record_misses and not grounded:              # deficit signal → sleep mines it (D1) / curiosity (D3)
            self.misslog.record(question, answer=answer, confidence=conf, grounded=grounded)
        return {"answer": answer, "confidence": round(float(conf), 4), "grounded": bool(grounded),
                "used_live": used_live, "support": titles, "engaged": True,
                "grounding_basis": "verified_evidence_answer_discriminator",
                "grounding_reason": verdict.get("reason"),
                "grounding_signals": verdict.get("signals") or {},
                "evidence": [
                    {
                        "origin": origin,
                        "title": title,
                        "verified": verified,
                        "candidate_index": index,
                    }
                    for index, (title, _text, verified, origin) in zip(
                        gate_indices, selected
                    )
                ],
                "type": out.get("type", "span")}
