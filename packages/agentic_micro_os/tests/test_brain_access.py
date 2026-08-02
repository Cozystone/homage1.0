from packages.agentic_micro_os.brain_access import BrainAccessRequest, BrainAccessRoad, strip_private_payload


def test_brain_access_roads():
    road = BrainAccessRoad()
    assert road.request(BrainAccessRequest("local_brain", "local_brain_direct_write", "x", "raw", "raw", "test", "loop")).allowed is False
    local_draft = road.request(BrainAccessRequest("local_brain", "local_brain_memory_candidate_draft", "x", "candidate", "redacted", "test", "loop"))
    assert local_draft.allowed is True
    assert local_draft.approval_required is True
    cloud_read = road.request(BrainAccessRequest("cloud_brain", "cloud_brain_verified_read_summary", "x", "verified", "public", "test", "loop"))
    assert cloud_read.allowed is True
    cloud_write = road.request(BrainAccessRequest("cloud_brain", "production_store_direct_write", "x", "prod", "public", "test", "loop"))
    assert cloud_write.allowed is False
    assert strip_private_payload({"public": "ok", "raw_private_memory": "secret"}) == {"public": "ok"}
