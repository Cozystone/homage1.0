# One mind: fluent prose, code understanding, and why they are the same problem

Owner directive, 2026-07-31: *"ATANOR는 유창한 산문이 중요해 … 이해 잘 하고 잘 만들고 잘 보고해야지.
사람처럼 소통하고 말을 느껴야해 … 이런 일련의 과정이 별도의 코드기관이라거나 이런 기관을 새로 짓는게
아니라 하나의 뇌에서 일어나야해."*

This is a research plan, and the honest kind: it says what is buildable now, what is hard, and what has
no known answer. Two measurements taken today are the reason it is shaped the way it is.

---

## 0. Today's two measurements, because they decide the plan

**MBPP, sealed slice: 18.9%, and the elaborate schema organ contributed 2 solves out of 181.** DP-2D,
topological sort, backtracking, graph traversal, keyed-store, induced value-maps — the machinery that
carries `mastery_v1` to 40/40 — is nearly inert on tasks somebody else wrote. It was built as a separate
organ beside the engine, and separate organs do not generalise.

**The code-QA lane was built, its graph was ingested, and it could never speak.** Its caller gated it on
`language == "ko"` in a system that has thought in English since 2026-07-18. Nothing failed loudly; it
simply never fired.

Both are the same disease, and the owner named it before either was measured: **a capability bolted on
beside the mind is not a capability.** So this plan's first commitment is consolidation, not addition.

---

## 1. The one-brain fix is concrete, not philosophical

Right now `codebase_ingest` writes to `data/graph_scale/codebase_knowledge.jsonl` — its **own ledger**,
with its own reader (`_rows()`, a full-file scan), its own resolver, its own answer composer, and no
connection to the conformal gate. That is literally a second brain: a second graph, a second query path,
a second voice.

The world-knowledge side already has all four of those, and they are better:

| | code lane today | the mind's own machinery |
|---|---|---|
| store | a JSONL re-scanned per query | `graph_scale.triple_store.TripleStore` (int-columnar, memmapped, indexed) |
| provenance | none until today | `facts_with_sources()` — citation is built into the store |
| multi-hop | none | `chain_reasoner.find_path` / `reason_chain`, engine-agnostic |
| abstention | a confidence constant of 0.82 | `conformal_gate.ConformalGate.decide()` — calibrated, certificated |
| composition | a private template stitcher | `answer_bridge` + `reasoning_certificate` |

**The work is to delete the parallel path, not to improve it.** Code facts become a DOMAIN in the one
graph — `defined_at`, `calls`, `in_module` sitting beside `born_in` and `used_for` — retrieved by the one
retriever, spoken by the one composer, gated by the one gate. Then "what does PropertyTable do" and "who
wrote Hamlet" are the same act, differing only in which triples answer them.

This is also what makes the rest of this document possible. Fluency built into a private composer would
be a third organ. Fluency built into the one composer is the mind learning to speak.

---

## 2. Fluent prose without giving up the no-fabrication floor

The apparent dilemma: the honesty floor is "say only what is verified, else abstain", and prose has no
verifier. So fluency looks like it costs honesty.

It does not, and the reason is a distinction the current design blurs:

> **Fabrication lives in the PROPOSITIONS, not in the PROSE.**

"`PropertyTable` is a class at `property_table.py:124`" is a claim, and it is checkable. Whether it is
said as *"PropertyTable, defined at line 124, is a class"* or *"You'll find PropertyTable at
property_table.py:124"* is not a truth question at all. So split the act:

    SELECT   which verified propositions to say, and in what order   <- where the real difficulty is
    REALIZE  turn that ordered set into sentences                    <- fabrication-free by construction

**Realization is provably safe if it is closed over its input.** If the realizer can only rearrange,
connect, pronominalise and subordinate the propositions it was handed — never introduce one — then no
output of it can assert anything unverified. That is a checkable property, not a hope: re-extract the
propositions from the produced prose and require the set to be a subset of the input. ATANOR already has
a realizer measured at 1.000 faithful; the floor survives.

### What is actually missing is mostly not linguistic

Comparing the sentence this repo produces today —

> *"`Rooms` is a class in `packages.workspace.rooms`, at rooms.py:90. It defines `__init__`, `_save`,
> `census`, `declare`, `place` and `room_of`, plus 1 more."*

— against what a person would say, four things differ, and only one of them is about language:

1. **Selection.** A person answering "what does Rooms do?" does not recite the method list. They lead
   with the point: *it decides where a file goes, and it enforces the rule that room's kind needs.*
   Choosing that is not fluency, it is knowing what matters — and the graph already carries the signals
   (centrality, docstring, who calls it) to rank it.
2. **Discourse order.** Given-before-new, the answer before the evidence. A structural choice.
3. **Cohesion.** Pronouns and connectives instead of repeating the subject. Genuinely linguistic, and
   the smallest of the four.
4. **Stance.** Hedging when the graph is thin, asserting when it is dense. ATANOR *computes* this
   already — the conformal gate holds a calibrated confidence — and then throws it away by printing a
   constant 0.82 and a flat declarative sentence either way.

