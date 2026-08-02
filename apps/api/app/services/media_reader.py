"""Read non-text media into text so ATANOR can ground on it like any other source.

ATANOR is a text-graph engine; the way to "read" a video or image is to turn it into
text it can resolve + ground. Two capabilities, each gracefully degrading:

- VIDEO  → transcript (YouTube captions via youtube-transcript-api; keyless, lightweight).
- IMAGE  → OCR text (pytesseract; needs the Tesseract binary installed, so it is gated
           on availability and reports how to enable it rather than crashing).

Full image *understanding* (what a photo depicts) needs a vision model and is out of
scope for the no-LLM, bundle-size-bounded build — honest about that.
"""
from __future__ import annotations

import os
import re
import shutil
from typing import Any


# Tesseract is commonly installed off-PATH on Windows (Program Files). Resolve it and
# its Korean tessdata explicitly so OCR works without a PATH/env edit by the user.
_TESSERACT_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
)


def _tesseract_cmd() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in _TESSERACT_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None


def _tessdata_dir() -> str | None:
    """Where kor.traineddata lives. Program Files is often non-writable, so the kor
    pack may have been placed in a user dir with TESSDATA_PREFIX pointing at it."""
    for candidate in (
        os.environ.get("TESSDATA_PREFIX"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "ATANOR", "tessdata"),
        r"C:\Program Files\Tesseract-OCR\tessdata",
    ):
        if candidate and os.path.exists(os.path.join(candidate, "kor.traineddata")):
            return candidate
    return None


_YT_ID = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/|live/)|v=)([A-Za-z0-9_-]{11})"
)


def _youtube_id(url_or_id: str) -> str | None:
    s = (url_or_id or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    m = _YT_ID.search(s)
    return m.group(1) if m else None


def read_video_transcript(url_or_id: str, *, languages: tuple[str, ...] = ("ko", "en"), max_chars: int = 6000) -> dict[str, Any]:
    """Fetch a YouTube video's caption transcript as plain text. Returns
    {ok, text, segments, source_url, error}. Keyless; no video download (reads the
    caption track), so it's fast and light."""
    vid = _youtube_id(url_or_id)
    if not vid:
        return {"ok": False, "text": "", "error": "not_a_youtube_url"}
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception:
        return {"ok": False, "text": "", "error": "youtube_transcript_api_not_installed"}
    try:
        fetched = YouTubeTranscriptApi().fetch(vid, languages=list(languages))
        snippets = list(fetched)
    except Exception as exc:
        # try any available language before giving up
        try:
            fetched = YouTubeTranscriptApi().fetch(vid)
            snippets = list(fetched)
        except Exception:
            return {"ok": False, "text": "", "error": f"no_transcript:{type(exc).__name__}"}
    text = re.sub(r"\s+", " ", " ".join(getattr(s, "text", "") for s in snippets)).strip()
    return {
        "ok": bool(text),
        "text": text[:max_chars],
        "segments": len(snippets),
        "source_url": f"https://www.youtube.com/watch?v={vid}",
        "source_type": "video_transcript",
        "error": None,
    }


def ocr_available() -> bool:
    if _tesseract_cmd() is None:
        return False
    try:
        import pytesseract  # noqa: F401
        return True
    except Exception:
        return False


def read_image_ocr(image_path: str, *, lang: str = "kor+eng", max_chars: int = 6000) -> dict[str, Any]:
    """Extract text from an image via Tesseract OCR. Resolves the Tesseract binary and
    Korean tessdata even when off-PATH; returns a clear enable-instruction (not a crash)
    when OCR isn't installed."""
    cmd = _tesseract_cmd()
    if cmd is None:
        return {
            "ok": False,
            "text": "",
            "error": "ocr_not_available",
            "enable": "Install Tesseract OCR (`winget install UB-Mannheim.TesseractOCR`) + the Korean "
            "data 'kor', and `pip install pytesseract`. Then OCR auto-enables — no code change.",
        }
    try:
        import pytesseract
        from PIL import Image

        pytesseract.pytesseract.tesseract_cmd = cmd
        tessdata = _tessdata_dir()
        # Point Tesseract at the kor tessdata via env (passing --tessdata-dir through
        # pytesseract's space-split config mangles a quoted Windows path). Fall back to
        # eng-only if the kor pack isn't present.
        if tessdata:
            os.environ["TESSDATA_PREFIX"] = tessdata
        use_lang = lang if (tessdata or "kor" not in lang) else "eng"
        text = pytesseract.image_to_string(Image.open(image_path), lang=use_lang)
    except Exception as exc:
        return {"ok": False, "text": "", "error": f"ocr_failed:{type(exc).__name__}"}
    text = re.sub(r"[ \t]+", " ", text).strip()
    return {"ok": bool(text), "text": text[:max_chars], "source_type": "image_ocr", "error": None}


def read_image_ocr_b64(image_b64: str, *, lang: str = "kor+eng", max_chars: int = 6000) -> dict[str, Any]:
    """OCR an UPLOADED image given as base64 (data-URL or raw) — for the chat composer's
    file attach. Decodes in-memory (no temp file)."""
    cmd = _tesseract_cmd()
    if cmd is None:
        return {"ok": False, "text": "", "error": "ocr_not_available",
                "enable": "Install Tesseract OCR (winget install UB-Mannheim.TesseractOCR) + Korean data."}
    try:
        import base64
        import io

        import pytesseract
        from PIL import Image

        raw = image_b64.split(",", 1)[1] if image_b64.startswith("data:") else image_b64
        img = Image.open(io.BytesIO(base64.b64decode(raw)))
        pytesseract.pytesseract.tesseract_cmd = cmd
        tessdata = _tessdata_dir()
        if tessdata:
            os.environ["TESSDATA_PREFIX"] = tessdata
        use_lang = lang if (tessdata or "kor" not in lang) else "eng"
        text = pytesseract.image_to_string(img, lang=use_lang)
    except Exception as exc:
        return {"ok": False, "text": "", "error": f"ocr_failed:{type(exc).__name__}"}
    text = re.sub(r"[ \t]+", " ", text).strip()
    return {"ok": bool(text), "text": text[:max_chars], "source_type": "image_ocr", "error": None}


def media_capabilities() -> dict[str, Any]:
    """What media ATANOR can currently read into text (honest capability report)."""
    try:
        import youtube_transcript_api  # noqa: F401
        video = True
    except Exception:
        video = False
    return {
        "video_transcript": video,
        "image_ocr": ocr_available(),
        "image_understanding": False,  # needs a vision model — out of scope (no-LLM, bundle-bounded)
    }
