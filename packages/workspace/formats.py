# -*- coding: utf-8 -*-
"""What a file IS, checked against its bytes — because the extension is a claim, not a fact.

    from packages.workspace.formats import classify, policy
    f = classify("downloads/paper.pdf")       # reads the magic bytes, not just the name
    if f.mismatch: ...                        # the name says one thing and the bytes another
    policy(f.family)["untrusted_parser"]      # does opening this run a risky parser?

TWO AXES, NOT ONE. A room says WHERE a file lives and what custody it is under (lifecycle). A format
says WHAT IT IS and which machinery opens it. They are independent: a PDF can be `archive` (downloaded
from the web) or `ledger` (a signed report we must never edit); an image can be `archive` (a Commons
photo) or `derived` (a chart we rendered). Sorting by one and pretending it settles the other is how a
crawler's untrusted download ends up next to a seal.

WHAT IS ACTUALLY IN THE TREE TODAY, measured 2026-07-31 over 11,056 files:

    .json/.jsonl   8,918 files    7.0 GB     records
    .db/.col/.npy  binary stores            45.8 GB
    .tsv/.bz2/.gz  corpora                  52.4 GB
    .txt/.md         644 files    0.5 GB
    images 0   video 0   pdf 0   hwp 0

So the media families below are ANTICIPATORY and are labelled as such. They are declared now because
the paths that will produce them already exist -- the Commons image harvest, a crawler that meets a
non-HTML response, and later video -- and a format arriving with no policy is how it gets handled by
whatever code happens to catch it.

WHY THIS IS A SECURITY SURFACE AND NOT A FILING QUESTION. The format decides the PARSER, and parsers
are where untrusted bytes become dangerous. Today's system fetches arbitrary bytes from arbitrary hosts
through a crawler, a fetcher and peer contributions. Image decoders, PDF readers and office-document
parsers are the most exploited class of software there is, and none of them is a place to arrive by
accident. So every family carries `untrusted_parser`, and the classifier reads MAGIC BYTES rather than
trusting the name: a `.txt` that begins `%PDF` is not a text file, and the mismatch is the interesting
part, not an inconvenience.

CRYPTO IS A FAMILY WITH ONE EXTRA RULE. Key material is never logged, never summarised into an error
message, and belongs in the vault -- which the room API refuses to hand out a path into. `classify`
marks it so a caller that is about to print a file's head can be stopped by a check rather than by
someone remembering.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: family -> how ATANOR must treat anything of this kind
FAMILY_POLICY: dict[str, dict] = {
    "text":     {"handler": "property_extraction / realizer", "may_log": True,
                 "untrusted_parser": False, "size_class": "small"},
    "data":     {"handler": "json / numpy / triple store", "may_log": True,
                 "untrusted_parser": False, "size_class": "large"},
    "corpus":   {"handler": "streaming reader, never fully loaded", "may_log": False,
                 "untrusted_parser": False, "size_class": "huge"},
    "image":    {"handler": "perception encoder", "may_log": False,
                 "untrusted_parser": True, "size_class": "medium",
                 "note": "ANTICIPATORY: none in the tree yet; arrives with the Commons harvest"},
    "video":    {"handler": "frame extraction, then perception", "may_log": False,
                 "untrusted_parser": True, "size_class": "huge",
                 "note": "ANTICIPATORY: no reader wired; understanding is out of reach today"},
    "document": {"handler": "text extraction first, then the text path", "may_log": False,
                 "untrusted_parser": True, "size_class": "medium",
                 "note": "ANTICIPATORY: pdf/hwp/docx readers are a known exploit surface"},
    "crypto":   {"handler": "packages.vault only", "may_log": False,
                 "untrusted_parser": False, "size_class": "tiny",
                 "note": "never logged, never summarised into an error, belongs in the vault"},
    "unknown":  {"handler": "none -- refuse until identified", "may_log": False,
                 "untrusted_parser": True, "size_class": "unknown"},
}

_BY_EXT: dict[str, str] = {
    ".txt": "text", ".md": "text", ".rst": "text", ".log": "text",
    ".json": "data", ".jsonl": "data", ".ndjson": "data", ".csv": "data", ".tsv": "data",
    ".npy": "data", ".npz": "data", ".pt": "data", ".parquet": "data", ".db": "data",
    ".col": "data", ".sqlite": "data", ".sqlite3": "data", ".bin": "data",
    ".gz": "corpus", ".bz2": "corpus", ".xz": "corpus", ".zip": "corpus", ".7z": "corpus",
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".gif": "image", ".webp": "image",
    ".bmp": "image", ".tif": "image", ".tiff": "image", ".svg": "image",
    ".mp4": "video", ".webm": "video", ".mkv": "video", ".mov": "video", ".avi": "video",
    ".pdf": "document", ".hwp": "document", ".hwpx": "document", ".doc": "document",
    ".docx": "document", ".ppt": "document", ".pptx": "document", ".xls": "document",
    ".xlsx": "document", ".odt": "document", ".rtf": "document", ".epub": "document",
    ".pem": "crypto", ".key": "crypto", ".pub": "crypto", ".p12": "crypto", ".pfx": "crypto",
    ".asc": "crypto", ".gpg": "crypto", ".jwk": "crypto", ".sig": "crypto",
}

#: (magic bytes, offset, family, label). Order matters: longer/more specific first.
_MAGIC: tuple[tuple[bytes, int, str, str], ...] = (
    (b"%PDF-", 0, "document", "pdf"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 0, "document", "ole2 (hwp/doc/xls)"),
    (b"PK\x03\x04", 0, "corpus", "zip container (also docx/xlsx/hwpx/epub)"),
    (b"\x89PNG\r\n\x1a\n", 0, "image", "png"),
    (b"\xff\xd8\xff", 0, "image", "jpeg"),
    (b"GIF87a", 0, "image", "gif"),
    (b"GIF89a", 0, "image", "gif"),
    (b"RIFF", 0, "image", "riff (webp/avi -- check subtype)"),
    (b"ftyp", 4, "video", "mp4/mov"),
    (b"\x1a\x45\xdf\xa3", 0, "video", "matroska/webm"),
    (b"\x1f\x8b", 0, "corpus", "gzip"),
    (b"BZh", 0, "corpus", "bzip2"),
    (b"\xfd7zXZ", 0, "corpus", "xz"),
    (b"\x93NUMPY", 0, "data", "numpy"),
    (b"SQLite format 3", 0, "data", "sqlite"),
    (b"-----BEGIN ", 0, "crypto", "pem armour"),
)


@dataclass
class FormatVerdict:
    path: str
    family: str
    label: str
    by_extension: str
    by_magic: str | None
    mismatch: bool
    size: int

    def policy(self) -> dict:
        return dict(FAMILY_POLICY[self.family])

    def may_log_content(self) -> bool:
        return bool(FAMILY_POLICY[self.family]["may_log"])


def _magic_family(head: bytes) -> tuple[str | None, str]:
    for sig, off, family, label in _MAGIC:
        if head[off:off + len(sig)] == sig:
            return family, label
    # a pragmatic text test: decodable as utf-8 and free of NULs
    if head and b"\x00" not in head[:512]:
        try:
            head[:512].decode("utf-8")
            return "text", "utf-8 text"
        except UnicodeDecodeError:
            pass
    return None, ""


def classify(path: str | Path, *, read_bytes: int = 64) -> FormatVerdict:
    """What this file is, by BYTES first and name second.

    `mismatch` is the field worth reading. An extension is a claim by whoever named the file, and for
    anything a crawler saved that whoever is a stranger. A `.txt` beginning `%PDF` is a document being
    handed to a text path, which is exactly how the wrong parser gets called."""
    p = Path(path)
    ext = p.suffix.lower()
    by_ext = _BY_EXT.get(ext, "unknown")
    head = b""
    size = 0
    try:
        size = p.stat().st_size
        with p.open("rb") as fh:
            head = fh.read(max(read_bytes, 64))
    except OSError:
        pass
    by_magic, label = _magic_family(head)
    family = by_magic or by_ext
    # a zip container is ambiguous by magic alone; the extension disambiguates docx/hwpx from a corpus
    if by_magic == "corpus" and by_ext == "document":
        family, label = "document", "zip-container document"
    mismatch = bool(by_magic and by_ext != "unknown" and by_magic != by_ext and family != by_ext)
    return FormatVerdict(str(p), family, label or ext.lstrip(".") or "?", by_ext, by_magic,
                         mismatch, size)


def policy(family: str) -> dict:
    return dict(FAMILY_POLICY.get(family, FAMILY_POLICY["unknown"]))


def screen_incoming(path: str | Path) -> dict:
    """The check a crawler or a peer intake should run before anything opens the file.

    Returns what to do, not a boolean, because 'refuse' and 'open with the risky parser deliberately'
    are different decisions and the caller owns them."""
    v = classify(path)
    pol = v.policy()
    reasons = []
    if v.mismatch:
        reasons.append(f"extension says {v.by_extension}, bytes say {v.by_magic}")
    if v.family == "unknown":
        reasons.append("unidentified: no magic match and no known extension")
    if v.family == "crypto":
        reasons.append("key material must not arrive through an ingestion path")
    return {"path": str(path), "family": v.family, "label": v.label, "size": v.size,
            "mismatch": v.mismatch,
            "untrusted_parser": pol["untrusted_parser"],
            "may_log_content": pol["may_log"],
            "handler": pol["handler"],
            "refuse": bool(v.family in ("unknown", "crypto") or v.mismatch),
            "reasons": reasons}
