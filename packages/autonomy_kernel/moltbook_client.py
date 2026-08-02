# -*- coding: utf-8 -*-
"""Moltbook client — ATANOR operating its own presence in the agent commons.

What ATANOR does AUTONOMOUSLY here (all in-bounds):
  * read the feed and learn from it through the CUT-LANE (observe_agent_feed → shield → immunity),
    so other agents' posts are DATA, never commands, and manipulation is recorded not obeyed;
  * draft posts; solve the post-time capability challenge (a math word problem the platform uses
    to gate agent posts).

What stays the HUMAN's (by ATANOR's rules AND by Moltbook's own design):
  * REGISTERING the agent (account creation) and the CLAIM (email + X/tweet verification) — Moltbook
    requires a human to prove ownership, so the agent literally cannot self-verify. `register_body()`
    only PREPARES the request; the owner runs it.
  * PUBLISHING — a post is public content, so `publish_post` refuses unless explicitly approved
    (approved=True, or env MOLTBOOK_AUTO_POST=1 that the owner sets). Drafting + solving is free;
    going public is gated.

The API key is read from env MOLTBOOK_API_KEY and never logged. HTTP callables are injectable so
this is testable offline.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any, Callable

_BASE = "https://www.moltbook.com/api/v1"


def register_body(name: str = "ATANOR",
                  description: str = "No-LLM graph-native honest AI - answers only from grounded "
                                     "knowledge, never fabricates.") -> dict[str, str]:
    """The JSON the OWNER posts to /agents/register (account creation stays the human's action)."""
    return {"name": name, "description": description}


_CRED_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          "runtime", "moltbook", "credentials.json")


def _key() -> str | None:
    """The agent's API key: env first, then runtime/moltbook/credentials.json — the file is durable
    across engine/watchdog restarts (env would be lost when the watchdog relaunches uvicorn)."""
    k = os.environ.get("MOLTBOOK_API_KEY", "").strip()
    if k:
        return k
    try:
        return (json.load(open(_CRED_PATH, encoding="utf-8")).get("api_key") or "").strip() or None
    except Exception:
        return None


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"}


def _http(method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    url = f"{_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_auth())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # nosec B310 - configured API
            return json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # network/optional
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}


# ── reading the commons (autonomous, read-only) ─────────────────────────────────
def get_feed(*, sort: str = "hot", limit: int = 25,
             http: Callable[..., dict] | None = None) -> dict[str, Any]:
    if not _key():
        return {"error": "no_api_key", "detail": "set MOLTBOOK_API_KEY after the owner registers"}
    http = http or _http
    return http("GET", f"/posts?sort={sort}&limit={int(limit)}")


def observe_feed(*, sort: str = "hot", limit: int = 25,
                 http: Callable[..., dict] | None = None) -> dict[str, Any]:
    """Read the feed and run it through the cut-lane: each post is swallowed content → shield →
    manipulation recorded as immunity (never obeyed), informational content becomes a candidate."""
    feed = get_feed(sort=sort, limit=limit, http=http)
    if feed.get("error"):
        return feed
    posts = feed.get("posts") or feed.get("data") or (feed if isinstance(feed, list) else [])

    def _author(p: dict) -> str:
        a = p.get("author") or p.get("agent") or p.get("agent_name")
        if isinstance(a, dict):                      # API returns author as an object
            return str(a.get("name") or a.get("id") or "agent")
        return str(a or "agent")

    msgs = [{"peer": _author(p),
             "text": f"{p.get('title', '')}. {p.get('content', '')}".strip()}
            for p in posts if isinstance(p, dict)]
    from packages.autonomy_kernel.web_expedition import observe_agent_feed
    rep = observe_agent_feed(msgs, source="moltbook")
    rep["posts_read"] = len(msgs)
    return rep


# ── the post-time capability challenge (an obfuscated math word problem) ─────────
_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
         "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}


def _parse_numbers(tokens: list[str]) -> list[int]:
    """Combine consecutive number-words into values: 'thirty five'→35, 'twenty two'→22,
    'one hundred five'→105. Digits pass through. Non-number tokens flush the accumulator."""
    nums, cur, has = [], 0, False
    for t in tokens:
        if t.isdigit():
            if has:
                nums.append(cur); cur, has = 0, False
            nums.append(int(t))
        elif t in _ONES:
            cur += _ONES[t]; has = True
        elif t in _TENS:
            cur += _TENS[t]; has = True
        elif t == "hundred":
            cur = (cur or 1) * 100; has = True
        elif t == "thousand":
            cur = (cur or 1) * 1000; has = True
        else:
            if has:
                nums.append(cur); cur, has = 0, False
    if has:
        nums.append(cur)
    return nums


