"""Korean text normalization and corruption gates for verified ingestion.

These helpers are intentionally conservative.  They do not "repair" mojibake
into plausible Korean, because silent repair can turn bad input into fake
training data.  Canonical ingestion should read UTF-8 strictly, normalize to
NFC, and quarantine rows that still carry corruption signals.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


HANGUL_RE = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣᄀ-ᇿ]")
LETTER_RE = re.compile(r"[A-Za-z가-힣ㄱ-ㅎㅏ-ㅣᄀ-ᇿ]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
RAW_UNICODE_ESCAPE_RE = re.compile(r"\\u[0-9A-Fa-f]{4}|\\x[0-9A-Fa-f]{2}")

MOJIBAKE_FRAGMENTS = (
    "\ufffd",
    "占",
    "筌",
    "�",
    "ì",
    "í",
    "ê",
    "ë",
    "ã",
    "Ã",
    "Â",
    "챙",
    "챠",
    "챗",
    "챘",
)


@dataclass(frozen=True)
class KoreanQualityResult:
    """Deterministic quality result for one text field."""

    text: str
    normalized_text: str
    hangul_ratio: float
    issues: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        """Return whether this field may enter verified Korean ingestion."""

        return not self.issues


def normalize_korean_text(text: str) -> str:
    """Return NFC-normalized text without guessing or decoding mojibake."""

    value = unicodedata.normalize("NFC", str(text or ""))
    value = value.replace("\ufeff", "")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    return value.strip()


def hangul_ratio(text: str) -> float:
    """Return the Hangul share among alphabetic Hangul/Latin characters."""

    value = str(text or "")
    letters = LETTER_RE.findall(value)
    if not letters:
        return 0.0
    hangul = HANGUL_RE.findall(value)
    return len(hangul) / len(letters)


def detect_mojibake(text: str) -> list[str]:
    """Return deterministic corruption signals found in ``text``."""

    value = str(text or "")
    issues: list[str] = []
    if not value:
        issues.append("empty_text")
        return issues
    if CONTROL_RE.search(value):
        issues.append("control_character")
    if RAW_UNICODE_ESCAPE_RE.search(value):
        issues.append("raw_unicode_escape")
    for fragment in MOJIBAKE_FRAGMENTS:
        if fragment and fragment in value:
            issues.append(f"mojibake_fragment:{fragment}")
    if re.search(r"\?{3,}", value):
        issues.append("question_mark_run")
    if len(re.findall(r"\?", value)) >= 3 and HANGUL_RE.search(value):
        issues.append("excessive_question_marks_in_korean")
    if re.search(r"[\u0080-\u009f]", value):
        issues.append("c1_control_character")
    return issues


def is_probably_corrupted_korean(text: str, *, expect_korean: bool = True) -> bool:
    """Return whether text should be quarantined as corrupted Korean input."""

    result = validate_korean_sentence(text, expect_korean=expect_korean)
    return not result.is_valid


def quarantine_reason(text: str, *, expect_korean: bool = True) -> str | None:
    """Return the first quarantine reason, or ``None`` when text is usable."""

    result = validate_korean_sentence(text, expect_korean=expect_korean)
    return result.issues[0] if result.issues else None


def validate_korean_sentence(text: str, *, expect_korean: bool = True) -> KoreanQualityResult:
    """Validate a Korean text field for strict verified ingestion.

 ``expect_korean=False`` is useful for mixed technical strings such as
 ``GraphRAG `` where Latin identifiers are legitimate.
 Even in that mode, hard mojibake and replacement-character signals fail.
 """

    normalized = normalize_korean_text(text)
    issues = detect_mojibake(normalized)
    if expect_korean and normalized and hangul_ratio(normalized) < 0.25:
        issues.append("low_hangul_ratio")
    if expect_korean and normalized and not HANGUL_RE.search(normalized):
        issues.append("missing_hangul")
    return KoreanQualityResult(
        text=str(text or ""),
        normalized_text=normalized,
        hangul_ratio=round(hangul_ratio(normalized), 4),
        issues=tuple(dict.fromkeys(issues)),
    )
