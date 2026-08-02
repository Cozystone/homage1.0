from packages.graph_hub.entitlement import check_entitlement, expire_subscription, grant_free_entitlement, grant_local_one_time_entitlement, grant_local_subscription_entitlement


def test_entitlement_modes():
    assert grant_free_entitlement("atanor_base_free")["status"] == "free"
    assert grant_local_one_time_entitlement("startup_strategy_demo")["status"] == "owned"
    assert grant_local_subscription_entitlement("korean_writing_demo")["status"] == "active_subscription"
    assert check_entitlement("korean_writing_demo")["attach_allowed"] is True
    assert expire_subscription("korean_writing_demo")["status"] == "expired_subscription"
    assert check_entitlement("korean_writing_demo")["attach_allowed"] is False