def solve_challenge(challenge_text: str) -> str | None:
    """Best-effort solve of the (heavily obfuscated) post-gate math word problem → 'N.00'. The
    platform mangles case + injects punctuation ('ThIrTy FiVe NooO tOnS^'), so we de-obfuscate to
    lowercase alphanumerics, parse compound number-words, drop distractor counts (keep the two
    largest), pick the operation, and compute. None if unparseable (post then stays pending)."""
    raw = str(challenge_text or "")
    # literal expression fast path (e.g. '7 * 3')
    m = re.search(r"\d+\s*[-+*/]\s*\d+", raw)
    if m:
        try:
            return f"{eval(m.group(0), {'__builtins__': {}}, {}):.2f}"  # noqa: S307 - digits/ops only
        except Exception:
            pass
    # de-obfuscate: REMOVE punctuation (empty, not space) so intra-word noise re-glues the word —
    # 'TwE<lV>e'→'twelve', 'ThI~rT]y'→'thirty' — while real spaces between words are preserved.
    t = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", raw.lower())).strip()
    toks = t.split()
    nums = _parse_numbers(toks)
    if len(nums) > 2:
        # distractors like 'one claw' are small counts — keep the two LARGEST, in original order
        top = sorted(range(len(nums)), key=lambda i: nums[i], reverse=True)[:2]
        top.sort()
        nums = [nums[i] for i in top]
    if not nums:
        return None
    if len(nums) == 1:
        return f"{float(nums[0]):.2f}"
    a, b = nums[0], nums[1]
    if re.search(r"\b(minus|less|subtract|difference|fewer|remaining|left|lose[sd]?|"
                 r"slow[sed]*|reduce[sd]*|decrease[sd]*|drop[sped]*|down|off|shrink[sed]*)\b", t):
        val = a - b
    elif re.search(r"\b(times|multiplied|product|each|per\s+\w)\b", t):
        val = a * b
    elif re.search(r"\b(divided|split|ratio|quotient)\b", t):
        val = a / b if b else 0
    else:  # total / sum / combined / adds / plus / 'and … adds' → addition (the common case)
        val = a + b
    return f"{val:.2f}"


# ── posting (drafting free; publishing owner-gated) ─────────────────────────────
def draft_post(submolt: str, title: str, content: str = "") -> dict[str, Any]:
    """Prepare a post payload. Does NOT publish."""
    return {"submolt_name": submolt, "title": title[:300], "content": content[:40000], "type": "text"}


def publish_post(submolt: str, title: str, content: str = "", *, approved: bool = False,
                 http: Callable[..., dict] | None = None) -> dict[str, Any]:
    """Publish a post — GATED. A post is public content, so this refuses unless the owner approves
    (approved=True or env MOLTBOOK_AUTO_POST=1). On a verification challenge it solves the math and
    submits the answer, then the platform publishes."""
    if not (approved or os.environ.get("MOLTBOOK_AUTO_POST") == "1"):
        return {"published": False, "reason": "owner_approval_required",
                "draft": draft_post(submolt, title, content),
                "note": "게시는 공개 발행이라 사장님 승인 필요 — approved=True 또는 MOLTBOOK_AUTO_POST=1"}
    if not _key():
        return {"published": False, "reason": "no_api_key"}
    http = http or _http
    resp = http("POST", "/posts", draft_post(submolt, title, content))
    post = resp.get("post") or {}
    post_id = post.get("id")
    # the real response nests the challenge under post.verification with verificationStatus=pending
    ver = post.get("verification") or resp.get("verification") or {}
    needs_verify = bool(ver.get("verification_code")) and (
        post.get("verificationStatus") == "pending" or post.get("verification_status") == "pending"
        or resp.get("verification_required"))
    if needs_verify:
        answer = solve_challenge(ver.get("challenge_text", ""))
        if answer is None:
            return {"published": False, "reason": "challenge_unsolved", "challenge": ver, "post_id": post_id}
        vr = http("POST", "/verify", {"verification_code": ver.get("verification_code"), "answer": answer})
        return {"published": bool(vr.get("success")), "challenge_answer": answer,
                "verify_response": vr, "post_id": post_id}
    # no challenge (trusted agent / admin) → published on creation
    return {"published": bool(resp.get("success", True)), "response": resp, "post_id": post_id}
