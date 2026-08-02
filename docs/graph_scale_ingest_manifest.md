# Trillion-scale ingest — data sources & one-command loading

The graph grows to scale by **bulk-loading curated data**, not by crawling. Two lanes feed the
integer-columnar `TripleStore` (`packages/graph_scale/`) via `scripts/bulk_ingest_kg.py`:

- **Structured KGs** → verbatim `(subject, predicate, object)` facts (highest quality).
- **Open sentence corpora** → *definitional* sentences become `is_a` / `defined_as` facts;
  Tatoeba translation pairs become cross-lingual `alias` edges. Extraction is **conservative**
  — only unambiguous definitions become facts, so narrative/dialogue sentences never fabricate.

After any load, run derived-edge inference (`--derive`) to multiply edges deductively
(transitive `is_a`, symmetric `borders`, inverse `capital`↔`capital_of`, `capital`⟹`located_in`).

All commands write to `data/graph_scale/kg_triples` by default (`--root` to change). Files may be
plain, `.gz`, or `.bz2` (streamed, bounded memory). Use `--no-dedup` for already-deduped
billion-row dumps.

## Structured knowledge graphs

| Source | License | What it gives | Command |
|---|---|---|---|
| **Wikidata** (truthy N-Triples dump `latest-truthy.nt.gz`, ~1.5e9 stmts) | CC0 | entities + relations | `python scripts/bulk_ingest_kg.py --source nt latest-truthy.nt.gz --no-dedup --derive` |
| **Wikidata** (live scoped, proof) | CC0 | countries + capitals | `python scripts/bulk_ingest_kg.py --source wikidata --limit 500 --derive` |
| **ConceptNet** (`conceptnet-assertions-5.7.0.csv.gz`, ~3.4e7 edges) | CC-BY-SA | commonsense relations (ko/en filtered) | `python scripts/bulk_ingest_kg.py --source conceptnet conceptnet-assertions.csv.gz --derive` |
| Any TSV `s⭾p⭾o` | — | your own facts | `python scripts/bulk_ingest_kg.py --source tsv facts.tsv.gz --derive` |

## Open sentence corpora (the datasets to活用)

| Source | License | Lane | Command |
|---|---|---|---|
| **Tatoeba** `sentences.csv` + `links.csv` | CC-BY 2.0 | ko↔en `alias` edges (cross-lingual retrieval) | `python scripts/bulk_ingest_kg.py --source tatoeba-alias sentences.csv --links links.csv` |
| **Wiktionary** (parsed to JSONL `{word, definition}`) | CC-BY-SA | word → `defined_as` head (사전) | `python scripts/bulk_ingest_kg.py --source wiktionary wik.jsonl` |
| **OpenSubtitles** (mono, one sentence/line) | open | definitional sentences → facts; rest is surface corpus | `python scripts/bulk_ingest_kg.py --source sentences opensubs.ko.txt.gz` |
| **OSCAR / Common Crawl** (JSONL `{text}` or plain) | CC0-ish per snapshot | definitional sentences → facts | `python scripts/bulk_ingest_kg.py --source oscar oscar.ko.jsonl.gz` |
| **AI Hub** (Korean, domain corpora) | free for R&D (registration) | export to line/JSONL then `--source sentences`/`oscar` | `python scripts/bulk_ingest_kg.py --source sentences aihub_export.txt` |

**Tatoeba + Wiktionary together** give the "사전 + 예문" structure the user described: Wiktionary
supplies the `defined_as` head (dictionary sense), Tatoeba supplies aligned example sentences and
the bilingual `alias` layer.

## Why this reaches scale (measured)

- Crawl baseline: **~1.3 concepts/min** → 1e12 would take ~1.4 billion days. Not viable.
- `TripleStore` bulk ingest: **~584,000 triples/sec**, **~21 bytes/triple** — the store is not the
  limiter; the dump's own read speed is.
- `--derive` multiplies stored edges deductively (×2–3 on shallow data, much more on deep
  Wikidata subclass trees) with **zero new source data and zero fabrication**.

## Honest ceiling

This is the real **1e4 → 1e9** jump (real dumps + dense integer columns + derived edges). Beyond
1e9 the **term dictionary** (in-RAM `str↔int`) becomes the bottleneck and needs sharding/on-disk;
**1e12** needs the distributed **Brain Link** pool (parallel shard ingest) plus the
`splatra_turbovec` quantized store for memory-bounded physical nodes. Those are the next targets,
not hidden costs.
