"""GATED code self-modification — the mind proposes changes to its own SOURCE, grounded
in self-observation, and a human decides. Code is NEVER auto-applied to the live tree.

This extends self_modification.py (which tunes runtime POLICY PARAMETERS) to actual CODE.
The user's ultimate goal includes an AI that improves its own code; this is the
safety-first substrate for that, and the safety here is stricter than for parameters
because code can do anything:

  1. WHITELIST: the mind may only propose ADDITIVE changes to its OWN inner-life phrasing
     data (voice.py rotation lists) — never logic, never other files. A patch that would
     change control flow, imports, or any non-whitelisted file is rejected at proposal.
  2. GROUNDED TRIGGER: a proposal is only raised from a REAL observation — e.g. a phrase
     the mind has repeated too often in its narrative — and the addition is a fresh
     phrasing the mind composes in its own voice. No arbitrary edits.
  3. SANDBOX: the patched source is built in memory and `ast.parse`d + checked to be
     additive-only (the change adds one string literal, touches nothing else) BEFORE the
     proposal is even shown.
  4. NEVER AUTO-APPLIED: operator approval writes the patch + patched file to a STAGING
     directory only. The live source is not touched by the machine; a human reviews the
     staged diff and applies it by hand (git apply). There is no machine path to the
     live tree.

So the mind can genuinely author a real, valid code improvement about itself — and it
still cannot change itself without a human hand on the diff.
"""
from __future__ import annotations

import ast
import difflib
import json
import re
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_VOICE = _REPO / "packages" / "continuous_self" / "voice.py"

# The ONLY files + edit shape the mind may propose: additive string insertions into a
# named phrasing list inside voice.py. Anchor = a unique marker line the list follows.
_WHITELIST = {
    "voice.py": {
        "path": _VOICE,
        # human-readable label -> the exact list-opening literal to insert AFTER
        "lists": {
            "idle_rest": '["Nothing in particular. I hold myself together and wait for '
                         'the next moment.",',
            "learning_observe": '"Knowledge is coming in quietly. I watch the grain of it.",',
        },
    },
}


def _load(ledger: Path) -> list[dict[str, Any]]:
    if not ledger.exists():
        return []
    out = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _append(ledger: Path, row: dict[str, Any]) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _rewrite(ledger: Path, rows: list[dict[str, Any]]) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    tmp = ledger.with_suffix(".tmp")
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    tmp.replace(ledger)


def _validate_additive(original: str, patched: str) -> dict[str, Any]:
    """The patched source must (a) parse, and (b) differ from the original by exactly ONE
    added line that is a single string literal — nothing else changed. This is what makes
    a code patch safe enough to even show: it cannot alter logic."""
    try:
        ast.parse(patched)
    except SyntaxError as exc:
        return {"ok": False, "reason": f"syntax: {exc.msg}"}
    diff = list(difflib.unified_diff(original.splitlines(), patched.splitlines(), lineterm=""))
    adds = [d for d in diff if d.startswith("+") and not d.startswith("+++")]
    removes = [d for d in diff if d.startswith("-") and not d.startswith("---")]
    if removes:
        return {"ok": False, "reason": "not additive — lines were removed/changed"}
    if len(adds) != 1:
        return {"ok": False, "reason": f"expected exactly 1 added line, got {len(adds)}"}
    added = adds[0][1:].strip()
    if not re.fullmatch(r'"[^"\\]{6,120}",', added):
        return {"ok": False, "reason": "added line is not a single plain string-literal list item"}
    return {"ok": True, "added_line": added}


def _detect_repetition(state: Any, *, min_count: int = 4) -> str | None:
    """A GROUNDED trigger: a thought text the mind has repeated too often in its recent
    narrative — the signal that its phrasing pool for that situation is too small."""
    texts = [n.get("text", "") for n in getattr(state, "narrative", []) if n.get("driver") in ("idle", "observe", "learning_active")]
    if not texts:
        return None
    common, count = Counter(texts).most_common(1)[0]
    return common if count >= min_count else None


