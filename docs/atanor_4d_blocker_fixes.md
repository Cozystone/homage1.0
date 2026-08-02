# 4D BLOCKER fixes — design only (GREEN; no store write / schema apply / commit)

Codex's two RED blockers from the 4D vision-sync, designed against the real code.
Implementation is deferred (operator/Codex gate). Maturity here = DESIGN.

---

## BLOCKER #1 — functional-relation declaration must leave code (rule-table smell)

### Reality (grounded)
`packages/rag_engine/rag_engine/self_correction.py:46`
```python
FUNCTIONAL_RELATIONS = {"parent","child","born_in","located_in","founded_in","capital_of","part_of"}
```
used at `:259` (`if triple.predicate in FUNCTIONAL_RELATIONS`). Two problems:
1. A hand-coded code constant = the rule-table smell Codex flagged.
2. English predicate names only — does not match the live KO graph predicates (창립하다 …), so it
   is also largely inert on the real graph.

### Boundary that keeps this legal (NOT an answer table)
The allowed thing is an **ontological property of a relation TYPE** ("the `capital_of` relation is
functional — an entity has one value at a time"). The forbidden thing is a **specific
subject→answer mapping** ("구글 CEO = 피차이"). #1 declares only the former.

### Design: a data-layer `relation_type_schema`
A versioned, provenance-carrying declaration loaded as DATA (not a code constant). One row per
relation type:
```json
{
  "relation_type": "capital_of",
  "lang": "mul",                     // language-agnostic where possible
  "aliases": ["수도", "capital_of"], // surface forms (lexical, not answers)
  "arity": 2,
  "domain_type": "Place",            // type constraints (ontology, not instances)
  "range_type": "Place",
  "functional": true,                // <= the property #1 needs
  "temporal_policy": "single_value_at_a_time",  // functional ⇒ temporal exclusivity
  "provenance": {"source": "...", "approved_at": "...", "version": "0.1"},
  "schema_version": "relation_type_schema_v0"
}
```
- Stored as `relation_type_schema.jsonl` (sidecar), NOT in `verified_fact_retrieval.STORE_FILES`
  (so the answer path can never read it as fact/evidence).
- `self_correction.py` loads this file instead of the constant; `FUNCTIONAL_RELATIONS` becomes a
  derived view (`{r.relation_type for r in schema if r.functional}`).
- **Forbidden fields** (assert at load): `answer_text/person/target_answer/answer_entity_id` and any
  specific instance value. It declares types, never instances.
- Bootstrap: migrate the 7 existing + their KO equivalents AS data rows with provenance — same
  meaning, but now versioned/auditable/growable without code edits.

### Reversibility / verification
Sidecar file ⇒ revert = delete file (code falls back to empty set = current behavior off). A loader
unit test asserts: no forbidden fields, functional view matches intent, KO+EN predicates covered.

---

## BLOCKER #2 — permanent memory: in-place update loses history

### Reality (grounded — corrects an earlier overclaim)
- Candidate accumulator `accumulator.py:_append_unique (158)` = **append + skip-on-dup, never
  mutates** ✓.
- `candidate_promotion_merge.py:52` = **discrete growth shard, reversible, "no existing rows
  modified"** ✓ (docstring `:10`).
- **The destructive path is `semantic_growth.py:ingest_semantic_source (43)`** — a SemanticCloudStore
  **upsert**: `concepts_merged += 0 if created else 1` (`:100`, `:109`) and confidence passed at
  `:95/:104/:115` ⇒ when a row already exists it is **updated in place**, the prior state is lost.
  That is the only "永久기억 깨짐" path.

### Design: "update current + append temporal event" (history-preserving upsert)
Wrap the upsert so every in-place change first records the prior state:
```
on upsert(existing_row, new_values):
    if values_changed(existing_row, new_values):
        append to <collection>_history.jsonl:
            { entity/relation id, t_observed: now,
              prev: {confidence, trust, value, valid_to=now},
              next: {confidence, trust, value, valid_from=now},
              reason, provenance, schema_version }
        # for FUNCTIONAL relations (per #1 schema): close old, open new
        if relation_type.functional and value_changed:
            existing_row.valid_to = now           # supersede, do not erase
            write new row with valid_from = now, supersedes = existing.id
        else:
            update existing_row in place (confidence/trust) AS today
```
- New sidecars: `concept_history.jsonl`, `relation_history.jsonl` (append-only). Current rows stay
  where they are (answer path unchanged); history is a separate, queryable timeline → enables `V(t)`.
- **Minimal first step (smallest honest):** add ONLY the history-append on every in-place update
  (don't change update semantics yet). Pure observability, zero behavior change — then later turn on
  supersession for functional relations.
- History sidecars are NOT in `STORE_FILES` ⇒ never answer evidence (Contract C1).

### Reversibility / verification
History sidecars are append-only ⇒ revert = delete them (behavior returns to current). Test:
run an upsert that changes confidence twice → assert 2 history events + current row matches latest +
`V(t)` reconstructs the prior value.

---

## Phasing (all RED until operator/Codex approve)
1. (DESIGN, done here) schemas + wrap points identified with file:line.
2. P-4D.fix.1 [RED]: add `relation_type_schema.jsonl` + loader (self_correction reads it); shadow
   parity test vs current constant.
3. P-4D.fix.2 [RED]: add history sidecars + history-append wrapper on `semantic_growth` upsert
   (observability only, no semantic change).
4. P-4D.fix.3 [RED]: enable functional supersession (close/open) using #1's `functional` flag.
Each step: backup + sidecar-delete rollback. None touch `STORE_FILES` / the answer path.

## For Codex (re-review asks)
1. Is `relation_type_schema.jsonl` the right home, or should it extend the existing `schema.json`?
2. Is `semantic_growth.ingest_semantic_source` the ONLY in-place mutator, or are there others?
3. Does the functional-supersession close/open interact safely with the 3 merge paths you flagged
   for P1-③ (candidate_promotion_gate / candidate_promotion_merge / agentic_micro_os auto-promote)?
