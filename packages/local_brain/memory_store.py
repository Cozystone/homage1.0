"""Local Brain cumulative memory — durable PRIVATE on-device knowledge.

The local analog of the Cloud Brain's public-web cumulative learning. It
accumulates:

1. **User preferences / info** extracted from conversations with the user.
2. **Graph Hub imported sources** — persona (personality) and knowledge sources
   the user pulls in on demand.

Everything here is private and on-device. It is never uploaded, never written to
the cloud production store, and carries provenance for every fact so the agent
can say *why* it knows something about the user.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


FactKind = Literal["preference", "identity", "info", "persona", "knowledge"]
FactSource = Literal["conversation", "graph_hub"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for raw in str(text or "").lower().split():
        tok = raw.strip(".,!?;:()[]{}\"'~…")
        if len(tok) >= 2:
            out.append(tok)
    return out


@dataclass
class LocalBrainFact:
    fact_id: str
    kind: FactKind
    subject: str
    value: str
    source: FactSource
    source_ref: str = ""
    confidence: float = 0.7
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fact_id(kind: str, subject: str) -> str:
    digest = hashlib.sha256(f"{kind}|{subject.strip().lower()}".encode("utf-8")).hexdigest()[:16]
    return f"{kind}_{digest}"


class LocalBrainMemory:
    """Durable private store of user facts. JSON-backed, atomic writes."""

    def __init__(self, store_path: Path | str | None = None, *, max_facts: int | None = None) -> None:
        self.store_path = Path(store_path) if store_path else Path("runtime/local_brain/local_memory.json")
        # Optional cap so a high-churn store (e.g. looked-up web facts) cannot grow
        # without bound; the least-recently-updated facts are evicted first.
        self.max_facts = int(max_facts) if max_facts else None
        self.facts: dict[str, LocalBrainFact] = {}
        self._load()

    def _evict_if_over_cap(self) -> None:
        if not self.max_facts or len(self.facts) <= self.max_facts:
            return
        ordered = sorted(self.facts.values(), key=lambda f: f.updated_at)
        for fact in ordered[: len(self.facts) - self.max_facts]:
            self.facts.pop(fact.fact_id, None)

    # ----- persistence -----------------------------------------------------------

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - corrupt artifact → start empty
            return
        for raw in data.get("facts", []) or []:
            if not isinstance(raw, dict) or not raw.get("fact_id"):
                continue
            fields = {k: raw.get(k) for k in LocalBrainFact.__dataclass_fields__ if k in raw}
            try:
                fact = LocalBrainFact(**fields)
            except TypeError:  # pragma: no cover
                continue
            self.facts[fact.fact_id] = fact

    def save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        payload = {"facts": [f.to_dict() for f in self.facts.values()], "updated_at": _utc_now()}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.store_path)

    # ----- accumulation ----------------------------------------------------------

    def remember(
        self,
        kind: FactKind,
        subject: str,
        value: str,
        *,
        source: FactSource = "conversation",
        source_ref: str = "",
        confidence: float = 0.7,
        save: bool = True,
    ) -> LocalBrainFact:
        """Add or update a fact, deduped by (kind, subject). Latest value wins."""
        subject = str(subject or "").strip()
        value = str(value or "").strip()
        fid = _fact_id(kind, subject)
        existing = self.facts.get(fid)
        if existing:
            existing.value = value or existing.value
            existing.confidence = max(existing.confidence, float(confidence))
            existing.updated_at = _utc_now()
            if source_ref:
                existing.source_ref = source_ref
            fact = existing
        else:
            fact = LocalBrainFact(
                fact_id=fid,
                kind=kind,
                subject=subject,
                value=value,
                source=source,
                source_ref=source_ref,
                confidence=float(confidence),
            )
            self.facts[fid] = fact
            self._evict_if_over_cap()
        if save:
            self.save()
        return fact

    def import_graph_hub_source(
        self,
        source_id: str,
        kind: FactKind,
        items: list[dict[str, Any]],
    ) -> list[LocalBrainFact]:
        """Accumulate a persona/knowledge source the user pulled from Graph Hub.

        Each item is {subject, value, confidence?}. ``kind`` is "persona" or
        "knowledge". Provenance records the Graph Hub source id.
        """
        added: list[LocalBrainFact] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            subject = str(item.get("subject") or item.get("name") or "").strip()
            value = str(item.get("value") or item.get("text") or "").strip()
            if not subject or not value:
                continue
            raw_confidence = item["confidence"] if "confidence" in item else 0.8
            try:
                confidence = float(raw_confidence)
            except (TypeError, ValueError):
                confidence = 0.8
            if not math.isfinite(confidence):
                confidence = 0.8
            added.append(
                self.remember(
                    kind,
                    subject,
                    value,
                    source="graph_hub",
                    source_ref=f"graph_hub:{source_id}",
                    confidence=max(0.0, min(1.0, confidence)),
                    save=False,
                )
            )
        if added:
            self.save()
        return added

    # ----- recall ----------------------------------------------------------------

    def recall(self, query: str, *, limit: int = 6) -> list[LocalBrainFact]:
        """Return facts relevant to a query by token overlap, highest first."""
        q = set(_tokens(query))
        scored: list[tuple[float, LocalBrainFact]] = []
        for fact in self.facts.values():
            hay = set(_tokens(f"{fact.subject} {fact.value}"))
            if not hay:
                continue
            overlap = len(q & hay)
            # identity facts (name) surface easily on identity-style queries
            score = overlap + (0.5 if fact.kind in {"identity", "preference"} else 0.0)
            if overlap > 0:
                scored.append((score, fact))
        scored.sort(key=lambda pair: (pair[0], pair[1].confidence), reverse=True)
        return [fact for _, fact in scored[:limit]]

    def all_facts(self) -> list[LocalBrainFact]:
        return sorted(self.facts.values(), key=lambda f: f.updated_at, reverse=True)

    def status(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        by_source: dict[str, int] = {}
        for fact in self.facts.values():
            by_kind[fact.kind] = by_kind.get(fact.kind, 0) + 1
            by_source[fact.source] = by_source.get(fact.source, 0) + 1
        return {
            "local_brain_memory_available": True,
            "private_on_device": True,
            "uploaded_to_cloud": False,
            "production_store_mutated": False,
            "total_facts": len(self.facts),
            "by_kind": by_kind,
            "by_source": by_source,
            "store_path": str(self.store_path),
        }
