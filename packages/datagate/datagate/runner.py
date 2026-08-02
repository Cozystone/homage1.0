"""PipelineRunner: orchestrate discovery, filtering, scoring, and output.

Deterministic, fail-fast, full-batch overwrite. Never raises for per-document
problems (an unreadable file becomes a ``read_error`` rejection); only an
unexpected pipeline-level failure produces a ``failed`` RunReport.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .config import DataGateConfig
from .filters import default_filters
from .filters.base import BaseFilter
from .filters.link_density import compute_link_density
from .filters.special_char_ratio import compute_special_char_ratio
from .hashing import content_hash, doc_id_for, normalize_text
from .io import discover_files, load_document, write_outputs
from .models import Document, DocumentMetadata, RunReport
from .scoring import QualityScorer

logger = logging.getLogger("datagate.runner")

READ_ERROR = "read_error"


def _utc_now_iso() -> str:
    """ISO 8601 UTC timestamp (informational only, never in a decision path)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_run_id() -> str:
    return "dg-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


class PipelineRunner:
    def __init__(
        self,
        config: DataGateConfig,
        filters: list[BaseFilter] | None = None,
        scorer: QualityScorer | None = None,
    ) -> None:
        self.config = config
        self.filters = filters if filters is not None else default_filters(config)
        self.scorer = scorer if scorer is not None else QualityScorer(config)

    def run(self) -> RunReport:
        run_id = _make_run_id()
        started_at = _utc_now_iso()
        logger.info("DataGate run %s starting", run_id)

        # Stateful filters (e.g. DuplicateHashFilter) must start fresh each run.
        for flt in self.filters:
            flt.reset()

        documents: list[Document] = []
        rejection_breakdown: dict[str, int] = {}
        accepted = 0
        rejected = 0

        try:
            rel_paths = discover_files(self.config.input_dir)
            for rel_path in rel_paths:
                doc = self._process_one(rel_path, run_id)
                documents.append(doc)
                meta = doc.metadata
                assert meta is not None
                if meta.status == "accepted":
                    accepted += 1
                else:
                    rejected += 1
                    key = meta.rejected_by or "unknown"
                    rejection_breakdown[key] = rejection_breakdown.get(key, 0) + 1

            write_outputs(self.config, documents)

            logger.info(
                "DataGate run %s completed: total=%d accepted=%d rejected=%d",
                run_id,
                len(documents),
                accepted,
                rejected,
            )
            return RunReport(
                run_id=run_id,
                state="completed",
                total=len(documents),
                accepted=accepted,
                rejected=rejected,
                rejection_breakdown=rejection_breakdown,
                started_at=started_at,
                finished_at=_utc_now_iso(),
            )
        except Exception as exc:  # pragma: no cover - defensive pipeline guard
            logger.exception("DataGate run %s failed", run_id)
            return RunReport(
                run_id=run_id,
                state="failed",
                total=len(documents),
                accepted=accepted,
                rejected=rejected,
                rejection_breakdown=rejection_breakdown,
                started_at=started_at,
                finished_at=_utc_now_iso(),
                error=str(exc),
            )

    def _process_one(self, rel_path: str, run_id: str) -> Document:
        processed_at = _utc_now_iso()

        try:
            doc = load_document(self.config.input_dir, rel_path)
        except (UnicodeDecodeError, OSError) as exc:
            return self._read_error_document(rel_path, run_id, processed_at, exc)

        text = doc.text
        special_ratio = compute_special_char_ratio(text)
        link_ratio = compute_link_density(text)
        full_hash = content_hash(normalize_text(text))

        filters_passed: list[str] = []
        status = "accepted"
        rejection_reason: str | None = None
        rejected_by: str | None = None

        for flt in self.filters:
            result = flt.apply(doc)
            if result.passed:
                filters_passed.append(flt.name)
            else:
                status = "rejected"
                rejection_reason = result.reason
                rejected_by = flt.name
                break  # fail-fast: skip remaining filters

        quality_score: float | None = None
        if status == "accepted":
            quality_score = self.scorer.score(
                doc,
                {
                    "special_char_ratio": special_ratio,
                    "link_density": link_ratio,
                    "char_count": len(text),
                },
            )

        meta = DocumentMetadata(
            doc_id=doc.doc_id,
            source_path=rel_path,
            char_count=len(text),
            word_count=len(text.split()),
            line_count=len(text.splitlines()),
            special_char_ratio=round(special_ratio, 6),
            link_density=round(link_ratio, 6),
            content_hash=full_hash,
            status=status,
            rejection_reason=rejection_reason,
            rejected_by=rejected_by,
            quality_score=quality_score,
            filters_passed=filters_passed,
            run_id=run_id,
            processed_at=processed_at,
        )
        doc.metadata = meta
        return doc

    def _read_error_document(
        self, rel_path: str, run_id: str, processed_at: str, exc: Exception
    ) -> Document:
        # Derive a stable doc_id from the path so the rejected output file and
        # jsonl line are deterministic even though the content is unreadable.
        marker = f"read_error:{rel_path}"
        full_hash = content_hash(marker)
        doc_id = doc_id_for(marker)
        meta = DocumentMetadata(
            doc_id=doc_id,
            source_path=rel_path,
            char_count=0,
            word_count=0,
            line_count=0,
            special_char_ratio=0.0,
            link_density=0.0,
            content_hash=full_hash,
            status="rejected",
            rejection_reason=f"read_error: {exc}",
            rejected_by=READ_ERROR,
            quality_score=None,
            filters_passed=[],
            run_id=run_id,
            processed_at=processed_at,
        )
        return Document(doc_id=doc_id, source_path=rel_path, text="", metadata=meta)
