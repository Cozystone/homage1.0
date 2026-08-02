# -*- coding: utf-8 -*-
"""Book ingestion: PDF text/OCR -> sentences -> corpus (behind the truth gates)."""
from packages.cloud_brain.book_ingest import _sentences, ingest_book


def test_sentence_split_keeps_real_sentences():
    text = ("System 1 operates automatically and quickly. System 2 allocates "
            "attention to effortful mental activities. 42\n\nPAGE HEADER\n\n"
            "Anchoring biases numerical estimates.")
    s = _sentences(text)
    assert any("System 1 operates" in x for x in s)
    assert any("Anchoring biases" in x for x in s)
    assert "42" not in s and "PAGE HEADER" not in s     # page number / header dropped


def test_missing_file_is_honest():
    r = ingest_book("/no/such/book.pdf")
    assert r.sentences == 0 and "not found" in r.note


def test_korean_sentences_kept():
    s = _sentences("생각에 관한 생각은 흥미로운 주제이다. 이 문장은 유지되어야 한다.")
    assert len(s) >= 1 and any("생각" in x for x in s)
