from packages.hermes_intake.code_reuse_plan import build_code_reuse_plan


def test_code_reuse_plan_rejects_providers():
    plan = build_code_reuse_plan("abc", "MIT")
    assert plan["license_notice_required"] is True
    assert any(item["classification"] == "reject" and item["source_path"] == "providers/" for item in plan["candidates"])
