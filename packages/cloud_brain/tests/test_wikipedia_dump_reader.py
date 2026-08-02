from __future__ import annotations

import bz2
from pathlib import Path

from packages.cloud_brain.wikipedia_dump_reader import clean_wikitext, iter_wikipedia_sentences


def _dump_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">
  <page>
    <title>Kubernetes</title>
    <ns>0</ns>
    <id>123</id>
    <revision>
      <id>456</id>
      <timestamp>2026-01-01T00:00:00Z</timestamp>
      <text xml:space="preserve"><![CDATA[
{{Short description|container orchestration system}}
Kubernetes manages [[containerized application|containerized applications]] across distributed clusters. It supports declarative configuration for reliable public infrastructure.
== References ==
* https://example.invalid/reference
      ]]></text>
    </revision>
  </page>
  <page>
    <title>Redirected page</title>
    <ns>0</ns>
    <id>999</id>
    <redirect title="Target" />
    <revision><id>1000</id><text>Redirect text should never be emitted.</text></revision>
  </page>
  <page>
    <title>Talk:Kubernetes</title>
    <ns>1</ns>
    <id>777</id>
    <revision><id>778</id><text>Talk namespace should never be emitted.</text></revision>
  </page>
</mediawiki>
"""


def test_iter_wikipedia_sentences_streams_main_namespace_and_skips_redirects(tmp_path: Path) -> None:
    dump = tmp_path / "enwiki.xml"
    dump.write_text(_dump_xml(), encoding="utf-8")

    rows = list(iter_wikipedia_sentences(dump))

    assert [row.text for row in rows] == [
        "Kubernetes manages containerized applications across distributed clusters.",
        "It supports declarative configuration for reliable public infrastructure.",
    ]
    assert {row.title for row in rows} == {"Kubernetes"}
    assert {row.page_id for row in rows} == {"123"}
    assert {row.revision_id for row in rows} == {"456"}
    assert rows[0].sentence_index == 1
    assert rows[0].license == "CC BY-SA 4.0"


def test_iter_wikipedia_sentences_supports_bz2_dumps(tmp_path: Path) -> None:
    dump = tmp_path / "enwiki.xml.bz2"
    dump.write_bytes(bz2.compress(_dump_xml().encode("utf-8")))

    rows = list(iter_wikipedia_sentences(dump, max_rows=1))

    assert len(rows) == 1
    assert rows[0].title == "Kubernetes"
    assert rows[0].text.startswith("Kubernetes manages")


def test_clean_wikitext_removes_templates_refs_and_links() -> None:
    cleaned = clean_wikitext("{{x}} [[Graph theory|Graph theory]] <ref>noise</ref> describes relationships.")

    assert "{{" not in cleaned
    assert "<ref" not in cleaned
    assert cleaned == "Graph theory describes relationships."
