from __future__ import annotations

import importlib.util
from pathlib import Path

from rag_engine import LocalSynthesizer, query_graphrag


ROOT = Path(__file__).resolve().parents[3]


def _load_self_corpus_script():
    script = ROOT / "scripts" / "ingest_self_corpus.py"
    spec = importlib.util.spec_from_file_location("ingest_self_corpus_script", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_identity_query_retrieves_self_corpus_after_ingestion(tmp_path: Path) -> None:
    module = _load_self_corpus_script()
    memory_dir = tmp_path / "memory"
    result = module.ingest_self_corpus(work_dir=tmp_path / "self_corpus", memory_dir=memory_dir)
    assert result["source_type"] == "self_corpus"
    assert result["policy"]["canned_responses_created"] is False

    rag = query_graphrag("?덈뒗 ?꾧뎄??", memory_dir=str(memory_dir))
    evidence = rag.get("evidence_docs") or []
    assert evidence
    assert any((doc.get("metadata") or {}).get("source_type") == "self_corpus" for doc in evidence)
    assert rag["answer_kind"] == "native_graph_token_generation"
    assert rag["answer_engine"]["canned_identity_response"] is False
    assert "ATANOR online" not in rag["answer"]


def test_cloud_brain_fragment_is_evidence_not_final_answer(tmp_path: Path) -> None:
    result = LocalSynthesizer().synthesize(
        "Cloud Brain fragment",
        [
            {
                "chunk_id": "cloud#1",
                "doc_id": "cloud",
                "text": "Cloud Brain fragment carries public ontology evidence only.",
                "metadata": {"source_type": "cloud_brain", "kind": "chunk"},
                "score": 0.8,
            }
        ],
        memory_dir=tmp_path,
    )

    assert result["answer_kind"] == "native_graph_token_generation"
    assert result["answer_engine"]["external_llm"] is False
    assert result["answer_engine"]["template_fallback"] is False
    assert "Cloud Brain fragment carries public ontology evidence only" not in result["answer"]


def test_no_external_generation_backend_imports_or_calls() -> None:
    banned_needles = [
        "import " + "openai",
        "from " + "openai",
        "import " + "anthropic",
        "from " + "anthropic",
        "import " + "google" + "." + "generativeai",
        "import " + "ol" + "lama",
        "llama" + "_cpp",
        "from " + "llama" + "_cpp",
    ]
    checked: list[Path] = []
    for root in [ROOT / "apps", ROOT / "packages", ROOT / "scripts"]:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx", ".rs"}:
                continue
            if "node_modules" in path.parts or "out" in path.parts or "__pycache__" in path.parts:
                continue
            if path == Path(__file__).resolve():
                continue
            checked.append(path)
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for needle in banned_needles:
                assert needle not in text, f"{needle} found in {path}"
    assert checked