**Three of the four are selection and confidence problems wearing a linguistic costume.** That is the
good news: they are addressable with signals the system already has, and they are measurable.

### Measuring it — the owner's own round-trip idea, generalised

The owner proposed (2026-07-31) taking good websites, reverse-deriving a clean prompt, rebuilding the
site from that prompt alone, and scoring similarity to the reference. That is a **round-trip consistency
oracle**, and its value is that it is free, automatic and unflatterable — the same property that makes
code the ideal No-LLM domain.

The same trick measures prose:

    propositions -> prose -> re-extract propositions -> compare to the original set

* **additions** ⇒ fabrication. Must be zero. This is the floor, mechanically checked.
* **losses** ⇒ the prose dropped something it was asked to convey.
* **fluency** is then scored separately, on prose already known to be faithful.

**The failure mode that decides whether any round-trip design works: the intermediate must be a real
bottleneck.** In the website version, an unconstrained "prompt" lets the optimal strategy become
smuggling — the prompt degenerates into `#3A7BD5, 14px, margin 22px`, or in the limit the HTML itself.
Similarity then scores high and nothing was understood. This is the classic degenerate-autoencoder /
cycle-consistency pathology. The constraints that convert it from a compression test into a
comprehension test: a hard length cap, natural language only (no hex, no pixel values, no CSS property
names), and the writer and the rebuilder never sharing the reference. The same discipline applies to
prose: the proposition set must be the only channel.

---

## 3. "Feeling" language — what is real here and what is not

*"사람처럼 소통하고 말을 느껴야해."* Splitting this honestly:

**Reading tone is tractable and safe.** Whether a question is exploratory, precise, frustrated, or
rhetorical is a property of the INPUT, and misreading it costs a badly-pitched answer, not a fabricated
one. Comprehension carries no fabrication risk — which is exactly why the owner's instinct to keep input
in natural language while constraining output is the right cut. Register detection on the way in, and
matching it on the way out, is buildable.

**Claiming to FEEL is not.** Per this project's own charter, the subjective claim is out of scope and
stays out. What is in scope is the correlate: responding differently to a hurried question than to a
careful one, and being right about which it was. That is measurable. The felt part is not, and this
document does not promise it.

---

## 4. Simulation before writing — and why code is where it actually works

The owner's idea: when facing a hard problem, use a spatiotemporal working model to predict what a
candidate implementation would produce, and pick the best direction rather than guessing.

For code this is not just tractable, it is the single best-conditioned learning problem available,
because **the prediction can be checked by running it.** Predict → execute → compare. Zero human labels,
exact ground truth, unlimited data. Concretely:

    given a function and an input, predict the output BEFORE running it
    given a diff, predict which tests flip
    given two candidate implementations, predict which passes -- then run both

A predictor trained this way is exactly the "which direction should I go" organ the owner described, and
its accuracy is a number, not a claim. `packages/code_reason/code_situation.py` already extracts
per-function structure (params, returns, calls, raises, loops, branches, recursion) and is the natural
substrate.

**And it must not be a new organ.** Prediction-before-acting is not code-specific — it is the same
capacity as anticipating what an answer will look like before composing it. It belongs in the deliberation
path that already exists, with code as the domain where it can be *trained*, precisely because code is
the domain that grades itself.

---

## 5. What is genuinely hard, stated so it is not quietly skipped

* **Selection has no free oracle.** Whether "it decides where a file goes" beats "it defines 7 methods"
  as an answer cannot be settled by running anything. Round-trip catches fabrication and omission, not
  *aptness*. This is the real wall, and it is the same wall as design taste in code review.
* **Fluency proxies are gameable.** Any automatic naturalness score becomes a target that can be
  optimised without improving communication. Any metric adopted here must be reported alongside what it
  cannot see.
* **The corpus, not the model, is the fluency bottleneck** — already measured on this project. Register
  variety and discourse patterns come from what was read, and the answer-voice corpus was for a long time
  being learned from a fact database, which is a category error that no amount of decoder work fixes.
* **Unbounded prose remains out of reach and should stay out.** Nothing here proposes free generation.
  Everything proposed is closed over verified propositions. If that ceiling is ever raised, it should be
  a deliberate decision with its own gate, not a drift.

---

## 6. Order of work

1. **Consolidate.** Code facts into the one graph, one retriever, one composer, one gate. Delete the
   parallel path rather than improving it. *(Measurable: code questions answered through the same call
   as world questions, with a conformal certificate instead of a hardcoded 0.82.)*
2. **Round-trip faithfulness harness.** propositions → prose → re-extract → compare. Gives a mechanical
   fabrication check on every sentence the system speaks, and a loss score for what it drops.
3. **Selection and stance.** Rank propositions by the signals already computed; let calibrated confidence
   change the sentence's hedging instead of being printed as a number.
4. **Cohesion.** Pronouns, connectives, given/new order — the smallest piece, deliberately last, because
   doing it first would polish sentences that are choosing the wrong things to say.
5. **Predict-then-run, in the deliberation path.** Trained on code because code grades itself.

No dates. Each step is a gate that is either green or not.
