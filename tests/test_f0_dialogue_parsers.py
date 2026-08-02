# -*- coding: utf-8 -*-
"""F0 dialogue parsers for the G2 register corpus — pure, tested on synthetic samples."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "f0id", Path(__file__).resolve().parents[1] / "scripts" / "f0_ingest_dialogue.py")
f0 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(f0)


def test_wiki_talk_pairs_a_reply_with_its_parent():
    raw = "\n".join(json.dumps(u) for u in [
        {"id": "1", "text": "Should we cite the primary source here?", "reply-to": None},
        {"id": "2", "text": "Yes, and add a page number.", "reply-to": "1"},
    ])
    out = list(f0.parse_wiki_talk(raw))
    assert len(out) == 1
    assert out[0]["register"] == "collab-talk"
    assert "Should we cite" in out[0]["text"] and "add a page number" in out[0]["text"]


def test_stackexchange_pairs_question_with_top_answer_and_strips_html():
    raw = (
        '<row Id="10" PostTypeId="1" Title="Ill vs sick?" '
        'Body="&lt;p&gt;What is the &lt;em&gt;difference&lt;/em&gt;?&lt;/p&gt;" />'
        '<row Id="11" PostTypeId="2" ParentId="10" Score="3" '
        'Body="&lt;p&gt;They overlap; &amp;quot;ill&amp;quot; is more formal.&lt;/p&gt;" />'
        '<row Id="12" PostTypeId="2" ParentId="10" Score="9" '
        'Body="&lt;p&gt;Use either in most cases.&lt;/p&gt;" />'
    )
    out = list(f0.parse_stackexchange(raw))
    assert len(out) == 1
    assert "<" not in out[0]["text"] and ">" not in out[0]["text"]     # no markup survives
    assert "Use either in most cases" in out[0]["text"]                # highest-score answer chosen


def test_strip_html_decodes_before_stripping():
    assert f0._strip_html("&lt;p&gt;hello&lt;/p&gt;") == "hello"
    assert "<" not in f0._strip_html("&lt;b&gt;x&lt;/b&gt; &amp; y")


def test_llm_generated_source_stays_refused():
    assert f0.SOURCES["ultrachat"]["adopt"] is False           # No-LLM: never distil an LLM
    assert f0.SOURCES["wiki_talk"]["adopt"] and f0.SOURCES["stackexchange"]["adopt"]
