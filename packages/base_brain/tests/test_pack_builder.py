from packages.base_brain.models import PACK_PATH, SEED_PATH, SEMANTIC_PATH, SURFACE_PATH
from packages.base_brain.pack_builder import build_base_brain_pack_v0


def test_combined_base_brain_pack_builds() -> None:
    pack = build_base_brain_pack_v0()
    assert PACK_PATH.exists()
    assert SEED_PATH.exists()
    assert SEMANTIC_PATH.exists()
    assert SURFACE_PATH.exists()
    assert pack["pack_id"] == "atanor_base_brain_v0"
    assert len(pack["semantic_graph"]["concepts"]) >= 30
    assert len(pack["surface_graph"]["constructions"]) >= 16
    assert pack["metadata"]["honesty"]["external_llm_used"] is False
