from __future__ import annotations

import pytest

from packages.atlas_p2p_sandbox.models import ExchangeResult, SandboxPeer


def test_peer_trust_score_bounds():
    with pytest.raises(ValueError):
        SandboxPeer("bad", "peer", 1.5, "public", True)


def test_exchange_result_blocks_local_brain_write():
    with pytest.raises(ValueError):
        ExchangeResult(True, None, "test", True, safe_for_local_brain=True)
