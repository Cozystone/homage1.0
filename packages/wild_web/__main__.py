# -*- coding: utf-8 -*-
"""CLI: run one live wild-web learning session against the live SearXNG (:8888).

    python -m packages.wild_web                         # next curiosity topic, else default
    python -m packages.wild_web how do people fix a flat # explicit topic
    python -m packages.wild_web --max-pages 2 --status   # also print store status
"""
from __future__ import annotations

import argparse
import json

from . import store as S
from .session import wild_session


def main() -> None:
    ap = argparse.ArgumentParser(description="ATANOR wild-web learning session")
    ap.add_argument("topic", nargs="*", help="topic (default: next curiosity topic / benign default)")
    ap.add_argument("--max-pages", type=int, default=3)
    ap.add_argument("--status", action="store_true", help="also print store status after the session")
    a = ap.parse_args()

    topic = " ".join(a.topic).strip() or None
    out = wild_session(topic, max_pages=a.max_pages)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if a.status:
        print(json.dumps(S.status(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