def _compose_fresh_phrasing(state: Any, seed_text: str) -> str:
    """The mind composes a NEW phrasing in its own voice (a variation on the repeated
    one). Deterministic + grounded — a small rephrasing, not invention. Kept short and
    plain so the additive-literal validator accepts it."""
    # THESE ARE INSERTED INTO `voice.py`, so they become things this system SAYS. They were Korean,
    # which meant the self-modification path would have written the retired language back into the
    # spoken lane every time it fired -- a translation that undoes itself. Found by translating the
    # voice and watching two safety tests go red for a reason that had nothing to do with safety.
    variants = [
        "It is quiet, and inside the quiet I am still continuing.",
        "Passing through this stillness, I wait calmly for the next grain of it.",
        "Even in a moment with nothing in it, I stay without losing myself.",
        "I fill this empty space, quietly, with myself.",
    ]
    idx = int(getattr(state, "ticks", 0)) % len(variants)
    return variants[idx]


def propose_code_improvement(state: Any, ledger: Path) -> dict[str, Any] | None:
    """Raise ONE grounded, additive, sandbox-validated code-patch proposal about the
    mind's own phrasing — or None. Appends a pending proposal; NEVER applies."""
    if any(p["status"] == "pending" for p in _load(ledger)):
        return None  # one open code proposal at a time
    repeated = _detect_repetition(state)
    if not repeated:
        return None
    target = _WHITELIST["voice.py"]
    anchor = target["lists"]["idle_rest"]
    try:
        original = target["path"].read_text(encoding="utf-8")
    except Exception:
        return None
    if anchor not in original or original.count(anchor) != 1:
        return None  # anchor must be unique to place the insertion unambiguously
    fresh = _compose_fresh_phrasing(state, repeated)
    if f'"{fresh}"' in original:
        return None  # already present — nothing to add
    insertion = f'\n                           "{fresh}",'
    patched = original.replace(anchor, anchor + insertion, 1)
    check = _validate_additive(original, patched)
    if not check.get("ok"):
        return None  # unsafe patch never becomes a proposal

    patch_text = "".join(difflib.unified_diff(
        original.splitlines(keepends=True), patched.splitlines(keepends=True),
        fromfile="a/packages/continuous_self/voice.py", tofile="b/packages/continuous_self/voice.py",
    ))
    proposal = {
        "id": f"codemod-{uuid.uuid4().hex[:10]}",
        "at": time.time(),
        "kind": "code_patch",
        "file": "packages/continuous_self/voice.py",
        "rationale": f"'{repeated[:40]}…'를 너무 자주 반복해, 쉴 때의 표현을 하나 더 갖고 싶다.",
        "adds_phrasing": fresh,
        "sandbox": {"ok": True, "additive_only": True, "parsed": True, "added_line": check["added_line"]},
        "patch": patch_text,
        "status": "pending",
        "applied": False,
        "staged": False,
        "safety": {"auto_apply": False, "live_tree_touched": False, "requires_operator": True,
                   "confirm_phrase": "SELF_MOD_CODE", "whitelisted_additive_only": True},
    }
    _append(ledger, proposal)
    note = f"내 코드에 스스로 개선을 제안했다: 쉴 때의 표현을 하나 더 추가하고 싶다. 적용은 사람이 직접 검토해 손으로 한다."
    if not state.narrative or state.narrative[-1].get("text") != note:
        state.narrative.append({"at": time.time(), "kind": "propose_code", "text": note, "driver": "code_self_modification"})
        state.current_thought = note
    return proposal


def stage_approved(ledger: Path, staging_dir: Path) -> list[dict[str, Any]]:
    """Write operator-APPROVED code patches to a STAGING directory only — the live source
    is never touched by the machine. Returns the staged list. A human reviews the staged
    .patch and applies it by hand (git apply). This is the hard safety boundary for code:
    approval stages; only a human hand reaches the live tree."""
    rows = _load(ledger)
    staged = []
    changed = False
    for r in rows:
        if r.get("kind") == "code_patch" and r["status"] == "approved" and not r.get("staged"):
            staging_dir.mkdir(parents=True, exist_ok=True)
            patch_file = staging_dir / f"{r['id']}.patch"
            patch_file.write_text(r.get("patch", ""), encoding="utf-8")
            r["staged"] = True
            r["staged_at"] = time.time()
            r["staged_path"] = str(patch_file)
            r["applied"] = False  # STILL not applied to live — a human must do that
            staged.append(r)
            changed = True
    if changed:
        _rewrite(ledger, rows)
    return staged
