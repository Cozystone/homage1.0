# -*- coding: utf-8 -*-
"""Feed ATANOR a book PDF: python scripts/ingest_book.py <file.pdf> [--title T]"""
import argparse, glob, os, sys
sys.path.insert(0, ".")
for _d in sorted(glob.glob("packages/*")):
    if os.path.isdir(_d):
        sys.path.append(_d)
from packages.cloud_brain.book_ingest import ingest_book

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--title", default=None)
    ap.add_argument("--max-pages", type=int, default=None)
    a = ap.parse_args()
    r = ingest_book(a.pdf, title=a.title, max_pages=a.max_pages)
    import json
    print(json.dumps(r.to_dict(), ensure_ascii=False, indent=1))
