from packages.agentic_micro_os.web_collection_store import WebCollectionStore, WebSourceRecord


def test_collection_store_dedupes_sources_and_creates_draft_only_candidate() -> None:
    store = WebCollectionStore()
    source = WebSourceRecord.from_visible_text("http://docs.local/a", "A", "public source text")

    store.add_source(source)
    store.add_source(source)
    draft = store.create_candidate_draft(source)

    assert len(store.sources) == 1
    assert draft.candidate_status == "draft"
    assert draft.production_mutation is False
    assert draft.approval_required is True
