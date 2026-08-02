# -*- coding: utf-8 -*-
"""ConceptNet connector — common-sense relations into the GATED candidate lane.

Owner's dataset call (2026-07-09): ConceptNet gives the relation DIVERSITY the
graph lacks (bird→can fly, knife→used for cutting) — exactly what the fluency
doctrine needs. But the owner also warned: bulk imports are where contamination
sneaks in. So this lands ConceptNet edges as CANDIDATES only: mapped to our
predicates, weight-filtered, and the Surgeon reviews every is_a before it is even
allowed into the candidate ledger. Nothing here writes production; promotion
stays the operator/evidence gate.

A bounded, seed-driven harvest (per_term edges for a list of seeds) — the full
dump is a scheduled bulk op, not an inline call. The HTTP fetcher is injectable
so this is testable offline and degrades honestly when there is no network.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

LEDGER_DIR = Path(__file__).resolve().parents[2] / "data" / "cloud_brain" / "derived_candidates"

# ConceptNet /r/* -> our predicates. Only relations that are real graph edges
# (entity->entity); we drop chatty ones (RelatedTo/Synonym) that would just add
# noise to a KG meant for reasoning.
RELATION_MAP = {
    "/r/IsA": "is_a", "/r/PartOf": "part_of", "/r/HasA": "has_part",
    "/r/UsedFor": "used_for", "/r/CapableOf": "capable_of",
    "/r/AtLocation": "located_in", "/r/Causes": "원인",
    "/r/MadeOf": "구성요소", "/r/HasProperty": "has_property",
}
_MIN_WEIGHT = 1.0          # ConceptNet weight floor — drop weak crowd edges


def _http_get_json(url: str, *, retries: int = 3) -> dict[str, Any]:
    """GET with backoff — ConceptNet's hosted API is frequently 502/flaky, so a
    transient failure must not abort a harvest."""
    import time
    import urllib.error
    import urllib.request
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ATANOR-KG/1.0"})
            with urllib.request.urlopen(req, timeout=12) as r:  # noqa: S310 (fixed host)
                return json.loads(r.read().decode("utf-8", "ignore"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 502, 503, 504) and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except Exception as e:
            last = e
            if attempt < retries - 1:
                time.sleep(1.0)
                continue
            raise
    if last:
        raise last
    return {}


def _label_from_uri(uri: str) -> tuple[str, str]:
    """'/c/en/new_york_city' -> ('en', 'new york city')."""
    parts = uri.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "c":
        return parts[1], parts[2].replace("_", " ")
    return "", ""


def harvest_from_dump(dump_path: str | Path, *, langs: tuple[str, ...] = ("en", "ko"),
                      out_dir: str | Path | None = None, store: Any = None,
                      max_rows: int = 5_000_000) -> dict[str, Any]:
    """Offline harvest from a ConceptNet assertions dump (TSV: uri, rel, start,
    end, meta-json) — the robust path when the API is down. Same gates as the API
    harvest: predicate-mapped, weight-filtered, Surgeon-reviewed is_a, candidate
    ledger only. This is how the clean-source geometry unlock actually lands at scale."""
    dump_path = Path(dump_path)
    if not dump_path.exists():
        return {"harvested": False, "reason": "dump_not_found", "path": str(dump_path)}
    out_dir = Path(out_dir) if out_dir else LEDGER_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        from .surgeon import inspect as surgeon_inspect
    except Exception:
        surgeon_inspect = None

    by_pred: dict[str, list[tuple[str, str, str, float]]] = {}
    seen_rows = kept = excised = 0
    opener = _dump_opener(dump_path)
    with opener as fh:
        for line in fh:
            seen_rows += 1
            if seen_rows > max_rows:
                break
            try:
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 5:
                    continue
                pred = RELATION_MAP.get(cols[1])
                if not pred:
                    continue
                ls, s = _label_from_uri(cols[2])
                lo, o = _label_from_uri(cols[3])
                if ls not in langs or lo not in langs or not s or not o or s == o:
                    continue
                w = float(json.loads(cols[4]).get("weight", 1.0))
                if w < _MIN_WEIGHT or len(s) > 40 or len(o) > 40:
                    continue
                if pred == "is_a" and surgeon_inspect is not None and store is not None:
                    v = surgeon_inspect(store, s, o)
                    if isinstance(v, dict) and v.get("contaminated"):
                        excised += 1
                        continue
                by_pred.setdefault(pred, []).append((s, pred, o, round(w, 3)))
                kept += 1
            except Exception:
                continue
    written = _flush_candidates(by_pred, out_dir)
    return {"harvested": True, "dump": str(dump_path), "rows_scanned": seen_rows,
            "kept": kept, "surgeon_excised": excised, "candidates_written": written,
            "predicates": sorted(by_pred), "written_to_production": False}


def _dump_opener(path: Path):
    import gzip
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="ignore")
    return open(path, "r", encoding="utf-8", errors="ignore")


def fetch_edges(term: str, lang: str = "en", limit: int = 40,
                fetcher: Callable[[str], dict[str, Any]] | None = None
                ) -> list[tuple[str, str, str, float]]:
    """Bounded edges for one concept as (subject, predicate, object, weight),
    already mapped to our predicates. fetcher lets tests inject canned JSON."""
    get = fetcher or _http_get_json
    url = f"https://api.conceptnet.io/c/{lang}/{term}?limit={int(limit)}"
    try:
        payload = get(url)
    except Exception:
        return []
    out: list[tuple[str, str, str, float]] = []
    for e in payload.get("edges", []) or []:
        rel = (e.get("rel") or {}).get("@id")
        pred = RELATION_MAP.get(rel)
        if not pred:
            continue
        s = ((e.get("start") or {}).get("label") or "").strip()
        o = ((e.get("end") or {}).get("label") or "").strip()
        w = float(e.get("weight") or 0.0)
        if s and o and s.lower() != o.lower() and w >= _MIN_WEIGHT and len(s) <= 40 and len(o) <= 40:
            out.append((s, pred, o, round(w, 3)))
    return out


def harvest(seed_terms: list[str], *, lang: str = "en", per_term: int = 40,
            out_dir: str | Path | None = None, store: Any = None,
            fetcher: Callable[[str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Fetch common-sense edges for the seeds, Surgeon-review is_a, and append the
    clean ones to the candidate ledger (tier=candidate, provenance conceptnet).
    Candidate-only; never touches production. Returns an audit dict."""
    out_dir = Path(out_dir) if out_dir else LEDGER_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        from .surgeon import inspect as surgeon_inspect
    except Exception:
        surgeon_inspect = None

    by_pred: dict[str, list[tuple[str, str, str, float]]] = {}
    fetched = excised = 0
    for term in seed_terms[:500]:
        for s, pred, o, w in fetch_edges(term, lang=lang, limit=per_term, fetcher=fetcher):
            fetched += 1
            # the Surgeon guards is_a: a type-disjoint claim is contamination, cut it
            if pred == "is_a" and surgeon_inspect is not None and store is not None:
                try:
                    v = surgeon_inspect(store, s, o)
                    if isinstance(v, dict) and v.get("contaminated"):
                        excised += 1
                        continue
                except Exception:
                    pass
            by_pred.setdefault(pred, []).append((s, pred, o, w))

    written = _flush_candidates(by_pred, out_dir)
    return {"seeds": len(seed_terms[:500]), "fetched": fetched,
            "surgeon_excised": excised, "candidates_written": written,
            "predicates": sorted(by_pred), "written_to_production": False,
            "note": "gated candidates only — promotion stays the operator/evidence gate"}


def _flush_candidates(by_pred: dict[str, list[tuple[str, str, str, float]]],
                      out_dir: Path) -> int:
    """Append deduped (s, o) candidate rows per predicate to the ledger."""
    written = 0
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for pred, rows in by_pred.items():
        path = out_dir / f"conceptnet_{pred}.jsonl"
        seen: set[tuple[Any, Any]] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                    seen.add((r.get("s"), r.get("o")))
                except Exception:
                    pass
        with path.open("a", encoding="utf-8") as fh:
            for s, p, o, w in rows:
                if (s, o) in seen:
                    continue
                seen.add((s, o))
                fh.write(json.dumps({"s": s, "p": p, "o": o, "weight": w,
                                     "src": "conceptnet", "tier": "candidate", "at": now},
                                    ensure_ascii=False) + "\n")
                written += 1
    return written
