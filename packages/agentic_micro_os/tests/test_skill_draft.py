from packages.agentic_micro_os.skill_draft import draft_skill_from_sources
from packages.agentic_micro_os.web_collection_store import WebSourceRecord


def test_web_skill_draft_is_not_promoted() -> None:
    source = WebSourceRecord.from_visible_text("http://docs.local/fish", "Fish", "public fish notes")
    draft = draft_skill_from_sources("research local tts alternatives", [source])

    assert draft is not None
    assert draft.status == "draft"
    assert draft.promotion_required is True
    assert "browser_read" in draft.required_capabilities
    assert "no Local Brain write" in draft.safety_notes
    assert source.content_hash in draft.source_refs
