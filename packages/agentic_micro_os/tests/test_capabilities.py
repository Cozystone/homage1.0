from datetime import datetime, timedelta, timezone

import pytest

from packages.agentic_micro_os.capabilities import CapabilityKernel
from packages.agentic_micro_os.models import CapabilityToken


def test_missing_expired_and_forbidden_tokens_rejected():
    kernel = CapabilityKernel()
    assert kernel.decide("dashboard_action", None).allowed is False
    expired = CapabilityToken("t", "dashboard_action", "proof", datetime.now(timezone.utc) - timedelta(seconds=1), 1, "test", "test")
    assert kernel.decide("dashboard_action", expired).allowed is False
    assert kernel.decide("unrestricted_shell", None).allowed is False
    with pytest.raises(ValueError):
        kernel.issue("git_push")


def test_allowed_token_accepted():
    kernel = CapabilityKernel()
    token = kernel.issue("dashboard_action")
    assert kernel.decide("dashboard_action", token).allowed is True
