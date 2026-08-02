# -*- coding: utf-8 -*-
"""Korean taxonomy from the Korean Wikipedia category tree — a second, diverse,
NOT-rate-limited clean source alongside Wikidata.

Owner (2026-07-09): ". ." Wikidata (wikidata_ko) is one clean source
but WDQS throttles hard (~1 req/min). The Korean Wikipedia category graph is a
second, independent taxonomy: its SUBCATEGORY relation is a clean is_a-ish signal
(: ⊂ : = is_a ), and page membership is a
weaker is_a ( ∈ :). The MediaWiki API (ko.wikipedia.org/w/api.php)
has a far more generous rate limit than WDQS, so the two harvests run concurrently.

BFS from a diverse set of seed roots (////////…),
extracting (child, parent) edges into the SAME gated candidate ledger as every
other clean source. Candidate-tier, never production.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

LEDGER_DIR = Path(__file__).resolve().parents[2] / "data" / "cloud_brain" / "derived_candidates"
_API = "https://ko.wikipedia.org/w/api.php"
_CAT = "분류:"   # Korean "Category:" prefix

# Diverse roots so the crawl spans domains, not one silo. Mixes ABSTRACT domains


# of waiting for a deep BFS descent that may never reach them within max_depth.
_SEEDS = (
    # abstract domains
    "동물", "식물", "과학", "기술", "수학", "물리학", "화학", "생물학",
    "역사", "지리", "국가", "도시", "언어", "문학", "예술", "음악",
    "음식", "요리", "스포츠", "인물", "철학", "종교", "경제", "정치",
    "컴퓨터", "의학", "천문학", "지질학", "교통", "건축",
    # concrete categories -> their page-members are everyday concepts
    "과일", "채소", "음료", "자동차", "포유류", "조류", "어류", "곤충",
    "꽃", "나무", "악기", "가전제품", "의류", "가구", "무기", "항공기",
    "선박", "기계", "금속", "광물", "질병", "신체", "감정", "색",
    "운동", "게임", "영화", "텔레비전 프로그램", "소프트웨어", "웹사이트",
    "도구", "요리",
)


def _api(params: dict[str, str], *, timeout: int = 30, retries: int = 4) -> dict[str, Any]:
    import urllib.error
    q = dict(params)
    q.update({"action": "query", "format": "json", "maxlag": "5"})
    url = _API + "?" + urllib.parse.urlencode(q)
    last: Exception | None = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "ATANOR-KG/1.0 (research; graph learning; contact blueyjkim@gmail.com)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8", "ignore"))
            if "error" in data and data["error"].get("code") == "maxlag":
                time.sleep(5.0)
                continue
            return data
        except urllib.error.HTTPError as e:
            last = e
            time.sleep(10.0 if e.code == 429 else 3.0)
        except Exception as e:
            last = e
            time.sleep(3.0)
    if last:
        raise last
    return {}


def _members(cat: str, kind: str, cont: str | None = None) -> tuple[list[str], str | None]:
    """One page of category members. kind='subcat' (subcategories) or 'page'."""
    params = {
        "list": "categorymembers",
        "cmtitle": _CAT + cat,
        "cmtype": kind,
        "cmlimit": "500",
    }
    if cont:
        params["cmcontinue"] = cont
    data = _api(params)
    members = data.get("query", {}).get("categorymembers", [])
    names = []
    for m in members:
        title = m.get("title", "")
        if kind == "subcat":
            title = title[len(_CAT):] if title.startswith(_CAT) else title
        names.append(title.strip())
    nxt = data.get("continue", {}).get("cmcontinue")
    return names, nxt


def _bad(label: str) -> bool:
    if not label or len(label) > 40:
        return True
    # skip meta/admin categories and disambiguation cruft
    for junk in ("위키", "틀:", "분류:", "동음이의", "목록", "(", "일람",
                 "프로젝트", "포털", "따른", "토막글", "토론", "관한 ",
                 "분류가 필요", "생몰년"):
        if junk in label:
            return True

    if "별 " in label or label.endswith("별"):
        return True
    return False


def harvest_ko_categories(*, seeds: tuple[str, ...] = _SEEDS, max_depth: int = 3,
                          max_edges: int = 60000, include_pages: bool = True,
                          pace_sec: float = 0.5, out_dir: str | Path | None = None,
                          ledger_name: str = "wikipedia_ko_is_a.jsonl",
                          log: Any = print) -> dict[str, Any]:
    """BFS the category tree from diverse seeds; write (child is_a parent) edges to
    the candidate ledger. Deduped, candidate-tier, never production. A distinct
    ledger_name lets a second crawl run concurrently without append contention."""
    out_dir = Path(out_dir) if out_dir else LEDGER_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    path = out_dir / ledger_name

    seen_edges: set[tuple[str, str]] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                seen_edges.add((r.get("s"), r.get("o")))
            except Exception:
                pass

    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque((s, 0) for s in seeds)
    written = 0
    fh = path.open("a", encoding="utf-8")
    try:
        while queue and written < max_edges:
            cat, depth = queue.popleft()
            if cat in visited or depth > max_depth:
                continue
            visited.add(cat)

            # subcategories: child is_a cat
            cont = None
            while True:
                try:
                    subs, cont = _members(cat, "subcat", cont)
                except Exception as e:
                    log(f"  subcat {cat}: {type(e).__name__} — skip")
                    break
                for child in subs:
                    if _bad(child) or child == cat:
                        continue
                    if depth + 1 <= max_depth:
                        queue.append((child, depth + 1))
                    if (child, cat) not in seen_edges:
                        seen_edges.add((child, cat))
                        fh.write(json.dumps({"s": child, "p": "is_a", "o": cat,
                                             "src": "wikipedia:ko:category", "tier": "candidate",
                                             "at": now}, ensure_ascii=False) + "\n")
                        written += 1
                if not cont or written >= max_edges:
                    break
                time.sleep(pace_sec)

            # page members: page is_a cat (weaker, but useful instance edges)
            if include_pages and depth >= 1:      # skip huge top-level page lists
                cont = None
                pages_here = 0
                while True:
                    try:
                        pages, cont = _members(cat, "page", cont)
                    except Exception:
                        break
                    for pg in pages:
                        if _bad(pg) or pg == cat:
                            continue
                        if (pg, cat) not in seen_edges:
                            seen_edges.add((pg, cat))
                            fh.write(json.dumps({"s": pg, "p": "is_a", "o": cat,
                                                 "src": "wikipedia:ko:category", "tier": "candidate",
                                                 "at": now}, ensure_ascii=False) + "\n")
                            written += 1
                            pages_here += 1
                    if not cont or pages_here >= 500 or written >= max_edges:
                        break
                    time.sleep(pace_sec)

            if len(visited) % 25 == 0:
                log(f"  visited {len(visited)} cats, written {written} edges, queue {len(queue)}")
            time.sleep(pace_sec)
    finally:
        fh.close()

    return {"harvested": True, "categories_visited": len(visited),
            "edges_written": written, "written_to_production": False,
            "ledger": str(path),
            "note": "clean Korean taxonomy from Korean Wikipedia category tree — gated candidates"}
