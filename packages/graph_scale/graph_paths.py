"""Canonical graph read path and non-authoritative mutation spool paths.

The shipped graph is a reader surface. Producers must never borrow its path from
another producer module or reinterpret a proposal fragment as the shared world
ledger. These constants separate those roles while the immutable mutation-batch
contract is adopted incrementally.

Paths below the mutation spool are proposal fragments only. Presence there means
neither ``staged`` nor ``applied``; only a verified sibling candidate and a
COMMITTED operator-signed swap can establish those later lifecycle phases.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_GRAPH_ROOT = (
    REPOSITORY_ROOT / "data" / "graph_scale" / "kg_triples"
)
GRAPH_MUTATION_SPOOL_ROOT = (
    REPOSITORY_ROOT / "runtime" / "graph_mutation_spool"
)
MUTATION_BATCHES_ROOT = GRAPH_MUTATION_SPOOL_ROOT / "batches"
SHIPPED_STORE_TARGET_ID = "atanor:graph-scale:kg-triples-primary"

_PRODUCER_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_MUTATION_BATCH_ID = re.compile(r"^gmb_[0-9a-f]{32}$")


def _is_link_or_junction(path: Path) -> bool:
    is_junction = getattr(os.path, "isjunction", None)
    return path.is_symlink() or bool(is_junction and is_junction(path))


def _absolute_resolved(path: str | Path) -> Path:
    lexical = Path(path).expanduser()
    absolute = Path(os.path.abspath(lexical))
    try:
        return absolute.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError("graph path cannot be resolved safely") from exc


def same_graph_path(left: str | Path, right: str | Path) -> bool:
    """Compare normalized graph paths without requiring either to exist."""

    return os.path.normcase(str(_absolute_resolved(left))) == os.path.normcase(
        str(_absolute_resolved(right))
    )


def is_shipped_graph_root(path: str | Path) -> bool:
    """Return whether ``path`` resolves to the one canonical reader surface."""

    return same_graph_path(path, SHIPPED_GRAPH_ROOT)


def _assert_existing_path_chain_has_no_links(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() and _is_link_or_junction(current):
            raise ValueError("graph path must not traverse a symlink or junction")


def _validated_batches_root(
    batches_root: str | Path | None,
    *,
    create_parents: bool,
) -> Path:
    lexical = Path(
        MUTATION_BATCHES_ROOT if batches_root is None else batches_root
    ).expanduser()
    _assert_existing_path_chain_has_no_links(lexical)
    if create_parents:
        lexical.mkdir(parents=True, exist_ok=True)
        _assert_existing_path_chain_has_no_links(lexical)
    resolved = _absolute_resolved(lexical)
    shipped = _absolute_resolved(SHIPPED_GRAPH_ROOT)
    if resolved == shipped or shipped in resolved.parents or resolved in shipped.parents:
        raise ValueError("mutation batches root must be disjoint from shipped graph")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("mutation batches root must be a directory")
    return resolved


def mutation_batch_root(
    batch_id: str,
    *,
    batches_root: str | Path | None = None,
) -> Path:
    """Compute one confined immutable mutation-batch directory."""

    if (
        not isinstance(batch_id, str)
        or _MUTATION_BATCH_ID.fullmatch(batch_id) is None
    ):
        raise ValueError("invalid graph mutation batch id")
    root = _validated_batches_root(batches_root, create_parents=False)
    candidate = root / batch_id
    resolved = _absolute_resolved(candidate)
    if resolved.parent != root:
        raise ValueError("graph mutation batch path escapes its batches root")
    if candidate.exists() and _is_link_or_junction(candidate):
        raise ValueError("graph mutation batch path is a link or junction")
    return candidate


def create_mutation_batch_root(
    batch_id: str,
    *,
    batches_root: str | Path | None = None,
) -> Path:
    """Create one new batch root; collisions and partial roots fail closed."""

    root = _validated_batches_root(batches_root, create_parents=True)
    candidate = mutation_batch_root(batch_id, batches_root=root)
    candidate.mkdir(exist_ok=False)
    return candidate


def legacy_proposal_fragment_root(producer_id: str) -> Path:
    """Return a producer-isolated transitional proposal path.

    This helper deliberately says ``legacy``: fixed fragment directories do not
    provide per-run atomicity, base binding, or immutable manifests. New producers
    must use ``mutation_batch`` instead. The helper exists only to stop shipped
    readers and unrelated producers from sharing the old abstain path while each
    producer is migrated.
    """

    if (
        not isinstance(producer_id, str)
        or _PRODUCER_ID.fullmatch(producer_id) is None
    ):
        raise ValueError("invalid graph mutation producer id")
    return (
        GRAPH_MUTATION_SPOOL_ROOT
        / "legacy_proposal_fragments"
        / producer_id
    )


ABSTAIN_PROPOSAL_FRAGMENT_ROOT = legacy_proposal_fragment_root(
    "abstain_feeder"
)
BULK_INGEST_PROPOSAL_FRAGMENT_ROOT = legacy_proposal_fragment_root(
    "bulk_ingest"
)
SENSORY_PROPOSAL_FRAGMENT_ROOT = legacy_proposal_fragment_root(
    "sensory_cortex"
)
VISUAL_PROPOSAL_FRAGMENT_ROOT = legacy_proposal_fragment_root(
    "visual_kg"
)
WEB_KNOWLEDGE_PROPOSAL_FRAGMENT_ROOT = legacy_proposal_fragment_root(
    "web_knowledge"
)
STRUCTURED_PROFILE_PROPOSAL_FRAGMENT_ROOT = (
    legacy_proposal_fragment_root("structured_profile")
)
RELATION_MINER_PROPOSAL_FRAGMENT_ROOT = legacy_proposal_fragment_root(
    "relation_miner"
)
KNOWLEDGE_HARVEST_PROPOSAL_FRAGMENT_ROOT = (
    legacy_proposal_fragment_root("knowledge_harvest")
)
KAIKKI_PROPOSAL_FRAGMENT_ROOT = legacy_proposal_fragment_root(
    "kaikki_ingest"
)
URIMALSEM_PROPOSAL_FRAGMENT_ROOT = legacy_proposal_fragment_root(
    "urimalsaem"
)
WIKIDATA_TERM_PROPOSAL_FRAGMENT_ROOT = legacy_proposal_fragment_root(
    "wikidata_term_resolver"
)


__all__ = [
    "ABSTAIN_PROPOSAL_FRAGMENT_ROOT",
    "BULK_INGEST_PROPOSAL_FRAGMENT_ROOT",
    "GRAPH_MUTATION_SPOOL_ROOT",
    "MUTATION_BATCHES_ROOT",
    "KNOWLEDGE_HARVEST_PROPOSAL_FRAGMENT_ROOT",
    "KAIKKI_PROPOSAL_FRAGMENT_ROOT",
    "REPOSITORY_ROOT",
    "RELATION_MINER_PROPOSAL_FRAGMENT_ROOT",
    "SENSORY_PROPOSAL_FRAGMENT_ROOT",
    "SHIPPED_GRAPH_ROOT",
    "SHIPPED_STORE_TARGET_ID",
    "STRUCTURED_PROFILE_PROPOSAL_FRAGMENT_ROOT",
    "URIMALSEM_PROPOSAL_FRAGMENT_ROOT",
    "VISUAL_PROPOSAL_FRAGMENT_ROOT",
    "WEB_KNOWLEDGE_PROPOSAL_FRAGMENT_ROOT",
    "WIKIDATA_TERM_PROPOSAL_FRAGMENT_ROOT",
    "create_mutation_batch_root",
    "is_shipped_graph_root",
    "legacy_proposal_fragment_root",
    "mutation_batch_root",
    "same_graph_path",
]
