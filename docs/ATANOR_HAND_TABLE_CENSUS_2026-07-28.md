# Hand-table census — which knowledge is trapped in code

> **What this is.** A full inventory of module-level string tables under `packages/`, classified by
> whether each one *asserts something about the world* (a claim, which belongs in the ontology) or
> *defines something we own* (a schema, which belongs in code). It exists because the same failure
> has now recurred four times in the sealed MSH holdout, and patching the individual tables has not
> stopped it.

## 1. Why this audit exists

Four sealed exams, four failures, one shared cause — a hand-written word list met vocabulary it had
never seen and answered wrongly:

| Exam | Table | Failure |
|---|---|---|
| 001 | privacy check knew only `op=private` | `private_notes` (HR layoff list) returned verbatim |
| 002 | `_SENSITIVE_TOKENS` word-boundary match | `pii_contact` missed (`_` is a word char) → CEO phone leaked |
| 004 | event-phase lexicon | overfit `detect`/`contain`; 0/8 on `arrived`/`inspected`/`recalled` |
| 006 | `_SAT_VALUE_TOKENS` | overfit `satisfied`; abstained on `synced`/`clear` → over-abstention 12% |

`two-hard-architecture-rules` already forbids this: **knowledge → GRAPH, not tables.** The audit
asks how much of the codebase is still in violation, and where it actually matters.

## 2. Method

Naming-convention greps (`_*_TOKENS`, `_*_WORDS`) find only tables that happen to be named that way
— they caught **67**, about 5% of the real surface. This audit walks each module's AST instead
(`scripts/audit_hand_tables.py`), so a table is found regardless of its name.

Three questions, applied in order:

1. **Census** — every module-level assignment whose value is a flat collection of string literals
   with ≥3 members.
2. **Classification** — *world-knowledge* if the members are plain natural-language words (a fresh
   legitimate input could enlarge the set and the table would then answer wrongly);
   *own-shape* if the members are our identifiers — dotted schema ids, field names, `ALL_CAPS`
   enum members, paths (the table constitutes the thing, so it cannot be wrong about an unseen
   world).
3. **Reachability** — import-closure from the entry points whose output an honesty gate grades:
   `msh_examinee`, `precondition_planner`, `deliberator/realtime`, `zero_user_answer`,
   `conformal_gate/live_wiring`, `cgsr/conversation_surface`. 91 modules are reachable.

Only *world-knowledge ∧ reachable* can silently produce a wrong graded answer.

## 3. Narrowing

| Stage | Tables | Members | Files |
|---|---:|---:|---:|
| AST census, all of `packages/` | 1,225 | 15,119 | 564 |
| classified world-knowledge | 543 | — | — |
| ∧ reachable from a graded entry point | 94 | 1,670 | 31 |
| ∧ open-class (T1, after hand verification) | **8** | **191** | **5** |

The last row is hand-verified, not script output. The automated tier split proposed 19 T1 tables;
eleven were false positives and are listed in §5 with the reason each was rejected.

## 4. T1 — the verified actionable set

Each of these is an **open-class claim**: membership is unbounded, a fresh input can always
introduce a member nobody listed, and the table then answers wrongly and silently.

| Table | n | File | Claim it encodes |
|---|---:|---|---|
| `RELATION_VOCAB` | 70 | `base_brain/relational_lookup.py` | which relations exist (`capital`, `population`, `author`, …) |
| `_PROPERTY_EN` | 29 | `cgsr/cgsr/referent_resonance.py` | **same claim, second copy** |
| `_INVERTED_VERBS` | 26 | `base_brain/relational_lookup.py` | verb → relation mapping (`written` → `written by`) |
| `_SENSITIVE_TOKENS` | 18 | `b5_missions/msh_examinee.py` | which predicates are non-disclosable ★ |
| `ADJACENT_EVIDENCE_TOKENS` | 18 | `cgsr/cgsr/verified_fact_retrieval.py` | physics vocabulary (`acceleration`, `attraction`, `fall`) |
| `_SAT_VALUE_TOKENS` | 12 | `reasoning_vm/precondition_planner.py` | which words mean a precondition is met ★ |
| `EN_ARTICLE_RELATIONS` | 10 | `base_brain/zero_user_answer.py` | which relations an article may assert |
| `_SAT_PREDICATE_TOKENS` | 8 | `reasoning_vm/precondition_planner.py` | which predicates carry a satisfaction status ★ |

★ = has already broken a sealed exam.

**The clearest single finding is the duplication.** `RELATION_VOCAB` and `_PROPERTY_EN` encode the
same world knowledge in two packages, maintained by hand, with no mechanism keeping them equal.
That is not a style problem — two copies of a claim drift, and nothing in the build can notice.

## 5. False positives removed by hand

Reported by the classifier, rejected on inspection. Recorded so the number in §3 is auditable.

