"""Filter behavior: min length, duplicate, special char ratio, link density."""

from __future__ import annotations

from datagate import (
    DataGateConfig,
    Document,
    DuplicateHashFilter,
    LinkDensityFilter,
    MinLengthFilter,
    SpecialCharRatioFilter,
    doc_id_for,
    normalize_text,
)


def _doc(text: str) -> Document:
    return Document(doc_id=doc_id_for(normalize_text(text)), source_path="x.txt", text=text)


# --- MinLengthFilter -------------------------------------------------------

def test_min_length_below_threshold_rejected():
    flt = MinLengthFilter(DataGateConfig(min_chars=10))
    result = flt.apply(_doc("short"))
    assert result.passed is False
    assert "< min 10" in result.reason
    assert result.metrics["char_count"] == 5


def test_min_length_exactly_at_threshold_passes():
    flt = MinLengthFilter(DataGateConfig(min_chars=5))
    assert flt.apply(_doc("hello")).passed is True


def test_min_length_above_threshold_passes():
    flt = MinLengthFilter(DataGateConfig(min_chars=3))
    assert flt.apply(_doc("hello world")).passed is True


def test_min_length_whitespace_only_rejected():
    flt = MinLengthFilter(DataGateConfig(min_chars=5))
    result = flt.apply(_doc("        \n\t   "))
    assert result.passed is False
    assert result.metrics["char_count"] == 0


# --- DuplicateHashFilter ---------------------------------------------------

def test_duplicate_second_rejected_with_first_doc_id():
    flt = DuplicateHashFilter()
    d1 = _doc("identical content here")
    d2 = Document(doc_id=d1.doc_id, source_path="other.txt", text="identical content here")
    assert flt.apply(d1).passed is True
    result = flt.apply(d2)
    assert result.passed is False
    assert d1.doc_id in result.reason


def test_duplicate_whitespace_normalized():
    flt = DuplicateHashFilter()
    a = _doc("hello   world\n\nfoo")
    b = _doc("hello world foo")
    assert flt.apply(a).passed is True
    # normalized forms collapse to the same content -> duplicate
    assert flt.apply(b).passed is False


def test_duplicate_state_resets():
    flt = DuplicateHashFilter()
    d = _doc("repeatable content")
    assert flt.apply(d).passed is True
    assert flt.apply(d).passed is False
    flt.reset()
    assert flt.apply(d).passed is True


# --- SpecialCharRatioFilter ------------------------------------------------

def test_special_char_clean_prose_passes():
    flt = SpecialCharRatioFilter(DataGateConfig(max_special_char_ratio=0.30))
    assert flt.apply(_doc("This is clean prose, with normal punctuation.")).passed


def test_special_char_symbol_soup_rejected():
    flt = SpecialCharRatioFilter(DataGateConfig(max_special_char_ratio=0.30))
    result = flt.apply(_doc("█▓▒░@#$%^&*<>{}=+█▓▒░@#$%^&*"))
    assert result.passed is False
    assert "special_char_ratio" in result.reason


def test_special_char_korean_passes():
    flt = SpecialCharRatioFilter(DataGateConfig(max_special_char_ratio=0.30))
    assert flt.apply(_doc("한국어 텍스트는 유니코드 영숫자로 처리된다.")).passed


def test_special_char_boundary_passes():
    # 1 special char out of 10 -> ratio 0.1 exactly equals threshold -> passes
    flt = SpecialCharRatioFilter(DataGateConfig(max_special_char_ratio=0.1))
    assert flt.apply(_doc("abcdefghi█")).passed is True


# --- LinkDensityFilter -----------------------------------------------------

def test_link_density_prose_one_link_passes():
    flt = LinkDensityFilter(DataGateConfig(max_link_density=0.40))
    text = (
        "Here is a long paragraph of ordinary prose that mentions a single "
        "link https://example.com/article somewhere in the middle and then "
        "keeps going with plenty of additional explanatory text afterwards."
    )
    assert flt.apply(_doc(text)).passed is True


def test_link_density_link_list_rejected():
    flt = LinkDensityFilter(DataGateConfig(max_link_density=0.40))
    text = "\n".join(f"https://example.com/{i}" for i in range(20))
    result = flt.apply(_doc(text))
    assert result.passed is False
    assert "link_density" in result.reason


def test_link_density_markdown_counted():
    flt = LinkDensityFilter(DataGateConfig(max_link_density=0.40))
    text = "[a](https://example.com/aaaaaaaaaaaaaaaaaaaa) [b](https://example.com/bbbbbbbbbbbbbbbbbbbb)"
    assert flt.apply(_doc(text)).passed is False
