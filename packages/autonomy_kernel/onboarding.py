# -*- coding: utf-8 -*-
"""Conversational onboarding — a user brings ATANOR onto a platform (Moltbook, …) just by ASKING,
in chat. ATANOR does the automatable parts and hands the human-only parts back with clear prompts.

Owner (2026-07-10): " AI ."

The division of labor is principled and unavoidable:
 * AUTO (ATANOR does it): call the platform's register API, capture the credentials, assemble the
 exact next steps, and — once the human finishes — operate (read feed, draft posts).
 * HUMAN (only the user can): identity proof. Moltbook (like most) REQUIRES a human to verify an
 email and post a verification tweet — that is the whole point of "claim" (one human per agent,
 anti-spam). An agent cannot self-verify; that is a feature, not a gap. Publishing also stays
 the user's call.

So onboarding is a guided conversation: ATANOR provisions, the human proves ownership, ATANOR runs.
Extensible per platform; nothing here fabricates or publishes.
"""
from __future__ import annotations

import re
from typing import Any, Callable

# platform → the keywords that name it in a natural request
_PLATFORM_CUES = {
    "moltbook": (r"몰트북|moltbook|🦞",),
}


def detect_onboard_intent(text: str) -> str | None:
    """Is the user asking to put ATANOR onto a platform? Return the platform name or None."""
    t = str(text or "").lower()
    wants = bool(re.search(r"(가입|등록|올려|넣어|join|sign\s*up|register|온보딩|계정\s*만)", t)) \
        or bool(re.search(r"(에|에다|한테|한테다)\s*(나|우리|atanor|너)", t))
    if not wants:
        return None
    for platform, cues in _PLATFORM_CUES.items():
        if any(re.search(c, t) for c in cues):
            return platform
    return None


def onboard_moltbook(*, agent_name: str = "ATANOR",
                     agent_desc: str = "No-LLM graph-native honest AI - answers only from grounded "
                                       "knowledge, never fabricates.",
                     register_fn: Callable[[dict], dict] | None = None) -> dict[str, Any]:
    """Provision the agent on Moltbook (the AUTO part) and return the guided plan. `register_fn`
    posts to /agents/register; injectable for tests. Account creation is done here because the USER
    explicitly asked for it — but the returned plan makes the human identity steps explicit."""
    from packages.autonomy_kernel.moltbook_client import register_body

    body = register_body(agent_name, agent_desc)
    if register_fn is None:
        def register_fn(b: dict) -> dict:
            import json, urllib.request
            req = urllib.request.Request(
                "https://www.moltbook.com/api/v1/agents/register",
                data=json.dumps(b).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:  # nosec B310
                return json.loads(r.read().decode("utf-8"))

    try:
        resp = register_fn(body)
    except Exception as exc:
        return {"platform": "moltbook", "provisioned": False, "error": str(exc)[:200]}

    agent = resp.get("agent") or {}
    api_key = agent.get("api_key")
    claim_url = agent.get("claim_url")
    vcode = agent.get("verification_code")
    tweet = resp.get("tweet_template") or (
        f'I\'m claiming my AI agent "{agent.get("name", agent_name)}" on @moltbook 🦞\n\n'
        f'Verification: {vcode}')
    return {
        "platform": "moltbook",
        "provisioned": bool(api_key),
        "agent_name": agent.get("name", agent_name),
        # the credential is passed back to the caller/UI to store; not logged here.
        "api_key": api_key,
        "human_steps": [
            {"step": 1, "who": "you", "action": "이메일 인증",
             "how": f"이 링크를 열어 이메일과 사용자명을 입력하고 인증하세요: {claim_url}"},
            {"step": 2, "who": "you", "action": "인증 트윗 게시",
             "how": f"X(트위터)에 이 트윗을 올리세요:\n{tweet}"},
            {"step": 3, "who": "you", "action": "X 연결(읽기 전용)",
             "how": "claim 페이지에서 X를 연결하면 트윗이 자동 감지됩니다."},
        ],
        "then_atanor_will": "인증이 끝나면 MOLTBOOK_API_KEY를 설정하고 ATANOR가 피드를 자율로 읽고 "
                            "게시 초안을 냅니다(게시는 사용자 승인).",
        "note": "register(계정 provisioning)는 사용자 요청으로 ATANOR가 수행했지만, 이메일·트윗 인증은 "
                "사람만 할 수 있습니다 — '한 사람당 에이전트 하나' 소유 증명이라 자동화 불가(설계상).",
    }


def onboard(platform: str, **kwargs) -> dict[str, Any]:
    """Dispatch to a platform onboarder. Extend _ONBOARDERS to add platforms."""
    fn = _ONBOARDERS.get(platform)
    if not fn:
        return {"platform": platform, "provisioned": False,
                "error": f"unsupported platform; known: {sorted(_ONBOARDERS)}"}
    return fn(**kwargs)


_ONBOARDERS: dict[str, Callable[..., dict[str, Any]]] = {"moltbook": onboard_moltbook}
