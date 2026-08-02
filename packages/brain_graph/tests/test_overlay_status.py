from packages.brain_graph.overlay_status import get_overlay_status


def test_overlay_status_never_claims_local_write():
    status = get_overlay_status()
    assert status["local_brain_write"] is False
    assert status["cloud_attached_counts_as_local"] is False
