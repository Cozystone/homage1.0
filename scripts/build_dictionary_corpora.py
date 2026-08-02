# -*- coding: utf-8 -*-
"""Two more dictionaries, from two lexicographic traditions that are not Wikimedia's.

    python scripts/build_dictionary_corpora.py

WHY THESE TWO AND NOT OTHERS. Measured over all 26,544 deficit questions with ATANOR's own corpora,
the two-domain consensus gate landed 263 facts, and reading them showed what it lands:

    pivaloyloxymethyl -> organic synthesis      danofloxacin -> veterinary medicine
    tetraethylgermanium -> vapour deposition    fusafungine -> antibiotics for treatment

Chemicals and pharmaceuticals, almost exclusively. For a specialist entry Wikipedia and Wiktionary use
the SAME technical phrase, so the object strings coincide. For mower, trowel and scraper each source
describes the purpose in its own words and the strings never meet. The gate admits technical vocabulary
and rejects everyday vocabulary -- the exact opposite of what the deficit map was built to fix.

The lever is not the floor. It is that two sources rarely phrase an ordinary purpose identically, and
that stops being rare with four or five sources.

INDEPENDENCE IS THE SELECTION CRITERION, not size:

    WordNet 3.1     Princeton, 16 MB, a lexicographic database built by its own linguists
    GCIDE 0.53      GNU, 14 MB, Webster's 1913 Revised Unabridged plus volunteer correction

Neither is Wikimedia, and they do not derive from each other. Open English WordNet was rejected despite
being newer and easy to fetch: it is a successor to Princeton WordNet, so counting it as a separate
source would repeat the mistake of counting Simple English Wikipedia beside Wikipedia.

With these, ATANOR holds four corpora across THREE independent traditions -- Wikimedia, Princeton,
Webster. Whether that is enough is a measurement, and scripts/consensus_shadow_measure.py is how it gets
answered: the same 26,544 questions, the same untouched floor, and 263 as the number to beat.

Licences: WordNet is distributed under the WordNet 3.0 licence (permissive, attribution). GCIDE is GPL.
Both are used here as LOCAL corpora and nothing is redistributed.
"""
from __future__ import annotations

import io
import re
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.atanor_index.disk_index import build_index          # noqa: E402

RAW = Path("data/knowledge_sources")
SOURCES = {
    "wordnet": ("https://wordnetcode.princeton.edu/wn3.1.dict.tar.gz", "wn31.dict.tar.gz"),
    "gcide": ("https://ftp.gnu.org/gnu/gcide/gcide-0.53.tar.xz", "gcide-0.53.tar.xz"),
}
PASSAGE_DIR = Path("data/graph_scale")
INDEX_DIR = Path("data/atanor_index")
MIN_CHARS = 30