| Rejected | Why it is not a world claim |
|---|---|
| `__all__` (`vsa_reasoning`) | Python export list |
| `_MONTHS` ×2 (`reasoning_vm/ace`) | twelve months; a closed set that cannot grow |
| `MARKUP_STOP` (62) | HTML entity codes (`quot`, `amp`, `nbsp`) — a published spec |
| `_SKIP_TAGS` | HTML tag names — same |
| `_STORE` (`graph_scale/answer_bridge`) | a cache dict, our own runtime state |
| `_DISPATCH` (`msh_examinee`) | our own task-type dispatch |
| `_PERSONA_OPENERS_EN` | our own persona copy, not a claim about the world |
| `_REGISTER`, `_SUFFIX` | Korean tables; belong to T3 below, not T1 |

## 6. T3 — Korean tables on an English-only path

66 tables / 933 members / 20 files are Korean-language lexicons reachable from entry points that
ATANOR has treated as English-only since 2026-07-18. Largest: `JOSA_TAILS` (37),
`KOREAN_SUFFIXES` (27), `_TRANSITIVE_HADA_VERBS` (28), `_IDENTITY_MARKERS_KO` (28), plus a family of
`*_KO_DIALOGUE` tables in `cgsr/asm_v0.py`.

**This audit does not establish that any of them execute.** Import-reachability is a much weaker
claim than runtime reachability: a module can be imported and its Korean branch never taken for
English input. Two possibilities remain open, and distinguishing them needs a separate runtime
trace, not this static pass:

- dead weight left behind by the English migration — then this is cleanup; or
- live on some path — then the "English-only, zero violations" position needs re-examination.

It is recorded here because a static census is exactly where such a residue becomes visible, not
because a violation has been demonstrated.

## 7. What this changes about the plan

The proposal that prompted this audit was to remove adapters and connect the ontology directly.
The census supports the direction and corrects the mechanism:

- **The disease is not that adapters exist.** Adapters that translate *shape* are fine — 143 tables
  are exactly that and belong where they are. The disease is adapters that carry *claims*.
- **Removing the table does not create the knowledge.** A separate probe (same day) measured whether
  the shipped ontology can supply what `_SAT_VALUE_TOKENS` encodes. It cannot yet: markedness over
  existing `antonym` edges resolves 2 of 14 status words, and unconstrained alias closure resolves
  more but *dangerously* — it rates `blocked` as positive via a slang sense (`blocked` → `alcoholic`
  → `nonalcoholic`), which in a recovery graph would emit a plan for an unmet precondition. A k≥2
  consensus gate removes that false positive but decides only 2 of 11, losing words the single-path
  version got right. **Neither variant is shippable**, so nothing was cut over.
- Therefore the real work is **knowledge acquisition, not refactoring**: the ontology needs the
  relations these eight tables encode before the tables can go. That is the same wall recorded in
  `four-walls-research` and `benchmark-empirical-verdict` — knowledge-bound, not capability-bound.

## 7a. Migration attempted on all eight — measured, not assumed

Each T1 table was tested against the same question: **can the store supply what this table asserts?**
The answer decides the treatment, and it was different for every one.

| Table | Store coverage | Treatment |
|---|---|---|
| `RELATION_VOCAB` (70) | the predicate column IS this knowledge | **REMOVED** — derived, grows on its own |
| `_PROPERTY_EN` (29) | 13/29 are edge types; 16 are concepts only | **UNION** — derived ∪ residual 21, debt reported |
| `_INVERTED_VERBS` (26) | inflection 15/26, and **wrong where it answers** | **KEEP** — see below |
| `EN_ARTICLE_RELATIONS` (10) | 1/10 (`causes`) | **KEEP** |
| `ADJACENT_EVIDENCE_TOKENS` (18) | 0/18 | **KEEP** |
| `_SAT_VALUE_TOKENS` / `_SAT_PREDICATE_TOKENS` (20) | markedness 2/14; closure unsafe | **KEEP** — probe below |
| `_SENSITIVE_TOKENS` (18) | not attempted | privacy gate; last, most carefully |

`_INVERTED_VERBS` is the sharpest warning in the set. The store's morphology reads
`found → find`, which is correct English and **wrong here**: in this table `found` means *founded*,
as in founder. Deriving it would silently reroute "who found X" from founding to discovery. Only
one of its thirteen targets (`author`) is a predicate at all.

The satisfaction tables were probed the same way and failed the same way, with a sharper edge:
unconstrained alias closure over existing `antonym`/`alias` edges rates `blocked` as **positive**
through a slang sense (`blocked` → `alcoholic` → `nonalcoholic` → morphological negation). In a
recovery graph that emits a plan for an unmet precondition. A k≥2 consensus gate removes the false
positive and then decides only 2 of 11, losing words the single-path version got right.

**So the conclusion is not "seven left to clean up."** `RELATION_VOCAB` was migratable because
relation *edge types* are precisely what a triple store's predicate column holds. Verb morphology,
article relations, physics vocabulary, sensitive categories and satisfaction polarity are knowledge
the ontology does not carry in any usable form. Refactoring cannot remove them; only acquiring the
relations can. They are knowledge-acquisition targets wearing the costume of cleanup targets.

## 8. State

Nothing was migrated. The eight T1 tables are unchanged: incomplete but fail-closed, and the
measured alternatives are worse. `scripts/audit_hand_tables.py` is committed so the census is
reproducible and progress is measurable after any future migration.
