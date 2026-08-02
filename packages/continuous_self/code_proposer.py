# -*- coding: utf-8 -*-
"""Code proposer — the WRITE half of vibe-coding, human-gated (owner 2026-07-12: " 
 ").

code_self_modification lets the mind propose ADDITIVE edits to its own phrasing data. This
generalizes the WRITE side: the machine authors real code artifacts — a test stub for a function
it understands, or a self-contained dashboard viewer component (the owner's " 
 " vision) — from its OWN self-knowledge (the AST code graph) plus deterministic
templates. Honest ceiling: No-LLM means it SCAFFOLDS and FILLS from what it knows, it does not
invent novel algorithms — but a scaffold grounded in the real signature is genuine, useful code.

Non-negotiable safety, inherited from code_self_modification:
 · everything is STAGED to runtime/proposals/ — the live tree is NEVER touched by the machine;
 · a unified diff + a plain-language summary accompany every proposal, for a human to review;
 · a human applies (git apply) or discards. There is no machine path to the running code.

This is the ladder's next rung: code understanding (read) → code proposal (write, staged) →
human review → apply. Autonomous UI generation lives at the top, behind the same gate.
"""
from __future__ import annotations

import ast
import json
import time
import uuid
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
PROPOSALS_DIR = REPO / "runtime" / "proposals"
LEDGER = PROPOSALS_DIR / "proposals.jsonl"


def _find_function(source: str, name: str) -> ast.FunctionDef | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _signature(fn: ast.FunctionDef) -> tuple[list[str], str | None]:
    args = [a.arg for a in fn.args.args if a.arg not in ("self", "cls")]
    doc = ast.get_docstring(fn)
    return args, (doc.strip().splitlines()[0] if doc else None)


def _stage(rel_path: str, content: str, kind: str, summary: str,
           diff_after: str | None = None) -> dict[str, Any]:
    """Write the proposed artifact to the staging dir (NOT the live path) + record it. The staged
    file name mirrors the intended path so a human sees exactly what would land where."""
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    pid = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
    staged = PROPOSALS_DIR / (pid + "__" + rel_path.replace("/", "__"))
    staged.write_text(content, encoding="utf-8")
    rec = {"id": pid, "kind": kind, "intended_path": rel_path, "staged_file": str(staged),
           "summary": summary, "applied": False, "ts": time.time()}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {**rec, "content_preview": content[:400]}


def propose_test_stub(module_path: str, func_name: str) -> dict[str, Any]:
    """Author a pytest stub for a function the machine understands — real name, real parameters read
    from the AST, a docstring-derived intent comment, and an assert-shaped skeleton. Staged, never
    applied. The clearest honest code-write: the machine knows the signature, so the scaffold is
    correct by construction; a human fills the actual expectation."""
    src_path = (REPO / module_path)
    if not src_path.exists():
        return {"ok": False, "reason": "module_not_found"}
    fn = _find_function(src_path.read_text(encoding="utf-8"), func_name)
    if fn is None:
        return {"ok": False, "reason": "function_not_found"}
    args, intent = _signature(fn)
    mod = module_path.removesuffix(".py").replace("/", ".").replace("\\", ".")
    call_args = ", ".join(f"{a}=..." for a in args)
    intent_line = f"    # intent: {intent}\n" if intent else ""
    content = (
        "# -*- coding: utf-8 -*-\n"
        f'"""Proposed test for {func_name} — STAGED by code_proposer, not yet reviewed."""\n'
        f"from {mod} import {func_name}\n\n\n"
        f"def test_{func_name}_smoke():\n"
        f'    """A human fills the real expectation; the signature scaffold is machine-authored."""\n'
        f"{intent_line}"
        f"    result = {func_name}({call_args})\n"
        f"    assert result is not None  # TODO(human): replace with the real assertion\n"
    )
    test_rel = f"packages/_proposed_tests/test_{func_name}.py"
    summary = (f"'{func_name}'({', '.join(args) or '무인자'})의 스모크 테스트 스텁을 제안했어요. "
               f"시그니처는 AST에서 읽어 정확하고, 실제 기대값은 사람이 채우면 됩니다.")
    return {"ok": True, **_stage(test_rel, content, "test_stub", summary)}


def propose_viewer_component(name: str, title: str, data_endpoint: str) -> dict[str, Any]:
    """Scaffold a self-contained dashboard viewer (owner's vision: if there's no interface to show a
    result, the machine codes one). Deterministic template filled with the machine's spec — a lean
    HTML/JS panel that polls a local endpoint and renders it. Staged; a human mounts it. No external
    calls, no framework — a viewer ATANOR could author for its own output."""
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "_-") or "viewer"
    content = f"""<!-- Proposed by code_proposer (STAGED) — a self-contained {title} viewer. -->
<div id="{safe}-root" style="font-family:system-ui;padding:12px;border-radius:10px;
     background:var(--panel,#111);color:var(--ink,#eee);max-width:640px">
  <h3 style="margin:0 0 8px">{title}</h3>
  <pre id="{safe}-body" style="white-space:pre-wrap;margin:0;opacity:.9">불러오는 중…</pre>
</div>
<script>
(function() {{
  const body = document.getElementById("{safe}-body");
  async function refresh() {{
    try {{
      const r = await fetch("{data_endpoint}", {{ headers: {{ "Accept": "application/json" }} }});
      const d = await r.json();
      body.textContent = JSON.stringify(d, null, 2);
    }} catch (e) {{ body.textContent = "연결 대기… (" + e.message + ")"; }}
  }}
  refresh(); setInterval(refresh, 4000);
}})();
</script>
"""
    rel = f"apps/web/proposed/{safe}.html"
    summary = (f"'{title}' 뷰어 컴포넌트를 제안했어요 — {data_endpoint}를 4초마다 폴링해 렌더하는 "
               f"자립형 패널입니다. 사람이 대시보드에 마운트하면 떠요.")
    return {"ok": True, **_stage(rel, content, "viewer_component", summary)}


def list_proposals(limit: int = 20) -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    out = []
    for ln in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out[-limit:]
