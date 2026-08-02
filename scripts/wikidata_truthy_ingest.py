# -*- coding: utf-8 -*-
"""Wikidata TRUTHY-dump ingest -> English common-sense triples in OUR relation vocab,
staged for operator-approved promotion (owner call 2026-07-23: download English Wikidata
to D: and feed it as common sense).

WHY WIKIDATA: it is already (subject, predicate, object), human-curated, CC0 — the exact
clean-source geometry the density levers need (same doctrine as scripts/stage_r2_conceptnet.py,
but Wikidata is ~50x larger and covers named entities ConceptNet never had: countries, people,
works, places). The truthy dump (`latest-truthy.nt.gz`, ~66 GB) is the best-rank projection:
one N-Triples line per best statement, so no rank/qualifier bookkeeping is needed.

THE SCALE PROBLEM AND THE FIX (two passes, bounded RAM):
  ~100M entities, each with an English label — the label table does NOT fit in RAM. So:
    PASS 1  stream the dump, write English Q-id labels to a compact on-disk key->label
            store and retain P-id English labels/aliases, datatypes, and revisions in separate
            catalog tables. Bounded RAM: entity labels live on disk; property metadata is small.
    PASS 2  stream the dump again, keep only the curated common-sense P-properties whose OBJECT
            is an entity (Q-id), and JOIN subject/object against the label store. A statement
            is emitted only if BOTH endpoints have an English label. Result: (subject_label,
            our_relation, object_label). The dump is grouped by subject, so the subject label is
            looked up once per entity (cached); object labels use a small LRU (class Q-ids like
            Q5 'human' repeat millions of times).

SAFETY / BINDING:
  * NEVER writes the shipped store (data/graph_scale/kg_triples). Writes ONLY to
    data/graph_scale/staging_b1_wikidata/. Promotion staging->shipped is the operator-signed
    morning step (candidate_promotion_gate); this stages + measures only.
  * ENGLISH-ONLY by construction: the label store holds only @en labels, so both endpoints of
    every emitted triple are English. A defensive Hangul reject mirrors the store's own gate.
  * NO FABRICATION: every staged triple is a real truthy statement line joined to two real
    @en label lines. provenance = "wikidata-truthy". `--trace N` dumps the first N
    (raw dump line -> emitted triple) pairs so the join is auditable end-to-end.
  * Relations map to the SHIPPED store's OWN predicate names (verified against its term dict:
    is_a, located_in, part_of, has_a, has_property, made_of, occupation, author, creator,
    country, capital, official_language, director, religion, manufacturer, industry, sport,
    employer, genre) so a future promotion merges with ZERO new vocab (no speech-frame debt).

USAGE
  # PASS 1 + PASS 2 on the truncated sample (develop/CI):
  python -X utf8 scripts/wikidata_truthy_ingest.py \
      --dump scratchpad/wd_sample.nt.gz --allow-truncated \
      --label-db scratchpad/wd_labels_sample.sqlite \
      --staging data/graph_scale/staging_b1_wikidata --trace 300
  # Full 66 GB run (when the D: download completes):
  python -X utf8 scripts/wikidata_truthy_ingest.py \
      --dump D:/wikidata/latest-truthy.nt.gz \
      --label-db D:/wikidata/wd_labels.sqlite \
      --staging data/graph_scale/staging_b1_wikidata --dict-backend sharded
  # Independent literal-only pass (reuses PASS-1 labels; never replaces entity staging):
  python -X utf8 scripts/wikidata_truthy_ingest.py \
      --pass literal --dump D:/wikidata/latest-truthy.nt.gz \
      --label-db D:/wikidata/wd_labels.sqlite \
      --literal-staging data/graph_scale/staging_s1_wikidata_literals \
      --dict-backend sharded --trace 300
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

_MEMBRANE_TRUTHY = {"1", "true", "yes", "on"}

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# --------------------------------------------------------------------------------------
# Curated common-sense P-property -> OUR predicate name. EVERY target is an existing shipped
# predicate (probed against the shipped term dict 2026-07-23) so promotion needs no new vocab.
# Only ENTITY-valued (Q-id object) properties are here; literal-valued props (dates,
# coordinates, quantities, external IDs, image files) are excluded by construction because
# pass 2 keeps a statement only when its object is <...entity/Q...> (see join_statements).
# --------------------------------------------------------------------------------------
RELMAP: dict[str, str] = {
    # taxonomic backbone
    "P31": "is_a",              # instance of      -> Douglas Adams is_a human
    "P279": "is_a",             # subclass of      -> dog is_a mammal
    # place / geography
    "P17": "country",           # country          -> Paris country France
    "P131": "located_in",       # located in admin territorial entity
    "P276": "located_in",       # location
    "P159": "located_in",       # headquarters location
    "P36": "capital",           # capital          -> France capital Paris  (fills a known gap)
    "P37": "official_language", # official language-> France official_language French
    # composition / mereology
    "P361": "part_of",          # part of          -> wheel part_of car
    "P527": "has_a",            # has part(s)      -> car has_a wheel
    "P186": "made_of",          # made from material
    "P1552": "has_property",    # has quality
    # people / works / orgs
    "P106": "occupation",       # occupation       -> Douglas Adams occupation writer
    "P50": "author",            # author           -> book author person
    "P170": "creator",          # creator          -> artwork creator person
    "P57": "director",          # director         -> film director person
    "P140": "religion",         # religion
    "P108": "employer",         # employer
    "P136": "genre",            # genre
    "P176": "manufacturer",     # manufacturer
    "P452": "industry",         # industry
    "P641": "sport",            # sport
    "P495": "country",          # country of origin -> product country Japan
}

# is_a object NOISE: administrative / metadata classes that pollute the taxonomy. Dropped by
# exact Q-id (fast, precise) AND defensively by an English-label pattern. These are NOT common
# sense (they are Wikimedia bookkeeping), so they never belong in an is_a walk.
NOISE_OBJECT_QIDS = {
    4167410,   # Wikimedia disambiguation page
    4167836,   # Wikimedia category
    11266439,  # Wikimedia template
    13406463,  # Wikimedia list article
    13442814,  # scholarly article
    22808320,  # Wikimedia human name disambiguation page
    17362920,  # Wikimedia duplicated page
    11753321,  # Wikimedia navigational template
    15184295,  # Wikimedia module
    4663903,   # Wikimedia portal
    15647814,  # Wikimedia administration category
    20010800,  # Wikimedia user language template
    21484471,  # (aggregation-of-quantities placeholder classes vary; label filter backstops)
}
NOISE_LABEL_RE = re.compile(r"(?i)\b(wikimedia|wikinews|wikispecies)\b|disambiguation page|"
                            r"metaclass|template$")

MAX_SURFACE = 80          # Wikidata labels are curated; 80 keeps 'People's Republic of China'
                          # (26) and drops scholarly-article-title-length noise.
HANGUL = re.compile(r"[가-힣]")   # defensive: mirror the store's English-only gate
_LABEL_PRED = "<http://www.w3.org/2000/01/rdf-schema#label>"
_ALT_LABEL_PRED = "<http://www.w3.org/2004/02/skos/core#altLabel>"
_PROPERTY_TYPE_PRED = "<http://wikiba.se/ontology#propertyType>"
_SCHEMA_VERSION_PRED = "<http://schema.org/version>"
_ENTITY_PREFIX = "<http://www.wikidata.org/entity/Q"
_ENTITY_QID_RE = re.compile(r"<http://www\.wikidata\.org/entity/Q([1-9]\d*)>\Z")
_ENTITY_PID_RE = re.compile(r"<http://www\.wikidata\.org/entity/P([1-9]\d*)>\Z")
_ENTITY_DATA_PID_RE = re.compile(
    r"<http://www\.wikidata\.org/wiki/Special:EntityData/P([1-9]\d*)>\Z"
)
_WIKIBASE_PROPERTY_TYPE_RE = re.compile(
    r"<http://wikiba\.se/ontology#([A-Za-z][A-Za-z0-9]*)>\Z"
)
_DIRECT = "/prop/direct/"
_DIRECT_PRED_RE = re.compile(
    r"<http://www\.wikidata\.org/prop/direct/(P[1-9]\d*)>\Z"
)
_IRI_RE = re.compile(r"<[^<>{}\"\\\x00-\x20]+>\Z")
_SHIPPED_ROOT = REPO / "data" / "graph_scale" / "kg_triples"
_ENTITY_STAGING_ROOT = REPO / "data" / "graph_scale" / "staging_b1_wikidata"
_LITERAL_STAGING_ROOT = REPO / "data" / "graph_scale" / "staging_s1_wikidata_literals"
_LITERAL_SCHEMA = REPO / "scripts" / "wikidata_literal_schema_v1.json"
_ENTITY_MANIFEST = "B1_WIKIDATA_MANIFEST.json"
_LITERAL_MANIFEST = "S1_WIKIDATA_LITERAL_MANIFEST.json"
_LITERAL_PARTIAL_MANIFEST = "S1_WIKIDATA_LITERAL_PARTIAL.json"
_XSD = "http://www.w3.org/2001/XMLSchema#"
_PID_RE = re.compile(r"P[1-9]\d*\Z")
_PREDICATE_RE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_DATE_RE = re.compile(
    r"(?P<year>[+-]?\d{4,})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"(?P<time>T(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?:\.\d+)?Z)?\Z"
)
_INTEGER_LEXICAL_RE = re.compile(r"[+-]?\d+\Z")
_DECIMAL_LEXICAL_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)\Z")


# --------------------------------------------------------------------------------------
# N-Triples parsing
# --------------------------------------------------------------------------------------
def stream_nt_lines(path: str | Path, *, allow_truncated: bool = False,
                    max_lines: int | None = None):
    """Yield complete decoded lines from a (possibly truncated) gzip. A range-request SAMPLE
    ends mid-member: gzip raises EOFError/BadGzipFile/OSError at the torn tail — we catch it and
    keep every COMPLETE line already read (a line without a trailing newline is the torn one and
    is dropped)."""
    if max_lines is not None and (type(max_lines) is not int or max_lines <= 0):
        raise ValueError("max_lines must be a positive integer or None")
    n = 0
    fh = gzip.open(path, "rt", encoding="utf-8", errors="strict")
    try:
        for line in fh:
            if not line.endswith("\n"):
                break                      # torn final line
            yield line
            n += 1
            if max_lines is not None and n >= max_lines:
                break
    except (EOFError, OSError, gzip.BadGzipFile) as e:
        if not allow_truncated:
            raise
        sys.stderr.write(f"[stream] torn-tail tolerated ({type(e).__name__}) after "
                         f"{n:,} complete lines\n")
    finally:
        try:
            fh.close()
        except Exception:
            pass


def parse_triple(line: str):
    """'<s> <p> o .' -> (s, p, o_raw). s/p are angle-bracket URIs (no internal spaces); o_raw is
    the object token(s) with the trailing ' .' removed (may contain spaces, e.g. a quoted label)."""
    if not isinstance(line, str) or not line or line[0] not in "<_":
        return None
    body = line.rstrip("\r\n")
    if not body.endswith(" ."):
        return None
    body = body[:-2]
    # subject: up to first space
    sp1 = body.find(" ")
    if sp1 <= 0:
        return None
    s = body[:sp1]
    rest = body[sp1:].lstrip(" ")
    sp2 = rest.find(" ")
    if sp2 <= 0:
        return None
    p = rest[:sp2]
    o = rest[sp2:].lstrip(" ")
    if not o or _IRI_RE.fullmatch(p) is None:
        return None
    if _IRI_RE.fullmatch(s) is None and re.fullmatch(r"_:[A-Za-z][A-Za-z0-9._-]*", s) is None:
        return None
    return s, p, o


def qid_int(uri: str):
    """'<http://www.wikidata.org/entity/Q42>' -> 42 ; anything else -> None (P-ids, lexemes,
    other URIs, blank nodes all return None)."""
    match = _ENTITY_QID_RE.fullmatch(uri)
    if match is None:
        return None
    digits = match.group(1)
    if len(digits) > 20:
        return None
    value = int(digits)
    return value if value <= 0xFFFFFFFFFFFFFFFF else None


def pid_int(uri: str):
    """'<http://www.wikidata.org/entity/P31>' -> 31; non-property URIs -> None."""
    match = _ENTITY_PID_RE.fullmatch(uri)
    if match is None:
        return None
    digits = match.group(1)
    if len(digits) > 10:
        return None
    value = int(digits)
    return value if value <= 0xFFFFFFFF else None


def property_data_pid_int(uri: str):
    """Return the PID from a canonical Wikidata entity-data node."""
    match = _ENTITY_DATA_PID_RE.fullmatch(uri)
    if match is None:
        return None
    digits = match.group(1)
    if len(digits) > 10:
        return None
    value = int(digits)
    return value if value <= 0xFFFFFFFF else None


def property_type_iri(object_uri: str) -> str | None:
    """Return one canonical Wikibase property-type IRI, or None."""
    match = _WIKIBASE_PROPERTY_TYPE_RE.fullmatch(object_uri)
    if match is None:
        return None
    return f"http://wikiba.se/ontology#{match.group(1)}"


def property_revision(object_literal: str) -> str | None:
    """Parse an exact non-negative schema:version xsd:integer literal."""
    split = _split_nt_literal(object_literal)
    if split is None:
        return None
    lexical, language, datatype = split
    if (
        language is not None
        or datatype != _XSD + "integer"
        or re.fullmatch(r"(?:0|[1-9]\d*)", lexical) is None
        or len(lexical) > 20
    ):
        return None
    return lexical


def direct_property_id(predicate_uri: str) -> str | None:
    match = _DIRECT_PRED_RE.fullmatch(predicate_uri)
    return match.group(1) if match is not None else None


_ESC = {"\\": "\\", '"': '"', "'": "'", "n": "\n", "t": "\t", "r": "\r",
        "b": "\b", "f": "\f"}


def unescape_nt(s: str) -> str:
    """Unescape N-Triples string escapes (\\\" \\\\ \\n \\t \\uXXXX \\UXXXXXXXX). Wikidata emits
    most characters as raw UTF-8, so this is a light path hit only on rows that carry a backslash."""
    if "\\" not in s:
        return s
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            if i + 1 >= n:
                raise ValueError("trailing N-Triples escape")
            nxt = s[i + 1]
            if nxt == "u":
                digits = s[i + 2:i + 6]
                if len(digits) != 4 or re.fullmatch(r"[0-9A-Fa-f]{4}", digits) is None:
                    raise ValueError("invalid N-Triples unicode escape")
                codepoint = int(digits, 16)
                if 0xD800 <= codepoint <= 0xDFFF:
                    raise ValueError("surrogate is not a Unicode scalar")
                out.append(chr(codepoint))
                i += 6
                continue
            if nxt == "U":
                digits = s[i + 2:i + 10]
                if len(digits) != 8 or re.fullmatch(r"[0-9A-Fa-f]{8}", digits) is None:
                    raise ValueError("invalid N-Triples unicode escape")
                codepoint = int(digits, 16)
                if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
                    raise ValueError("invalid Unicode scalar")
                out.append(chr(codepoint))
                i += 10
                continue
            if nxt not in _ESC:
                raise ValueError(f"unknown N-Triples escape: \\{nxt}")
            out.append(_ESC[nxt])
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def parse_en_label(o_raw: str):
    """'"Belgium"@en' -> 'Belgium' ; returns None for any non-@en literal or a URI object."""
    split = _split_nt_literal(o_raw)
    if split is None:
        return None
    lexical, language, datatype = split
    if language != "en" or datatype is not None or any(ord(ch) < 32 for ch in lexical):
        return None
    return lexical


def _split_nt_literal(o_raw: str) -> tuple[str, str | None, str | None] | None:
    """Return ``(lexical, language, datatype_uri)`` for one N-Triples literal.

    URI objects and malformed/unterminated strings return ``None``. The scanner respects escaped
    quotes instead of relying on ``rfind`` because arbitrary string-valued properties may contain
    suffix-like text.
    """
    if not o_raw or o_raw[0] != '"':
        return None
    escaped = False
    end = None
    for i in range(1, len(o_raw)):
        ch = o_raw[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            end = i
            break
    if end is None:
        return None
    try:
        lexical = unescape_nt(o_raw[1:end])
    except (ValueError, OverflowError):
        return None
    suffix = o_raw[end + 1:]
    if not suffix:
        return lexical, None, None
    if suffix.startswith("@") and re.fullmatch(r"@[A-Za-z]+(?:-[A-Za-z0-9]+)*", suffix):
        return lexical, suffix[1:].lower(), None
    if suffix.startswith("^^<") and suffix.endswith(">") and len(suffix) > 4:
        return lexical, None, suffix[3:-1]
    return None


def _valid_date_lexical(lexical: str, datatype: str) -> bool:
    match = _DATE_RE.fullmatch(lexical)
    if match is None:
        return False
    has_time = match.group("time") is not None
    if datatype == _XSD + "date" and has_time:
        return False
    if datatype == _XSD + "dateTime" and not has_time:
        return False
    year_text = match.group("year")
    if len(year_text.lstrip("+-")) > 18:
        return False
    year = int(year_text)
    month = int(match.group("month"))
    day = int(match.group("day"))
    if not 1 <= month <= 12:
        return False
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    month_days = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if not 1 <= day <= month_days[month - 1]:
        return False
    if has_time and (
        int(match.group("hour")) > 23
        or int(match.group("minute")) > 59
        or int(match.group("second")) > 59
    ):
        return False
    return True


def parse_literal_object(o_raw: str, spec: dict) -> dict[str, str] | None:
    """Parse one literal according to a versioned property profile.

    Property semantics live in schema data, not Python. This function implements only generic
    structural kinds: exact integer, bounded plain string, and ISO date/dateTime. Unsupported
    datatypes fail closed; no unit-bearing quantity is inferred from a unitless truthy value.
    """
    split = _split_nt_literal(o_raw)
    if split is None:
        return None
    lexical, language, datatype = split
    kind = str(spec.get("kind") or "")
    if kind == "integer":
        if language is not None:
            return None
        if datatype in (None, _XSD + "integer", _XSD + "nonNegativeInteger",
                        _XSD + "positiveInteger"):
            if _INTEGER_LEXICAL_RE.fullmatch(lexical) is None:
                return None
        elif datatype == _XSD + "decimal":
            if _DECIMAL_LEXICAL_RE.fullmatch(lexical) is None:
                return None
        else:
            return None
        from packages.reasoning_vm.quantity import parse_number
        value = parse_number(lexical)
        if value is None or value.denominator != 1:
            return None
        n = int(value)
        if datatype == _XSD + "nonNegativeInteger" and n < 0:
            return None
        if datatype == _XSD + "positiveInteger" and n <= 0:
            return None
        lower = spec.get("minimum")
        upper = spec.get("maximum")
        if lower is not None and (type(lower) is not int or n < lower):
            return None
        if upper is not None and (type(upper) is not int or n > upper):
            return None
        return {"value": str(n), "kind": kind, "datatype": datatype or "plain"}
    if kind == "plain_string":
        if language not in (None, "en") or datatype not in (None, _XSD + "string"):
            return None
        max_length = spec.get("max_length")
        if type(max_length) is not int or not 1 <= max_length <= 4096:
            return None
        value = lexical.strip()
        if not value or len(value) > max_length or HANGUL.search(value):
            return None
        if any(ord(ch) < 32 for ch in value):
            return None
        return {"value": value, "kind": kind,
                "datatype": datatype or ("lang:en" if language == "en" else "plain")}
    if kind == "date":
        if language is not None or datatype not in (_XSD + "date", _XSD + "dateTime"):
            return None
        if not _valid_date_lexical(lexical, datatype):
            return None
        return {"value": lexical, "kind": kind, "datatype": datatype}
    return None


def load_literal_schema(path: str | Path = _LITERAL_SCHEMA) -> tuple[dict[str, dict], str, dict]:
    """Load and validate the data-owned PID profile. Returns properties, SHA-256, raw document."""
    schema_path = Path(path)
    raw = schema_path.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if not isinstance(doc, dict) or set(doc) != {
        "schema_version", "profile", "quantity_semantics", "properties",
    }:
        raise ValueError("literal schema has missing or unknown top-level keys")
    if type(doc.get("schema_version")) is not int or doc["schema_version"] != 1:
        raise ValueError("literal schema must use integer schema_version 1")
    profile = doc.get("profile")
    if not isinstance(profile, str) or _PREDICATE_RE.fullmatch(profile) is None:
        raise ValueError("literal schema requires a nonempty machine-readable profile")
    if doc.get("quantity_semantics") != "unit-bearing quantities deferred":
        raise ValueError("literal schema must explicitly defer unit-bearing quantities")
    if not isinstance(doc.get("properties"), dict) or not doc["properties"]:
        raise ValueError("literal schema properties must be a nonempty object")
    props: dict[str, dict] = {}
    for pid, spec in doc["properties"].items():
        if not isinstance(pid, str) or _PID_RE.fullmatch(pid) is None or not isinstance(spec, dict):
            raise ValueError(f"invalid literal property entry: {pid!r}")
        if len(pid) > 11 or int(pid[1:]) > 0xFFFFFFFF:
            raise ValueError(f"literal property ID exceeds uint32 provenance format: {pid}")
        kind = spec.get("kind")
        allowed_keys = {
            "integer": {"predicate", "kind", "minimum", "maximum", "source"},
            "plain_string": {"predicate", "kind", "max_length", "source"},
            "date": {"predicate", "kind", "source"},
        }.get(kind)
        if allowed_keys is None:
            raise ValueError(f"unsupported literal kind for {pid}: {kind!r}")
        if set(spec) != allowed_keys:
            raise ValueError(f"missing or unknown keys for {pid}: {sorted(set(spec) ^ allowed_keys)}")
        predicate = str(spec.get("predicate") or "")
        if _PREDICATE_RE.fullmatch(predicate) is None or HANGUL.search(predicate):
            raise ValueError(f"invalid predicate for {pid}: {predicate!r}")
        if spec.get("source") != f"https://www.wikidata.org/wiki/Property:{pid}":
            raise ValueError(f"invalid official property source for {pid}")
        if kind == "integer":
            lower = spec["minimum"]
            upper = spec["maximum"]
            if type(lower) is not int or type(upper) is not int:
                raise ValueError(f"integer constraints for {pid} must be JSON integers")
            if lower > upper:
                raise ValueError(f"minimum exceeds maximum for {pid}")
        if kind == "plain_string":
            max_length = spec["max_length"]
            if type(max_length) is not int:
                raise ValueError(f"max_length for {pid} must be a JSON integer")
            if not 1 <= max_length <= 4096:
                raise ValueError(f"unsafe max_length for {pid}: {max_length}")
        props[pid] = dict(spec)
    return props, hashlib.sha256(raw).hexdigest(), doc


def _path_contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _paths_overlap(left: Path, right: Path) -> bool:
    return _path_contains(left, right) or _path_contains(right, left)


def guard_staging_target(staging: str | Path, *, literal_mode: bool) -> Path:
    """Refuse any target that could delete/overwrite shipped or the other staging lane."""
    target = Path(staging).resolve()
    shipped = _SHIPPED_ROOT.resolve()
    entity_stage = _ENTITY_STAGING_ROOT.resolve()
    literal_stage = _LITERAL_STAGING_ROOT.resolve()
    if target.parent == target or _path_contains(target, shipped) or _path_contains(shipped, target):
        raise ValueError(f"unsafe staging target overlaps shipped graph: {target}")
    if literal_mode and (
        _path_contains(target, entity_stage) or _path_contains(entity_stage, target)
    ):
        raise ValueError(f"literal staging target overlaps entity staging: {target}")
    if not literal_mode and (
        _path_contains(target, literal_stage) or _path_contains(literal_stage, target)
    ):
        raise ValueError(f"entity staging target overlaps literal staging: {target}")
    return target


def guard_label_db_target(dump: str | Path, label_db: str | Path, *,
                          extra_protected: tuple[str | Path, ...] = ()) -> Path:
    """Validate a destructive PASS-1 output before unlinking or creating anything."""
    target = Path(label_db).resolve()
    if target.parent == target or (target.exists() and target.is_dir()):
        raise ValueError(f"unsafe label DB target: {target}")
    protected = (
        Path(dump).resolve(),
        _SHIPPED_ROOT.resolve(),
        _ENTITY_STAGING_ROOT.resolve(),
        _LITERAL_STAGING_ROOT.resolve(),
        *(Path(path).resolve() for path in extra_protected),
    )
    for path in protected:
        if _paths_overlap(target, path):
            raise ValueError(f"unsafe label DB target overlaps protected path {path}: {target}")
    return target


def guard_ingest_paths(dump: str | Path, label_db: str | Path, staging: str | Path, *,
                       literal_mode: bool, schema_path: str | Path | None = None,
                       label_db_writable: bool = False) -> Path:
    """Preflight every source/output path before a staging delete or PASS-1 database rebuild."""
    target = guard_staging_target(staging, literal_mode=literal_mode)
    sources = [Path(dump).resolve(), Path(label_db).resolve()]
    if schema_path is not None:
        sources.append(Path(schema_path).resolve())
    for source in sources:
        if _paths_overlap(target, source):
            raise ValueError(f"staging target overlaps ingest input {source}: {target}")
    if label_db_writable:
        extra = (target,) if schema_path is None else (target, schema_path)
        guard_label_db_target(dump, label_db, extra_protected=extra)
    return target


def open_label_db_readonly(label_db: str | Path) -> sqlite3.Connection:
    path = Path(label_db).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"label DB not found: {path}")
    con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        con.execute("PRAGMA query_only=ON")
        columns = [row[1:3] for row in con.execute("PRAGMA table_info(l)")]
        if columns != [("k", "INTEGER"), ("v", "TEXT")]:
            raise ValueError("label DB must contain l(k INTEGER PRIMARY KEY, v TEXT)")
    except Exception:
        con.close()
        raise
    return con


def validate_dump_input(dump: str | Path) -> Path:
    path = Path(dump).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Wikidata dump not found: {path}")
    with path.open("rb") as fh:
        if fh.read(2) != b"\x1f\x8b":
            raise ValueError(f"Wikidata input is not gzip: {path}")
    return path


def file_identity(path: str | Path) -> dict[str, object]:
    resolved = Path(path).resolve()
    stat = resolved.stat()
    return {
        "resolved_path": str(resolved),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def label_db_binding(label_db: str | Path, dump: str | Path) -> dict[str, object]:
    identity = file_identity(label_db)
    con = open_label_db_readonly(label_db)
    try:
        rows = dict(con.execute(
            "SELECT k, v FROM meta WHERE k IN "
            "('dump_path', 'dump_size_bytes', 'dump_mtime_ns', 'scope')"
        )) if con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'"
        ).fetchone() else {}
    finally:
        con.close()
    current = file_identity(dump)
    identity_matches = (
        rows.get("dump_path") == current["resolved_path"]
        and rows.get("dump_size_bytes") == str(current["size_bytes"])
        and rows.get("dump_mtime_ns") == str(current["mtime_ns"])
    )
    if identity_matches and rows.get("scope") == "complete":
        status = "verified_dump_identity"
    elif identity_matches:
        status = "partial_dump_identity"
    else:
        status = "unbound_legacy"
    return {
        **identity,
        "binding_status": status,
        "recorded_scope": rows.get("scope"),
        "recorded_dump": rows or None,
    }


# --------------------------------------------------------------------------------------
# PASS 1 — English Q-id labels plus PID-preserving property catalog
# --------------------------------------------------------------------------------------
def build_label_db(dump: str | Path, label_db: str | Path, *, allow_truncated: bool = False,
                   max_lines: int | None = None, log_every: int = 5_000_000) -> dict:
    """Build Q labels and a PID-preserving property catalog in one dump scan.

    The original ``l`` table remains the exact Q-id -> English-label join
    index used by entity and literal PASS-2.  The separate ``pl``/``pa``/
    ``pt``/``pr`` tables retain property labels, aliases, exact Wikibase
    datatype IRIs, and entity revisions.  Those rows are source data for
    graph-conditioned Auto-binding; they do not map PIDs to hand-written
    predicates and they do not write the shipped graph.
    """
    label_db = guard_label_db_target(dump, label_db)
    dump_path = validate_dump_input(dump)
    label_db.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{label_db.name}.build-", suffix=".sqlite", dir=label_db.parent,
    )
    os.close(fd)
    temp_db = Path(temp_name)
    con = sqlite3.connect(str(temp_db))
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA cache_size=-262144")   # ~256 MB page cache
    con.execute("CREATE TABLE l(k INTEGER PRIMARY KEY, v TEXT)")
    con.execute("CREATE TABLE pl(k INTEGER PRIMARY KEY, v TEXT NOT NULL)")
    con.execute(
        "CREATE TABLE pa(k INTEGER NOT NULL, v TEXT NOT NULL, "
        "PRIMARY KEY(k, v))"
    )
    con.execute("CREATE TABLE pt(k INTEGER PRIMARY KEY, v TEXT NOT NULL)")
    con.execute("CREATE TABLE pr(k INTEGER PRIMARY KEY, v TEXT NOT NULL)")
    con.execute("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    seen = kept = 0
    t0 = time.time()
    batch: list[tuple[int, str]] = []
    property_labels: dict[int, str] = {}
    property_aliases: set[tuple[int, str]] = set()
    property_types: dict[int, str] = {}
    property_revisions: dict[int, str] = {}
    ins = con.executemany

    def bind_unique(
        rows: dict[int, str],
        pid: int,
        value: str,
        field: str,
    ) -> None:
        previous = rows.get(pid)
        if previous is not None and previous != value:
            raise ValueError(
                f"conflicting Wikidata property {field} for P{pid}"
            )
        rows[pid] = value

    for line in stream_nt_lines(dump, allow_truncated=allow_truncated, max_lines=max_lines):
        seen += 1
        # cheapest possible pre-filter before the full parse
        if (
            _LABEL_PRED not in line
            and _ALT_LABEL_PRED not in line
            and _PROPERTY_TYPE_PRED not in line
            and _SCHEMA_VERSION_PRED not in line
        ):
            if log_every and seen % log_every == 0:
                sys.stderr.write(f"[pass1] {seen:,} lines  kept={kept:,}  "
                                 f"{time.time()-t0:.0f}s\n")
            continue
        t = parse_triple(line)
        if t is None:
            continue
        s, p, o = t
        qid = qid_int(s)
        if p == _LABEL_PRED and qid is not None:
            label = parse_en_label(o)
            if label is None:
                continue
            batch.append((qid, label))
            kept += 1
            if len(batch) >= 100_000:
                ins("INSERT OR IGNORE INTO l(k, v) VALUES(?, ?)", batch)
                batch.clear()
            continue

        pid = pid_int(s)
        if pid is not None and p == _LABEL_PRED:
            label = parse_en_label(o)
            if label is not None:
                bind_unique(property_labels, pid, label, "label")
        elif pid is not None and p == _ALT_LABEL_PRED:
            alias = parse_en_label(o)
            if alias is not None:
                property_aliases.add((pid, alias))
        elif pid is not None and p == _PROPERTY_TYPE_PRED:
            datatype = property_type_iri(o)
            if datatype is not None:
                bind_unique(property_types, pid, datatype, "datatype")
        elif p == _SCHEMA_VERSION_PRED:
            data_pid = property_data_pid_int(s)
            revision = property_revision(o)
            if data_pid is not None and revision is not None:
                bind_unique(
                    property_revisions,
                    data_pid,
                    revision,
                    "revision",
                )
        if log_every and seen % log_every == 0:
            sys.stderr.write(f"[pass1] {seen:,} lines  kept={kept:,}  {time.time()-t0:.0f}s\n")
    if batch:
        ins("INSERT OR IGNORE INTO l(k, v) VALUES(?, ?)", batch)
    ins(
        "INSERT INTO pl(k, v) VALUES(?, ?)",
        sorted(property_labels.items()),
    )
    ins(
        "INSERT INTO pa(k, v) VALUES(?, ?)",
        sorted(property_aliases),
    )
    ins(
        "INSERT INTO pt(k, v) VALUES(?, ?)",
        sorted(property_types.items()),
    )
    ins(
        "INSERT INTO pr(k, v) VALUES(?, ?)",
        sorted(property_revisions.items()),
    )
    dump_id = file_identity(dump_path)
    property_label_count = con.execute("SELECT COUNT(*) FROM pl").fetchone()[0]
    property_alias_count = con.execute("SELECT COUNT(*) FROM pa").fetchone()[0]
    property_type_count = con.execute("SELECT COUNT(*) FROM pt").fetchone()[0]
    property_revision_count = con.execute("SELECT COUNT(*) FROM pr").fetchone()[0]
    con.executemany("INSERT INTO meta(k, v) VALUES(?, ?)", [
        ("dump_path", str(dump_id["resolved_path"])),
        ("dump_size_bytes", str(dump_id["size_bytes"])),
        ("dump_mtime_ns", str(dump_id["mtime_ns"])),
        ("scope", "partial" if allow_truncated or max_lines is not None else "complete"),
        ("property_catalog_profile", "wikidata_property_catalog_v1"),
        ("property_label_count", str(property_label_count)),
        ("property_alias_count", str(property_alias_count)),
        ("property_type_count", str(property_type_count)),
        ("property_revision_count", str(property_revision_count)),
    ])
    con.commit()
    n_labels = con.execute("SELECT COUNT(*) FROM l").fetchone()[0]
    con.close()
    os.replace(temp_db, label_db)
    return {
        "lines_scanned": seen,
        "en_labels_written": kept,
        "distinct_labels": n_labels,
        "property_labels": property_label_count,
        "property_aliases": property_alias_count,
        "property_types": property_type_count,
        "property_revisions": property_revision_count,
        "property_catalog_profile": "wikidata_property_catalog_v1",
        "label_db_bytes": label_db.stat().st_size,
        "elapsed_s": round(time.time() - t0, 1),
    }


# --------------------------------------------------------------------------------------
# PASS 2 — join curated statements against the label store, stage the triples
# --------------------------------------------------------------------------------------
class _LRU(OrderedDict):
    """Tiny LRU for object-label lookups (class/occupation/country Q-ids repeat heavily)."""
    def __init__(self, cap: int):
        super().__init__()
        self.cap = cap

    def get_put(self, key, factory):
        if key in self:
            self.move_to_end(key)
            return self[key]
        val = factory(key)
        self[key] = val
        if len(self) > self.cap:
            self.popitem(last=False)
        return val


def join_statements(dump: str | Path, label_db: str | Path, staging: str | Path, *,
                    allow_truncated: bool = False, max_lines: int | None = None,
                    dict_backend: str = "ram", trace_n: int = 0,
                    log_every: int = 5_000_000, stage_pass=None) -> dict:
    """Stream the dump, keep curated entity-valued P-statements, join both endpoints against the
    label store, and stage (subject_label, relation, object_label) into a SEPARATE TripleStore.

    ``stage_pass`` (optional, default None): a ``truth_maintenance.FirewallStagePass``. When
    supplied (only under --firewall / ATANOR_MEMBRANE_LIVE), each staged edge is ALSO observed by
    the contamination-firewall membrane (provenance/justification/nogood metadata). It is
    observe-only: what gets written to the staging store is unchanged."""
    from packages.graph_scale.triple_store import TripleStore

    staging = guard_ingest_paths(
        dump, label_db, staging, literal_mode=False, label_db_writable=False,
    )
    validate_dump_input(dump)
    con = open_label_db_readonly(label_db)
    if staging.exists():
        con.close()
        raise FileExistsError(f"entity build target already exists: {staging}")
    con.execute("PRAGMA cache_size=-262144")
    cur = con.cursor()

    def lookup(k: int):
        r = cur.execute("SELECT v FROM l WHERE k=?", (k,)).fetchone()
        return r[0] if r else None

    obj_cache = _LRU(1_000_000)
    cur_subj_k = -1
    cur_subj_label = None

    store = TripleStore(staging, dict_backend=dict_backend)
    src_id = store.intern_source("wikidata-truthy",
                                 "https://www.wikidata.org/w/index.php?search={s}")

    per_rel_added: Counter[str] = Counter()
    per_rel_dup: Counter[str] = Counter()
    seen = kept_stmts = 0
    d_no_subj_label = d_no_obj_label = d_noise = d_self = d_long = d_hangul = 0
    trace: list[dict] = []
    t0 = time.time()

    for line in stream_nt_lines(dump, allow_truncated=allow_truncated, max_lines=max_lines):
        seen += 1
        if log_every and seen % log_every == 0:
            sys.stderr.write(f"[pass2] {seen:,} lines  staged={sum(per_rel_added.values()):,}  "
                             f"{time.time()-t0:.0f}s\n")
        if _DIRECT not in line:
            continue
        t = parse_triple(line)
        if t is None:
            continue
        s, p, o = t
        # predicate must be prop/direct/P... (NOT prop/direct-normalized, which is external-ID noise)
        pid = direct_property_id(p)
        if pid is None:
            continue
        rel = RELMAP.get(pid)
        if rel is None:
            continue
        ok = qid_int(s)
        oko = qid_int(o)
        if ok is None or oko is None:         # object must be an entity (Q-id); drops all literals
            continue
        kept_stmts += 1
        # --- subject label (one lookup per entity: the dump is grouped by subject) ---
        if ok != cur_subj_k:
            cur_subj_k = ok
            cur_subj_label = lookup(ok)
        s_lab = cur_subj_label
        if s_lab is None:
            d_no_subj_label += 1
            continue
        # --- object label (LRU: class/country/occupation Q-ids repeat heavily) ---
        o_lab = obj_cache.get_put(oko, lookup)
        if o_lab is None:
            d_no_obj_label += 1
            continue
        # --- noise / hygiene gates ---
        if rel == "is_a" and (oko in NOISE_OBJECT_QIDS or NOISE_LABEL_RE.search(o_lab)):
            d_noise += 1
            continue
        if s_lab == o_lab:
            d_self += 1
            continue
        if len(s_lab) > MAX_SURFACE or len(o_lab) > MAX_SURFACE:
            d_long += 1
            continue
        if HANGUL.search(s_lab) or HANGUL.search(o_lab):
            d_hangul += 1
            continue
        # --- stage it ---
        if store.add(s_lab, rel, o_lab, source=src_id):
            per_rel_added[rel] += 1
            if stage_pass is not None:                      # firewall membrane (observe-only)
                stage_pass.observe(s_lab, rel, o_lab)
            if len(trace) < trace_n:
                trace.append({"dump_line": line.strip()[:200],
                              "subject_qid": f"Q{ok}", "object_qid": f"Q{oko}",
                              "staged_triple": [s_lab, rel, o_lab]})
        else:
            per_rel_dup[rel] += 1

    store.flush()
    store.terms.flush()
    store.rebuild_index()
    con.close()

    stats = {
        "lines_scanned": seen,
        "curated_entity_statements": kept_stmts,
        "staged_edges": int(sum(per_rel_added.values())),
        "added_per_relation": dict(per_rel_added.most_common()),
        "duplicates_per_relation": dict(per_rel_dup),
        "dropped": {
            "no_subject_label_in_slice": d_no_subj_label,
            "no_object_label_in_slice": d_no_obj_label,
            "is_a_noise_class": d_noise,
            "self_loop": d_self,
            "over_max_surface": d_long,
            "hangul_defensive": d_hangul,
        },
        "distinct_subjects": None,   # filled below
        "total_store_edges": len(store),
        "elapsed_s": round(time.time() - t0, 1),
    }
    if trace_n:
        (staging / "PROVENANCE_TRACE.jsonl").write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in trace) + "\n",
            encoding="utf-8")
    return stats, store


def join_literal_statements(dump: str | Path, label_db: str | Path, staging: str | Path,
                            properties: dict[str, dict], *,
                            allow_truncated: bool = False, max_lines: int | None = None,
                            dict_backend: str = "sharded", trace_n: int = 0,
                            log_every: int = 5_000_000, stage_pass=None,
                            replace: bool = False) -> tuple[dict, object]:
    """Stage profiled literal-valued direct statements into a separate TripleStore.

    This low-level builder requires a new directory. The driver performs validated transactional
    replacement after the new stage and its manifest are complete.
    """
    from packages.graph_scale.triple_store import TripleStore

    staging = guard_ingest_paths(
        dump, label_db, staging, literal_mode=True, label_db_writable=False,
    )
    validate_dump_input(dump)
    con = open_label_db_readonly(label_db)
    if staging.exists():
        con.close()
        raise FileExistsError(f"literal build target already exists: {staging}")
    con.execute("PRAGMA cache_size=-262144")
    cur = con.cursor()

    def lookup(k: int):
        row = cur.execute("SELECT v FROM l WHERE k=?", (k,)).fetchone()
        return row[0] if row else None

    store = TripleStore(staging, dict_backend=dict_backend)
    source_ids = {
        pid: store.intern_source("wikidata-truthy-literal", str(spec["source"]))
        for pid, spec in properties.items()
    }
    import struct
    qid_pid_fh = (staging / "qid_pid.col").open("wb")
    per_pid_seen: Counter[str] = Counter()
    per_pid_added: Counter[str] = Counter()
    per_relation_added: Counter[str] = Counter()
    per_datatype_added: Counter[str] = Counter()
    duplicates: Counter[str] = Counter()
    dropped: Counter[str] = Counter()
    trace: list[dict] = []
    seen = 0
    cur_subj_k = -1
    cur_subj_label = None
    t0 = time.time()

    for line in stream_nt_lines(dump, allow_truncated=allow_truncated, max_lines=max_lines):
        seen += 1
        if log_every and seen % log_every == 0:
            sys.stderr.write(
                f"[literal-pass] {seen:,} lines  staged={sum(per_pid_added.values()):,}  "
                f"{time.time()-t0:.0f}s\n"
            )
        if _DIRECT not in line:
            continue
        triple = parse_triple(line)
        if triple is None:
            continue
        s, p, o = triple
        pid = direct_property_id(p)
        if pid is None:
            continue
        spec = properties.get(pid)
        if spec is None:
            continue
        per_pid_seen[pid] += 1
        subject_qid = qid_int(s)
        if subject_qid is None:
            dropped["subject_not_qid"] += 1
            continue
        parsed = parse_literal_object(o, spec)
        if parsed is None:
            dropped["literal_parse_or_constraint"] += 1
            continue
        if subject_qid != cur_subj_k:
            cur_subj_k = subject_qid
            cur_subj_label = lookup(subject_qid)
        subject = cur_subj_label
        if subject is None:
            dropped["no_subject_label_in_slice"] += 1
            continue
        value = parsed["value"]
        predicate = str(spec["predicate"])
        if len(subject) > MAX_SURFACE:
            dropped["subject_over_max_surface"] += 1
            continue
        if HANGUL.search(subject) or HANGUL.search(value):
            dropped["hangul_defensive"] += 1
            continue
        if subject == value:
            dropped["self_loop"] += 1
            continue
        if store.add(subject, predicate, value, source=source_ids[pid]):
            per_pid_added[pid] += 1
            per_relation_added[predicate] += 1
            per_datatype_added[parsed["datatype"]] += 1
            qid_pid_fh.write(struct.pack("<QI", subject_qid, int(pid[1:])))
            if stage_pass is not None:
                stage_pass.observe(subject, predicate, value)
            if len(trace) < trace_n:
                trace.append({
                    "dump_line": line.strip()[:500],
                    "subject_qid": f"Q{subject_qid}",
                    "property_pid": pid,
                    "literal_kind": parsed["kind"],
                    "literal_datatype": parsed["datatype"],
                    "staged_triple": [subject, predicate, value],
                })
        else:
            duplicates[pid] += 1

    store.flush()
    store.terms.flush()
    store.rebuild_index()
    qid_pid_fh.flush()
    qid_pid_fh.close()
    con.close()
    if trace_n:
        (staging / "PROVENANCE_TRACE.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in trace) + "\n",
            encoding="utf-8",
        )
    stats = {
        "lines_scanned": seen,
        "profiled_statements": int(sum(per_pid_seen.values())),
        "staged_edges": int(sum(per_pid_added.values())),
        "seen_per_property": dict(per_pid_seen),
        "added_per_property": dict(per_pid_added),
        "added_per_relation": dict(per_relation_added),
        "added_per_datatype": dict(per_datatype_added),
        "duplicates_per_property": dict(duplicates),
        "dropped": dict(dropped),
        "distinct_subjects": None,
        "total_store_edges": len(store),
        "qid_pid_sidecar": {
            "path": "qid_pid.col",
            "record_format": "little-endian uint64 QID number + uint32 PID number",
            "record_bytes": 12,
            "records": int(sum(per_pid_added.values())),
        },
        "elapsed_s": round(time.time() - t0, 1),
    }
    return stats, store


def _count_distinct_subjects(store) -> int:
    import numpy as np
    cols = store.open_columns()
    s = cols["s"]
    return int(len(np.unique(s))) if len(s) else 0


def _validate_owned_stage(target: Path, *, literal_mode: bool) -> dict:
    markers = (
        (_LITERAL_MANIFEST, _LITERAL_PARTIAL_MANIFEST)
        if literal_mode else (_ENTITY_MANIFEST,)
    )
    for marker in markers:
        path = target / marker
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict):
            continue
        if literal_mode and doc.get("mode") == "wikidata-truthy-literal-only" \
                and doc.get("provenance") == "wikidata-truthy-literal":
            return doc
        if not literal_mode and doc.get("provenance") == "wikidata-truthy" \
                and isinstance(doc.get("relation_map"), dict):
            return doc
    raise ValueError(f"refusing to replace an unowned or malformed staging directory: {target}")


def _begin_stage_build(target: Path, *, literal_mode: bool, replace: bool) -> tuple[Path, Path]:
    if target.exists():
        if not replace:
            raise FileExistsError(f"staging already exists (explicit replace required): {target}")
        _validate_owned_stage(target, literal_mode=literal_mode)
    target.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    wrapper = Path(tempfile.mkdtemp(prefix=f".{target.name}.build-", dir=target.parent))
    return wrapper / "stage", wrapper


def _close_stage_store(store) -> None:
    terms = getattr(store, "terms", None)
    close = getattr(terms, "close", None)
    if callable(close):
        close()


def _install_completed_stage(build: Path, target: Path, wrapper: Path, *,
                             literal_mode: bool) -> str | None:
    """Install a fully built/marked sibling stage; roll back if the rename fails."""
    _validate_owned_stage(build, literal_mode=literal_mode)
    backup = wrapper / "previous"
    if target.exists():
        target.rename(backup)
    try:
        build.rename(target)
    except Exception:
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise
    retained = None
    try:
        import shutil
        shutil.rmtree(wrapper)
    except OSError:
        retained = str(wrapper)
    return retained


# --------------------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------------------
def run(dump, label_db, staging, *, allow_truncated=False, max_lines=None, do_pass1=True,
        do_pass2=True, dict_backend="ram", trace_n=0, stage_pass=None,
        replace=False) -> dict:
    target = guard_ingest_paths(
        dump, label_db, staging, literal_mode=False, label_db_writable=do_pass1,
    )
    partial = bool(allow_truncated or max_lines is not None)
    report = {"dump": str(dump), "label_db": str(label_db), "staging": str(staging),
              "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "allow_truncated": bool(allow_truncated), "max_lines": max_lines,
              "completion_state": "partial" if partial else "complete",
              "relation_map": RELMAP,
              "curated_property_count": len(set(RELMAP)),
              "distinct_target_relations": sorted(set(RELMAP.values()))}
    if do_pass1:
        report["pass1_labels"] = build_label_db(
            dump, label_db, allow_truncated=allow_truncated, max_lines=max_lines)
    if do_pass2:
        build, wrapper = _begin_stage_build(
            target, literal_mode=False, replace=replace,
        )
        try:
            stats, store = join_statements(
                dump, label_db, build, allow_truncated=allow_truncated, max_lines=max_lines,
                dict_backend=dict_backend, trace_n=trace_n, stage_pass=stage_pass)
            stats["distinct_subjects"] = _count_distinct_subjects(store)
            report["pass2_join"] = stats
            if stage_pass is not None:                      # firewall membrane summary (default off)
                report["firewall_membrane"] = stage_pass.manifest()
            manifest = {
                "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "dump": str(Path(dump).resolve()),
                "dump_identity": file_identity(dump),
                "label_db": label_db_binding(label_db, dump),
                "provenance": "wikidata-truthy",
                "completion_state": "partial" if partial else "complete",
                "allow_truncated": bool(allow_truncated),
                "max_lines": max_lines,
                "english_only": "label store holds only rdfs:label@en; both endpoints English by construction",
                "no_fabrication": "every edge = one truthy statement line joined to two @en label rows",
                "gates": {"object_must_be_entity_Qid": True, "max_surface_len": MAX_SURFACE,
                          "drop_self_loops": True, "is_a_noise_stoplist": sorted(NOISE_OBJECT_QIDS),
                          "hangul_defensive_reject": True},
                "relation_map": RELMAP,
                "shipped_store_untouched": "transactional staging build only",
                **stats,
            }
            (build / _ENTITY_MANIFEST).write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            _close_stage_store(store)
            del store
            retained = _install_completed_stage(
                build, target, wrapper, literal_mode=False,
            )
            if retained:
                report["retained_backup"] = retained
        except Exception:
            if wrapper.exists() and not (wrapper / "previous").exists():
                import shutil
                shutil.rmtree(wrapper, ignore_errors=True)
            raise
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return report


def run_literal_ingest(dump, label_db, staging, schema_path=_LITERAL_SCHEMA, *,
                       allow_truncated=False, max_lines=None, build_labels=False,
                       dict_backend="sharded", trace_n=0, stage_pass=None,
                       replace=False) -> dict:
    """Run the independent Wikidata literal lane. Output remains staging-only."""
    target = guard_ingest_paths(
        dump, label_db, staging, literal_mode=True, schema_path=schema_path,
        label_db_writable=build_labels,
    )
    properties, schema_hash, schema_doc = load_literal_schema(schema_path)
    partial = bool(allow_truncated or max_lines is not None)
    report = {
        "dump": str(dump),
        "label_db": str(label_db),
        "staging": str(staging),
        "mode": "literal-only",
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "schema_path": str(schema_path),
        "schema_sha256": schema_hash,
        "schema_profile": schema_doc.get("profile"),
        "allow_truncated": bool(allow_truncated),
        "max_lines": max_lines,
        "completion_state": "partial" if partial else "complete",
    }
    if build_labels:
        report["pass1_labels"] = build_label_db(
            dump, label_db, allow_truncated=allow_truncated, max_lines=max_lines,
        )
    dump_before = file_identity(dump)
    label_db_before = file_identity(label_db)
    binding = label_db_binding(label_db, dump)
    build, wrapper = _begin_stage_build(
        target, literal_mode=True, replace=replace,
    )
    try:
        stats, store = join_literal_statements(
            dump, label_db, build, properties,
            allow_truncated=allow_truncated, max_lines=max_lines,
            dict_backend=dict_backend, trace_n=trace_n, stage_pass=stage_pass,
        )
        dump_after = file_identity(dump)
        label_db_after = file_identity(label_db)
        if dump_after != dump_before or label_db_after != label_db_before:
            _close_stage_store(store)
            del store
            raise RuntimeError("Wikidata dump or label DB changed during literal staging scan")
        binding = label_db_binding(label_db, dump)
        stats["distinct_subjects"] = _count_distinct_subjects(store)
        report["literal_pass"] = stats
        if stage_pass is not None:
            report["firewall_membrane"] = stage_pass.manifest()
        promotion_eligible = not partial and binding["binding_status"] == "verified_dump_identity"
        manifest = {
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": "wikidata-truthy-literal-only",
            "dump": str(Path(dump).resolve()),
            "dump_identity": dump_after,
            "label_db": binding,
            "provenance": "wikidata-truthy-literal",
            "completion_state": "partial" if partial else "complete",
            "promotion_eligible": promotion_eligible,
            "allow_truncated": bool(allow_truncated),
            "max_lines": max_lines,
            "schema_profile": schema_doc.get("profile"),
            "schema_sha256": schema_hash,
            "property_profile": properties,
            "language_scope": "English subject labels; schema-profiled language-neutral values; "
                              "non-English tags and Hangul denied",
            "evidence_binding": "each staged row retains aligned QID/PID provenance",
            "gates": {
                "profile_default_deny": True,
                "generic_literal_kinds": ["integer", "plain_string", "date"],
                "unit_bearing_quantities_deferred": True,
                "drop_self_loops": True,
                "hangul_defensive_reject": True,
            },
            "entity_staging_untouched": str(_ENTITY_STAGING_ROOT),
            "shipped_store_untouched": str(_SHIPPED_ROOT),
            **stats,
        }
        marker = _LITERAL_PARTIAL_MANIFEST if partial else _LITERAL_MANIFEST
        (build / marker).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        _close_stage_store(store)
        del store
        if file_identity(dump) != dump_after or file_identity(label_db) != label_db_after:
            raise RuntimeError("Wikidata dump or label DB changed before staging installation")
        retained = _install_completed_stage(
            build, target, wrapper, literal_mode=True,
        )
        if retained:
            report["retained_backup"] = retained
    except Exception:
        if wrapper.exists() and not (wrapper / "previous").exists():
            import shutil
            shutil.rmtree(wrapper, ignore_errors=True)
        raise
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump", default="D:/wikidata/latest-truthy.nt.gz")
    ap.add_argument("--label-db", default="D:/wikidata/wd_labels.sqlite")
    ap.add_argument("--staging", default=str(REPO / "data" / "graph_scale" / "staging_b1_wikidata"))
    ap.add_argument("--allow-truncated", action="store_true",
                    help="tolerate a torn gzip tail (range-request SAMPLE)")
    ap.add_argument("--max-lines", type=int, default=None, help="cap lines/pass (dev)")
    ap.add_argument("--pass", dest="which", choices=["1", "2", "all", "literal"], default="all")
    ap.add_argument("--dict-backend", choices=["ram", "sharded"], default="ram",
                    help="staging vocab backend; 'sharded' for the full 66 GB run")
    ap.add_argument("--trace", type=int, default=0, help="write first N join traces (audit)")
    ap.add_argument("--literal-schema", default=str(_LITERAL_SCHEMA),
                    help="versioned PID/type profile for the literal-only pass")
    ap.add_argument("--literal-staging", default=str(_LITERAL_STAGING_ROOT),
                    help="separate output store for --pass literal")
    ap.add_argument("--replace-entity-staging", action="store_true",
                    help="transactionally replace an owned entity stage; default refuses")
    ap.add_argument("--replace-literal-staging", action="store_true",
                    help="transactionally replace an owned literal stage; default refuses")
    ap.add_argument("--firewall", action="store_true",
                    help="route staged edges through the contamination-firewall membrane "
                         "(observe-only provenance/nogood metadata; also honors "
                         "ATANOR_MEMBRANE_LIVE). Default off -> staging behaves exactly as today.")
    ap.add_argument("--firewall-out", default=None,
                    help="where to write the firewall membrane manifest (default "
                         "runtime/firewall/wikidata_truthy_firewall_manifest.json; never data/graph_scale)")
    a = ap.parse_args(argv)

    # firewall membrane: opt-in (--firewall OR ATANOR_MEMBRANE_LIVE). Flag OFF -> no import,
    # no-op, byte-identical to today (the membrane module is never even loaded).
    fp = None
    if bool(a.firewall) or os.environ.get("ATANOR_MEMBRANE_LIVE", "").strip().lower() in _MEMBRANE_TRUTHY:
        from packages.truth_maintenance.live_membrane import (
            FirewallStagePass, default_firewall_out, write_manifest)
        provenance = "wikidata-truthy-literal" if a.which == "literal" else "wikidata-truthy"
        fp = FirewallStagePass(provenance=provenance)

    if a.which == "literal":
        rep = run_literal_ingest(
            a.dump, a.label_db, a.literal_staging, a.literal_schema,
            allow_truncated=a.allow_truncated, max_lines=a.max_lines,
            build_labels=False, dict_backend=a.dict_backend, trace_n=a.trace,
            stage_pass=fp, replace=a.replace_literal_staging,
        )
    else:
        rep = run(a.dump, a.label_db, a.staging, allow_truncated=a.allow_truncated,
                  max_lines=a.max_lines, do_pass1=a.which in ("1", "all"),
                  do_pass2=a.which in ("2", "all"), dict_backend=a.dict_backend, trace_n=a.trace,
                  stage_pass=fp, replace=a.replace_entity_staging)
    if fp is not None:
        lane = "wikidata_truthy_literal" if a.which == "literal" else "wikidata_truthy"
        out = write_manifest(fp, a.firewall_out or default_firewall_out(lane))
        rep["firewall_manifest_path"] = str(out)
        print(f"[firewall] membrane manifest -> {out}  "
              f"(observed={fp.observed} passed={fp.passed} quarantined={len(fp.quarantined)})",
              file=sys.stderr)
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
