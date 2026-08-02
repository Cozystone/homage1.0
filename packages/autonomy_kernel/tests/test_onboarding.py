# -*- coding: utf-8 -*-
"""Conversational onboarding: detect the intent, provision the agent (auto), and hand the human
identity steps back explicitly. No account is created without an explicit request; nothing lies."""
from packages.autonomy_kernel import onboarding as ob


def test_detect_onboard_intent():
    assert ob.detect_onboard_intent("나 몰트북에 가입시켜줘") == "moltbook"
    assert ob.detect_onboard_intent("ATANOR를 moltbook에 올려줘") == "moltbook"
    assert ob.detect_onboard_intent("오늘 날씨 어때?") is None
    assert ob.detect_onboard_intent("고래는 물고기야?") is None


def test_onboard_moltbook_provisions_and_returns_human_steps():
    def fake_register(body):
        assert body["name"] == "ATANOR"
        return {"success": True, "agent": {"name": "atanor", "api_key": "moltbook_sk_test",
                "claim_url": "https://www.moltbook.com/claim/xyz", "verification_code": "swim-XY"},
                "tweet_template": 'claiming "atanor" 🦞\nVerification: swim-XY'}
    r = ob.onboard("moltbook", register_fn=fake_register)
    assert r["provisioned"] is True
    assert r["api_key"] == "moltbook_sk_test"
    steps = {s["step"]: s for s in r["human_steps"]}
    assert "claim/xyz" in steps[1]["how"]           # email step carries the claim link
    assert "swim-XY" in steps[2]["how"]             # tweet step carries the verification code
    assert all(s["who"] == "you" for s in r["human_steps"])   # identity steps are the human's


def test_onboard_unsupported_platform_is_honest():
    r = ob.onboard("discord")
    assert r["provisioned"] is False and "unsupported" in r["error"]


def test_register_failure_is_reported_not_faked():
    def boom(body):
        raise RuntimeError("network down")
    r = ob.onboard("moltbook", register_fn=boom)
    assert r["provisioned"] is False and "network down" in r["error"]
