"""Consensus-evidence ledger — the quarantine layer of the two-tier learning store.

THE keystone of the extraction-quality plan ( P1). Instead of trusting any single
extraction, every extracted relation first lands here as an EVIDENCE EVENT. A relation
is promoted to the verified candidate store only when it is confirmed by at least
`min_sources` INDEPENDENT pieces of evidence (distinct sentence hashes). Noise is
idiosyncratic per sentence; true facts recur — so extraction precision becomes a
counting problem that improves with data volume instead of with more hand rules
(the NELL / Knowledge Vault insight).

Two guards run before an evidence event is even counted:
 1. round-trip head check — the subject and object labels must actually occur in
 the source sentence; if extraction mangled a head, the evidence is rejected.
 2. degenerate-head check — single-char / date-unit heads are rejected (reuses the
 same class of guards as the decomposer, as defence in depth).

The ledger is append-only JSONL (events are the source of truth); aggregates are
rebuilt on load, so a crash can never corrupt counts.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_DATE_UNIT_HEADS = {"일", "월", "년", "시", "분", "초", "세기", "요일", "주", "세", "차"}
_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_relation_key(source_label: str, relation: str, target_label: str,
                           resolver: Any = None) -> str:
    """Canonical claim key. With a resolver, surface forms collapse first
 ( == Nvidia), so evidence for the same fact never splits ( 1)."""
    if resolver is not None:
        source_label = resolver.resolve(source_label)
        target_label = resolver.resolve(target_label)
    raw = f"{source_label.strip().lower()}|{relation.strip().lower()}|{target_label.strip().lower()}"
    return "cons_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def head_roundtrip_ok(label: str, sentence_text: str) -> bool:
    """The extracted head must be a real, non-degenerate part of the source sentence."""
    label = (label or "").strip()
    if len(label) < 2 and label not in _TOKEN.findall(sentence_text or ""):
        return False
    if label in _DATE_UNIT_HEADS:
        return False
    return bool(label) and label in (sentence_text or "")


@dataclass
class RecordResult:
    events_recorded: int = 0
    events_rejected_roundtrip: int = 0
    events_duplicate: int = 0
    relations_seen: int = 0

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class PromotionResult:
    promoted: int = 0
    still_quarantined: int = 0
    curated_quarantined: int = 0
    promoted_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"promoted": self.promoted, "still_quarantined": self.still_quarantined,
                "curated_quarantined": self.curated_quarantined,
                "promoted_keys": self.promoted_keys[:20]}


class ConsensusLedger:
    """Append-only evidence ledger with consensus promotion."""

    def __init__(self, root: str | Path, *, min_sources: int = 2) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "evidence_ledger.jsonl"
        self.promoted_path = self.root / "promoted_keys.jsonl"
        self.min_sources = max(1, int(min_sources))
        from .alias_resolution import AliasResolver

        self.resolver = AliasResolver(self.root / "aliases.jsonl")
        # aggregates: key -> {sources: set(sentence hashes), voices: set(provenance
        # source ids — the Sybil-capped consensus unit), row, labels}
        self._agg: dict[str, dict[str, Any]] = {}
        self._promoted: set[str] = set()
        self._load()

    # ---------- persistence ----------
    def _load(self) -> None:
        if self.ledger_path.exists():
            for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue  # torn tail write must not poison the ledger
                self._apply(ev)
        if self.promoted_path.exists():
            for line in self.promoted_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        self._promoted.add(json.loads(line)["key"])
                    except (json.JSONDecodeError, KeyError):
                        continue

    def _apply(self, ev: dict[str, Any]) -> None:
        # the key is RECOMPUTED through the current alias resolver rather than
        # trusted from the event, so newly learned aliases merge OLD evidence too.
        row = ev.get("row") or {}
        key = canonical_relation_key(str(ev.get("source_label") or ""),
                                     str(row.get("relation") or ""),
                                     str(ev.get("target_label") or ""),
                                     resolver=self.resolver)
        slot = self._agg.setdefault(key, {"sources": set(), "voices": set(), "row": row,
                                          "source_label": ev.get("source_label"),
                                          "target_label": ev.get("target_label")})
        slot["sources"].add(ev["evidence_id"])
        voice = str((row.get("provenance") or {}).get("source_id") or ev["evidence_id"])
        slot["voices"].add(voice)
        if row:
            slot["row"] = row

    def _append(self, ev: dict[str, Any]) -> None:
        with self.ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

    # ---------- recording ----------
    def record_decomposition(self, decomposition: Any) -> RecordResult:
        """Record all relations of one DecompositionResult as evidence events."""
        result = RecordResult()
        concepts = {c.get("concept_id"): c for c in getattr(decomposition, "concepts", [])}
        evidence = getattr(decomposition, "evidence", None) or {}
        sentence_text = str(evidence.get("text") or "")
        evidence_id = str(evidence.get("source_hash") or evidence.get("dedupe_key") or
                          hashlib.sha256(sentence_text.encode("utf-8")).hexdigest())

        # surface forms of the same entity merge — including retroactively on reload.
        if sentence_text:
            self.resolver.learn_from_sentence(sentence_text)
        for rel in getattr(decomposition, "relations", []):
            result.relations_seen += 1
            src = concepts.get(rel.get("source_concept_id"), {})
            tgt = concepts.get(rel.get("target_concept_id"), {})
            src_label = str(src.get("canonical_name") or src.get("label") or src.get("surface") or "")
            tgt_label = str(tgt.get("canonical_name") or tgt.get("label") or tgt.get("surface") or "")
            if sentence_text and not (head_roundtrip_ok(src_label, sentence_text)
                                      and head_roundtrip_ok(tgt_label, sentence_text)):
                result.events_rejected_roundtrip += 1
                continue
            key = canonical_relation_key(src_label, str(rel.get("relation") or ""), tgt_label,
                                         resolver=self.resolver)
            slot = self._agg.get(key)
            if slot and evidence_id in slot["sources"]:
                result.events_duplicate += 1
                continue
            ev = {"key": key, "evidence_id": evidence_id, "recorded_at": _utc_now(),
                  "source_label": src_label, "target_label": tgt_label, "row": rel}
            self._apply(ev)
            self._append(ev)
            result.events_recorded += 1
        return result

    # ---------- promotion ----------
    def promotable(self) -> list[tuple[str, dict[str, Any]]]:
        """Consensus counts VOICES (distinct provenance sources), not sentences —
 one website saying something twice is still one voice (Sybil cap ⑧).

 VARIABLE-k (protective skepticism): the bar is not fixed. When the
 ledger itself holds a SUBSTANTIAL rival claim (same subject+relation,
 a different object that also reached min_sources), the claim class is
 measured-contested and every variant needs one voice more than the
 base. Data-derived contention, no topic tables; non-exclusive
 predicates ( is_a AND ) still promote — both sides just
 need the higher bar. Downstream, the contradiction sweep still owns
 exclusive-predicate conflicts."""
        def _n(v: dict[str, Any]) -> int:
            return len(v.get("voices") or v["sources"])

        contested: dict[tuple[str, str], int] = {}
        for v in self._agg.values():
            sp = (str(v.get("source_label") or "").strip().lower(),
                  str((v.get("row") or {}).get("relation") or ""))
            if _n(v) >= self.min_sources:
                contested[sp] = contested.get(sp, 0) + 1
        out: list[tuple[str, dict[str, Any]]] = []
        for k, v in self._agg.items():
            if k in self._promoted:
                continue
            sp = (str(v.get("source_label") or "").strip().lower(),
                  str((v.get("row") or {}).get("relation") or ""))
            required = self.min_sources + (1 if contested.get(sp, 0) >= 2 else 0)
            if _n(v) >= required:
                out.append((k, v))
        return out

    def promote_into(self, store: Any) -> PromotionResult:
        """Write consensus-confirmed relations into the verified candidate store.

 Respects the drift-freeze flag ( P5-⑧): if the CUSUM monitor tripped on a
 promotion surge, nothing promotes until the operator clears the flag — the
 quarantine keeps accumulating evidence meanwhile, so nothing is lost."""
        try:  # local import: avoid cycle; tolerate both path styles
            from cgsr.ingestion.accumulator import AccumulationResult
        except ImportError:
            from packages.cgsr.cgsr.ingestion.accumulator import AccumulationResult
        from .trust_audit import is_frozen, update_drift

        result = PromotionResult()
        if is_frozen(self.root):
            result.still_quarantined = sum(1 for k in self._agg if k not in self._promoted)
            return result
        # truth-discovery gate (P2 wiring): a claim that LOST its exclusion group
        # (low belief despite source count) stays quarantined — unmarked, so it can
        # still promote later if new evidence raises its belief.
        beliefs: dict[str, float] = {}
        scores_path = self.root / "truth_scores.json"
        if scores_path.exists():
            try:
                beliefs = json.loads(scores_path.read_text(encoding="utf-8")).get("claim_belief") or {}
            except json.JSONDecodeError:
                beliefs = {}
        import os as _os

        min_belief = float(_os.environ.get("ATANOR_TRUTH_MIN_BELIEF", "0.34"))
        # curated-KG judge (chronic-class #2): a claim the CURATED store contradicts never
        # promotes, however many web voices agree — quality outranks quorum. Left unmarked
        # so it can release if curated facts later change. Judge failure = judge silent.
        judge_store = None
        try:
            from packages.graph_scale.answer_bridge import _ROOT as _kg_root
            from packages.graph_scale.curated_judge import judge as _curated_judge
            from packages.graph_scale.triple_store import TripleStore as _TS

            if (_kg_root / "meta.json").exists():
                judge_store = _TS(_kg_root)
        except Exception:
            judge_store = None

        agg = AccumulationResult()
        for key, slot in self.promotable():
            if key in beliefs and beliefs[key] < min_belief:
                continue  # held by truth discovery; evidence keeps accumulating
            if judge_store is not None:
                verdict = _curated_judge(str(slot.get("source_label") or ""),
                                         str((slot.get("row") or {}).get("relation") or ""),
                                         str(slot.get("target_label") or ""), judge_store)
                if verdict["verdict"] in ("contradicted", "type_conflict"):
                    result.curated_quarantined += 1
                    with (self.root / "curated_quarantine.jsonl").open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"key": key, "at": _utc_now(), **verdict},
                                            ensure_ascii=False) + "\n")
                    continue
            row = dict(slot["row"])
            row["evidence_count"] = len(slot.get("voices") or slot["sources"])
            row["truth_belief"] = beliefs.get(key)
            row["consensus_key"] = key
            row["consensus_promoted_at"] = _utc_now()
            appended = store._append_unique("relations", row, agg)  # noqa: SLF001 - store API
            self._promoted.add(key)
            with self.promoted_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": key, "at": row["consensus_promoted_at"],
                                     "evidence_count": row["evidence_count"]}, ensure_ascii=False) + "\n")
            if appended:
                result.promoted += 1
                result.promoted_keys.append(key)
        result.still_quarantined = sum(1 for k, v in self._agg.items()
                                       if k not in self._promoted)
        update_drift(self.root, result.promoted)  # CUSUM surge monitor (may trip freeze)
        return result

    def evidence_for_label(self, label: str) -> dict[str, Any]:
        """READ-ONLY aggregate evidence view for one subject label — the deliberation
        loop's probe surface. Counts real ledger state (voices = Sybil-capped consensus
        unit); never mutates, never promotes."""
        label_l = (label or "").strip().lower()
        relations: list[dict[str, Any]] = []
        for key, slot in self._agg.items():
            if str(slot.get("source_label") or "").strip().lower() != label_l:
                continue
            relations.append({
                "key": key,
                "relation": str((slot.get("row") or {}).get("relation") or ""),
                "target": slot.get("target_label"),
                "voices": len(slot.get("voices") or slot["sources"]),
                "evidence": len(slot["sources"]),
                "promoted": key in self._promoted,
            })
        return {
            "label": label,
            "distinct_relations": len(relations),
            "max_voices": max((r["voices"] for r in relations), default=0),
            "relations": relations,
            "min_sources_required": self.min_sources,
        }

    def stats(self) -> dict[str, Any]:
        def _n(v: dict[str, Any]) -> int:
            return len(v.get("voices") or v["sources"])

        counts = [_n(v) for v in self._agg.values()]
        return {
            "relations_quarantined": sum(1 for k in self._agg if k not in self._promoted),
            "relations_promoted_total": len(self._promoted),
            "min_sources": self.min_sources,
            "max_evidence_count": max(counts) if counts else 0,
            "pending_at_threshold": sum(1 for k, v in self._agg.items()
                                        if k not in self._promoted and _n(v) >= self.min_sources),
            "alias_clusters": len({self.resolver.resolve(str(v.get("source_label") or ""))
                                   for v in self._agg.values()}),
        }