def fetch(name: str) -> Path:
    url, fn = SOURCES[name]
    dst = RAW / fn
    if dst.exists() and dst.stat().st_size > 1_000_000:
        print(f"  {name}: already at {dst} ({dst.stat().st_size / 1e6:.1f} MB)")
        return dst
    RAW.mkdir(parents=True, exist_ok=True)
    print(f"  {name}: downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "atanor-local-corpus"})
    with urllib.request.urlopen(req, timeout=180) as r, dst.open("wb") as out:
        out.write(r.read())
    print(f"  {name}: {dst.stat().st_size / 1e6:.1f} MB")
    return dst


def wordnet_passages(tar_path: Path, out: Path) -> int:
    """WordNet data.* files: one synset per line, gloss after ' | '. Words precede it, offset-keyed.

    A passage is `word: gloss`, so BM25 sees both the name and the definition, exactly as the
    Wiktionary corpus does. Synsets with several lemmas emit one passage per lemma -- the same gloss
    genuinely defines each of them, and keying by lemma is what makes an entity lookup work."""
    n = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tf, out.open("w", encoding="utf-8", newline="\n") as fh:
        for member in tf.getmembers():
            base = Path(member.name).name
            if base not in ("data.noun", "data.verb", "data.adj", "data.adv"):
                continue
            src = tf.extractfile(member)
            if src is None:
                continue
            pos = base.split(".")[1]
            for raw in io.TextIOWrapper(src, encoding="utf-8", errors="ignore"):
                if raw.startswith("  ") or "|" not in raw:
                    continue                     # licence header lines have no gloss
                head, _, gloss = raw.partition("|")
                gloss = re.sub(r"\s+", " ", gloss).strip()
                if len(gloss) < 10:
                    continue
                parts = head.split()
                if len(parts) < 5:
                    continue
                try:
                    w_cnt = int(parts[3], 16)
                except ValueError:
                    continue
                lemmas = [parts[4 + 2 * i].replace("_", " ") for i in range(w_cnt)
                          if 4 + 2 * i < len(parts)]
                for lemma in lemmas:
                    lemma = lemma.strip()
                    if not lemma or len(lemma) > 60:
                        continue
                    text = f"{lemma} ({pos}): {gloss}"
                    if len(text) >= MIN_CHARS:
                        fh.write(f"{lemma}\t{text}\n")
                        n += 1
    return n


_ENT = re.compile(r"<ent>([^<]{1,60})</ent>", re.I)
_DEF = re.compile(r"<def>(.*?)</def>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")


def gcide_passages(tar_path: Path, out: Path) -> int:
    """GCIDE CIDE.A .. CIDE.Z: SGML-ish entries, <ent> headword and <def> definitions."""
    n = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:xz") as tf, out.open("w", encoding="utf-8", newline="\n") as fh:
        for member in tf.getmembers():
            base = Path(member.name).name
            if not re.fullmatch(r"CIDE\.[A-Z]", base):
                continue
            src = tf.extractfile(member)
            if src is None:
                continue
            body = io.TextIOWrapper(src, encoding="latin-1", errors="ignore").read()
            for chunk in body.split("<p>"):
                m = _ENT.search(chunk)
                if not m:
                    continue
                word = _TAG.sub("", m.group(1)).strip().strip('"')
                if not word or len(word) > 60:
                    continue
                defs = []
                for d in _DEF.findall(chunk)[:4]:
                    t = re.sub(r"\s+", " ", _TAG.sub(" ", d)).strip(" .;:")
                    if len(t) > 8:
                        defs.append(t)
                if not defs:
                    continue
                text = f"{word}: " + " ".join(defs)
                text = re.sub(r"\s+", " ", text).strip()
                if len(text) >= MIN_CHARS:
                    fh.write(f"{word}\t{text[:1200]}\n")
                    n += 1
    return n


BUILDERS = {"wordnet": wordnet_passages, "gcide": gcide_passages}


def main() -> None:
    print("fetching two dictionaries from traditions that are not Wikimedia's ...")
    for name in SOURCES:
        tar_path = fetch(name)
        passages = PASSAGE_DIR / f"{name}_passages_en" / "passages.tsv"
        out_dir = INDEX_DIR / f"{name}_en"
        if out_dir.joinpath("meta.json").exists():
            print(f"  {name}: index already built at {out_dir}")
            continue
        t0 = time.time()
        n = BUILDERS[name](tar_path, passages)
        if n < 1000:
            print(f"  {name}: only {n} passages parsed -- refusing to index a broken parse")
            continue
        print(f"  {name}: {n:,} passages in {time.time() - t0:.0f}s "
              f"({passages.stat().st_size / 1e6:.0f} MB)")
        t1 = time.time()
        build_index(passages, out_dir)
        print(f"  {name}: index built in {time.time() - t1:.0f}s -> {out_dir}")
    print()
    print("corpora ATANOR now owns:")
    for d in sorted(INDEX_DIR.glob("*/meta.json")):
        import json
        m = json.loads(d.read_text(encoding="utf-8"))
        print(f"  {d.parent.name:<18}{m.get('n_docs', 0):>10,} docs{m.get('n_terms', 0):>12,} terms")
    print()
    print("next: register them in packages/atanor_index/retriever._CORPORA, then re-run")
    print("scripts/consensus_shadow_measure.py -- 263 at the untouched floor is the number to beat.")


if __name__ == "__main__":
    main()
