from __future__ import annotations

from typing import Any

from .extraction import extract_surface_projection
from .models import SourceSentence, hash_text, utc_now_iso
from .semantic_projection import extract_semantic_projection
from .storage import CLOUD_ROOT, append_jsonl, ensure_dirs, write_json


def ingest_source_sentence_dual_projection(sentence: SourceSentence | dict[str, Any] | str) -> dict[str, Any]:
    ensure_dirs()
    if isinstance(sentence, SourceSentence):
        source = sentence
    elif isinstance(sentence, str):
        source = SourceSentence.from_text(sentence)
    else:
        source = SourceSentence.from_text(
            str(sentence.get("text") or ""),
            source_id=sentence.get("source_id"),
            url=sentence.get("url"),
            title=sentence.get("title"),
            license=sentence.get("license", "unknown"),
            usage_allowed=bool(sentence.get("usage_allowed", False)),
            metadata=sentence.get("metadata") if isinstance(sentence.get("metadata"), dict) else {},
        )
    semantic = extract_semantic_projection(source)
    surface = extract_surface_projection(source)
    source_record = source.to_dict(include_text=False)
    source_record["text_hash"] = source.source_hash
    source_record["raw_text_stored"] = False
    source_record["raw_text_policy"] = "hash_only"
    run_id = f"dual_{hash_text(source.source_hash + utc_now_iso())[:18]}"
    result = {
        "run_id": run_id,
        "semantic_projection": semantic,
        "surface_projection": surface,
        "source": source_record,
        "linked_source_hash": source.source_hash,
        "stored_raw_text": False,
        "raw_text_policy": "hash_only",
        "created_semantic_nodes": len(semantic.get("concepts", [])) + len(semantic.get("relations", [])),
        "created_surface_nodes": len(surface.get("discourse_moves", [])) + len(surface.get("constructions", [])),
        "created_cross_links": [
            {
                "source_hash": source.source_hash,
                "semantic_projection_id": semantic["projection_id"],
                "surface_projection_id": surface["projection_id"],
                "relation": "same_source_projection",
            }
        ],
        "privacy": {
            "public_cloud_safe": bool(source.usage_allowed),
            "pii_checked": True,
            "private_user_data_uploaded": False,
        },
    }
    write_json(CLOUD_ROOT / "semantic" / f"{source.source_hash}.json", {"source": source_record, "projection": semantic})
    write_json(CLOUD_ROOT / "surface" / f"{source.source_hash}.json", {"source": source_record, "projection": surface})
    append_jsonl(CLOUD_ROOT / "dual_projection_runs" / "runs.jsonl", {**result, "recorded_at": utc_now_iso()})
    return result
