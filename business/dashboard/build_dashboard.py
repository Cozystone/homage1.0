# -*- coding: utf-8 -*-
"""ATANOR Mission Control — renders the agent team's shared state as one page.

The team does NOT chat in a room; it coordinates through the business/ folder
(BUSINESS_LOG = shared log, approval_queue = draft->approved->posted, metrics =
daily/weekly). This script reads that single source of truth + git + live stars
and emits a self-contained dashboard/index.html. Re-run any time (the daily ops
sweep can call it) to refresh. No server needed — open the HTML file directly.

Run:  python -X utf8 business/dashboard/build_dashboard.py
"""
from __future__ import annotations

import glob
import html
import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIZ = ROOT / "business"
AGENTS_DIR = Path(os.path.expanduser("~")) / ".claude" / "agents"
OUT = BIZ / "dashboard" / "index.html"

ACCENT = "#d2521f"   # ATANOR orange
REPOS = ["Cozystone/ATANOR", "Cozystone/ATANOR-Demo"]

# automation cadence (human-readable; source of truth is ~/.claude/scheduled-tasks)
SCHEDULE = [
    ("daily ops sweep", "매일 09:10", "ops", "스택 헬스 → metrics/daily"),
    ("growth batch", "월·목 10:09", "marketing", "채널 초안 → approval_queue"),
    ("weekly report", "월 09:32", "chief", "지표 종합 + 우선순위 3"),
    ("self-wake", "매시간", "orchestrator", "읽기전용 점검 + 알림"),
]


def _frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    fm: dict = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    return fm


def read_agents() -> list[dict]:
    out = []
    for f in sorted(glob.glob(str(AGENTS_DIR / "atanor-*.md"))):
        fm = _frontmatter(Path(f).read_text(encoding="utf-8", errors="ignore"))
        name = fm.get("name", Path(f).stem)
        desc = fm.get("description", "")
        out.append({"name": name, "role": desc.split("—")[-1].split(".")[0].strip()[:70]})
    return out


def read_queue() -> list[dict]:
    out = []
    for f in sorted(glob.glob(str(BIZ / "approval_queue" / "2026*.md"))):
        fm = _frontmatter(Path(f).read_text(encoding="utf-8", errors="ignore"))
        out.append({"file": Path(f).name, "channel": fm.get("channel", "?"),
                    "status": fm.get("status", "draft"),
                    "posted_url": fm.get("posted_url", "")})
    return out


def read_log(n: int = 8) -> list[str]:
    p = BIZ / "BUSINESS_LOG.md"
    if not p.exists():
        return []
    blocks = re.split(r"\n(?=## )", p.read_text(encoding="utf-8", errors="ignore"))
    return [b.strip() for b in blocks if b.strip().startswith("## ")][-n:][::-1]


def latest_metrics() -> str:
    files = sorted(glob.glob(str(BIZ / "metrics" / "daily" / "*.md")))
    if not files:
        return ""
    return Path(files[-1]).read_text(encoding="utf-8", errors="ignore")


def stars() -> dict:
    out = {}
    for r in REPOS:
        try:
            v = subprocess.run(["gh", "api", f"repos/{r}", "--jq", ".stargazers_count"],
                               capture_output=True, text=True, timeout=15)
            out[r] = v.stdout.strip() or "?"
        except Exception:
            out[r] = "?"
    return out


def git_recent(n: int = 6) -> list[str]:
    try:
        v = subprocess.run(["git", "log", "--oneline", f"-{n}", "--", "business/"],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=15)
        return [l for l in v.stdout.splitlines() if l.strip()]
    except Exception:
        return []


def _pill(status: str) -> str:
    colors = {"draft": "#8a8f98", "approved": "#3fb950", "posted": ACCENT,
              "rejected": "#f85149"}
    c = colors.get(status, "#8a8f98")
    return f'<span class="pill" style="border-color:{c};color:{c}">{html.escape(status)}</span>'


def _metric_num(text: str, pat: str, default: str = "—") -> str:
    m = re.search(pat, text)
    return m.group(1) if m else default


