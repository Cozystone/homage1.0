from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import re
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from packages.cgsr.cgsr.ingestion.source_reader import clean_source_text, detect_language
from packages.cgsr.cgsr.ingestion.verification_gate import has_mock_signal

from .verified_payload_feeder import DEFAULT_PAYLOAD_DIR, LearningPayload, stable_hash


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = DEFAULT_PAYLOAD_DIR / "web_feeds"
DEFAULT_REJECTED_DIR = DEFAULT_PAYLOAD_DIR / "rejected"
DEFAULT_MANIFEST_PATH = DEFAULT_PAYLOAD_DIR / "manifest.json"
COLLECTOR_VERSION = "approved_web_feeder_v1"
DEFAULT_ALLOWED_DOMAINS = {"en.wikipedia.org", "ko.wikipedia.org", "www.gutenberg.org", "gutenberg.org"}

NAVIGATION_RESIDUE = re.compile(
    r"\b(main menu|jump to content|create account|log in|appearance|move to sidebar|contents)\b",
    re.IGNORECASE,
)
MOJIBAKE_MARKERS = re.compile(r"(\ufffd|Ã|Â|ì|ë|í|荑|愿|洹|寃|利|\?덈)", re.IGNORECASE)
MOCK_TEMPLATE = re.compile(r"AtanorSeedConcept\d+|\bsector\s+\d+\b", re.IGNORECASE)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=다\.)\s+")


class _TextExtractor(HTMLParser):
    """Small bounded text extractor for explicit public URLs.

    This is not a crawler.  It only extracts visible text from an explicitly
    approved source URL and never follows links.
    """

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "header", "footer"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "header", "footer"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = " ".join(data.split())
        if cleaned:
            self._chunks.append(cleaned)

    def text(self) -> str:
        return " ".join(self._chunks)


@dataclass(frozen=True)
class WebFeederPolicy:
    """Safety policy for turning public web/corpus text into approved payloads."""

    allowed_source_types: set[str] = field(
        default_factory=lambda: {
            "wikipedia",
            "approved_public_corpus",
            "public_web_feed",
            "local_public_corpus_file",
            "local_public_corpus_shard",
            "manual_public_sentence",
        }
    )
    allowed_domains: set[str] = field(default_factory=lambda: set(DEFAULT_ALLOWED_DOMAINS))
    max_sentences_per_source: int = 1000
    max_concurrent_requests: int = 1
    require_license_hint: bool = True
    require_url_or_path: bool = True
    allow_unknown_language: bool = False
    prefer_language: str = "en"
    allow_korean: bool = True
    min_sentence_chars: int = 12
    max_sentence_chars: int = 700
    max_bytes_per_source: int = 1_500_000
    request_timeout_seconds: float = 12.0
    rest_max_retries: int = 2
    rest_backoff_base_seconds: float = 1.0

    @property
    def source_allowlist(self) -> set[str]:
        """Backward-compatible alias for older call sites."""

        return self.allowed_source_types


