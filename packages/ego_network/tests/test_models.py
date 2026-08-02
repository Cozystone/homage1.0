from __future__ import annotations

import pytest

from packages.ego_network.models import (
    CheckinResult,
    EgoDevice,
    MidnightCongressTopic,
)


def test_device_validation() -> None:
    device = EgoDevice("desktop", "Desktop", "main_brain", 1.0, True, None, {})
    assert device.to_dict()["device_role"] == "main_brain"
    with pytest.raises(ValueError):
        EgoDevice("bad", "Bad", "real_peer", 0.5, True, None, {})
    with pytest.raises(ValueError):
        EgoDevice("bad", "Bad", "test_peer", 1.5, True, None, {})


def test_topic_validation() -> None:
    topic = MidnightCongressTopic("t", "Title", "knowledge_gap", [], True, "synthetic", "proposed")
    assert topic.public_only is True
    with pytest.raises(ValueError):
        MidnightCongressTopic("t", "Title", "knowledge_gap", [], True, "raw_private", "proposed")


def test_checkin_cannot_mutate_stores() -> None:
    with pytest.raises(ValueError):
        CheckinResult("r", "owner", "desktop", "remote", False, "proposal_only", local_brain_mutated=True)