def build() -> str:
    agents = read_agents()
    queue = read_queue()
    log = read_log()
    mtext = latest_metrics()
    st = stars()
    commits = git_recent()
    now = time.strftime("%Y-%m-%d %H:%M")

    edges = _metric_num(mtext, r"([\d,]{7,})")
    posted = sum(1 for q in queue if q["status"] == "posted")
    approved = sum(1 for q in queue if q["status"] == "approved")
    drafts = sum(1 for q in queue if q["status"] == "draft")

    def esc(s): return html.escape(str(s))

    agent_cards = "".join(
        f'<div class="card"><div class="an">{esc(a["name"])}</div>'
        f'<div class="ar">{esc(a["role"])}</div></div>' for a in agents)

    sched_rows = "".join(
        f'<tr><td>{esc(n)}</td><td class="mono">{esc(c)}</td>'
        f'<td class="accent">{esc(who)}</td><td class="dim">{esc(d)}</td></tr>'
        for n, c, who, d in SCHEDULE)

    queue_rows = "".join(
        f'<tr><td class="mono">{esc(q["channel"])}</td>'
        f'<td>{_pill(q["status"])}</td>'
        f'<td class="dim">{esc(q["file"])}</td></tr>' for q in queue) or \
        '<tr><td colspan="3" class="dim">큐 비어 있음</td></tr>'

    log_items = "".join(
        f'<div class="logitem"><pre>{esc(b[:600])}</pre></div>' for b in log)

    commit_items = "".join(
        f'<li class="mono dim">{esc(c)}</li>' for c in commits)

    return TEMPLATE.format(
        accent=ACCENT, now=esc(now), edges=esc(edges),
        star1=esc(st.get("Cozystone/ATANOR", "?")),
        star2=esc(st.get("Cozystone/ATANOR-Demo", "?")),
        drafts=drafts, approved=approved, posted=posted,
        agent_cards=agent_cards, sched_rows=sched_rows,
        queue_rows=queue_rows, log_items=log_items,
        commit_items=commit_items, agent_count=len(agents))


TEMPLATE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ATANOR Mission Control</title>
<style>
:root{{--accent:{accent}}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0b0c0e;color:#e6e6e6;font-family:-apple-system,'Segoe UI',system-ui,sans-serif;
  padding:28px 32px;line-height:1.5}}
.mono{{font-family:'SF Mono','Consolas',monospace;font-size:12px}}
.dim{{color:#8a8f98}} .accent{{color:var(--accent)}}
h1{{font-size:20px;font-weight:600;letter-spacing:.3px}}
h1 .g{{color:var(--accent)}}
.sub{{color:#8a8f98;font-size:12px;margin-top:4px}}
.strip{{display:flex;gap:14px;margin:22px 0;flex-wrap:wrap}}
.kpi{{border:1px solid #22252a;border-radius:10px;padding:14px 18px;min-width:120px;background:#101216}}
.kpi .v{{font-size:22px;font-weight:600}} .kpi .l{{font-size:11px;color:#8a8f98;margin-top:2px;text-transform:uppercase;letter-spacing:.5px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:8px}}
.panel{{border:1px solid #22252a;border-radius:12px;padding:18px;background:#0e0f12}}
.panel h2{{font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:#8a8f98;margin-bottom:12px;font-weight:600}}
.card{{display:inline-block;border:1px solid #24272c;border-radius:8px;padding:9px 12px;margin:0 6px 6px 0;min-width:120px}}
.card .an{{font-weight:600;font-size:13px}} .card .ar{{font-size:11px;color:#8a8f98;margin-top:2px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
td{{padding:6px 8px;border-bottom:1px solid #191b1f;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
.pill{{border:1px solid;border-radius:999px;padding:1px 9px;font-size:11px;font-weight:600}}
.logitem pre{{white-space:pre-wrap;font-family:'SF Mono',Consolas,monospace;font-size:11px;
  color:#c9ccd1;border-left:2px solid var(--accent);padding:2px 0 2px 12px;margin-bottom:12px}}
ul{{list-style:none}} li{{padding:3px 0}}
.gate{{margin-top:18px;border:1px solid #3a2a1a;background:#17110b;border-radius:10px;padding:12px 16px;font-size:12px;color:#d9a066}}
.full{{grid-column:1/3}}
.sr-only{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}}
</style></head><body>
<h2 class="sr-only">ATANOR 에이전트 팀의 현재 상태: 지표, 팀 구성, 자동화 스케줄, 승인 큐, 활동 로그.</h2>
<h1>ATANOR <span class="g">Mission Control</span></h1>
<div class="sub">에이전트 팀 공유 상태 · 생성 {now} · business/ 폴더에서 재생성</div>

<div class="strip">
  <div class="kpi"><div class="v">{edges}</div><div class="l">graph edges</div></div>
  <div class="kpi"><div class="v accent">★ {star1} / {star2}</div><div class="l">stars ATANOR / Demo</div></div>
  <div class="kpi"><div class="v">{drafts}·{approved}·{posted}</div><div class="l">draft·appr·posted</div></div>
  <div class="kpi"><div class="v accent">{agent_count}</div><div class="l">active agents</div></div>
</div>

<div class="grid">
  <div class="panel full"><h2>팀 (business/ 공유 작업대로 협업)</h2>{agent_cards}</div>

  <div class="panel"><h2>자동화 스케줄</h2>
    <table>{sched_rows}</table></div>

  <div class="panel"><h2>승인 큐 · 게시는 운영자 승인 후</h2>
    <table>{queue_rows}</table></div>

  <div class="panel full"><h2>활동 로그 (BUSINESS_LOG)</h2>{log_items}</div>

  <div class="panel full"><h2>최근 커밋 (business/)</h2>
    <ul>{commit_items}</ul></div>
</div>

<div class="gate">인간 게이트: 외부 게시 · 결제 · 파괴적 조치 · 계정 로그인은 에이전트가 실행하지 않습니다. 초안 → 운영자 승인 → 게시.</div>
</body></html>"""


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT}")