@dataclass(frozen=True)
class SourceSpec:
    """Explicit source declaration for an approved feeder run."""

    source_type: str
    source_id: str
    source_url_or_path: str
    license_hint: str
    source_title: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class ApprovedPayloadFeederResult:
    """Summary of one bounded web approved-payload feeder run."""

    state: str
    mode: str
    sources_configured: int
    sources_checked: int
    payloads_seen: int
    payloads_approved: int
    payloads_rejected: int
    duplicate_count: int
    rejection_reasons: dict[str, int]
    approved_payload_path: str | None = None
    rejected_payload_path: str | None = None
    manifest_path: str | None = None
    warning: str = "approved payloads are candidate learning inputs only; no production promotion occurs"
    production_store_mutated: bool = False
    local_brain_write: bool = False
    false_confident: int = 0
    forgetting_count: int = 0
    eval_rows_used_for_learning: bool = False
    external_llm_used: bool = False
    mock_growth: bool = False
    pair_edges_sent: int = 0
    private_data_used_for_cloud_learning: bool = False
    unsupported_claims: int = 0
    source_mode: str = "rest_api"
    rate_limited_count: int = 0
    backoff_seconds: float = 0.0
    source_rotation_count: int = 0
    last_429_at: str | None = None
    recommended_source_for_long_run: str = "local_dump_shard"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> str:
    """Return a compact UTC timestamp."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_type_for_url(url: str) -> str:
    return "public_web_feed"


def _is_allowed_url(url: str, policy: WebFeederPolicy) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"}:
        return False
    host = parsed.netloc.lower()
    return host in policy.allowed_domains


def _fetch_public_url(url: str, policy: WebFeederPolicy, stats: dict[str, Any] | None = None) -> str:
    if not _is_allowed_url(url, policy):
        raise ValueError("source_domain_not_allowed")
    request = Request(url, headers={"User-Agent": "ATANOR-approved-payload-feeder/1.0"})
    for attempt in range(max(1, int(policy.rest_max_retries) + 1)):
        try:
            with urlopen(request, timeout=policy.request_timeout_seconds) as response:  # nosec B310 - explicit allowlist.
                content_type = response.headers.get("content-type", "")
                raw = response.read(policy.max_bytes_per_source + 1)
            break
        except HTTPError as exc:
            if exc.code != 429 or attempt >= int(policy.rest_max_retries):
                raise
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else policy.rest_backoff_base_seconds * (2**attempt)
            except ValueError:
                delay = policy.rest_backoff_base_seconds * (2**attempt)
            if stats is not None:
                stats["rate_limited_count"] = int(stats.get("rate_limited_count") or 0) + 1
                stats["backoff_seconds"] = float(stats.get("backoff_seconds") or 0.0) + delay
                stats["last_429_at"] = utc_now()
            time.sleep(min(delay, 30.0))
    else:  # pragma: no cover - defensive only.
        raise ValueError("source_fetch_failed")
    if len(raw) > policy.max_bytes_per_source:
        raw = raw[: policy.max_bytes_per_source]
    text = raw.decode("utf-8", errors="replace")
    if "json" in content_type:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(payload, dict):
            chunks = [str(payload.get(key) or "") for key in ("title", "description", "extract")]
            return " ".join(chunk for chunk in chunks if chunk)
    parser = _TextExtractor()
    parser.feed(text)
    return parser.text()


def _read_source_text(source: SourceSpec, policy: WebFeederPolicy, stats: dict[str, Any] | None = None) -> str:
    if source.text is not None:
        return source.text
    if source.source_type in {"wikipedia", "public_web_feed"} or source.source_url_or_path.startswith(("http://", "https://")):
        return _fetch_public_url(source.source_url_or_path, policy, stats)
    path = Path(source.source_url_or_path)
    if not path.exists() or not path.is_file():
        raise ValueError("source_file_missing")
    return path.read_text(encoding="utf-8")


def _source_items(source: SourceSpec, policy: WebFeederPolicy, stats: dict[str, Any]) -> list[tuple[SourceSpec, str]]:
    """Return bounded text items for one configured public source.

    ``local_public_corpus_shard`` is the long-run path: JSONL rows or
    one-sentence-per-line text are read locally, with line-scoped provenance,
    so candidate-only learning does not depend on live REST API rate limits.
    """

    if source.source_type != "local_public_corpus_shard":
        return [(source, _read_source_text(source, policy, stats))]
    path = Path(source.source_url_or_path)
    if not path.exists() or not path.is_file():
        raise ValueError("source_file_missing")
    items: list[tuple[SourceSpec, str]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        text = line.strip()
        title = source.source_title
        url_or_path = f"{path}#L{line_no}"
        license_hint = source.license_hint
        if path.suffix.lower() == ".jsonl":
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                row = {}
            if isinstance(row, dict):
                text = str(row.get("text") or row.get("sentence") or row.get("extract") or "").strip()
                title = str(row.get("title") or title or "") or title
                url_or_path = str(row.get("source_url") or row.get("url") or url_or_path)
                license_hint = str(row.get("license_hint") or row.get("license") or license_hint)
        if not text:
            continue
        items.append(
            (
                SourceSpec(
                    source_type=source.source_type,
                    source_id=f"{source.source_id}:line:{line_no}",
                    source_url_or_path=url_or_path,
                    license_hint=license_hint,
                    source_title=title,
                    text=text,
                ),
                text,
            )
        )
    return items


def _split_sentences(text: str, *, max_sentences: int) -> list[str]:
    cleaned = clean_source_text(text)
    chunks: list[str] = []
    for item in SENTENCE_SPLIT.split(cleaned):
        sentence = item.strip()
        if sentence:
            chunks.append(sentence)
        if len(chunks) >= max_sentences:
            break
    return chunks


def _sentence_quality_flags(sentence: str, source: SourceSpec, policy: WebFeederPolicy) -> list[str]:
    flags: list[str] = []
    normalized = clean_source_text(sentence)
    language = detect_language(normalized)
    if len(normalized) < policy.min_sentence_chars or len(normalized) > policy.max_sentence_chars:
        flags.append("quality_rejected")
        flags.append("length_out_of_bounds")
    if NAVIGATION_RESIDUE.search(normalized):
        flags.append("quality_rejected")
        flags.append("navigation_residue")
    if MOJIBAKE_MARKERS.search(normalized):
        flags.append("quality_rejected")
        flags.append("mojibake_detected")
    if MOCK_TEMPLATE.search(normalized) or has_mock_signal(normalized, source.source_id, source.source_type):
        flags.append("quality_rejected")
        flags.append("mock_template_signal")
    if policy.require_license_hint and not source.license_hint:
        flags.append("quality_rejected")
        flags.append("missing_license")
    if policy.require_url_or_path and not source.source_url_or_path:
        flags.append("quality_rejected")
        flags.append("missing_public_provenance")
    if source.source_type not in policy.source_allowlist:
        flags.append("quality_rejected")
        flags.append("source_type_not_allowed")
    if language == "unknown" and not policy.allow_unknown_language:
        flags.append("quality_rejected")
        flags.append("unknown_language")
    if language == "ko" and not policy.allow_korean:
        flags.append("quality_rejected")
        flags.append("korean_not_allowed")
    alpha_count = sum(1 for char in normalized if char.isalpha())
    if normalized and alpha_count / max(1, len(normalized)) < 0.35:
        flags.append("quality_rejected")
        flags.append("low_alpha_ratio")
    return flags


def _payload_from_sentence(sentence: str, source: SourceSpec, index: int, policy: WebFeederPolicy) -> LearningPayload:
    normalized = clean_source_text(sentence)
    provenance_hash = stable_hash(f"{source.source_type}:{source.source_id}:{source.source_url_or_path}:{normalized}")
    payload_id = f"approved_{provenance_hash[:24]}"
    return LearningPayload(
        payload_id=payload_id,
        source_type=source.source_type,
        source_id=source.source_id,
        text=sentence,
        normalized_text=normalized,
        language=detect_language(normalized),
        provenance_hash=provenance_hash,
        source_url_or_path=source.source_url_or_path,
        license_hint=source.license_hint,
        collected_at=utc_now(),
        is_private=False,
        is_generated=False,
        is_eval_row=False,
        quality_flags=_sentence_quality_flags(normalized, source, policy),
        target_store="verified_store_v0_candidate",
        learning_mode="semantic_graph",
    )


def approved_payload_to_dict(payload: LearningPayload, source: SourceSpec, *, raw_text: str) -> dict[str, Any]:
    """Return the public approved-payload JSONL schema.

    Extra schema fields are preserved for auditability while
    ``VerifiedPayloadFeeder`` remains free to normalize only the fields it needs.
    """

    data = payload.to_dict()
    data.update(
        {
            "source_title": source.source_title,
            "raw_text_hash": stable_hash(raw_text),
            "normalized_text_hash": stable_hash(payload.normalized_text),
            "collector": "atanor_web_feeder",
            "collector_version": COLLECTOR_VERSION,
            "is_mock": False,
        }
    )
    return data


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _write_manifest(path: Path, result: ApprovedPayloadFeederResult, sources: list[SourceSpec]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "collector": COLLECTOR_VERSION,
        "updated_at": utc_now(),
        "approved_payload_path": result.approved_payload_path,
        "rejected_payload_path": result.rejected_payload_path,
        "payloads_approved": result.payloads_approved,
        "payloads_rejected": result.payloads_rejected,
        "sources": [asdict(source) | {"text": None} for source in sources],
        "invariants": {
            "production_store_mutated": result.production_store_mutated,
            "local_brain_write": result.local_brain_write,
            "false_confident": result.false_confident,
            "forgetting_count": result.forgetting_count,
            "eval_rows_used_for_learning": result.eval_rows_used_for_learning,
            "external_llm_used": result.external_llm_used,
            "mock_growth": result.mock_growth,
            "pair_edges_sent": result.pair_edges_sent,
            "private_data_used_for_cloud_learning": result.private_data_used_for_cloud_learning,
            "unsupported_claims": result.unsupported_claims,
        },
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def collect_approved_payloads(
    sources: list[SourceSpec],
    *,
    policy: WebFeederPolicy | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    rejected_dir: str | Path = DEFAULT_REJECTED_DIR,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    dry_run: bool = True,
    max_sources: int = 3,
    max_sentences: int = 1000,
    max_seconds: float = 60.0,
) -> ApprovedPayloadFeederResult:
    """Collect approved public payload rows without mutating production stores."""

    active_policy = policy or WebFeederPolicy()
    if not sources:
        return ApprovedPayloadFeederResult(
            state="no_configured_public_source",
            mode="dry_run" if dry_run else "execute",
            sources_configured=0,
            sources_checked=0,
            payloads_seen=0,
            payloads_approved=0,
            payloads_rejected=0,
            duplicate_count=0,
            rejection_reasons={},
        )

    started = time.perf_counter()
    source_mode = "local_dump_shard" if any(source.source_type == "local_public_corpus_shard" for source in sources) else "rest_api"
    stats: dict[str, Any] = {
        "rate_limited_count": 0,
        "backoff_seconds": 0.0,
        "source_rotation_count": max(0, min(len(sources), max_sources) - 1),
        "last_429_at": None,
    }
    approved: list[LearningPayload] = []
    approved_rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    seen_text_hashes: set[str] = set()
    duplicate_count = 0
    sources_checked = 0
    for source in sources[: max(1, max_sources)]:
        if time.perf_counter() - started > max_seconds:
            break
        sources_checked += 1
        try:
            source_items = _source_items(source, active_policy, stats)
        except Exception as exc:
            rejected.append({"source_id": source.source_id, "reason": str(exc), "source_url_or_path": source.source_url_or_path})
            continue
        for item_source, raw_text in source_items:
            remaining = max(0, min(max_sentences, active_policy.max_sentences_per_source) - len(approved) - len(rejected))
            if remaining <= 0:
                break
            for index, sentence in enumerate(_split_sentences(raw_text, max_sentences=remaining)):
                payload = _payload_from_sentence(sentence, item_source, index, active_policy)
                text_hash = stable_hash(payload.normalized_text)
                if payload.provenance_hash in seen_hashes or text_hash in seen_text_hashes:
                    duplicate_count += 1
                    rejected.append({"source_id": item_source.source_id, "reason": "duplicate_payload", "text": payload.normalized_text})
                    continue
                seen_hashes.add(payload.provenance_hash)
                seen_text_hashes.add(text_hash)
                if "quality_rejected" in set(payload.quality_flags):
                    rejected.append(
                        {
                            "source_id": item_source.source_id,
                            "reason": ",".join(flag for flag in payload.quality_flags if flag != "quality_rejected") or "quality_rejected",
                            "text": payload.normalized_text,
                        }
                    )
                    continue
                approved.append(payload)
                approved_rows.append(approved_payload_to_dict(payload, item_source, raw_text=raw_text))
            if len(approved) + len(rejected) >= max_sentences:
                break

    rejection_reasons: dict[str, int] = {}
    for row in rejected:
        reason = str(row.get("reason") or "unknown")
        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    approved_path = str(Path(output_dir) / f"approved_payloads_{stamp}.jsonl")
    rejected_path = str(Path(rejected_dir) / f"rejected_payloads_{stamp}.jsonl")
    state = "payloads_approved" if approved else "no_approved_payloads_after_policy"
    result = ApprovedPayloadFeederResult(
        state=state,
        mode="dry_run" if dry_run else "execute",
        sources_configured=len(sources),
        sources_checked=sources_checked,
        payloads_seen=len(approved) + len(rejected),
        payloads_approved=len(approved),
        payloads_rejected=len(rejected),
        duplicate_count=duplicate_count,
        rejection_reasons=rejection_reasons,
        approved_payload_path=None if dry_run or not approved else approved_path,
        rejected_payload_path=None if dry_run or not rejected else rejected_path,
        manifest_path=None if dry_run else str(manifest_path),
        source_mode=source_mode,
        rate_limited_count=int(stats.get("rate_limited_count") or 0),
        backoff_seconds=round(float(stats.get("backoff_seconds") or 0.0), 3),
        source_rotation_count=int(stats.get("source_rotation_count") or 0),
        last_429_at=stats.get("last_429_at"),
        recommended_source_for_long_run="local_dump_shard",
    )
    if not dry_run:
        if approved:
            _write_jsonl(Path(approved_path), approved_rows)
        if rejected:
            _write_jsonl(Path(rejected_path), rejected)
        _write_manifest(Path(manifest_path), result, sources)
    return result


def _sources_from_args(args: argparse.Namespace) -> list[SourceSpec]:
    sources: list[SourceSpec] = []
    for url in args.source_url or []:
        sources.append(
            SourceSpec(
                source_type=_source_type_for_url(url),
                source_id=f"url:{stable_hash(url)[:16]}",
                source_url_or_path=url,
                license_hint=args.license_hint,
                source_title=args.source_title,
            )
        )
    for file_path in args.source_file or []:
        sources.append(
            SourceSpec(
                source_type=args.source_type,
                source_id=f"file:{stable_hash(str(Path(file_path).resolve()))[:16]}",
                source_url_or_path=str(file_path),
                license_hint=args.license_hint,
                source_title=args.source_title,
            )
        )
    for sentence in args.manual_public_sentence or []:
        sources.append(
            SourceSpec(
                source_type="manual_public_sentence",
                source_id=f"manual:{stable_hash(sentence)[:16]}",
                source_url_or_path=args.manual_source_url or "manual://approved-public-sentence",
                license_hint=args.license_hint,
                source_title=args.source_title,
                text=sentence,
            )
        )
    return sources


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create approved public Cloud Brain learning payloads.")
    parser.add_argument("--source-url", action="append", default=[])
    parser.add_argument("--source-file", action="append", default=[])
    parser.add_argument("--source-type", default="local_public_corpus_shard")
    parser.add_argument("--manual-public-sentence", action="append", default=[])
    parser.add_argument("--manual-source-url", default="")
    parser.add_argument("--license-hint", default="")
    parser.add_argument("--source-title", default=None)
    parser.add_argument("--allowed-domain", action="append", default=[])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--rejected-dir", default=str(DEFAULT_REJECTED_DIR))
    parser.add_argument("--manifest-path", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--max-sources", type=int, default=3)
    parser.add_argument("--max-sentences", type=int, default=1000)
    parser.add_argument("--max-seconds", type=float, default=60.0)
    parser.add_argument("--execute", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for the approved public payload feeder."""

    args = _parse_args(argv)
    allowed_domains = set(DEFAULT_ALLOWED_DOMAINS)
    allowed_domains.update(domain.lower() for domain in args.allowed_domain or [])
    policy = WebFeederPolicy(allowed_domains=allowed_domains)
    dry_run = True if not args.execute else bool(args.dry_run)
    result = collect_approved_payloads(
        _sources_from_args(args),
        policy=policy,
        output_dir=args.output_dir,
        rejected_dir=args.rejected_dir,
        manifest_path=args.manifest_path,
        dry_run=dry_run,
        max_sources=args.max_sources,
        max_sentences=args.max_sentences,
        max_seconds=args.max_seconds,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.state in {"payloads_approved", "no_configured_public_source", "no_approved_payloads_after_policy"} else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
